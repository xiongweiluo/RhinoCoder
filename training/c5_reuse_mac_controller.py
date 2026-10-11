"""Actual eight public slots; explicit preparation/host readiness first.

No private cases, training, retries or score-based model corrections. This
source cannot create an independent owner readiness/final custody witness.
"""
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import time
from plugin.rhino_listener.c5_research_channel import publish_json,read_json,private_directory
from plugin.rhino_listener.c5_reuse_field_scope import validate_binding
from plugin.rhino_listener.c5_reuse_public_plan import public_plan,ORDER
from plugin.rhino_listener.c5_reuse_runtime_scope import MAC_PARENT,INSTANCE,read_bytes
from training.c5_reuse_evidence import canonical,require,sha,strict,ZERO
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_native_channel import NativeChannel
from training.c5_reuse_native_handoff import NativeHandoff
from training.c5_reuse_field_wire import envelope
from training.c5_model_transport import request
from training.c5_reuse_ssh import FieldSSHSession

CUSTODY=MAC_PARENT/(INSTANCE+'-external-custody')


class NativeJournal:
    def __init__(self,binding):
        validate_binding(binding);self.binding=binding
        self.root=Path(binding['paths']['state_root'])/'native-controller'
        self.root.mkdir(mode=0o700);self.rows=[];self.head=ZERO
        self.append('native_controller_open',{'binding':binding})

    def append(self,kind,payload):
        fd=private_directory(self.root)
        try:require(set(os.listdir(fd))=={'raw-%04d.json'%i for i in range(len(self.rows))},'reuse_native_journal_population')
        finally:os.close(fd)
        require(len(self.rows)<128,'reuse_native_journal_capacity')
        if self.rows:require(read_json(self.root,'raw-%04d.json'%(len(self.rows)-1))==self.rows[-1],'reuse_native_previous_drift')
        value={'seq':len(self.rows),'previous_sha256':self.head,'scope_sha256':sha(self.binding),'kind':kind,'payload':payload}
        value['record_sha256']=sha(value)
        publish_json(self.root,'raw-%04d.json'%len(self.rows),value)
        require(read_json(self.root,'raw-%04d.json'%len(self.rows))==value,'reuse_native_journal_readback')
        self.rows.append(strict(canonical(value)));self.head=value['record_sha256']


def prepare(binding,guard):
    """Called only after direct exact approval, never by freeze preparation."""
    validate_binding(binding);require(binding['endpoint']=='mac','reuse_prepare_mac')
    guard();state=Path(binding['paths']['state_root'])
    # State/grant were placed by the owner. Do not replace an existing claim.
    publish_json(state,'new-preparation.claim.json',{'runtime_sha256':binding['runtime_sha256'],'replay_allowed':False})
    root=Path(binding['paths']['admission_root'])
    with AdmissionRegistry(binding,create=not os.path.lexists(root)) as registry:registry.audit()
    publish_json(state,'hub.key',{'key_hex':secrets.token_bytes(32).hex()})
    for slot in ORDER:
        directory=state/slot;directory.mkdir(mode=0o700)
        publish_json(directory,'handoff.key',{'key_hex':secrets.token_bytes(32).hex()})
    guard()
    publish_json(state,'prepared.json',{'study_id':binding['study_id'],'spec_sha256':binding['spec_sha256'],
        'runtime_sha256':binding['runtime_sha256'],'model_calls':0,'private_formal_reads':0})


def backup_database(directory,name):
    p=directory/name;target=directory/(name.replace('.sqlite3','-audit.sqlite3'))
    require(not os.path.lexists(target),'reuse_backup_no_replace')
    # Original database remains; evidence backup is consistent with its WAL.
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
    source=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);output=sqlite3.connect(target)
    try:
        require(source.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'reuse_backup_integrity')
        source.backup(output);output.commit()
        require(output.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'reuse_backup_output_integrity')
    finally:output.close();source.close()
    fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'name':target.name,'raw_sha256':hashlib.sha256(read_bytes(target,limit=16*1024*1024,private=True)).hexdigest()}


