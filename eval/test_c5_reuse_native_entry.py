"""Whole eight-slot fake Rhino/event loop with real permission and SQLite.

Actual NativeChannel, new Hub/settlement, field wire/peer and independent raw
native audit run together. All models, Rhino types and GPU/SSH are CPU fakes.
"""
import contextlib
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from eval.test_c5_reuse_field_preparation import records,Tokenizer
from eval.test_c5_host_assurance_session import Backend as HostBackend
from eval.test_c5_research_session import Event
from eval.test_c5_research_native import schemas
from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_reuse_field_scope import bind
from plugin.rhino_listener.c5_reuse_public_plan import public_plan,SOURCE,ORDER
from plugin.rhino_listener.c5_reuse_host_session import ReuseHostSession
from plugin.rhino_listener.c5_reuse_native_hub import ReuseNativeHub
from plugin.rhino_listener.c5_deferred_baseline import DeferredBaselineAdmission
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_generation import GenerationPeer
from training.c5_reuse_field_transport import FieldModelChannel
from training.c5_reuse_mac_controller import MacController,prepare
from training.c5_reuse_native_channel import NativeChannel
from training.c5_reuse_native_audit import audit_native_eight
from training.c5_reuse_field_transport_audit import audit_join
from training.c5_reuse_worker_loop import readiness,validate_begin
from training.c5_reuse_field_wire import frame
from training.c5_reuse_evidence import canonical,sha,strict

ROOT=Path(__file__).resolve().parents[1]


class FakeDoc:
    def __init__(self,serial):
        self.RuntimeSerialNumber=serial;self.scene={'unit':'Millimeters','objects':[],'groups':{}}


class NativeBackend:
    def __init__(self,doc,active,schemas):
        self.doc,self.active,self.schemas=doc,active,schemas
        self.serial,self.active_serial=doc.RuntimeSerialNumber,active.RuntimeSerialNumber
        self.initial_active_sha='e'*64;self.closed=False;self.calls=[]
    def guard(self):assert not self.closed
    def readback(self):return copy.deepcopy(self.doc.scene)
    def target(self,alias,**kwargs):return alias
    def dispatch(self,operation,args):
        self.calls.append(operation)
        if operation=='create_box':
            self.doc.scene['objects'].append({'alias':'A','min':[0,0,0],'max':[2,3,4],'volume':24.,
                'centroid':[1,1.5,2],'solid':True,'face_count':6,'layer':'Default','color':[0,0,0],'groups':[]})
            return {'done':True}
        from training.c5_modelbridge_joint_audit import semantic
        return semantic(self.doc.scene)
    def close(self):
        self.closed=True
        return {'fixture_serial':self.serial,'before_close_active_serial':self.active_serial,
            'after_close_active_serial':self.active_serial,'fixture_registry_absent':True,
            'fixture_before_close_native':self.readback(),'initial_active_sha256':'e'*64,
            'before_close_active_sha256':'e'*64,'after_close_active_sha256':'e'*64}


class PeerPipe:
    def __init__(self,peer):self.peer=peer;self.raw=b'';self.response=b''
    def write(self,raw,deadline):
        self.raw+=raw
        if self.raw.endswith(b'\n'):
            self.response=frame(self.peer.infer(strict(self.raw)));self.raw=b''
        return len(raw)
    def read(self,deadline):
        chunk,self.response=self.response[:32768],self.response[32768:];return chunk


