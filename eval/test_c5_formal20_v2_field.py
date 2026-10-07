"""40-route v2 CPU harness: real signers/ledgers/timing, fake Rhino/model.

All task text is the pre-existing checked-in synthetic fixture. No new private
questions, model assets, SSH, installed Rhino or actual admission is touched.
"""
import copy
import json
import time
from types import SimpleNamespace
import pytest

from eval.test_c5_formal20_field_adapters import setup_field,SyntheticWire,ACTIVE
from eval.test_c5_formal20_v2 import records
from eval.test_c5_host_assurance_session import Backend
from eval.test_c5_model_transport import Tokenizer
from plugin.rhino_listener.c5_research_native import digest
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_formal20_host_session_v2 import FormalHostSession
from plugin.rhino_listener import c5_formal20_hub_v2 as hubs
from plugin.rhino_listener.c5_lifecycle_deadlines import PhaseClock
from training.c5_formal20_adapters_v2 import NativeAdapterV2,ModelAdapterV2
from training.c5_formal20_transport_v2 import NativeChannelV2
from training.c5_formal20_runner import FormalRunner
from training.c5_formal20_joint_audit_v2 import audit_run_v2,public_summary
from training.c5_startup_transport import startup_receipt
from training.c5_model_transport import frame
from training.c5_modelbridge_runtime import file_sha


class TimedSyntheticWire(SyntheticWire):
    def __init__(self,*args,local,**kwargs):
        super().__init__(*args,**kwargs);self.local=local
        self.ready=startup_receipt(self.spec['study_id'],digest(self.freeze),self.freeze['source_inventory_sha256'],
            self.freeze['environment_sha256'],self.freeze['model_identities'])
        self.model_seq=self.control_seq=0
    def exchange(self,sent):
        phase=PhaseClock(180)
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


