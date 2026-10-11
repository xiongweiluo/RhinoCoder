"""Real consent/atomic SQLite over CPU backend; original public task text only."""
import contextlib
import copy
import json
from pathlib import Path
import shutil

import pytest

from eval.test_c5_reuse_field_preparation import binding,records,Tokenizer,sha_raw
from eval.test_c5_reuse_field_negative import rechain
from eval.test_c5_research_gate import fixture
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_field_journal import FieldJournal
from training.c5_reuse_development_plan import public_plan,SOURCE
from training.c5_reuse_generation import GenerationPeer
from training.c5_reuse_native_handoff import NativeHandoff
from training.c5_reuse_native_handoff_audit import audit_handoffs
from training.c5_reuse_field_wire import envelope
from training.c5_model_transport import request
from plugin.rhino_listener.c5_research_gate import ResearchGate
from plugin.rhino_listener.c5_research_native import NativeError
from training.tool_controller_candidate import task_sha256


def setup(tmp_path,slot='write-base',*,kind='good'):
    repository=Path(__file__).resolve().parents[1]
    info=public_plan(repository); plans=info['task_plans']
    mac=binding(tmp_path,plans=plans,endpoint='mac'); gpu=binding(tmp_path,plans=plans)
    source=Path(mac['paths']['source_root'])/SOURCE; source.parent.mkdir(parents=True)
    shutil.copyfile(repository/SOURCE,source)
    for b in (mac,gpu): Path(b['paths']['state_root']).mkdir(mode=0o700)
    directory=Path(mac['paths']['state_root'])/slot; directory.mkdir(mode=0o700)
    backend,atomic,_=fixture(directory)
    atomic.clock=lambda:100
    initial={'state':atomic.snapshot(),'native':{**backend.readback(),'groups':{}}}
    mac_registry=AdmissionRegistry(mac,create=True); gpu_registry=AdmissionRegistry(gpu,create=True)
    journal=FieldJournal(mac,'controller',mac_registry)
    handoff=NativeHandoff(journal,backend.schemas,lambda:None,lambda:None,epoch=lambda:100)
    task=plans[slot]['steps'][0]
    operation='get_scene_summary' if slot.startswith('read') and kind!='policy' else 'create_box'
    args={} if operation=='get_scene_summary' else {'width':2,'depth':3,'height':4}
    def generate(prompt,stage):
        raw=json.dumps({'tool':operation} if stage=='selector' else {'name':operation,'arguments':args})
        return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':sha_raw(prompt),'output_sha256':sha_raw(raw)}
    peer=GenerationPeer(gpu,gpu_registry,plans,Tokenizer(),generate,lambda route:contextlib.nullcontext(),lambda:None,lambda:None)
    sent=envelope(mac,request(mac['study_id'],slot,plans[slot]['route'],0,task,initial['native'],initial['state'],
                             mac['runtime_sha256'],'cpu-native-request'))
    result=peer.infer(sent)
    policy=info['slot_policies'][slot]
    gate=ResearchGate(backend,atomic,b'x'*32,mac['runtime_sha256'],task_sha256=task_sha256(task),
                     max_writes=policy['max_writes'],max_reads=policy['max_reads'],clock=lambda:100)
    def capture(): return {'state':atomic.snapshot(),'native':{**backend.readback(),'groups':{}}}
    return handoff,sent,result,initial,capture,gate,backend,atomic,info,mac_registry,gpu_registry,directory


@pytest.mark.parametrize('slot',['write-base','read-lora'])
def test_new_scope_original_model_signer_and_sqlite_independently_joined(tmp_path,slot):
    h,sent,result,before,capture,gate,backend,atomic,info,mr,gr,directory=setup(tmp_path,slot)
    try:
        receipt=h.execute(sent,result,before,capture,gate.execute,b'x'*32)
        assert backend.calls==[result['observation']['name']]
        source={slot:{'secret':b'x'*32,'consent_path':directory/'consent.sqlite3','ledger_path':atomic.path}}
        audit=audit_handoffs(h.journal.records,h.binding,h.journal.head,info,source,backend.schemas)
        assert audit['permission_ledger_slots_verified']==1 and audit['complete_handoff_records']
        assert not audit['geometry_quality_verified'] and not audit['cleanup_verified'] and not audit['execution_ready']
        # Legal wrong geometry remains the unmodified model call: write task asks
        # for a cylinder, injected CPU model selects a box. No repair/quality PASS.
        if slot.startswith('write'): assert receipt['payload']['operation']=='create_box'
        with pytest.raises(ValueError): h.execute(sent,result,before,capture,gate.execute,b'x'*32)
        with pytest.raises(ValueError,match='reconstruction'): NativeHandoff(h.journal,backend.schemas,lambda:None,lambda:None)
    finally: mr.close(); gr.close()