def setup(tmp_path,monkeypatch,*,failure=None):
    public=public_plan(ROOT);spec,runtime,approval,_=records(tmp_path,plans=public['task_plans'])
    for record in (spec,runtime):
        record['resources']['generation_cutoff_epoch']=2000000000;record['resources']['lease_expiry_epoch']=2000001000
    runtime['spec_sha256']=approval['spec_sha256']=sha(spec);approval['runtime_sha256']=sha(runtime)
    mac=bind(spec,runtime,approval,now=100,endpoint='mac');gpu=bind(spec,runtime,approval,now=100,endpoint='gpu')
    for b in (mac,gpu):
        Path(b['paths']['source_root']).mkdir(parents=True)
        p=Path(b['paths']['source_root'])/SOURCE;p.parent.mkdir(parents=True);shutil.copyfile(ROOT/SOURCE,p)
        Path(b['paths']['state_root']).mkdir(mode=0o700)
    guard=lambda **kwargs:sha(runtime['source_files'])
    prepare(mac,guard);mr=AdmissionRegistry(mac);gr=AdmissionRegistry(gpu,create=True)
    event=Event();active=FakeDoc(1);docs=[]
    def create(_):doc=FakeDoc(100+len(docs));docs.append(doc);return doc
    rhino=SimpleNamespace(RhinoApp=SimpleNamespace(IsOnMainThread=True,Idle=event,InCommand=False,Version='8.21.25188.17002'),
        RhinoDoc=SimpleNamespace(ActiveDoc=active,CreateHeadless=create),UnitSystem=SimpleNamespace(Millimeters='mm'))
    monkeypatch.setitem(sys.modules,'Rhino',rhino)
    import plugin.rhino_listener.c5_modelbridge_hub as hub_module
    import plugin.rhino_listener.c5_research_session as session_module
    monkeypatch.setattr(hub_module,'NativeDoc',NativeBackend)
    if failure=='native_unknown':
        class UnknownBackend(NativeBackend):
            def dispatch(self,operation,args):
                super().dispatch(operation,args)
                raise TimeoutError('CPU unknown after actual fake mutation')
        monkeypatch.setattr(hub_module,'NativeDoc',UnknownBackend)
    monkeypatch.setattr(hub_module,'active_content_digest',lambda doc:'e'*64)
    monkeypatch.setattr(hub_module,'rhino_scene_digest',lambda doc:digest(doc.scene))
    monkeypatch.setattr(session_module,'active_content_digest',lambda doc:'e'*64)
    assurance=ReuseHostSession(mac,mr,HostBackend(),guard,sha(runtime['source_files']),cleanup_source=guard)
    hub=ReuseNativeHub(mac,runtime,mr,schemas(),active,guard,assurance);state=Path(mac['paths']['state_root'])
    deferred=DeferredBaselineAdmission(source_guard=guard,seal=lambda:assurance.seal_baseline(),
        publish_ready=lambda:None,mark_failure=lambda _:None,dispatch=hub.tick)
    # Explicit return barrier and separate first Idle. No warmup or actual host.
    hub.attach();deferred.release_after_entry_return();deferred.tick(in_command=False);hub.preparing=False
    publish_json(state,'entry-return-release.json',{'study_id':mac['study_id'],'runtime_sha256':mac['runtime_sha256'],
        'source_inventory_sha256':sha(runtime['source_files']),'baseline_sealed':False,'replay_allowed':False})
    publish_json(state,'host-continuity-ready.json',{'study_id':mac['study_id'],'runtime_sha256':mac['runtime_sha256'],
        'host_baseline_head_sha256':assurance.head,'generation_stages':0,'full_byte_closure_proven':False})
    def poll(_):
        for callback in list(event.handlers):callback(None,None)
    def channel(*args,**kwargs):return NativeChannel(*args,**kwargs,sleep=poll)
    calls=[]
    def generate(prompt,stage):
        slot=ORDER[len([r for r in peer.journal.records if r['kind']=='request_intent'])-1]
        calls.append((slot,stage))
        if failure=='model' and slot==ORDER[0]:raise TimeoutError('CPU model unknown')
        raw=json.dumps({'tool':None} if slot.startswith(('clarify','unsupported')) else
                       {'tool':'get_scene_summary' if slot.startswith('read') else 'create_box'}) if stage=='selector' else \
            json.dumps({'name':'get_scene_summary','arguments':{}} if slot.startswith('read') else
                       {'name':'create_box','arguments':{'width':2,'depth':3,'height':4}})
        return {'raw':raw,'tokens':10,'seconds':.01,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                'output_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    peer=GenerationPeer(gpu,gr,public['task_plans'],Tokenizer(),generate,lambda _:contextlib.nullcontext(),lambda:None,lambda:None)
    class Session:
        def __init__(self,binding,registry,plans,transport,guard,budget):
            self.stop_spent=False;self.stops=0
            self.channel=FieldModelChannel(binding,registry,PeerPipe(peer),guard,budget,plans)
        def await_ready(self):return readiness(gpu,'a'*64,peer.journal.records[0]['record_sha256'])
        def begin(self,owner):
            validate_begin({'kind':'reuse_begin_after_external_readiness','protocol':mac['protocol'],
                'scope_sha256':sha(__import__('training.c5_reuse_field_scope',fromlist=['common_scope']).common_scope(mac)),
                'owner_readiness':owner},gpu)
            if failure=='ready':raise ValueError('CPU ready drift')
        def close(self):return {'worker_final_head_sha256':peer.journal.head}
        def export(self):return canonical({'cpu_fixture_only':True})
        def independent_stop(self):self.stops+=1;self.stop_spent=True
    runner=MacController(mac,{'transport':{},'source_files':runtime['source_files']},schemas(),mr,guard,lambda:None,
                         session_factory=Session,channel_factory=channel)
    def external(host,worker):return {'study_id':mac['study_id'],'instance_id':mac['instance_id'],
        'spec_sha256':mac['spec_sha256'],'runtime_sha256':mac['runtime_sha256'],'actor':'repository_owner',
        'host_baseline_head_sha256':host['host_baseline_head_sha256'],'worker_readiness_sha256':sha(worker),
        'captured_after_host_baseline':True,'approved_generation_start':True}
    return runner,external,peer,mr,gr,hub,event,public,runtime,calls


def test_eight_real_sqlite_handoffs_native_events_and_original_raw_audit(tmp_path,monkeypatch):
    runner,external,peer,mr,gr,hub,event,public,runtime,calls=setup(tmp_path,monkeypatch)
    try:
        result=runner.drive(external);assert not result['whole_field_pass'] and hub.stopped and not event.handlers
        assert [r['payload']['slot_id'] for r in runner.journal.rows if r['kind']=='slot_closed']==list(ORDER)
        assert len(calls)==12  # 4 real fake-core requests ×2 +4 abstentions ×1.
        slots={}
        for slot in ORDER:
            d=runner.state/slot;key=read_json(runner.state/'audit-key-custody',slot+'.json')
            slots[slot]={'secret':bytes.fromhex(key['key_hex']),'consent_path':d/'consent.sqlite3','ledger_path':d/'fixture.sqlite3'}
            assert not (d/'handoff.key').exists()
        assert not (runner.state/'hub.key').exists()
        # Synthetic warmup evidence only, never a real host/field claim.
        c=NativeBackend(FakeDoc(90),FakeDoc(1),schemas()).close()
        publish_json(runner.state,'warmup.result.json',{'study_id':runner.binding['study_id'],
            'runtime_freeze_sha256':runner.binding['runtime_sha256'],'before_native':c['fixture_before_close_native'],
            'close_capture':c,'active_sha256':'e'*64,'tool_dispatches':0,'model_calls':0})
        seal=read_json(runner.state/'host','host-continuity-seal.json')
        assertions=json.loads((ROOT/SOURCE).read_bytes())['independent_write_assertions']
        outcome=audit_native_eight(runner.journal.rows,runner.binding,runner.journal.head,
            runner.session.channel.journal.records,runner.session.channel.journal.head,public,schemas(),slots,
            bytes.fromhex(read_json(runner.state/'audit-key-custody','hub.json')['key_hex']),
            source_files=runtime['source_files'],external_host_seal_sha256=digest(seal),write_assertions=assertions)
        assert outcome['complete_eight_native_permission_lifecycle_records']
        assert not outcome['all_eight_quality_passed'] and not outcome['quality_by_slot']['write-base']
        assert outcome['quality_by_slot']['read-base'] and outcome['quality_by_slot']['clarify-base']
        joined=audit_join(runner.session.channel.journal.records,peer.journal.records,runner.binding,peer.binding,
            runner.session.channel.journal.head,peer.journal.head,public['task_plans'],Tokenizer())
        assert joined['complete_raw_join'] and joined['model_acknowledgements']==8
        with pytest.raises(ValueError,match='no_retry'):runner.drive(external)
    finally:mr.close();gr.close()


@pytest.mark.parametrize('failure',['ready','model','native_unknown'])
def test_unknown_before_or_during_generation_retires_and_stops_once(tmp_path,monkeypatch,failure):
    runner,external,peer,mr,gr,hub,event,public,runtime,calls=setup(tmp_path,monkeypatch,failure=failure)
    try:
        with pytest.raises((ValueError,RuntimeError,NativeError)):runner.drive(external)
        count=len(calls);assert runner.session.stops==1 and any(r['kind']=='controller_retired_no_retry' for r in runner.journal.rows)
        if failure=='native_unknown':
            assert not hub.stopped and event.handlers and (runner.state/ORDER[0]/'handoff.key').exists()
            assert not any(r['kind']=='failure_cleanup_intent' for r in runner.journal.rows)
        else:assert hub.stopped and not event.handlers
        with pytest.raises(ValueError,match='no_retry'):runner.drive(external)
        assert len(calls)==count and runner.session.stops==1
    finally:mr.close();gr.close()


def test_wrong_actual_root_all_new_entries_refuse_before_host_or_keys(tmp_path):
    from tools.run_c5_reuse_rhino_entry import start
    with pytest.raises(ValueError,match='fixed_entry_root'):start()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('change',['extra_native_request','missing_timing','signed_control','fixture_reuse',
                                  'hidden_dispatch','key_returned','too_many_settles','native_head','hub_scope','backup_alias'])
def test_full_eight_raw_native_tampering_does_not_become_field_pass(tmp_path,monkeypatch,change):
    runner,external,peer,mr,gr,hub,event,public,runtime,calls=setup(tmp_path,monkeypatch)
    try:
        runner.drive(external);slots={}
        for slot in ORDER:
            d=runner.state/slot
            slots[slot]={'secret':bytes.fromhex(read_json(runner.state/'audit-key-custody',slot+'.json')['key_hex']),
                         'consent_path':d/'consent.sqlite3','ledger_path':d/'fixture.sqlite3'}
        c=NativeBackend(FakeDoc(90),FakeDoc(1),schemas()).close()
        publish_json(runner.state,'warmup.result.json',{'study_id':runner.binding['study_id'],
            'runtime_freeze_sha256':runner.binding['runtime_sha256'],'before_native':c['fixture_before_close_native'],
            'close_capture':c,'active_sha256':'e'*64,'tool_dispatches':0,'model_calls':0})
        d=runner.state/ORDER[0];rows=copy.deepcopy(runner.journal.rows)
        def overwrite(path,value):path.write_text(json.dumps(value));path.chmod(0o600)
        if change=='extra_native_request':publish_json(d,'request-0099.json',{'kind':'control'})
        elif change=='missing_timing':(d/'service-time-0001.json').unlink()
        elif change=='signed_control':
            p=d/'request-0001.json';v=read_json(d,p.name);v['envelope']['signature']='0'*64;overwrite(p,v)
        elif change=='fixture_reuse':
            second=runner.state/ORDER[1];v=read_json(second,'engine-created.json');v['fixture_serial']=100
            overwrite(second/'engine-created.json',v)
        elif change=='hidden_dispatch':publish_json(d,'execute-0099.json',{'status':'done'})
        elif change=='key_returned':publish_json(d,'handoff.key',{'key_hex':('x'*32).encode().hex()})
        elif change=='too_many_settles':
            next(r for r in rows if r['kind']=='slot_native_result')['payload']['native_result']['settling_samples']*=3
        elif change=='hub_scope':
            v=read_json(runner.state,'hub-request-0001.json');v['payload']['owner_freeze_sha256']='0'*64
            overwrite(runner.state/'hub-request-0001.json',v)
        elif change=='backup_alias':
            p=d/'fixture-audit.sqlite3';p.unlink();p.symlink_to(d/'fixture.sqlite3')
        previous='0'*64
        for row in rows:
            row['previous_sha256']=previous;row['record_sha256']=sha({k:v for k,v in row.items() if k!='record_sha256'})
            previous=row['record_sha256']
        with pytest.raises((ValueError,NativeError,OSError,KeyError)):
            audit_native_eight(rows,runner.binding,'0'*64 if change=='native_head' else previous,
                runner.session.channel.journal.records,runner.session.channel.journal.head,public,schemas(),slots,
                bytes.fromhex(read_json(runner.state/'audit-key-custody','hub.json')['key_hex']),
                source_files=runtime['source_files'],external_host_seal_sha256=digest(read_json(runner.state/'host','host-continuity-seal.json')),
                write_assertions=json.loads((ROOT/SOURCE).read_bytes())['independent_write_assertions'])
    finally:mr.close();gr.close()
