"""Complete formal wire timing, including validation. No effects on import."""
import secrets
import time
import hashlib

from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_lifecycle_deadlines import PhaseClock
from training.c5_model_transport import FramedPipe, validate_request, validate_response
from training.c5_startup_transport import StartupReadyPipe, validate_startup_receipt
from training.c5_lifecycle_timing_audit import audit_phase


class NativeChannelV2:
    def __init__(self,directory,secret,freeze_sha,task=None,*,hub=False,guard=lambda:None,
                 pump=lambda:None,clock=time.monotonic,sleep=time.sleep):
        self.directory,self.secret,self.freeze,self.task,self.hub=directory,secret,freeze_sha,task,hub
        self.guard,self.pump,self.clock,self.sleep=guard,pump,clock,sleep
        self.seq,self.unresolved=1,False

    def exchange(self,message):
        require(not self.unresolved and self.seq <= (41 if self.hub else 128),'formal channel uncertain/exhausted')
        self.unresolved=True
        phase=PhaseClock(120,clock=self.clock)
        prefix='hub-' if self.hub else ''
        phase.call('guard',self.guard)
        phase.call('request-publish',lambda:publish_json(self.directory,prefix+'request-%04d.json'%self.seq,message))
        response_name=prefix+'response-%04d.json'%self.seq
        proof_name=prefix+'service-time-%04d.json'%self.seq
        while True:
            phase.check('receive-poll',record=False)
            if (self.directory/response_name).exists() and (self.directory/proof_name).exists(): break
            self.pump();self.sleep(0.01)
        value=phase.call('reply-decode',lambda:read_json(self.directory,response_name))
        proof=phase.call('completion-decode',lambda:read_json(self.directory,proof_name))
        phase.call('completion-validate',lambda:audit_phase(proof,role='hub' if self.hub else 'native',
            sequence=self.seq,freeze_sha=self.freeze,request=message,response=value,cap=120))
        if not self.hub and message.get('kind')=='execute' and value.get('status')=='done':
            settled=phase.call('settle-decode',lambda:read_json(self.directory,'settle-time-%04d.json'%self.seq))
            phase.call('settle-validate',lambda:audit_phase(settled,role='settle',sequence=self.seq,
                freeze_sha=self.freeze,request=message,response=value,cap=60))
        receipt=phase.receipt(final_event='response-validated',role='client',sequence=self.seq,
            runtime_freeze_sha256=self.freeze,request_sha256=digest(message),response_sha256=digest(value))
        require(receipt['completed_in_budget'] is True,'formal complete native acknowledgement expired')
        publish_json(self.directory,prefix+'client-time-%04d.json'%self.seq,receipt)
        phase.check('after-client-journal')
        self.seq+=1;self.unresolved=False
        return value

    def control(self,action,slot=None):
        p={'version':1,'request_id':secrets.token_urlsafe(24),'action':action,
            'owner_freeze_sha256':self.freeze,'expires_at':int(time.time())+120}
        if self.hub:
            p['slot_id']=slot
            return self.exchange({'payload':p,'signature':signature(self.secret,p)})
        p['task_sha256']=hashlib.sha256(self.task.encode()).hexdigest()
        return self.exchange({'kind':'control','envelope':{'payload':p,'signature':signature(self.secret,p)}})


class FormalLifecyclePipe(StartupReadyPipe):
    def __init__(self,*args,model_identities,journal_state=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.identities,self.last_phase,self.model_seq,self.control_seq=model_identities,None,0,0
        self.journal_state=journal_state

    def wait_ready(self):
        phase=PhaseClock(self.startup_timeout,clock=self.clock)
        try:
            value=super().wait_ready()
            phase.check('startup-full-validation')
            self.last_phase=phase.receipt(final_event='response-validated',role='startup',sequence=0,
                runtime_freeze_sha256=self.expected['runtime_freeze_sha256'],
                request_sha256=digest(None),response_sha256=digest(value))
            require(self.last_phase['completed_in_budget'] is True,'formal complete startup expired')
            return value
        except BaseException:
            self.blocked=True
            raise

    def exchange(self,sent):
        if self.blocked or not self.ready:
            self.blocked=True
            require(False,'formal channel not ready/uncertain')
        phase=PhaseClock(self.timeout,clock=self.clock)
        try:
            if 'kind' not in sent:phase.call('request-validate',lambda:validate_request(sent))
            value=super().exchange(sent)
            model='kind' not in sent
            if model:
                validate_response(value,sent,self.identities[sent['route']])
                self.model_seq+=1;sequence,role=self.model_seq,'model'
            else:
                require(value.get('request_sha256')==digest(sent),'formal control request binding differs')
                kind=sent['kind']
                if kind=='formal_bootstrap':
                    require(set(value)=={'status','request_sha256','runtime_freeze_sha256','model_identities','startup_receipt'}
                        and value['status']=='formal_worker_ready'
                        and value['model_identities']==self.identities
                        and value['runtime_freeze_sha256']==self.expected['runtime_freeze_sha256'],
                        'formal bootstrap identity differs')
                    validate_startup_receipt(value['startup_receipt'],self.expected)
                elif kind=='formal_export_step':
                    require(set(value)=={'status','request_sha256','key','records'}
                        and value['status']=='formal_raw_step_evidence' and value['key']==sent['key']
                        and isinstance(value['records'],dict) and 4<=len(value['records'])<=10,
                        'formal bounded export shape differs')
                elif kind=='formal_stop':
                    require(set(value)=={'status','request_sha256','runtime_freeze_sha256','raw_records','file_sha256',
                        'asset_environment_preflight','resource'} and value['status']=='formal_worker_stopped'
                        and value['runtime_freeze_sha256']==self.expected['runtime_freeze_sha256'],
                        'formal complete stop shape differs')
                elif kind=='formal_abort_before_bootstrap':
                    require(value=={'status':'formal_prebootstrap_aborted_zero_generation','request_sha256':digest(sent),
                        'runtime_freeze_sha256':self.expected['runtime_freeze_sha256'],'generation_requests':0},
                        'formal zero-stage abort differs')
                else: require(False,'unknown formal control kind')
                self.control_seq+=1;sequence,role=self.control_seq,'formal-control'
            phase.check('formal-full-validation')
            self.last_phase=phase.receipt(final_event='response-validated',role=role,sequence=sequence,
                runtime_freeze_sha256=self.expected['runtime_freeze_sha256'],
                request_sha256=digest(sent),response_sha256=digest(value))
            require(self.last_phase['completed_in_budget'] is True,'formal complete wire validation expired')
            if not model and self.journal_state is not None:
                prefix='control-%04d-'%sequence
                publish_json(self.journal_state,prefix+'request.json',sent)
                publish_json(self.journal_state,prefix+'response.json',value)
                publish_json(self.journal_state,prefix+'time.json',self.last_phase)
                phase.check('after-control-journal')
            return value
        except BaseException:
            self.blocked=True
            raise
