"""Owner-side v2 adapters. New exact scope gate precedes construction/use.

Zero-stage arming/loading has no task input. It is still a separately approved
live operation, not a CPU preflight. Only the owner entry invokes it.
"""
import os
import time
import secrets
import subprocess

from training.c5_formal_reuse_adapters_base import NativeAdapter, ModelAdapter
from training.c5_formal_reuse_transport import NativeChannelV2, FormalLifecyclePipe
from plugin.rhino_listener.c5_formal_reuse_scope import (
    STUDY_ID,REMOTE_SOURCE,REMOTE_ENV,SSH_SOCKET,SSH_PORT,SSH_KNOWN_HOSTS,SSH_KNOWN_HOSTS_SHA,native_plans)
from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import require,digest
from training.c5_formal_reuse_model_wire import request,rebind_observation
from training.c5_startup_transport import startup_receipt
from training.c5_modelbridge_runtime import file_sha


class NativeAdapterV2(NativeAdapter):
    def __init__(self,*args,channel_factory=NativeChannelV2,cleanup_guard=None,**kwargs):
        self.cleanup_guard=kwargs['guard'] if cleanup_guard is None else cleanup_guard
        from functools import partial
        spec=args[1] if len(args)>1 else kwargs['spec']
        hub_limit=81 if 'slot_protocol' in spec.get('run_package',{}) else 41
        super().__init__(*args,channel_factory=partial(channel_factory,cleanup_guard=self.cleanup_guard,hub_limit=hub_limit),**kwargs)
        self.armed=False

    def shared_health(self,slot_id):
        self.cleanup_guard()
        require(self.current is None and not self.unresolved(slot_id),'slot_cleanup_must_be_known')
        response=self.hub.control('health',slot_id)
        request=read_json(self.state,'hub-request-%04d.json'%(self.hub.seq-1))
        require(response=={'status':'slot_shared_health_verified','slot_id':slot_id,
            'request_sha256':digest(request),'active_serial':read_json(self.state,'hub-bootstrap.json')['active_serial'],
            'active_sha256':read_json(self.state,'hub-bootstrap.json')['active_sha256'],
            'source_sha256':self.freeze['source_inventory_sha256'],
            'previous_fixture_closed':True,'previous_bridge_stopped':True},'slot_fresh_shared_health_binding')
        self.cleanup_guard();return response

    def verify_prepared_keys(self):
        labels={'hub'}|{'F%02d-%s'%(n,r) for n in range(1,21) for r in ('base','lora')}
        custody=self.state/'audit-key-custody'
        require(custody.is_dir() and {p.name for p in custody.iterdir()}=={n+'.json' for n in labels},
            'formal_reuse_complete_prepared_key_custody')
        self.keys=[]
        for label in sorted(labels):
            directory,name=(self.state,'hub.key') if label=='hub' else (self.state/label,'handoff.key')
            value=read_json(directory,name)
            require(set(value)=={'key_hex'} and type(value['key_hex']) is str
                and len(value['key_hex'])==64 and all(c in '0123456789abcdef' for c in value['key_hex'])
                and read_json(custody,label+'.json')=={**value,'runtime_sha256':digest(self.freeze)},
                'formal_reuse_prepared_original_key_binding')
            self.keys.append((directory,name))
        self.armed=True

    def arm(self):
        self.guard()
        require(not self.armed and all(not (self.state/n).exists() for n in
            ('formal20.started.json','remote-launch-intent.json','formal20.hub-started.claim.json')),
            'formal_reuse_repair_only_unloaded_unattached_preparation')
        require(read_json(self.state,'formal20.zero-started.claim.json')=={
            'study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze),'replay_allowed':False},
            'new exact zero-stage claim required')
        labels=['hub']+['F%02d-%s'%(n,r) for n in range(1,21) for r in ('base','lora')]
        custody=self.state/'audit-key-custody'
        if not custody.exists():custody.mkdir(mode=0o700)
        require({p.name for p in custody.iterdir()}<={n+'.json' for n in labels},
            'formal_reuse_unknown_partial_key_custody')
        for label in labels:
            directory,name=(self.state,'hub.key') if label=='hub' else (self.state/label,'handoff.key')
            if not directory.exists():directory.mkdir(mode=0o700)
            if not (directory/name).exists():
                require(not (custody/(label+'.json')).exists(),'formal_reuse_dispatch_key_cannot_be_recreated')
                publish_json(directory,name,{'key_hex':secrets.token_bytes(32).hex()})
            value=read_json(directory,name)
            expected={**value,'runtime_sha256':digest(self.freeze)}
            if (custody/(label+'.json')).exists():
                require(read_json(custody,label+'.json')==expected,'formal_reuse_partial_key_scope_drift')
            else:publish_json(custody,label+'.json',expected)
        self.verify_prepared_keys()
        prepared={'study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze),'private_rows_read':0,'model_calls':0}
        if (self.state/'formal20.zero-prepared.json').exists():
            require(read_json(self.state,'formal20.zero-prepared.json')==prepared,'formal_reuse_prepared_scope_drift')
        else:publish_json(self.state,'formal20.zero-prepared.json',prepared)

    def wait_zero_ready(self):
        self.guard()
        while not (self.state/'host-continuity-ready.json').exists():
            require(not (self.state/'deferred-baseline.failed.json').exists(),'formal_reuse_host_preparation_failed')
            self.guard()
            if 'run_package' in self.spec:
                policy=self.spec['run_package']['policy']
                require(time.time()+(len(self.spec['run_package']['slot_protocol']['selected_indices'])*policy['slot_work_upper_seconds'] if 'slot_protocol' in self.spec['run_package'] else policy['remaining_chain_upper_seconds'])+policy['startup_seconds']
                    +policy['export_reserve_seconds']<=self.spec['run_package']['lease_expiry_epoch'],
                    'run_package_remaining_work_window_unavailable')
            else:
                require(time.time()<=self.spec['latest_owner_start_epoch'],'formal_reuse_full_window_no_longer_available')
            time.sleep(0.05)
        require(read_json(self.state,'host-continuity-ready.json')=={'study_id':STUDY_ID,
            'runtime_freeze_sha256':digest(self.freeze),'legacy_byte_closure_verified':False,
            'sealed_before_model_generation':True},'formal_reuse_actual_host_ready_binding')
        self.guard()

    def prepare(self,plans,*,freeze_sha256):
        self.guard()
        require(self.armed and freeze_sha256==digest(self.freeze)
            and read_json(self.state,'formal20.started.json')['runtime_freeze_sha256']==freeze_sha256,
            'formal pre-armed/private started scope required')
        self.plans=native_plans(plans)
        require(digest(plans['slot_order'])==self.spec['slot_order_sha256'],'formal sealed order differs')
        publish_json(self.state,'native-plans.json',plans)
        publish_json(self.state,'native-prepared.json',{'study_id':STUDY_ID,
            'native_plans_sha256':digest(plans),'runtime_freeze_sha256':freeze_sha256})

    def start(self):
        deadline=time.monotonic()+self.spec['hub_attach_timeout_seconds']
        if self.attach_wait is not None:self.attach_wait()
        while not (self.state/'hub-bootstrap.json').exists():
            require(not (self.state/'formal20.hub-initialization.failed.json').exists(),
                'formal private initialization failed; no retry')
            self.guard()
            require(time.monotonic()<deadline,'formal private hub attachment unknown')
            time.sleep(0.05)
        bootstrap=read_json(self.state,'hub-bootstrap.json')
        require(not (self.state/'formal20.hub-initialization.failed.json').exists()
            and bootstrap['runtime_freeze_sha256']==digest(self.freeze)
            and bootstrap['source_sha256']==self.freeze['source_inventory_sha256']
            and bootstrap['native_plans_sha256']==digest(self.plans),
            'formal actual hub bootstrap differs')
        self.guard()
        channel=self.channel_factory(self.state,bytes.fromhex(read_json(self.state,'hub.key')['key_hex']),
            digest(self.freeze),hub=True,guard=self.guard)
        require(time.monotonic()<deadline,'formal complete hub attachment expired')
        self.hub=channel

    def finish(self):
        original=self.guard;self.guard=self.cleanup_guard
        try:return self._finish_known_native()
        finally:self.guard=original

    def _finish_known_native(self):
        if (self.state/'formal20.hub-initialization.claim.json').exists() or self.hub is not None:
            return super().finish()
        self.guard()
        if (self.state/'preload-abort.response.json').exists():
            result=read_json(self.state,'preload-abort.response.json')
            require(result['status']=='preload_aborted' and result['runtime_freeze_sha256']==digest(self.freeze),
                'formal_reuse_preload_abort_binding')
            return result
        if not (self.state/'host-continuity-ready.json').exists():
            return super().finish()
        from plugin.rhino_listener.c5_research_gate import signature
        secret=bytes.fromhex(read_json(self.state,'hub.key')['key_hex'])
        payload={'action':'abort_uninitialized_native','runtime_freeze_sha256':digest(self.freeze)}
        request={'payload':payload,'signature':signature(secret,payload)}
        if (self.state/'preload-abort.request.json').exists():
            require(read_json(self.state,'preload-abort.request.json')==request,'run_package_original_abort_request_changed')
        else:publish_json(self.state,'preload-abort.request.json',request)
        deadline=time.monotonic()+120
        while not (self.state/'preload-abort.response.json').exists():
            self.guard();require(time.monotonic()<deadline,'formal_reuse_preload_abort_unknown');time.sleep(0.05)
        result=read_json(self.state,'preload-abort.response.json')
        require(result['status']=='preload_aborted' and result['runtime_freeze_sha256']==digest(self.freeze),
            'formal_reuse_preload_abort_binding')
        return result


class ModelAdapterV2(ModelAdapter):
    def __init__(self,*args,process_factory=subprocess.Popen,pipe_factory=FormalLifecyclePipe,**kwargs):
        super().__init__(*args,process_factory=process_factory,pipe_factory=pipe_factory,**kwargs)
        self.zero_ready=False;self.bootstrapped=False

    def start_zero(self):
        self.guard()
        require(self.process is None and not (self.state/'formal20.started.json').exists(),
            'formal_reuse_zero_load_once_before_exposure')
        from training.c5_formal_reuse_ssh import argv,verify
        from training.c5_followup_diagnostics import CapturedStreams
        from training.c5_formal_reuse_supervisor import validate_load_permit
        from training.c5_reuse_evidence import canonical
        from training.c5_reuse_field_transport import FieldPipe
        verify(self.spec,self.freeze)
        validate_load_permit(self.load_permit,self.spec,self.freeze,self.attempt)
        self.capture=CapturedStreams(self.state,'serve',stdout_cap=self.spec['raw_stdout_cap_bytes'],
            stderr_cap=self.spec['raw_stderr_cap_bytes']);self.diagnostics_finished=False
        args=argv(self.spec,'serve',self.attempt)
        publish_json(self.state,'remote-launch-intent.json',{'argv':args,'attempt':self.attempt,
            'load_permit_sha256':digest(self.load_permit),'replay_allowed':False})
        self.process=self.process_factory(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        self.capture.start(self.process,protocol=True)
        publish_json(self.state,'load-permit.json',self.load_permit)
        sender=FieldPipe(self.process.stdin.fileno(),self.process.stdout.fileno())
        raw=canonical(self.load_permit)+b'\n';offset=0;deadline=time.monotonic()+60
        while offset<len(raw):offset+=sender.write(raw[offset:],deadline)
        expected=startup_receipt(STUDY_ID,digest(self.freeze),self.freeze['source_inventory_sha256'],
            self.freeze['environment_sha256'],self.freeze['model_identities'])
        self.pipe=self.pipe_factory(self.process,expected,capture=self.capture,
            model_identities=self.freeze['model_identities'],timeout=360,startup_timeout=600,journal_state=self.state)
        ready=self.pipe.wait_ready()
        publish_json(self.state,'startup-time.json',self.pipe.last_phase)
        publish_json(self.state,'worker-startup-ready.json',ready)
        self.guard();self.zero_ready=True

    def start(self):
        self.guard()
        require(self.zero_ready and not self.bootstrapped and self.plans is not None,
            'formal zero readiness and one new hash bootstrap required')
        sent={'kind':'formal_bootstrap','study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze),
            'started':read_json(self.state,'formal20.started.json'),'plans':self.plans}
        if 'slot_protocol' in self.spec.get('run_package',{}):
            sent['slot_order']=read_json(self.state,'native-plans.json')['slot_order']
        publish_json(self.state,'worker-bootstrap-request.json',sent)
        value=self.pipe.exchange(sent)
        publish_json(self.state,'worker-bootstrap-response.json',value)
        self.bootstrapped=True

    def infer(self,*,slot_id,route,step_index,task_text,scene,binding,freeze_sha256):
        self.guard()
        require(self.bootstrapped and freeze_sha256==digest(self.freeze),'formal loaded/bootstrap scope required')
        sent=request(STUDY_ID,slot_id,route,step_index,task_text,scene,binding,freeze_sha256,'m-'+secrets.token_urlsafe(24))
        key=digest({'slot':slot_id,'step':step_index,'freeze':freeze_sha256})
        self.attempts.append(key)
        publish_json(self.state,key+'-model-request.json',sent)
        wire=self.pipe.exchange(sent)
        publish_json(self.state,key+'-model-time.json',self.pipe.last_phase)
        publish_json(self.state,key+'-model-response.json',wire)
        observed=rebind_observation(wire,sent,self.freeze['model_identities'][route],binding)
        return {**wire,'observation':observed,'wire_request':sent,'wire_response':wire}

    def export_completed_slot(self,slot_id):
        """Read-only export of each original step BEFORE allowing the next slot."""
        require('slot_protocol' in self.spec.get('run_package',{}) and self.bootstrapped,
            'slot_export_current_approved_protocol')
        exported=[]
        for key in self.attempts:
            request=read_json(self.state,key+'-model-request.json')
            if request['slot_id']!=slot_id:continue
            name=key+'-remote-evidence.json'
            require(not (self.state/name).exists(),'slot_original_step_export_once')
            sent={'kind':'formal_export_step','study_id':STUDY_ID,
                'runtime_freeze_sha256':digest(self.freeze),'key':key}
            value=self.pipe.exchange(sent)
            require(value.get('status')=='formal_raw_step_evidence' and value.get('key')==key
                and value.get('request_sha256')==digest(sent),'slot_original_step_export_binding')
            publish_json(self.state,name,value);exported.append(key)
        return exported

    def _stop_zero_protocol(self):
        require(not self.bootstrapped,'zero-stage abort cannot follow private bootstrap')
        if self.process is None: return
        try:
            require(self.zero_ready and not self.pipe.blocked,'unknown startup acknowledgement; no reconnect or abort resend')
            sent={'kind':'formal_abort_before_bootstrap','study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze)}
            value=self.pipe.exchange(sent)
            publish_json(self.state,'worker-zero-abort-response.json',value)
        finally:
            self.process.stdin.close()
            try:code=self.process.wait(timeout=180)
            except subprocess.TimeoutExpired:code=None
            # CapturedStreams retains original bytes through EOF.
            if self.stderr_fd is not None:os.close(self.stderr_fd);self.stderr_fd=None
            publish_json(self.state,'worker-process-exit.json',{'exit_code':code,'replay_allowed':False})
        require(code==0,'formal zero-stage worker exit unknown')

    def _supervisor_snapshot(self,mode):
        original_name=mode+'-original.json'
        if (self.state/original_name).is_file():return read_json(self.state,original_name)
        from training.c5_formal_reuse_ssh import argv,verify
        from training.c5_reuse_evidence import strict
        verify(self.spec,self.freeze)
        result=subprocess.run(argv(self.spec,mode,self.attempt),capture_output=True,timeout=90)
        observation=mode+'-transport-observation.json'
        if (self.state/observation).exists():
            observation=mode+'-transport-observation-%04d.json'%len(list(self.state.glob(mode+'-transport-observation*.json')))
        publish_json(self.state,observation,{'exit_code':result.returncode,
            'stdout_raw_sha256':__import__('hashlib').sha256(result.stdout).hexdigest(),
            'stderr_raw_sha256':__import__('hashlib').sha256(result.stderr).hexdigest(),
            'bytes':len(result.stdout),'model_restart':False})
        require(result.returncode==0,'formal_reuse_independent_supervisor_rpc_failed')
        value=strict(result.stdout,limit=2097152)
        publish_json(self.state,mode+'-original.json',value);return value

    def _finalize(self):
        if getattr(self,'diagnostics_finished',False):return
        self.diagnostics_finished=True
        self.process.wait(timeout=60)
        value=self.capture.finish()
        if self.pipe is not None:value['unconsumed_protocol_tail_bytes']+=len(self.pipe.buffer)
        publish_json(self.state,'raw-streams-final.json',value)
        self.process.stdout.close();self.process.stderr.close()
        self._supervisor_snapshot('export-supervisor')

    def stop(self):
        primary=None
        try:return super().stop()
        except BaseException as error:
            primary=error
            try:self._supervisor_snapshot('stop')
            except BaseException as cleanup:
                publish_json(self.state,'independent-stop-failed.json',{'error_type':type(cleanup).__name__})
            raise
        finally:
            if self.process is not None:
                try:self._finalize()
                except BaseException as cleanup:
                    publish_json(self.state,'diagnostic-finalize-failed.json',{'error_type':type(cleanup).__name__})
                    if primary is None:raise

    def stop_zero(self):
        primary=None
        try:return self._stop_zero_protocol()
        except BaseException as error:
            primary=error
            try:self._supervisor_snapshot('stop')
            except BaseException as cleanup:
                publish_json(self.state,'independent-stop-failed.json',{'error_type':type(cleanup).__name__})
            raise
        finally:
            if self.process is not None:
                try:self._finalize()
                except BaseException as cleanup:
                    publish_json(self.state,'diagnostic-finalize-failed.json',{'error_type':type(cleanup).__name__})
                    if primary is None:raise
