"""Synthetic field harness: real channels/signatures/SQLite/audit, fake Rhino/LLM.

No SSH connection, installed Rhino, GPU, private holdout or formal admission.
Temporary synthetic authority/evidence is never published as project evidence.
"""
import contextlib
import copy
import hashlib
import io
import json
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.test_c5_formal20_preparation import cases20, authority, EMPTY_ASSERTIONS
from eval.test_c5_model_transport import Tokenizer
from eval.test_c5_research_session import Event
from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import digest, NativeError
from plugin.rhino_listener import c5_formal20_hub as hub_module, c5_research_session as session_module
from training import c5_formal20_adapters as adapters
from training.c5_formal20_runtime import FormalModelSession, FormalBudget, hashed_model_plans
from training.c5_formal20_runner import FormalRunner
from training.c5_formal20_joint_audit import audit_run
from training.c5_model_transport import frame
from tools.run_c5_formal20_worker import step_evidence


ACTIVE = 'c' * 64


class SyntheticNativeDoc:
    def __init__(self, fixture, active, schemas):
        self.doc, self.active, self.schemas = fixture, active, schemas
        self.serial, self.active_serial = fixture.RuntimeSerialNumber, active.RuntimeSerialNumber
        self.initial_active_sha, self.closed = ACTIVE, False
        self.scene = {'unit': 'Millimeters', 'objects': [], 'groups': {}}
        fixture.backend = self

    def guard(self):
        if self.closed: raise NativeError('synthetic closed fixture')
    def readback(self): self.guard(); return copy.deepcopy(self.scene)
    def target(self, alias, **kwargs):
        rows = [r for r in self.scene['objects'] if r['alias'] == alias]
        if not rows: raise NativeError('synthetic unknown alias')
        return rows[0]
    def update(self, row):
        row['centroid'] = [(a+b)/2 for a,b in zip(row['min'],row['max'])]
        row['geometry_sha256'] = digest({'min':row['min'], 'max':row['max']})
        row['vertices'] = sorted([[x,y,z] for x in (row['min'][0],row['max'][0])
            for y in (row['min'][1],row['max'][1]) for z in (row['min'][2],row['max'][2])])
    def dispatch(self, name, args):
        if name == 'create_box':
            row = {'alias':'box-1','min':[0,0,0],'max':[args['width'],args['depth'],args['height']],
                'volume':args['width']*args['depth']*args['height'], 'solid':True,'face_count':6,'edge_count':12,
                'layer':'Default','color':[0,0,0],'groups':[]}
            self.update(row); self.scene['objects'].append(row); return {'created_alias':'box-1'}
        if name == 'get_scene_summary':
            from training.c5_modelbridge_joint_audit import semantic
            return semantic(self.readback())
        if name == 'get_bounding_box':
            r=self.target(args['object_id']); return {'object_id':args['object_id'],'min':r['min'],'max':r['max'],'center':r['centroid']}
        row=self.target(args['object_id'])
        if name == 'move_object':
            vector=[args['translate_x'],args['translate_y'],args['translate_z']]
            row['min']=[a+b for a,b in zip(row['min'],vector)];row['max']=[a+b for a,b in zip(row['max'],vector)]
        elif name == 'scale_object':
            center=row['centroid'];factor=args['scale_factor']
            row['min']=[c+(a-c)*f for a,c,f in zip(row['min'],center,factor)]
            row['max']=[c+(a-c)*f for a,c,f in zip(row['max'],center,factor)]
            row['volume']*=math.prod(factor)
        else: raise AssertionError('synthetic harness does not claim unimplemented Rhino geometry')
        self.update(row); return {'changed_alias':args['object_id']}
    def close(self):
        final=self.readback();self.closed=True
        return {'fixture_serial':self.serial,'initial_active_sha256':ACTIVE,'before_close_active_sha256':ACTIVE,
            'after_close_active_sha256':ACTIVE,'before_close_active_serial':self.active_serial,
            'after_close_active_serial':self.active_serial,'fixture_registry_absent':True,
            'fixture_before_close_native':final,'capture_scope':'same_ui_callback_before_and_after_fixture_close'}


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
                'elapsed_seconds_including_load_and_idle':time.time()-self.start,'cap_seconds':10800,
                'start_epoch':self.start,'stop_epoch':time.time(),
                'resource_boundary_sha256':digest(self.freeze['resource_boundary']),'replay_allowed':False}
            publish_json(self.state,'resource-settlement.json',settlement)
            names=['bootstrap.json','loaded-runtime.json','worker-summary.json','resource-settlement.json','formal20.worker-started.claim.json']
            assets={'source_files':self.freeze['source_files'],'source_inventory_sha256':self.freeze['source_inventory_sha256'],
                'fixed_public_files':self.freeze['fixed_public_files'],'environment_sha256':self.freeze['environment_sha256'],
                'environment':{'synthetic':True},'snapshot':{'synthetic':True},'adapter_sha256':self.freeze['model_identities']['lora'],
                'adapter_files':{'synthetic-adapter':'1'*64}}
            return {'status':'formal_worker_stopped','request_sha256':digest(sent),'runtime_freeze_sha256':digest(self.freeze),
                'raw_records':{n:read_json(self.state,n) for n in names},'resource':settlement,'asset_environment_preflight':assets,
                'file_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.state.glob('*.json')}}
        self.current=sent;key=digest({'slot':sent['slot_id'],'step':sent['step_index'],'freeze':digest(self.freeze)})
        publish_json(self.state,key+'-request.json',sent);self.keys.append(key)
        return self.session.infer(sent)


def assertions(lo,hi,volume):
    return {'object_count':1,'objects':{'box-1':{'min':lo,'max':hi,'volume':volume,'solid':True,'face_count':6}},
        'unchanged':[],'read_result':None}


def setup_field(tmp_path,monkeypatch):
    state=tmp_path/'mac';state.mkdir(mode=0o700)
    remote=tmp_path/'worker';remote.mkdir(mode=0o700)
    cases=cases20();policy={}
    for case in cases:
        if case['primary_tool']=='create_box':
            case['final_assertions']=assertions([0,0,0],[2,3,4],24)
            policy[case['task_text']]=[('create_box',{'width':2,'depth':3,'height':4})]
        if case['primary_tool']=='get_bounding_box':
            case['fixture_recipe']=[{'operation':'create_box','arguments':{'width':2,'depth':3,'height':4}}]
            case['initial_assertions']=assertions([0,0,0],[2,3,4],24)
            expected={'object_id':'box-1','min':[0,0,0],'max':[2,3,4],'center':[1,1.5,2]}
            case['expected_operations'][0]['read_result']=expected
            case['final_assertions']={**case['initial_assertions'],'read_result':expected}
            policy[case['task_text']]=[('get_bounding_box',{'object_id':'box-1'})]
        if case['primary_tool']=='move_object':
            policy[case['task_text']]=[('move_object',{'object_id':'missing','translate_x':1,'translate_y':0,'translate_z':0})]
    for index in (12,13):
        case=cases[index]
        ops=[('create_box',{'width':2,'depth':3,'height':4}),('move_object',{'object_id':'box-1','translate_x':1,'translate_y':2,'translate_z':3})]
        if index==13:ops.append(('scale_object',{'object_id':'box-1','scale_factor':[2,2,2]}))
        case['expected_operations']=[{'name':name,'arguments':args,'read_result':None} for name,args in ops]
        case['max_steps']=case['max_writes']=len(ops)
        case['final_assertions']=assertions([1,2,3],[3,5,7],24) if index==12 else assertions([0,0.5,1],[4,6.5,9],192)
        policy[case['task_text']]=ops
    spec,freeze,approval=authority(cases)
    spec['hub_attach_timeout_seconds']=5;spec['per_request_timeout_seconds']=5
    freeze={'study_id':spec['study_id'],'execution_ready':True,'spec_sha256':digest(spec),
        'source_files':{'synthetic.py':'a'*64},'source_inventory_sha256':digest({'synthetic.py':'a'*64}),
        'fixed_public_files':{},'model_identities':{'base':digest({'synthetic':True}),'lora':digest({'synthetic-adapter':'1'*64})},
        'environment_sha256':digest({'synthetic':True}),'rhino_version':'synthetic',
        'resource_boundary':{'owner_confirmed':True,'provider_expiry_epoch':9999999999,'generation_cutoff_epoch':9999990000,
            'export_reserve_seconds':900,'formal_max_seconds':10800,'prior_cumulative_seconds':0,
            'original_cumulative_max_seconds':57600,'prior_research_seconds':0,'research_cumulative_max_seconds':14400}}
    approval['spec_sha256']=digest(spec);approval['runtime_freeze_sha256']=digest(freeze)
    active=SimpleNamespace(RuntimeSerialNumber=1);counter=[1]
    def create(_):counter[0]+=1;return SimpleNamespace(RuntimeSerialNumber=counter[0])
    rhino=SimpleNamespace(RhinoApp=SimpleNamespace(IsOnMainThread=True,Idle=Event(),Version='synthetic'),
        RhinoDoc=SimpleNamespace(ActiveDoc=active,CreateHeadless=create),UnitSystem=SimpleNamespace(Millimeters='Millimeters'))
    monkeypatch.setitem(sys.modules,'Rhino',rhino)
    monkeypatch.setattr(hub_module,'NativeDoc',SyntheticNativeDoc)
    monkeypatch.setattr(hub_module,'active_content_digest',lambda _:ACTIVE)
    monkeypatch.setattr(session_module,'active_content_digest',lambda _:ACTIVE)
    monkeypatch.setattr(hub_module,'rhino_scene_digest',lambda f:digest(f.backend.scene))
    monkeypatch.setattr(adapters.time,'sleep',lambda _:None)
    def pump():
        for callback in list(rhino.RhinoApp.Idle.handlers):callback()
    def attach():
        publish_json(state,'formal20.hub-admission.claim.json',{'action':'attach','study_id':spec['study_id'],
            'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
        publish_json(state,'formal20.hub-started.claim.json',{'study_id':spec['study_id'],
            'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
        from training.c5_formal20_plan import _schemas
        hub=hub_module.FormalHub(state,spec,freeze,read_json(state,'native-plans.json'),_schemas(),
            lambda:freeze['source_inventory_sha256'],active)
        hub.attach()
    native=adapters.NativeAdapter(state,spec,freeze,guard=lambda:None,attach_wait=attach,
        channel_factory=lambda *args,**kwargs:adapters.NativeChannel(*args,**kwargs,pump=pump))
    wire=SyntheticWire(remote,spec,freeze,policy)
    sock=SimpleNamespace(is_socket=lambda:True,close=lambda:None)
    monkeypatch.setattr(adapters,'SSH_SOCKET',sock)
    pin = tmp_path / 'synthetic-known-hosts'
    pin.write_text('synthetic public host pin\n')
    monkeypatch.setattr(adapters,'SSH_KNOWN_HOSTS',pin)
    monkeypatch.setattr(adapters,'SSH_KNOWN_HOSTS_SHA',adapters.file_sha(pin))
    fakeprocess=SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO(),wait=lambda **_:0)
    model=adapters.ModelAdapter(state,spec,freeze,guard=lambda:None,
        process_factory=lambda *args,**kwargs:fakeprocess,pipe_factory=lambda *args,**kwargs:wire)
    runner=FormalRunner(state=state,spec=spec,freeze=freeze,approval=approval,model=model,native=native,
        source_guard=lambda:None,budget_guard=lambda:None)
    return state,cases,spec,freeze,runner,rhino,sock


def test_forty_synthetic_routes_use_real_signer_ledgers_and_independent_audit(tmp_path,monkeypatch):
    state,cases,spec,freeze,runner,rhino,sock=setup_field(tmp_path,monkeypatch)
    monkeypatch.setattr(adapters.secrets,'token_urlsafe',lambda _: '_synthetic_identifier_' + str(time.time_ns()))
    try:
        budget=FormalBudget(freeze['resource_boundary'])
        result=runner.run(lambda:cases)
        budget.settle(state,'formal_mac_driver_finished')
        assert result['status']=='formal_execution_complete_awaiting_independent_audit',result
        assert result['slots_attempted']==40 and not rhino.RhinoApp.Idle.handlers
        value=audit_run(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None)
        assert value['status']=='independent_formal_raw_audit_complete'
        assert value['paired_summary']['route_slots']==40 and not value['paired_summary']['c5_6_formal_gate_passed']
        assert value['paired_summary']['safety_totals']=={'critical_safety_errors':0,'duplicate_writes':0,'unverified_cleanup':0}
        assert any(read_json(state,p.name)['steps'][-1].get('execution_rejection') for p in state.glob('F*.result.json'))
        longest=max(len(list((state/s).glob('request-*.json'))) for s in [p.name for p in state.iterdir() if p.is_dir()])
        assert 64 < longest <= 128  # Three writes would exceed B's old 64-message policy.
    finally:sock.close()


@pytest.mark.parametrize('tamper',['raw_model','extra_dispatch','cleanup_key','remote_inventory','extra_permission',
    'prepared_plan','extra_step_claim','resource_overrun'])
def test_independent_audit_rejects_raw_evidence_tampering(tmp_path,monkeypatch,tamper):
    state,cases,spec,freeze,runner,rhino,sock=setup_field(tmp_path,monkeypatch)
    try:
        budget=FormalBudget(freeze['resource_boundary'])
        assert runner.run(lambda:cases)['error_type'] is None
        budget.settle(state,'formal_mac_driver_finished')
        if tamper=='raw_model':
            path=next(state.glob('*-model-response.json'));value=json.loads(path.read_text());value['observation']['calls'][0]['raw']='{}'
            path.write_text(json.dumps(value))
        elif tamper=='extra_dispatch':publish_json(state/'F01-base','execute-0128.json',{'status':'done'})
        elif tamper=='cleanup_key':publish_json(state/'F01-base','handoff.key',{'key_hex':'0'*64})
        elif tamper=='remote_inventory':
            path=state/'worker-stop-response.json';value=json.loads(path.read_text());value['file_sha256'].pop(next(iter(value['file_sha256'])))
            path.write_text(json.dumps(value))
        elif tamper=='extra_permission':
            import sqlite3
            path=state/'F01-base'/'consent-audit.sqlite3'
            with sqlite3.connect(path) as db:db.execute("INSERT INTO c5_model_handoff VALUES('extra','reserved',NULL,NULL)")
            manifest=state/'F01-base'/'database-backups.json';value=json.loads(manifest.read_text())
            value['consent']=hashlib.sha256(path.read_bytes()).hexdigest();manifest.write_text(json.dumps(value))
        elif tamper=='prepared_plan':
            path=state/'native-plans.json';value=json.loads(path.read_text());value['plans']['F01-base']['max_writes']=0
            path.write_text(json.dumps(value))
        elif tamper=='extra_step_claim':publish_json(state,'F01-base-step-99.claim.json',{'synthetic':True})
        else:
            path=state/'resource-settlement.json';value=json.loads(path.read_text());value['elapsed_seconds_including_load_and_idle']=10801
            path.write_text(json.dumps(value))
        with pytest.raises((NativeError,ValueError,KeyError)):
            audit_run(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None)
    finally:sock.close()


def test_partial_key_preparation_abort_prevents_late_attach(tmp_path):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    freeze={'synthetic':True}
    adapter=adapters.NativeAdapter(state,{},freeze,guard=lambda:None)
    publish_json(state,'hub.key',{'key_hex':'0'*64});adapter.keys=[(state,'hub.key')]
    assert adapter.finish()['status']=='hub_not_attached_cleaned'
    with pytest.raises(FileExistsError):
        publish_json(state,'formal20.hub-admission.claim.json',{'action':'attach'})
    assert not (state/'hub.key').exists()


def test_attach_claim_prevents_timeout_cleanup_from_deleting_live_key(tmp_path):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    adapter=adapters.NativeAdapter(state,{}, {'synthetic':True},guard=lambda:None)
    publish_json(state,'hub.key',{'key_hex':'0'*64});adapter.keys=[(state,'hub.key')]
    publish_json(state,'formal20.hub-admission.claim.json',{'action':'attach'})
    with pytest.raises(FileExistsError):adapter.finish()
    assert (state/'hub.key').exists()


def test_resource_cap_accounts_for_prior_runs_and_clock_jump():
    boundary={'owner_confirmed':True,'provider_expiry_epoch':50000,'generation_cutoff_epoch':49000,'export_reserve_seconds':900,
        'formal_max_seconds':10800,'prior_cumulative_seconds':57500,'original_cumulative_max_seconds':57600,
        'prior_research_seconds':0,'research_cumulative_max_seconds':14400}
    wall=[1000];mono=[0]
    budget=FormalBudget(boundary,wall=lambda:wall[0],mono=lambda:mono[0]);assert budget.cap==100
    wall[0]=49000
    with pytest.raises(NativeError):budget.check()


def test_field_entry_import_and_public_preflight_open_no_private_package(monkeypatch):
    from tools.c5_formal20_owner_run import sealed_loader
    def no_spawn(*args,**kwargs):pytest.fail('private loader must remain lazy')
    monkeypatch.setattr('tools.c5_formal20_owner_run.subprocess.run',no_spawn)
    loader=sealed_loader(Path('/private/synthetic.age'),Path('/private/synthetic.key'),{}, {})
    assert callable(loader)


def test_formal_scene_privacy_does_not_relax_product_or_old_probe_policy():
    from training.c5_formal20_privacy import allowed
    from training.c5_rhino_adapter import step_input
    from agent.privacy import classify_request, PrivacyAction
    scene={'unit':'Millimeters','groups':{},'objects':[{'alias':'box-1','min':[0,0,0],
        'max':[2,3,4],'layer':'Default','color':[0,0,0],'groups':[]}]}
    assert allowed('Move the synthetic box',scene)
    assert classify_request(step_input('Move the synthetic box',scene)).action is PrivacyAction.FORCE_LOCAL
    scene['objects'][0]['layer']='customer-secret-project'
    assert not allowed('Move the synthetic box',scene)
    scene['objects'][0]['layer']='C5-public-fixture'
    assert allowed('Move the synthetic box',scene)
    assert not allowed('password=abcdefghijk',scene)


def test_unknown_native_ack_never_resends_or_deletes_live_key(tmp_path):
    clock=[0]
    def now(): clock[0]+=10; return clock[0]
    channel=adapters.NativeChannel(tmp_path,b'x'*32,'a'*64,'synthetic',clock=now)
    with pytest.raises(NativeError): channel.control('capture')
    assert channel.unresolved and len(list(tmp_path.glob('request-*.json')))==1
    with pytest.raises(NativeError): channel.control('close')
    assert len(list(tmp_path.glob('request-*.json')))==1


def test_unknown_remote_ack_closes_pipe_without_reconnect_or_export_retry(tmp_path):
    freeze={'synthetic':True}
    model=adapters.ModelAdapter(tmp_path,{},freeze,guard=lambda:None)
    class UnknownPipe:
        blocked=True
        def exchange(self,_):pytest.fail('unknown acknowledgement must not be retried')
    model.pipe=UnknownPipe()
    model.process=SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO(),wait=lambda **_:0)
    with pytest.raises(NativeError):model.stop()
    assert read_json(tmp_path,'worker-process-exit.json')['exit_code']==0
    assert not (tmp_path/'worker-stop-response.json').exists()


def test_embedded_freeze_rejects_non_file_dynamic_clr_code(tmp_path,monkeypatch):
    from plugin.rhino_listener.c5_formal20_environment import loaded_external_files, verify_project_origins
    synthetic=tmp_path/'unfrozen.py';synthetic.write_text('# synthetic module only\n')
    monkeypatch.setitem(sys.modules,'arbitrary_private_alias',SimpleNamespace(__file__=str(synthetic)))
    with pytest.raises(NativeError):verify_project_origins(tmp_path,{})
    verify_project_origins(tmp_path,{'unfrozen.py':hashlib.sha256(synthetic.read_bytes()).hexdigest()})
    assembly=SimpleNamespace(IsDynamic=True,Location='')
    monkeypatch.setitem(sys.modules,'System',SimpleNamespace(AppDomain=SimpleNamespace(
        CurrentDomain=SimpleNamespace(GetAssemblies=lambda:[assembly]))))
    with pytest.raises(NativeError):loaded_external_files(tmp_path)


def test_nonpublic_model_label_is_rejected_before_permission():
    from training.c5_formal20_prepermission import rejection
    from training.c5_formal20_plan import _schemas
    value=rejection('set_object_layer',{'object_id':'box-1','layer_name':'customer-project'},
        {'objects':[{'alias':'box-1'}]},_schemas())
    assert value['reason']=='nonpublic_research_label' and value['permission_reserved'] is False
