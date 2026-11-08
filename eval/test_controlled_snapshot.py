"""CPU-only contracts and actual adapters over an explicit fake Rhino module."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

from plugin.rhino_listener import candidate_atomic_gate as ag
from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener.lora_development_host import RhinoSession


def gate(tmp_path, scene, **kwargs):
    return ag.RhinoAtomicGate(tmp_path/'ledger.sqlite3', 'new-private-doc', lambda:digest(scene),
                             create_ledger=True, state_contract=ag.CONTROLLED_SNAPSHOT, **kwargs)


def test_noop_and_controlled_aba_advance_durably_before_dispatch(tmp_path):
    scene, calls = {'x':0}, []
    atomic = gate(tmp_path, scene); before = atomic.snapshot()
    def dispatch(op, args):
        with sqlite3.connect(atomic.path) as db:
            assert db.execute('SELECT state FROM candidate_write WHERE idempotency_key=?',(args['key'],)).fetchone() == ('reserved',)
            assert db.execute('SELECT revision FROM candidate_scene').fetchone()[0] > args['prior']
        scene['x'] = args['x']; calls.append(op); return {'done':True}
    for index,x in enumerate((0,1,0)):
        prior=atomic.snapshot(); key='controlled_write_key_%05d'%index
        atomic.execute(key, prior, 'write', {'x':x,'key':key,'prior':prior['revision']}, dispatch)
        assert atomic.snapshot()['revision'] > prior['revision']
    after=atomic.snapshot()
    assert before['scene_sha256'] == after['scene_sha256'] and len(calls)==3
    with pytest.raises(ag.AtomicGateError,match='scene_changed'):
        atomic.execute('stale_authorization_000001',before,'write',{},lambda *_:pytest.fail('stale dispatch'))
    with pytest.raises(ag.AtomicGateError,match='already_reserved'):
        atomic.execute('controlled_write_key_00000',before,'write',{'x':0,'key':'controlled_write_key_00000','prior':0},dispatch)


def test_uncertain_dispatch_keeps_reservation_and_revision(tmp_path):
    atomic=gate(tmp_path,{}); before=atomic.snapshot()
    def fail(*_): raise TimeoutError('unknown native effect')
    key='uncertain_write_key_000001'
    with pytest.raises(TimeoutError): atomic.execute(key,before,'write',{},fail)
    assert atomic.inspect(key)['state']=='uncertain' and atomic.snapshot()['revision']>before['revision']
    with pytest.raises(ag.AtomicGateError,match='already_reserved'):
        atomic.execute(key,before,'write',{},lambda *_:pytest.fail('replayed'))


def test_external_aba_is_explicitly_unobservable_but_current_drift_rejected(tmp_path):
    scene={'x':0}; atomic=gate(tmp_path,scene); before=atomic.snapshot()
    scene['x']=1; scene['x']=0  # no controller call or intermediate observation
    assert atomic.snapshot()==before  # declared limitation, never a claimed pass of external ABA detection
    scene['x']=1
    with pytest.raises(ag.AtomicGateError,match='scene_changed'):
        atomic.execute('visible_drift_key_0000001',before,'write',{},lambda *_:pytest.fail('stale dispatch'))


def fake_rhino(monkeypatch):
    registry={}
    class Encoded:
        def __init__(self,value): self.value=value
        def ToJSON(self,options): return json.dumps(self.value)
    class Doc:
        IsHeadless=True; Path=''; ModelUnitSystem='Millimeters'
        ModelAbsoluteTolerance=1e-6; ModelAngleToleranceRadians=.01; NextUndoRecordSerialNumber=7
        def __init__(self):
            self.RuntimeSerialNumber=17; self.Objects=self; self.items={}; self.Layers=[]; self.next=0
            registry[17]=self
        def GetObjectList(self,settings): return list(self.items.values())
        def AddPoint(self,point):
            self.next+=1; key='point-'+str(self.next)
            self.items[key]=NS(Id=key,Geometry=Encoded(list(point)),Attributes=Encoded({'color':0}),RuntimeSerialNumber=self.next)
            return key
        def Delete(self,key,quiet): del self.items[key]; return True
        def Dispose(self): del registry[17]
    class ForbiddenSerial:
        @property
        def NextRuntimeSerialNumber(self): raise AssertionError('process-global counter read')
    rhino=NS(RhinoApp=NS(IsOnMainThread=True), UnitSystem=NS(Millimeters='Millimeters'),
        RhinoDoc=NS(CreateHeadless=lambda _:Doc(),FromRuntimeSerialNumber=registry.get),
        Geometry=NS(Point3d=lambda *xyz:xyz), FileIO=NS(SerializationOptions=lambda:NS()),
        DocObjects=NS(ObjectEnumeratorSettings=lambda:NS(),RhinoObject=ForbiddenSerial()))
    monkeypatch.setitem(sys.modules,'Rhino',rhino)
    return rhino,registry


def test_real_fingerprint_omits_global_counter_keeps_content_instance_and_settings(monkeypatch):
    rhino,_=fake_rhino(monkeypatch); doc=rhino.RhinoDoc.CreateHeadless(None); key=doc.AddPoint((0,0,0))
    original=ag.rhino_scene_fingerprint(doc,controlled_snapshot=True)
    assert original['components']['state_contract']=={'schema':ag.CONTROLLED_SNAPSHOT,'external_aba_detection':False}
    assert 'process_next_object_serial' not in original['components']
    for field in ('Geometry','Attributes','RuntimeSerialNumber'):
        obj=doc.items[key]; prior=getattr(obj,field)
        setattr(obj,field,99 if field=='RuntimeSerialNumber' else NS(ToJSON=lambda _: 'changed'))
        assert ag.rhino_scene_fingerprint(doc,controlled_snapshot=True)['scene_sha256'] != original['scene_sha256']
        setattr(obj,field,prior)
    doc.ModelAbsoluteTolerance=2e-6
    assert ag.rhino_scene_fingerprint(doc,controlled_snapshot=True)['scene_sha256'] != original['scene_sha256']


def test_actual_session_options_fixed_guard_then_task_ledger_and_close(tmp_path,monkeypatch):
    from tools.build_lora_common_probe import build
    from training.lora_common_probe_runner import prepare
    from plugin.rhino_listener import lora_development_native
    rhino,registry=fake_rhino(monkeypatch)
    class Backend:
        def __init__(self,doc,schemas): self.doc=doc; self.serial=doc.RuntimeSerialNumber; self.closed=False
        def guard(self): assert not self.closed
        def close(self):
            self.doc.Dispose(); self.closed=True
            return {'status':'closed','fixture_registry_absent':True}
    monkeypatch.setattr(lora_development_native,'DevelopmentDoc',Backend)
    package=build(Path(__file__).resolve().parents[1],tmp_path/'bundle',controlled_snapshot_probe=True)
    ready=prepare(Path(package['source_root']),package)
    assert ready['session_options']['state_contract']==ag.CONTROLLED_SNAPSHOT
    d=tmp_path/'synthetic';d.mkdir(mode=0o700)
    plan={'fixture_recipe':[],'task_sha256':'a'*64,'max_reads':1,'max_writes':1}
    session=RhinoSession(plan,'b'*64,b'x'*32,directory=d,schemas={},guard=lambda:None,**ready['session_options'])
    session.open()
    proof=json.loads((d/'snapshot-check.json').read_text())
    assert proof['controlled_aba_rejected'] and proof['fixed_native_operations']==2 and not proof['external_aba_detection']
    assert session.document_clock is None and session.gate.atomic.state_contract==ag.CONTROLLED_SNAPSHOT
    with sqlite3.connect(d/'snapshot-protection.sqlite3') as db:
        assert db.execute('SELECT state FROM candidate_write').fetchall()==[('done',),('done',)]
    with sqlite3.connect(d/'fixture.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM candidate_write').fetchone()==(0,)
    session.close(); assert not registry and session.finish()['status']=='stopped'
    assert not Path(package['state_root']).exists()
    import importlib.util
    from training.c5_research_audit import _tables
    path=Path(__file__).parent/'lora-development/common-probe-audit-procedure-20261027.py'
    spec=importlib.util.spec_from_file_location('snapshot_audit_cpu',path)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    fixed=_tables(d/'snapshot-protection.sqlite3',('candidate_write','candidate_scene'))
    read=lambda p:json.loads(p.read_text())
    checked=audit.review_controlled_snapshot(d,read,[],[],package['capacity'],fixed)
    assert checked['controlled_aba_and_fixed_ledger_verified'] and not checked['external_aba_detection']
    hashes,count=audit.review_controlled_fingerprints(d,read,[],[],package['capacity'])
    assert count==checked['fingerprint_records'] and proof['states'][0]['scene_sha256'] in hashes
    with pytest.raises(AssertionError):
        audit.review_controlled_fingerprints(d,read,[{'state':{'scene_sha256':'f'*64}}],[],package['capacity'])
    broken=copy.deepcopy(fixed);broken['candidate_write'][1]['state']='uncertain'
    with pytest.raises(AssertionError):audit.review_controlled_snapshot(d,read,[],[],package['capacity'],broken)
    def missing(p):
        if p.name=='snapshot-check.json':raise FileNotFoundError('partial preparation')
        return read(p)
    with pytest.raises(FileNotFoundError):audit.review_controlled_snapshot(d,missing,[],[],package['capacity'],fixed)


def test_new_probe_has_one_doc_no_events_and_cannot_inherit_scope_approval(tmp_path):
    from tools.build_lora_common_probe import build
    from training.lora_common_probe_runner import prepare
    from plugin.rhino_listener.lora_common_probe import approval_record,admit
    from plugin.rhino_listener.c5_research_channel import publish_json
    p=build(Path(__file__).resolve().parents[1],tmp_path/'bundle',controlled_snapshot_probe=True)
    ready=prepare(Path(p['source_root']),p);cap=p['capacity']
    assert [c['family_id'] for c in ready['cases']]==['COMMON-B01']
    assert cap['isolated_documents_max']==1 and cap['additional_fixture_operations_max']==2
    assert 'document_events_max' not in cap and cap['model_step_requests_max']==cap['generation_stages_max']==0
    state=Path(p['state_root']);assert not state.exists();state.mkdir(mode=0o700)
    wrong=approval_record(p);wrong['scope']='one_document_scope_and_move_read_probe_zero_models_no_final_test'
    publish_json(state,'owner-approval.json',wrong)
    with pytest.raises(NativeError,match='approval'):admit(Path(p['source_root']),p)
    drift=copy.deepcopy(p);drift['plan']['state_contract']='legacy_global_v1'
    with pytest.raises(NativeError,match='contract'):prepare(Path(p['source_root']),drift)


@pytest.mark.parametrize('mode', ['controlled_snapshot_probe', 'controlled_continuity_probe'])
def test_new_contract_runs_same_controller_and_audits_new_revision_receipt(tmp_path, mode):
    from eval.test_lora_common_chain import WriteFixture
    from tools.build_lora_common_probe import build
    from training.lora_common_probe_runner import controller
    from plugin.rhino_listener.lora_development_host import DevelopmentHost
    from plugin.rhino_listener.c5_research_native import CORE
    p=build(Path(__file__).resolve().parents[1],tmp_path/'bundle',**{mode:True})
    state=tmp_path/'synthetic';state.mkdir(mode=0o700)
    for name in ('host','controller','journal','permission','fixtures'):(state/name).mkdir(mode=0o700)
    secret=b'x'*32
    def factory(view,runtime,key):
        directory=state/'fixtures'/view['slot_id'];directory.mkdir(mode=0o700)
        fixture=WriteFixture(view,runtime,key,directory,None)
        fixture.atomic.state_contract=p['plan']['state_contract']
        return fixture
    host=DevelopmentHost(state=state/'host',runtime=digest(p),native_views=p['compiled']['views']['native'],
        schedule=p['compiled']['views']['schedule'],secret=secret,factory=factory,guard=lambda:None,
        cleanup_guard=lambda:None,operations=CORE,study=p['plan']['study_id'],messages_max=p['capacity']['host_messages_max'])
    run=controller(Path(p['source_root']),p,state,secret,host.handle,lambda:None,lambda:None)
    rows=run.run()
    if rows[0]['outcome']!='success':pytest.fail((state/'controller/common-000.evidence.json').read_text())
    assert host.finish()['owned_fixture_remaining'] is False
    e=json.loads((state/'controller/common-000.evidence.json').read_text())
    assert len(e['steps'])==2 and e['execution']['native_effect']=='verified_writes'
    assert e['score']['outcome_correct'] and e['execution']['fixture_cleanup']=='verified'


def test_continuity_probe_reuses_contract_without_repeating_fixed_checks(tmp_path):
    from tools.build_lora_common_probe import build
    from training.lora_common_probe_runner import prepare
    from plugin.rhino_listener.lora_common_probe import approval_record, admit
    from plugin.rhino_listener.c5_research_channel import publish_json
    p=build(Path(__file__).resolve().parents[1],tmp_path/'bundle',controlled_continuity_probe=True)
    ready=prepare(Path(p['source_root']),p)
    assert [c['family_id'] for c in ready['cases']]==['COMMON-B02']
    assert ready['session_options']['state_contract']=='controlled_snapshot_v1'
    assert ready['session_options']['snapshot_probe'] is False
    assert p['capacity']['additional_fixture_operations_max']==0
    assert p['capacity']['isolated_documents_max']==1
    assert p['capacity']['model_step_requests_max']==0
    state=Path(p['state_root']); assert not state.exists(); state.mkdir(mode=0o700)
    wrong=approval_record(p)
    wrong['scope']='one_controlled_snapshot_move_read_probe_zero_models_no_external_aba_no_final_test'
    publish_json(state,'owner-approval.json',wrong)
    with pytest.raises(NativeError,match='approval'):admit(Path(p['source_root']),p)


def test_partial_fixed_write_failure_keeps_uncertain_ledger_and_closes_owned_doc(tmp_path,monkeypatch):
    from plugin.rhino_listener import lora_development_native
    rhino,registry=fake_rhino(monkeypatch)
    create=rhino.RhinoDoc.CreateHeadless
    def broken_create(template):
        doc=create(template);doc.Delete=lambda *_:False;return doc
    rhino.RhinoDoc.CreateHeadless=broken_create
    class Backend:
        def __init__(self,doc,schemas):self.doc=doc;self.serial=doc.RuntimeSerialNumber;self.closed=False
        def close(self):
            self.doc.Dispose();self.closed=True
            return {'status':'closed','fixture_registry_absent':True}
    monkeypatch.setattr(lora_development_native,'DevelopmentDoc',Backend)
    tmp_path.chmod(0o700)
    session=RhinoSession({'fixture_recipe':[]},'a'*64,b'x'*32,directory=tmp_path,schemas={},
        guard=lambda:None,state_contract=ag.CONTROLLED_SNAPSHOT,snapshot_probe=True,fingerprint_limit=30)
    with pytest.raises(NativeError,match='fixed delete failed'):session.open()
    assert not (tmp_path/'snapshot-check.json').exists() and not (tmp_path/'fixture.sqlite3').exists()
    with sqlite3.connect(tmp_path/'snapshot-protection.sqlite3') as db:
        assert db.execute('SELECT state FROM candidate_write').fetchall()==[('done',),('uncertain',)]
    session.close();assert not registry and session.finish()['status']=='stopped'


@pytest.mark.parametrize('arguments,code,expected', [(['--help'],0,'--snapshot'),
    (['--help'],0,'--continuity'),
    (['--snapshot','--continuity','--output','unused.json'],2,'not allowed'),
    (['--snapshot','--diagnostic','--output','unused.json'],2,'not allowed')])
def test_actual_audit_cli_exposes_snapshot_and_rejects_mixed_modes(arguments,code,expected):
    import subprocess
    path=Path(__file__).parent/'lora-development/common-probe-audit-procedure-20261027.py'
    result=subprocess.run([sys.executable,'-B',str(path),*arguments],capture_output=True,text=True,timeout=10)
    assert result.returncode==code and expected in result.stdout+result.stderr