class MacController:
    def __init__(self,binding,plan,schemas,registry,guard,budget,*,session_factory=FieldSSHSession,
                 channel_factory=NativeChannel,epoch=time.time,clock=time.monotonic,sleep=time.sleep):
        validate_binding(binding);require(binding['endpoint']=='mac','reuse_controller_mac')
        self.binding,self.plan,self.schemas,self.registry=binding,plan,schemas,registry
        self.guard,self.budget,self.epoch,self.clock,self.sleep=guard,budget,epoch,clock,sleep
        self.session_factory,self.channel_factory=session_factory,channel_factory
        self.state=Path(binding['paths']['state_root']);self.public=public_plan(Path(binding['paths']['source_root']))
        require(self.public['development_plan_sha256']==binding['development_plan_sha256'],'reuse_controller_plan')
        self.journal=NativeJournal(binding);self.session=None;self.spent=False
        self.hub=None;self.current_child=None;self.native_cleanup_known=False;self.child_closed=False

    def _known_native_cleanup(self):
        """No control is sent after an uncertain native ACK/dispatch/close."""
        child=self.current_child
        if child is not None:
            if not self.native_cleanup_known or child.unresolved:return
            for action in (('stop',) if self.child_closed else ('close','stop')):
                self.journal.append('failure_cleanup_intent',{'action':action,'scope':'known_current_fixture_only'})
                value=child.control(action)
                self.journal.append('failure_cleanup_observed',{'action':action,'receipt':value})
                require(value.get('status')==('closed' if action=='close' else 'stopped'),'reuse_failure_cleanup_unknown')
                if action=='close':self.child_closed=True
            self.current_child=None
        if self.hub is not None and not self.hub.unresolved:
            self.journal.append('failure_cleanup_intent',{'action':'stop','scope':'known_hub_only'})
            value=self.hub.control('stop')
            self.journal.append('failure_cleanup_observed',{'action':'stop','receipt':value})
            require(value.get('status')=='hub_stopped','reuse_failure_hub_cleanup_unknown')
            self.hub=None

    def drive(self,external_ready):
        require(not self.spent,'reuse_driver_no_retry');self.spent=True
        try:return self._drive(external_ready)
        except BaseException as exc:
            self.journal.append('controller_retired_no_retry',{'error_type':type(exc).__name__})
            if self.session is not None and not self.session.stop_spent:
                self.session.independent_stop()
            try:self._known_native_cleanup()
            except BaseException as cleanup_error:
                self.journal.append('failure_cleanup_unknown_no_retry',{'error_type':type(cleanup_error).__name__})
            raise

    def _drive(self,external_ready):
        self.guard();self.budget()
        release=read_json(self.state,'entry-return-release.json')
        require(release=={'study_id':self.binding['study_id'],'runtime_sha256':self.binding['runtime_sha256'],
            'source_inventory_sha256':sha(self.plan['source_files']),'baseline_sealed':False,'replay_allowed':False},
            'reuse_explicit_entry_return')
        host=read_json(self.state,'host-continuity-ready.json')
        require(host['study_id']==self.binding['study_id'] and host['runtime_sha256']==self.binding['runtime_sha256']
                and host['generation_stages']==0 and host['full_byte_closure_proven'] is False,'reuse_host_before_loading')
        self.journal.append('host_ready_before_remote_launch',{'release':release,'ready':host})
        hub_secret=bytes.fromhex(read_json(self.state,'hub.key')['key_hex'])
        keys=self.state/'audit-key-custody';keys.mkdir(mode=0o700)
        publish_json(keys,'hub.json',{'key_hex':hub_secret.hex(),'runtime_sha256':self.binding['runtime_sha256']})
        hub=self.channel_factory(self.state,hub_secret,
                                 self.binding['runtime_sha256'],self.guard,hub=True)
        self.hub=hub
        self.session=self.session_factory(self.binding,self.registry,self.public['task_plans'],
                                          self.plan['transport'],self.guard,self.budget)
        ready=self.session.await_ready()
        owner=external_ready(host,ready)
        require(owner['host_baseline_head_sha256']==host['host_baseline_head_sha256'],'reuse_external_host_head')
        self.session.begin(owner)
        handoff=NativeHandoff(self.session.channel.journal,self.schemas,self.guard,self.budget)
        try:
            for slot in ORDER:
                self.guard();self.budget();self.journal.append('slot_open_intent',{'slot_id':slot})
                opened=hub.control('open',slot)
                require(opened.get('status')=='slot_opened' and opened.get('slot_id')==slot,'reuse_native_open_unknown')
                directory=self.state/slot;secret=bytes.fromhex(read_json(directory,'handoff.key')['key_hex'])
                task=self.public['task_plans'][slot]['steps'][0]
                child=self.channel_factory(directory,secret,self.binding['runtime_sha256'],self.guard,
                                            task=hashlib.sha256(task.encode()).hexdigest())
                self.current_child=child;self.native_cleanup_known=True;self.child_closed=False
                capture=child.control('capture');require(capture.get('status')=='captured','reuse_native_capture_unknown')
                before={k:capture[k] for k in ('state','native')}
                sent=envelope(self.binding,request(self.binding['study_id'],slot,
                    self.public['task_plans'][slot]['route'],0,task,before['native'],before['state'],
                    self.binding['runtime_sha256'],secrets.token_hex(16)))
                self.journal.append('slot_model_scene',{'slot_id':slot,'capture':capture,'request':sent})
                result=self.session.channel.exchange(sent)
                post=child.control('capture')
                require(post.get('status')=='captured' and {k:post[k] for k in ('state','native')}==before,
                        'reuse_post_model_actual_scene_drift')
                def current():
                    value=child.control('capture');require(value.get('status')=='captured','reuse_signing_capture_unknown')
                    return {k:value[k] for k in ('state','native')}
                def execute_signed(signed):
                    self.native_cleanup_known=False
                    value=child.execute(signed)
                    self.native_cleanup_known=value.get('status')=='done'
                    return value
                receipt=handoff.execute(sent,result,before,current,execute_signed,secret)
                self.journal.append('slot_native_result',{'slot_id':slot,'post_model_capture':post,
                    'model_result':result,'native_result':receipt})
                # Keep original keyed verifier input in separate private audit
                # custody; removing dispatch keys is NOT a memory-erasure claim.
                publish_json(keys,slot+'.json',{'key_hex':secret.hex(),'runtime_sha256':self.binding['runtime_sha256']})
                close=child.control('close');require(close.get('status')=='closed','reuse_native_close_unknown')
                self.child_closed=True
                stop=child.control('stop');require(stop.get('status')=='stopped','reuse_native_stop_unknown')
                self.current_child=None
                backups=[backup_database(directory,'fixture.sqlite3')]
                if (directory/'consent.sqlite3').exists():backups.append(backup_database(directory,'consent.sqlite3'))
                self.journal.append('slot_closed',{'slot_id':slot,'close':close,'stop':stop,'database_backups':backups})
                require(receipt.get('model_status')!='operational_failure_no_retry','reuse_model_operational_retirement')
            stopped=hub.control('stop');require(stopped.get('status')=='hub_stopped','reuse_hub_stop_unknown')
            self.hub=None
            self.journal.append('hub_closed',{'receipt':stopped,'host_terminal':read_json(self.state,'host-continuity-terminal-receipt.json')})
            final=self.session.close()
            exported=self.session.export()
            self.journal.append('controller_completed_records',{'worker_close':final,
                'gpu_export_raw_sha256':hashlib.sha256(exported).hexdigest(),'whole_field_pass':False})
            return {'native_head_sha256':self.journal.head,'worker_final_head_sha256':final['worker_final_head_sha256'],
                    'whole_field_pass':False,'external_final_capture_required':True}
        except BaseException as exc:
            # Unknown native/fixture state is retained; never guess a cleanup
            # identity or resend a close. Only the durably qualified GPU child
            # may receive the separate one-shot stop.
            raise


def external_readiness(binding,host,worker,*,clock=time.monotonic,sleep=time.sleep):
    print('C5_REUSE_EXTERNAL_READINESS_REQUIRED '+canonical({'host':host,'worker':worker}).decode(),flush=True)
    deadline=clock()+120;p=CUSTODY/'owner-readiness.json'
    while not os.path.lexists(p):
        require(clock()<deadline,'reuse_missing_external_readiness_no_retry');sleep(0.05)
    return strict(read_bytes(p,private=True))