def complete_v2_field(tmp_path,monkeypatch):
    state,cases,spec,freeze,_,rhino,_=setup_field(tmp_path,monkeypatch)
    # Real signature/SQLite/timing code below; ONLY geometry/model are fake.
    new_spec,new_freeze,_=records()
    spec.update(new_spec)
    freeze.update({k:v for k,v in new_freeze.items() if k not in ('spec_sha256',)})
    spec['max_generation_stages']=112
    freeze['resource_boundary'].update(formal_max_seconds=18000,research_cumulative_max_seconds=21600)
    freeze['spec_sha256']=digest(spec)
    grant={'study_id':spec['study_id'],'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
        'runtime_freeze_sha256':digest(freeze),'approval_basis':'direct repository_owner approval of complete C5-6 formal20 spec and runtime freeze'}
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
    publish_json(remote,'owner-approval.json',grant)
    publish_json(remote,'worker-startup-ready.json',wire.ready)
    publish_json(state,'formal20.zero-started.claim.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    publish_json(state,'formal20.hub-admission.claim.json',{'action':'attach','study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    publish_json(state,'formal20.hub-started.claim.json',{'study_id':spec['study_id'],
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    backend=Backend();backend.value['active_sha256']=ACTIVE
    from plugin.rhino_listener.c5_formal20_policy_v2 import validate_formal_binding
    host=FormalHostSession(state,validate_formal_binding(spec,freeze,grant),backend,
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
    from training.c5_formal20_plan import _schemas
    arm=hubs.FormalArm(state,spec,freeze,_schemas(),lambda:freeze['source_inventory_sha256'],rhino.RhinoDoc.ActiveDoc,host)
    def callback(sender=None,event=None):arm.tick(sender,event)
    arm._callback=callback
    rhino.RhinoApp.Idle.handlers.append(callback)
    def pump():
        for cb in list(rhino.RhinoApp.Idle.handlers):cb(None,None)
    native=NativeAdapterV2(state,spec,freeze,guard=lambda:None,
        channel_factory=lambda *a,**k:NativeChannelV2(*a,**k,pump=pump,sleep=lambda _:None))
    native.arm()
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
    startup=PhaseClock(180).receipt(final_event='response-validated',role='startup',sequence=0,
        runtime_freeze_sha256=digest(freeze),request_sha256=digest(None),response_sha256=digest(wire.ready))
    publish_json(state,'startup-time.json',startup)
    publish_json(state,'formal20.zero-readiness.json',{'study_id':spec['study_id'],'runtime_freeze_sha256':digest(freeze),
        'host_ready_sha256':digest(read_json(state,'host-continuity-ready.json')),'model_ready_sha256':digest(wire.ready),
        'private_rows_read':0,'formal_started_present':False})
    model=ModelAdapterV2(state,spec,freeze,guard=lambda:None)
    model.pipe=wire;model.zero_ready=True;model.process=SimpleNamespace(stdin=__import__('io').BytesIO(),
        stdout=__import__('io').BytesIO(),wait=lambda **_:0)
    old_prepare=native.prepare
    def prepare(*a,**k):old_prepare(*a,**k);pump()
    native.prepare=prepare
    runner=FormalRunner(state=state,spec=spec,freeze=freeze,approval=grant,model=model,native=native,
        source_guard=lambda:None,budget_guard=lambda:None)
    result=runner.run(lambda:cases)
    assert result['status']=='formal_execution_complete_awaiting_independent_audit',result
    publish_json(state,'resource-settlement.json',{'study_id':spec['study_id'],'status':'formal_mac_driver_finished',
        'resource_boundary_sha256':digest(freeze['resource_boundary']),'replay_allowed':False,
        'elapsed_seconds_including_load_and_idle':1.0,'cap_seconds':18000,'start_epoch':time.time()-1,'stop_epoch':time.time()})
    receipt=read_json(state,'host-continuity-terminal-receipt.json')
    private=audit_run_v2(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None,external_seal_sha=receipt['seal_sha256'])
    public=public_summary(private,spec,freeze,receipt['seal_sha256'])
    assert public['paired_summary']['route_slots']==40 and not public['private_content_included']
    assert not rhino.RhinoApp.Idle.handlers and not list(state.rglob('*.key'))
    text=json.dumps(public)
    for c in cases:assert c['task_text'] not in text and c['family_id'] not in text
    return state,cases,spec,freeze,receipt,private,public


def test_complete_v2_forty_routes_joint_audit_and_public_redaction(tmp_path,monkeypatch):
    complete_v2_field(tmp_path,monkeypatch)


@pytest.mark.parametrize('tamper',['missing_service','late_service','missing_settle','changed_model',
    'changed_control','changed_host','missing_peer_ready','changed_raw_grant','reappeared_key',
    'private_rows_before_ready','missing_initialization','extra_model_timing','extra_control_response'])
def test_v2_independent_audit_rejects_raw_tamper(tmp_path,monkeypatch,tamper):
    state,cases,spec,freeze,receipt,_,_=complete_v2_field(tmp_path,monkeypatch)
    def change(path,fn):
        value=json.loads(path.read_bytes());fn(value);path.write_text(json.dumps(value))
    if tamper=='missing_service':next(state.glob('*/service-time-*.json')).unlink()
    elif tamper=='late_service':
        change(next(state.glob('*/service-time-*.json')),lambda v:v.update(elapsed_seconds=120.0))
    elif tamper=='missing_settle':next(state.glob('*/settle-time-*.json')).unlink()
    elif tamper=='changed_model':
        change(next(state.glob('*-model-response.json')),lambda v:v.update(model_identity_sha256='f'*64))
    elif tamper=='changed_control':
        change(state/'control-0001-request.json',lambda v:v.update(study_id='changed'))
    elif tamper=='changed_host':
        change(state/'host-continuity-0003.json',lambda v:v.update(elapsed_seconds=-1))
    elif tamper=='missing_peer_ready':
        change(state/'worker-stop-response.json',lambda v:v['raw_records'].pop('worker-startup-ready.json'))
    elif tamper=='changed_raw_grant':
        change(state/'worker-stop-response.json',lambda v:v['raw_records']['owner-approval.json'].update(approved=False))
    elif tamper=='reappeared_key':
        directory=next(p for p in state.iterdir() if p.is_dir() and p.name.startswith('F'))
        publish_json(directory,'handoff.key',{'key_hex':'1'*64})
    elif tamper=='private_rows_before_ready':
        change(state/'formal20.zero-readiness.json',lambda v:v.update(private_rows_read=1))
    elif tamper=='missing_initialization':(state/'formal20.hub-initialization.claim.json').unlink()
    elif tamper=='extra_model_timing':publish_json(state,'extra-model-time.json',{})
    else:publish_json(state,'control-0999-response.json',{})
    with pytest.raises((ValueError,RuntimeError,KeyError,FileNotFoundError)):
        audit_run_v2(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None,external_seal_sha=receipt['seal_sha256'])
