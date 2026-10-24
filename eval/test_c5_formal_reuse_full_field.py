"""New identity CPU integration: real signatures, ledgers, wire parser and audit.

Uses only existing public synthetic families. Rhino geometry/model transport,
authority and physical GPU/real admission are fixtures; their actual CPU
process/raw-stream/admission tests are separate. No field entry is invoked.
"""
import contextlib,copy,hashlib,io,json,time
from types import SimpleNamespace
import pytest
from eval.test_c5_formal20_field_adapters import setup_field,SyntheticNativeDoc,ACTIVE
from eval.test_c5_formal20_v2 import records
from eval.test_c5_host_assurance_session import Backend
from eval.test_c5_model_transport import Tokenizer
from plugin.rhino_listener.c5_research_native import digest
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID
from plugin.rhino_listener.c5_formal_reuse_host_session import FormalHostSession
from plugin.rhino_listener import c5_formal_reuse_hub as hubs,c5_formal_reuse_hub_base as hub_base
from plugin.rhino_listener.c5_formal_reuse_deadlines import PhaseClock
from training.c5_formal_reuse_adapters import NativeAdapterV2,ModelAdapterV2
from training.c5_formal_reuse_transport import NativeChannelV2
from training.c5_formal_reuse_runtime import FormalModelSession
from training import c5_formal_reuse_runner as runner_module,c5_formal_reuse_evidence_audit as evidence
from training.c5_formal_reuse_runner import FormalRunner
from training.c5_formal_reuse_joint_audit import audit_run_v2,public_summary
from training.c5_startup_transport import startup_receipt
from training.c5_formal_reuse_model_wire import frame
from training.c5_modelbridge_runtime import file_sha
from tools.run_c5_formal_reuse_worker import step_evidence