def test_zero_write_public_read_policy_rejects_before_permission_or_native_effect(tmp_path):
    h,sent,result,before,capture,gate,backend,atomic,info,mr,gr,directory=setup(tmp_path,'read-lora',kind='policy')
    try:
        denied=h.execute(sent,result,before,capture,gate.execute,b'x'*32)
        assert denied['reason']=='development_task_policy' and backend.calls==[]
        assert not (directory/'consent.sqlite3').exists()
        source={'read-lora':{'secret':b'x'*32,'consent_path':directory/'consent.sqlite3','ledger_path':atomic.path}}
        audit=audit_handoffs(h.journal.records,h.binding,h.journal.head,info,source,backend.schemas)
        assert audit['complete_handoff_records'] and audit['permission_ledger_slots_verified']==0
    finally: mr.close(); gr.close()


@pytest.mark.parametrize('kind',['scene','model_args','raw','capture','signed_durability','native_unknown','late_guard'])
def test_drift_or_unknown_handoff_never_retries_or_repairs(tmp_path,kind):
    h,sent,result,before,capture,gate,backend,atomic,info,mr,gr,directory=setup(tmp_path)
    try:
        if kind=='scene': before['state']['revision']=1
        elif kind=='model_args': result['observation']['arguments']['width']=99
        elif kind=='raw': result['generation_returns'][1]['raw']='{}'
        elif kind=='capture':
            original=capture
            def capture():
                value=original(); value['state']['revision']+=1; return value
        elif kind=='signed_durability':
            original=h.journal.append
            def append(event,payload):
                if event=='native_signed_handoff': raise OSError('CPU disk full after consumption')
                original(event,payload)
            h.journal.append=append
        elif kind=='native_unknown': backend.fail=True
        else:
            def execute_signed(signed):
                value=gate.execute(signed)
                h.guard=lambda:(_ for _ in ()).throw(ValueError('CPU source drift after dispatch'))
                return value
        target=execute_signed if kind=='late_guard' else gate.execute
        with pytest.raises((ValueError,OSError,TimeoutError)):
            h.execute(sent,result,before,capture,target,b'x'*32)
        old=list(backend.calls)
        with pytest.raises(ValueError,match='no_retry'):
            h.execute(sent,result,before,capture,gate.execute,b'x'*32)
        assert backend.calls==old
        assert len(backend.calls)==int(kind in ('native_unknown','late_guard'))
    finally: mr.close(); gr.close()


@pytest.mark.parametrize('kind',['bound','signature','payload','capture','receipt','missing'])
def test_independent_rehashed_native_tampering_is_rejected(tmp_path,kind):
    h,sent,result,before,capture,gate,backend,atomic,info,mr,gr,directory=setup(tmp_path)
    try:
        h.execute(sent,result,before,capture,gate.execute,b'x'*32)
        rows=copy.deepcopy(h.journal.records)
        bound=next(r for r in rows if r['kind']=='native_permission_intent')
        signed=next(r for r in rows if r['kind']=='native_signed_handoff')
        receipt=next(r for r in rows if r['kind']=='native_dispatch_observed')
        if kind=='bound': bound['payload']['bound_observation']['arguments']['width']=99
        elif kind=='signature': signed['payload']['envelope']['signature']='0'*64
        elif kind=='payload': signed['payload']['envelope']['payload']['operation']='get_scene_summary'
        elif kind=='capture': next(r for r in rows if r['kind']=='native_signing_capture')['payload']['capture']['state']['revision']=3
        elif kind=='receipt': receipt['payload']['receipt']['after_state']['revision']=0
        else: rows.remove(signed)
        for i,row in enumerate(rows): row['seq']=i
        head=rechain(rows)
        source={'write-base':{'secret':b'x'*32,'consent_path':directory/'consent.sqlite3','ledger_path':atomic.path}}
        with pytest.raises((ValueError,NativeError)): audit_handoffs(rows,h.binding,head,info,source,backend.schemas)
    finally: mr.close(); gr.close()
