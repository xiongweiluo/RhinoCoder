"""One-shot signed native file transport with complete timing validation."""
import secrets
import time
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import digest
from plugin.rhino_listener.c5_lifecycle_deadlines import PhaseClock
from training.c5_lifecycle_timing_audit import audit_phase
from training.c5_reuse_evidence import require


class NativeChannel:
    def __init__(self,directory,secret,runtime_sha,guard,*,task=None,hub=False,
                 clock=time.monotonic,epoch=time.time,sleep=time.sleep):
        self.directory,self.secret,self.runtime_sha,self.guard=directory,secret,runtime_sha,guard
        self.task,self.hub,self.clock,self.epoch,self.sleep=task,hub,clock,epoch,sleep
        self.seq,self.unresolved=1,False

    def exchange(self,message,*,cleanup=False):
        require(not self.unresolved and self.seq<=(41 if self.hub else 128),'reuse_native_no_resend')
        self.unresolved=True
        prefix='hub-' if self.hub else '';phase=PhaseClock(120,clock=self.clock)
        def guard():return self.guard(cleanup_only=cleanup)
        phase.call('guard',guard)
        phase.call('request-publish',lambda:publish_json(self.directory,prefix+'request-%04d.json'%self.seq,message))
        name=prefix+'response-%04d.json'%self.seq;proof=prefix+'service-time-%04d.json'%self.seq
        while not (self.directory/name).exists() or not (self.directory/proof).exists():
            phase.check('receive-poll',record=False);self.sleep(0.05)
        value=phase.call('reply-decode',lambda:read_json(self.directory,name))
        timing=phase.call('completion-decode',lambda:read_json(self.directory,proof))
        phase.call('completion-validate',lambda:audit_phase(timing,role='hub' if self.hub else 'native',
            sequence=self.seq,freeze_sha=self.runtime_sha,request=message,response=value,cap=120))
        if not self.hub and message['kind']=='execute' and value.get('status')=='done':
            settled=phase.call('settle-decode',lambda:read_json(self.directory,'settle-time-%04d.json'%self.seq))
            phase.call('settle-validate',lambda:audit_phase(settled,role='settle',sequence=self.seq,
                freeze_sha=self.runtime_sha,request=message,response=value,cap=60))
        phase.call('final-guard',guard)
        receipt=phase.receipt(final_event='response-validated',role='client',sequence=self.seq,
            runtime_freeze_sha256=self.runtime_sha,request_sha256=digest(message),response_sha256=digest(value))
        require(receipt['completed_in_budget'] is True,'reuse_native_completion_expired')
        publish_json(self.directory,prefix+'client-time-%04d.json'%self.seq,receipt)
        phase.check('after-client-journal')
        self.seq+=1;self.unresolved=False
        return value

    def control(self,action,slot=None):
        require((self.hub and action in ('open','stop')) or
                (not self.hub and action in ('capture','close','stop')),'reuse_native_control_kind')
        p={'version':1,'request_id':secrets.token_hex(16),'action':action,
           'owner_freeze_sha256':self.runtime_sha,'expires_at':int(self.epoch())+120}
        if self.hub:p['slot_id']=slot
        else:p['task_sha256']=self.task
        envelope={'payload':p,'signature':signature(self.secret,p)}
        return self.exchange(envelope if self.hub else {'kind':'control','envelope':envelope},
                             cleanup=action in ('close','stop'))

    def execute(self,envelope):return self.exchange({'kind':'execute','envelope':envelope})