class SyntheticWire:
    def __init__(self, state, spec, freeze, raw_policy):
        self.state,self.spec,self.freeze,self.policy=state,spec,freeze,raw_policy
        self.blocked=False;self.current=None;self.keys=[];self.stages=0;self.start=time.time()
    def exchange(self, sent):
        assert not self.blocked
        if sent.get('kind') == 'formal_bootstrap':
            publish_json(self.state,'formal20.worker-started.claim.json',{'study_id':self.spec['study_id'],
                'runtime_freeze_sha256':digest(self.freeze),'replay_allowed':False})
            publish_json(self.state,'bootstrap.json',sent)
            loaded={'study_id':self.spec['study_id'],'environment_sha256':self.freeze['environment_sha256'],
                'source_inventory_sha256':self.freeze['source_inventory_sha256'],'model_identities':self.freeze['model_identities'],
                'torch_cuda':'synthetic-no-CUDA','gpu':'NVIDIA GeForce RTX 3090','default_route_changed':False,
                'base_dtype_cast':'prepare_model_for_kbit_training_no_checkpoint_hooks',
                'base_route':'same PEFT-wrapped base with disable_adapter context'}
            publish_json(self.state,'loaded-runtime.json',loaded)
            def generate(prompt,stage):
                self.stages+=1
                choices=self.policy.get(self.current['task'],[])
                choice=choices[self.current['step_index']] if choices else None
                raw=json.dumps({'tool':choice[0] if choice else None},separators=(',',':')) if stage=='selector' else json.dumps(
                    {'name':choice[0],'arguments':choice[1]},separators=(',',':'))
                if stage=='selector' and getattr(self,'invalid_task',None)==self.current['task']:raw='not-json'
                return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                    'output_sha256':hashlib.sha256(raw.encode()).hexdigest()}
            self.session=FormalModelSession(digest(self.freeze),sent['plans'],self.state,Tokenizer(),generate,
                lambda route:contextlib.nullcontext(),self.freeze['model_identities'],lambda:None,lambda:100)
            return {'status':'formal_worker_ready','request_sha256':digest(sent),'runtime_freeze_sha256':digest(self.freeze),
                'model_identities':self.freeze['model_identities']}
        if sent.get('kind') == 'formal_export_step':
            return {'status':'formal_raw_step_evidence','request_sha256':digest(sent),'key':sent['key'],
                'records':step_evidence(self.state,sent['key'])}
        if sent.get('kind') == 'formal_stop':
            publish_json(self.state,'worker-summary.json',{'requests':len(self.keys),'generation_stages':self.stages,
                'peak_allocated_bytes':0,'peak_reserved_bytes':0,'attempted_keys':self.keys})
            settlement={'study_id':self.spec['study_id'],'status':'formal_worker_stopped_no_replay',
                'elapsed_seconds_including_load_and_idle':time.time()-self.start,'cap_seconds':64800,
                'start_epoch':self.start,'stop_epoch':time.time(),
                'resource_boundary_sha256':digest(self.freeze['resource_boundary']),'replay_allowed':False}
            publish_json(self.state,'resource-settlement.json',settlement)
            names=['bootstrap.json','loaded-runtime.json','worker-summary.json','resource-settlement.json','formal20.worker-started.claim.json']
            assets={'source_files':self.freeze['source_files'],'source_inventory_sha256':self.freeze['source_inventory_sha256'],
                'fixed_public_files':self.freeze['fixed_public_files'],'environment_sha256':self.freeze['environment_sha256'],
                'environment':self.freeze['environment'],'snapshot':{'synthetic':True},'adapter_sha256':self.freeze['model_identities']['lora'],
                'adapter_files':{'synthetic-adapter':'1'*64}}
            return {'status':'formal_worker_stopped','request_sha256':digest(sent),'runtime_freeze_sha256':digest(self.freeze),
                'raw_records':{n:read_json(self.state,n) for n in names},'resource':settlement,'asset_environment_preflight':assets,
                'file_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.state.glob('*.json')}}
        self.current=sent;key=digest({'slot':sent['slot_id'],'step':sent['step_index'],'freeze':digest(self.freeze)})
        publish_json(self.state,key+'-request.json',sent);self.keys.append(key)
        return self.session.infer(sent)

class TimedSyntheticWire(SyntheticWire):
    def __init__(self,*args,local,**kwargs):
        super().__init__(*args,**kwargs);self.local=local
        self.ready=startup_receipt(self.spec['study_id'],digest(self.freeze),self.freeze['source_inventory_sha256'],
            self.freeze['environment_sha256'],self.freeze['model_identities'])
        self.model_seq=self.control_seq=0
    def exchange(self,sent):
        phase=PhaseClock(360)
        value=super().exchange(sent)
        if sent.get('kind')=='formal_bootstrap':
            value={**value,'startup_receipt':self.ready}
            publish_json(self.state,'worker-bootstrap-response.json',value)
        if sent.get('kind')=='formal_stop':
            raw=value['raw_records']
            raw.update({n:read_json(self.state,n) for n in
                ('worker-startup-ready.json','worker-bootstrap-response.json','owner-approval.json')})
            value['file_sha256']={p.name:file_sha(p) for p in self.state.glob('*.json')}
        if 'kind' in sent:
            self.control_seq+=1;seq,role=self.control_seq,'formal-control'
        else:self.model_seq+=1;seq,role=self.model_seq,'model'
        self.last_phase=phase.receipt(final_event='response-validated',role=role,sequence=seq,
            runtime_freeze_sha256=digest(self.freeze),request_sha256=digest(sent),response_sha256=digest(value))
        if 'kind' in sent:
            prefix='control-%04d-'%seq
            publish_json(self.local,prefix+'request.json',sent)
            publish_json(self.local,prefix+'response.json',value)
            publish_json(self.local,prefix+'time.json',self.last_phase)
        return value

def complete_scoped_field(tmp_path,monkeypatch,*,fail_before_model_at=None,slot_plan=None,slot_fault=None,fixture_mismatch_index=None,invalid_model_index=None,tail_repair=False,native_ttl_failure=False,model_infer_failure=False,backup_failure=False):
    state,cases,spec,freeze,_,rhino,_=setup_field(tmp_path,monkeypatch)
    # Real signature/SQLite/timing code below; ONLY geometry/model are fake.
    new_spec,new_freeze,_=records()
    spec.update(new_spec)
    freeze.update({k:v for k,v in new_freeze.items() if k not in ('spec_sha256',)})
    spec.update(study_id=STUDY_ID,max_generation_stages=112)
    freeze.update(study_id=STUDY_ID,environment={'synthetic':True})
    from eval.test_c5_formal_reuse_preparation import boundary
    freeze['resource_boundary']=boundary()
    if slot_plan is not None:
        if fixture_mismatch_index is not None:
            from training.c5_formal20_plan import slot_order,family_merkle_root
            target=slot_order(cases,seed=spec['slot_seed'])[fixture_mismatch_index]['family_id']
            case=next(c for c in cases if c['family_id']==target)
            case['initial_assertions']=copy.deepcopy(case['initial_assertions'])
            case['initial_assertions']['object_count']+=1
            spec['family_merkle_root_sha256']=family_merkle_root(cases)
        spec['run_package']={'slot_protocol':slot_plan}
        if tail_repair:
            from plugin.rhino_listener.c5_slot_tail_policy import POLICY as TAIL_POLICY
            spec['run_package']['tail_repair']={'version':1,'policy':TAIL_POLICY}
        freeze['tokenizer_dir']=str(tmp_path/'synthetic-tokenizer-not-read')
    freeze['spec_sha256']=digest(spec)
    grant={'study_id':spec['study_id'],'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
        'runtime_freeze_sha256':digest(freeze),'approval_basis':'direct repository_owner approval of complete disclosed-reuse formal40 spec and runtime freeze'}
    if slot_plan is not None:
        from plugin.rhino_listener.c5_formal_reuse_scope import expected_grant
        grant=expected_grant(spec,freeze,execution_approved=True)
    # Reuse the same synthetic model policy, not a new task-text family.
    # setup_field's policy is reconstructed from its existing generated plans.
    policy={}
    for c in cases:
        if c['primary_tool']=='create_box':policy[c['task_text']]=[('create_box',{'width':2,'depth':3,'height':4})]
        if c['primary_tool']=='get_bounding_box':policy[c['task_text']]=[('get_bounding_box',{'object_id':'box-1'})]
        if c['primary_tool']=='move_object':policy[c['task_text']]=[('move_object',{'object_id':'missing','translate_x':1,'translate_y':0,'translate_z':0})]
        if c['stratum']=='multistep':policy[c['task_text']]=[(r['name'],r['arguments']) for r in c['expected_operations']]
    remote=tmp_path/'remote-v2';remote.mkdir(mode=0o700)
    wire=TimedSyntheticWire(remote,spec,freeze,policy,local=state)
    if invalid_model_index is not None:
        from training.c5_formal20_plan import slot_order
        target=slot_order(cases,seed=spec['slot_seed'])[invalid_model_index]['family_id']
        wire.invalid_task=next(c for c in cases if c['family_id']==target)['task_text']
    if slot_fault=='remote_export':
        exchange=wire.exchange
        def altered_export(sent):
            value=exchange(sent)
            if sent.get('kind')=='formal_export_step':
                receipt=next(v for n,v in value['records'].items() if n.endswith('-raw.json'))
                receipt['output_sha256']='0'*64
            return value
        wire.exchange=altered_export
    publish_json(remote,'owner-approval.json',grant)
    publish_json(remote,'worker-startup-ready.json',wire.ready)
    publish_json(state,'formal20.zero-started.claim.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    def pump():
        for cb in list(rhino.RhinoApp.Idle.handlers):cb(None,None)
    native=NativeAdapterV2(state,spec,freeze,guard=lambda:None,
        channel_factory=lambda *a,**k:NativeChannelV2(*a,**k,pump=pump,sleep=lambda _:None))
    native.arm()
    publish_json(state,'formal20.hub-admission.claim.json',{'action':'attach','study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    publish_json(state,'formal20.hub-started.claim.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    backend=Backend();backend.value['active_sha256']=ACTIVE
    from plugin.rhino_listener.c5_formal20_policy_v2 import validate_formal_binding
    binding=validate_formal_binding(*records())
    binding.update(study_id=STUDY_ID,runtime_freeze_sha256=digest(freeze))
    host=FormalHostSession(state,binding,backend,
        lambda:freeze['source_inventory_sha256'],freeze['source_inventory_sha256'])
    host.seal_baseline()
    publish_json(state,'host-continuity-ready.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'legacy_byte_closure_verified':False,'sealed_before_model_generation':True})
    publish_json(state,'entry-return-release.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'source_inventory_sha256':freeze['source_inventory_sha256'],
        'baseline_sealed':False,'replay_allowed':False})
    publish_json(state,'deferred-baseline.prepared.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'baseline_sealed':False,'model_calls':0})
    monkeypatch.setattr(hubs,'active_content_digest',lambda _:ACTIVE)
    monkeypatch.setattr(hub_base,'NativeDoc',SyntheticNativeDoc)
    monkeypatch.setattr(hub_base,'active_content_digest',lambda _:ACTIVE)
    monkeypatch.setattr(hub_base,'rhino_scene_digest',lambda f:digest(f.backend.scene))
    from training.c5_formal20_plan import _schemas
    arm=hubs.FormalArm(state,spec,freeze,_schemas(),lambda:freeze['source_inventory_sha256'],rhino.RhinoDoc.ActiveDoc,host)
    def callback(sender=None,event=None):arm.tick(sender,event)
    arm._callback=callback
    rhino.RhinoApp.Idle.handlers.append(callback)
    publish_json(state,'warmup.started.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    # Empty fixture and deferred setup are simulated metadata, explicitly not
    # evidence of installed Rhino construction. The actual arm entry is separate.
    publish_json(state,'warmup.result.json',{'study_id':spec['study_id'],'runtime_freeze_sha256':digest(freeze),
        'before_native':{'unit':'Millimeters','objects':[],'groups':{}},'close_capture':{
            'fixture_before_close_native':{'unit':'Millimeters','objects':[],'groups':{}},'fixture_registry_absent':True,
            'initial_active_sha256':ACTIVE,'before_close_active_sha256':ACTIVE,'after_close_active_sha256':ACTIVE},
        'tool_dispatches':0,'model_calls':0,'active_sha256':ACTIVE})
    publish_json(state,'worker-startup-ready.json',wire.ready)
    startup=PhaseClock(600).receipt(final_event='response-validated',role='startup',sequence=0,
        runtime_freeze_sha256=digest(freeze),request_sha256=digest(None),response_sha256=digest(wire.ready))
    publish_json(state,'startup-time.json',startup)
    publish_json(state,'formal20.zero-readiness.json',{'study_id':spec['study_id'],'runtime_freeze_sha256':digest(freeze),
        'host_ready_sha256':digest(read_json(state,'host-continuity-ready.json')),'model_ready_sha256':digest(wire.ready),
        'private_rows_read':0,'formal_started_present':False})
    # Physical transport is synthetic here; real raw subprocess capture and
    # Linux fork/pidfd are exercised by their separate actual CPU tests.
    monkeypatch.setattr(ModelAdapterV2,'_finalize',lambda self:None)
    monkeypatch.setattr(runner_module,'validate_authority',lambda *a:digest(freeze))
    monkeypatch.setattr(evidence,'audit_supervisor',lambda *a,**k:{'permit_first_load_epoch':wire.start})
    monkeypatch.setattr(evidence,'audit_completed_admission',lambda *a,**k:{'first_load_epoch':wire.start})
    publish_json(state,'load-permit.json',{'first_load_epoch':wire.start,**({'rows':[{'payload':{'remaining_indices':slot_plan['selected_indices']}}]} if slot_plan is not None else {})})
    model=ModelAdapterV2(state,spec,freeze,guard=lambda:None)
    model.pipe=wire;model.zero_ready=True;model.process=SimpleNamespace(stdin=__import__('io').BytesIO(),
        stdout=__import__('io').BytesIO(),wait=lambda **_:0)
    old_prepare=native.prepare
    def prepare(*a,**k):old_prepare(*a,**k);pump()
    native.prepare=prepare
    runner=FormalRunner(state=state,spec=spec,freeze=freeze,approval=grant,model=model,native=native,
        source_guard=lambda:None,budget_guard=lambda:None)
    if slot_plan is not None:
        from training import c5_slot_runner as slot_module
        from training.c5_slot_runner import SlotRunner
        monkeypatch.setattr(slot_module,'validate_authority',lambda *a:digest(freeze))
        class Campaign:
            def __init__(self):self.indices=[];self.rows=[]
            def observation(self):return {'slot_attempted_indices':list(self.indices)}
            def _event(self,kind,payload):
                assert kind=='slot_attempt_recorded'
                assert payload['index']==slot_plan['selected_indices'][len(self.indices)]
                self.indices.append(payload['index']);self.rows.append(payload)
        campaign=Campaign()
        runner=SlotRunner(state=state,spec=spec,freeze=freeze,approval=grant,model=model,native=native,
            source_guard=lambda:None,budget_guard=lambda:None,campaign=campaign,tokenizer=Tokenizer())
        if slot_fault in ('proof_global','proof_cancel','proof_permission'):
            def failed_slot_proof(*args):
                if slot_fault=='proof_cancel':raise KeyboardInterrupt()
                if slot_fault=='proof_permission':raise PermissionError('CPU injection')
                raise slot_module.GlobalFault('source_drift')
            runner.proof_fn=failed_slot_proof
        if slot_fault=='post_model_capture_failure':
            original_capture=native.capture;capture_calls=[0]
            def missing_capture(slot_id):
                capture_calls[0]+=1
                if capture_calls[0]==3:return {'status':'failed_no_retry','error_type':'NativeError'}
                return original_capture(slot_id)
            native.capture=missing_capture
        if slot_fault is not None:
            original_slot=runner._slot
            def changed_slot(slot,case,freeze_sha,prompts):
                if slot_fault=='global':raise slot_module.GlobalFault('permission_or_safety')
                value=original_slot(slot,case,freeze_sha,prompts)
                if slot_fault=='cleanup':
                    # CPU failure injection: known close/stop acknowledgement lost.
                    value['stop']=None
                return value
            runner._slot=changed_slot
    if fail_before_model_at is not None:
        validate=runner_module.validate_fixture_readback
        calls=[0]
        def fail_public_fixture(case,actual):
            calls[0]+=1
            if calls[0]==fail_before_model_at:
                from training.c5_formal20_plan import FormalPlanError
                raise FormalPlanError('synthetic_pre_model_failure_not_actual_fixture_rejection')
            return validate(case,actual)
        monkeypatch.setattr(runner_module,'validate_fixture_readback',fail_public_fixture)
    def load_cases():
        if slot_plan is not None:publish_json(state,'private-cases.json',cases)
        return cases
    if native_ttl_failure:
        from plugin.rhino_listener.c5_research_gate import ResearchGate
        original_execute = ResearchGate.execute
        fired = [False]
        def refuse_once(self, envelope):
            if not fired[0]:
                fired[0] = True
                self.clock = lambda: envelope['payload']['expires_at']
            return original_execute(self, envelope)
        monkeypatch.setattr(ResearchGate, 'execute', refuse_once)
    if model_infer_failure:
        def failed_infer(**kwargs): raise TimeoutError('CPU private synthetic timeout')
        model.infer = failed_infer
    if backup_failure:
        from training import c5_formal_reuse_adapters_base as native_base
        def failed_backup(*a): raise OSError('CPU synthetic disk failure')
        monkeypatch.setattr(native_base, 'database_backup', failed_backup)
    result=runner.run(load_cases)
    if slot_plan is not None:
        return state,cases,spec,freeze,read_json(state,'host-continuity-terminal-receipt.json'),result,campaign
    if fail_before_model_at is None:
        assert result['status']=='formal_execution_complete_awaiting_independent_audit',result
    else:
        assert result['status']=='formal_incomplete_no_replay' and result['slots_attempted']==fail_before_model_at,result
    publish_json(state,'resource-settlement.json',{'study_id':spec['study_id'],'status':'formal_mac_driver_finished',
        'resource_boundary_sha256':digest(freeze['resource_boundary']),'replay_allowed':False,
        'elapsed_seconds_including_load_and_idle':time.time()-wire.start,'cap_seconds':64800,'start_epoch':wire.start,'stop_epoch':time.time()})
    receipt=read_json(state,'host-continuity-terminal-receipt.json')
    if fail_before_model_at is not None:return state,cases,spec,freeze,receipt,None,None
    private=audit_run_v2(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None,external_seal_sha=receipt['seal_sha256'])
    public=public_summary(private,spec,freeze,receipt['seal_sha256'])
    assert public['paired_summary']['route_slots']==40 and not public['private_content_included']
    assert not rhino.RhinoApp.Idle.handlers and not list(state.rglob('*.key'))
    text=json.dumps(public)
    for c in cases:assert c['task_text'] not in text and c['family_id'] not in text
    return state,cases,spec,freeze,receipt,private,public

def test_new_identity_forty_slots_signatures_ledgers_timing_and_complete_join(tmp_path,monkeypatch):
    _,_,_,_,_,private,public=complete_scoped_field(tmp_path,monkeypatch)
    assert private['signature_audit']['private_audit_keys_retained']==41
    assert private['signature_audit']['signed_requests_recomputed']>40
    assert public['label']=='disclosed_same_sealed_set_reuse'
    assert public['original_c5_no_go_changed'] is False

@pytest.mark.parametrize('mutation',['signature','consent','resource','model','host'])
def test_new_full_join_rejects_altered_original_evidence(tmp_path,monkeypatch,mutation):
    state,cases,spec,freeze,receipt,_,_=complete_scoped_field(tmp_path,monkeypatch)
    if mutation=='signature':
        p=next(state.glob('F*/request-*.json'));v=json.loads(p.read_bytes());v['envelope']['signature']='0'*64
    elif mutation=='consent':
        import sqlite3
        p=state/'F01-base/consent-audit.sqlite3'
        with sqlite3.connect(p) as db:db.execute("INSERT INTO c5_model_handoff VALUES('extra','reserved',NULL,NULL)")
        manifest=state/'F01-base/database-backups.json';record=json.loads(manifest.read_bytes())
        record['consent']=hashlib.sha256(p.read_bytes()).hexdigest();manifest.write_text(json.dumps(record))
        with pytest.raises((ValueError,RuntimeError,KeyError)):audit_run_v2(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None,external_seal_sha=receipt['seal_sha256'])
        return
    elif mutation=='resource':p=state/'resource-settlement.json';v=json.loads(p.read_bytes());v['cap_seconds']=999999
    elif mutation=='model':p=next(state.glob('*-model-response.json'));v=json.loads(p.read_bytes());v['model_identity_sha256']='f'*64
    else:p=state/'host-continuity-0003.json';v=json.loads(p.read_bytes());v['elapsed_seconds']=-1
    p.write_text(json.dumps(v))
    with pytest.raises((ValueError,RuntimeError,KeyError)):audit_run_v2(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None,external_seal_sha=receipt['seal_sha256'])
