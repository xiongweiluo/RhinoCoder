"""Public CPU fixtures for incremental deployment and private admission order."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE,STUDY_ID
from training.c5_formal_reuse_deployment import stage_local,verify
from eval.test_c5_formal_reuse_preparation import make_campaign,confirm,proof

def package():
    spec={'synthetic_public_fixture':True};raw=(json.dumps(spec)+'\n').encode()
    runtime={'source_files':{SPEC_FILE:hashlib.sha256(raw).hexdigest()},'spec_sha256':digest(spec)}
    return spec,runtime,{SPEC_FILE:raw,FREEZE_FILE:json.dumps(runtime).encode()}

def test_incremental_public_update_keeps_original_changed_bytes(tmp_path):
    root=tmp_path/'public';state=tmp_path/'state';archive=tmp_path/'archive'
    spec,runtime,payload=package();stage_local(root,payload,state_root=state)
    assert verify(root,spec,runtime)['execution_authority'] is False
    original=(root/SPEC_FILE).read_bytes()
    changed={**payload,SPEC_FILE:b'{"new_public_fixture":true}\n'}
    with pytest.raises(NativeError):stage_local(root,changed,state_root=state)
    assert (root/SPEC_FILE).read_bytes()==original
    stage_local(root,changed,state_root=state,archive_root=archive)
    assert next(archive.rglob(Path(SPEC_FILE).name)).read_bytes()==original
    assert (root/SPEC_FILE).read_bytes()==changed[SPEC_FILE]

@pytest.mark.parametrize('mutation',['missing','extra','extra_directory','symlink','byte_drift'])
def test_closed_public_population_rejects_incomplete_or_foreign_deployment(tmp_path,mutation):
    root=tmp_path/'public';spec,runtime,payload=package();stage_local(root,payload,state_root=tmp_path/'state')
    if mutation=='missing':(root/SPEC_FILE).unlink()
    elif mutation=='extra':(root/'foreign').write_text('unregistered')
    elif mutation=='extra_directory':(root/'foreign').mkdir()
    elif mutation=='symlink':(root/'foreign').symlink_to(root/SPEC_FILE)
    else:(root/SPEC_FILE).write_text('{}')
    with pytest.raises(NativeError):verify(root,spec,runtime)

def test_actual_state_presence_blocks_even_identical_public_redeployment(tmp_path):
    root=tmp_path/'public';state=tmp_path/'state';_,_,payload=package()
    stage_local(root,payload,state_root=state);state.mkdir()
    with pytest.raises(NativeError):stage_local(root,payload,state_root=state)

def test_formal_runner_40_synthetic_slots_preserves_global_exposure_before_loader(tmp_path,monkeypatch):
    from eval.test_c5_formal20_preparation import cases20,authority,SyntheticModel,SyntheticNative
    import training.c5_formal_reuse_runner as module
    from training.c5_formal_reuse_admission import consume_before_private
    cases=cases20();spec,freeze,grant=authority(cases)
    spec['study_id']=freeze['study_id']=STUDY_ID
    # Only the toy-fixture authority is replaced; the real disabled package is
    # independently tested to refuse execution before any loader is invoked.
    monkeypatch.setattr(module,'validate_authority',lambda *a:digest(freeze))
    campaign,_=make_campaign(tmp_path);confirm(campaign);campaign.start();campaign.ready('a'*64)
    state=tmp_path/'preload-1';state.mkdir(mode=0o700)
    consume_before_private(campaign,1,state);campaign.begin('a'*64)
    model,native=SyntheticModel(),SyntheticNative()
    def loader():
        assert campaign.observation()['formal_consumed'] is True
        assert (state/'formal20.started.json').exists()
        return cases
    try:
        runner=module.FormalRunner(state=state,spec=spec,freeze=freeze,approval=grant,
            model=model,native=native,source_guard=lambda:None,budget_guard=lambda:None)
        result=runner.run(loader)
        assert result['slots_attempted']==40 and result['status']=='formal_execution_complete_awaiting_independent_audit'
        assert len(model.calls)==native.opened==native.closed==native.stopped==40
        assert model.starts==model.stops==native.hub_starts==1
        assert all('expected_operations' not in json.dumps(p) for p in (model.plans,native.plans))
        with pytest.raises(FileExistsError):runner.run(lambda:pytest.fail('must not reload'))
    finally:campaign.log.close()

@pytest.mark.parametrize('mutation',['none','private_exposure','private_file','signature','key','terminal','missing_capture'])
def test_raw_failure_reconciliation_requires_original_host_abort_and_no_exposure(tmp_path,monkeypatch,mutation):
    import training.c5_formal_reuse_failure_audit as module
    from eval.test_c5_host_assurance_session import authority,Backend
    from plugin.rhino_listener.c5_host_assurance_session import validate_study_binding
    from plugin.rhino_listener.c5_formal_reuse_host_session import FormalHostSession
    from plugin.rhino_listener.c5_research_gate import signature
    campaign,_=make_campaign(tmp_path);confirm(campaign);campaign.start()
    if mutation=='private_exposure':campaign.ready('a'*64);campaign.expose_private('b'*64)
    permit={'rows':campaign.log.rows(),'first_load_epoch':campaign.observation()['first_load_epoch']}
    incomplete={**proof(),'capture_complete':False}
    campaign.failed('startup',incomplete)
    state=tmp_path/'preload-1';state.mkdir(mode=0o700)
    freeze={'source_inventory_sha256':'a'*64};binding=validate_study_binding(*authority())
    binding.update(study_id=STUDY_ID,formal_capacity_verified=True,runtime_freeze_sha256=digest(freeze))
    host=FormalHostSession(state,binding,Backend(),lambda:'a'*64,'a'*64)
    host.seal_baseline();host.checkpoint('preload-abort');terminal=host.finish()
    secret=b'x'*32;custody=state/'audit-key-custody';custody.mkdir(mode=0o700)
    publish_json(custody,'hub.json',{'key_hex':secret.hex(),'runtime_sha256':digest(freeze)})
    payload={'action':'abort_uninitialized_native','runtime_freeze_sha256':digest(freeze)}
    request={'payload':payload,'signature':signature(secret,payload)}
    response={'status':'preload_aborted','runtime_freeze_sha256':digest(freeze),'request_sha256':digest(request),
        'host_terminal':terminal,'hook_removed_in_same_callback':True,'private_rows_read_by_native_arm':0,
        'unused_keys_removed':[{'slot_id':'F%02d-%s'%(n,r),'key_removed':True,'actual_absence_checked':True}
            for n in range(1,21) for r in ('base','lora')],
        'hub_key_absence':{'key_removed':True,'actual_absence_checked':True}}
    for n in range(1,21):
        for r in ('base','lora'):(state/('F%02d-%s'%(n,r))).mkdir(mode=0o700)
    if mutation=='signature':request['signature']='0'*64
    if mutation=='terminal':terminal={**terminal,'seal_sha256':'e'*64}
    if mutation=='private_file':publish_json(state,'private-cases.json',{'synthetic':True})
    if mutation=='key':publish_json(state/'F01-base','handoff.key',{'key_hex':secret.hex()})
    for name,value in [('load-permit.json',permit),('preload-abort.request.json',request),
        ('preload-abort.response.json',response),('raw-streams-final.json',{'complete_raw_capture':True})]:
        publish_json(state,name,value)
    def checked_supervisor(*args,**kwargs):
        assert kwargs=={'completed':False}
        if mutation=='missing_capture':raise NativeError('fixture incomplete original capture')
        return {'independently_checked_cpu_fixture':True}
    monkeypatch.setattr(module,'audit_supervisor',checked_supervisor)
    try:
        if mutation=='none':
            result=module.audit_preexposure_failure(state,{},freeze,campaign,terminal)
            assert campaign.reconcile('startup',result)=='RETRYABLE_ENGINEERING'
            assert campaign.observation()['first_load_epoch']==2000000000
        else:
            with pytest.raises((NativeError,ValueError)):
                module.audit_preexposure_failure(state,{},freeze,campaign,terminal)
    finally:campaign.log.close()

def test_code_commit_cannot_be_just_any_40_character_string():
    from tools.prepare_c5_formal_reuse_freeze import verify_code_commit
    assert not verify_code_commit('f'*40,{'training/c5_formal_reuse_failure_audit.py':'0'*64})


def test_native_cleanup_remains_bounded_and_available_after_generation_budget_stop(tmp_path):
    from training.c5_formal_reuse_transport import NativeChannelV2
    from plugin.rhino_listener.c5_formal_reuse_deadlines import PhaseClock
    calls=[]
    def expired():
        calls.append('generation_guard');raise NativeError('fixture generation budget exhausted')
    def cleanup():calls.append('cleanup_source_guard')
    wire=None
    def pump():
        sent=json.loads((tmp_path/'request-0001.json').read_bytes());value={'status':'closed'}
        phase=PhaseClock(120)
        proof=phase.receipt(final_event='response-written',role='native',sequence=1,
            runtime_freeze_sha256='a'*64,request_sha256=digest(sent),response_sha256=digest(value))
        publish_json(tmp_path,'response-0001.json',value);publish_json(tmp_path,'service-time-0001.json',proof)
    wire=NativeChannelV2(tmp_path,b'x'*32,'a'*64,task='Synthetic CPU task',
        guard=expired,cleanup_guard=cleanup,pump=pump)
    assert wire.control('close')=={'status':'closed'}
    assert calls==['cleanup_source_guard'] and not wire.unresolved
    other=tmp_path/'other';other.mkdir(mode=0o700)
    wire=NativeChannelV2(other,b'x'*32,'a'*64,task='Synthetic CPU task',guard=expired,cleanup_guard=cleanup)
    with pytest.raises(NativeError):wire.control('capture')
    assert not list(other.glob('request-*.json')) and wire.unresolved


def test_gpu_role_tombstones_preserve_first_clock_and_refuse_duplicate_or_replaced_campaign(tmp_path,monkeypatch):
    import training.c5_formal_reuse_admission as admission
    from training.c5_formal_reuse_supervisor import claim_gpu_role
    root=tmp_path/'c5-reuse-global-admission-v1';root.mkdir(mode=0o700)
    monkeypatch.setitem(admission.ROOTS,'gpu',root)
    monkeypatch.setattr(admission,'history_guard',lambda *a,**k:lambda:None)
    permit={'scope':{'synthetic':True},'first_load_epoch':2000000000}
    freeze={'history':{'synthetic_fixture':True}}
    claim_gpu_role(permit,freeze,1)
    with pytest.raises((NativeError,ValueError)):claim_gpu_role(permit,freeze,1)
    with pytest.raises((NativeError,ValueError)):
        claim_gpu_role({**permit,'first_load_epoch':2000000010},freeze,2)
    claim_gpu_role(permit,freeze,2)
    value=json.loads((root/admission.NAMESPACE/'campaign.json').read_bytes())
    assert value['first_load_epoch']==2000000000
    assert len(list((root/admission.NAMESPACE).glob('worker-role-*.json')))==2

@pytest.mark.parametrize('truncated',[False,True])
def test_actual_bounded_public_upload_bootstrap_on_cpu(tmp_path,monkeypatch,truncated):
    import shlex,subprocess,sys
    import tools.stage_c5_formal_reuse_source as stage
    import training.c5_formal_reuse_ssh as transport
    from tools.prepare_c5_formal_reuse_freeze import assemble,encoded
    docs=assemble();spec,runtime=docs[SPEC_FILE],docs[FREEZE_FILE]
    files={n:encoded(docs[n]) if n in docs else (stage.ROOT/n).read_bytes() for n in runtime['source_files']}
    files[FREEZE_FILE]=encoded(runtime)
    monkeypatch.setattr(stage,'payload',lambda:(spec,runtime,files))
    monkeypatch.setattr(stage,'REMOTE_SOURCE',tmp_path/'source')
    monkeypatch.setattr(stage,'REMOTE_STATE',tmp_path/'state')
    monkeypatch.setattr(transport,'verify',lambda *a:None)
    monkeypatch.setattr(transport,'argv',lambda *a:['cpu-placeholder','command'])
    actual_run=subprocess.run
    def cpu(args,**kwargs):
        argv=shlex.split(args[-1]);argv[0]=sys.executable
        if truncated:kwargs['input']=kwargs['input'][:-1]
        return actual_run(argv,**kwargs)
    monkeypatch.setattr(subprocess,'run',cpu)
    if truncated:
        with pytest.raises(subprocess.CalledProcessError):stage.stage_gpu()
        assert not (tmp_path/'source').exists()
    else:
        value=stage.stage_gpu()
        assert value['complete_public_population_bytes_verified'] is True
        assert value['files']==len(files) and value['execution_authority'] is False
        assert not (tmp_path/'state').exists()
