"""Actual consent/atomic SQLite synthetic integration; no Rhino/model/GPU."""
import copy
import hashlib
import json

import pytest

from eval.test_c5_research_gate import fixture
from eval.test_c5_rhino_adapter import Tokenizer
from plugin.rhino_listener.c5_research_gate import ResearchGate
from plugin.rhino_listener.c5_research_native import NativeError, digest
from training.c5_inventory import load_public_mcp_tools
from training.c5_research_permission import ResearchSigner, SceneView
from training.c5_rhino_adapter import invoke_step, step_input
from training.consent_candidate import ConsentStore
from training.tool_controller_candidate import task_sha256

TASK = '创建宽2深3高4的盒体'


def setup(tmp_path, max_writes=2):
    backend, atomic, _ = fixture(tmp_path)
    clock = lambda:100
    atomic.clock = clock
    store = ConsentStore(tmp_path/'consent.sqlite3',load_public_mcp_tools(),clock=clock)
    scene = SceneView(atomic,lambda:{'unit':'Millimeters','objects':[],'groups':{}})
    signer = ResearchSigner(store,scene,b'x'*32,'a'*64,TASK,max_writes=max_writes,max_reads=2,clock=clock)
    gate = ResearchGate(backend,atomic,b'x'*32,'a'*64,task_sha256=task_sha256(TASK),max_writes=max_writes,max_reads=2,clock=clock)
    return backend,atomic,store,signer,gate


def observation(atomic,op='create_box',args=None):
    if args is None: args = {'width':2,'depth':3,'height':4}
    user_step = step_input(TASK,{'unit':'Millimeters','objects':[],'groups':{}})
    return invoke_step(Tokenizer(),lambda prompt,stage:{'raw':json.dumps({'tool':op} if stage=='selector' else {'name':op,'arguments':args})},user_step,scene_binding=atomic.snapshot())


def test_consume_original_call_before_handoff_one_done_and_replay_denied(tmp_path):
    backend,atomic,store,signer,gate = setup(tmp_path)
    signed = signer.issue(observation(atomic),schemas=backend.schemas)
    with store._tx() as db:
        row = dict(db.execute('SELECT * FROM consent_requests').fetchone())
    assert row['status'] == 'consumed' and digest(row) == signed['payload']['consent_row_sha256']
    assert [e['event_type'] for e in store.audit_events(row['request_id'])] == ['requested','approved','consumed','signed_handoff_issued']
    assert store.audit_events(row['request_id'])[1]['reason_code'] == 'codex_delegated_headless'
    assert store.audit_events(row['request_id'])[-1]['reason_code'] == digest(signed['payload'])
    result = gate.execute(signed)
    assert result['ledger_row']['state'] == 'done' and result['payload']['arguments'] == {'width':2,'depth':3,'height':4}
    with pytest.raises(NativeError): gate.execute(signed)
    assert backend.calls == ['create_box']


def test_zero_write_scope_denies_before_permission_creation(tmp_path):
    backend,atomic,store,signer,gate = setup(tmp_path,max_writes=0)
    with pytest.raises(NativeError): signer.issue(observation(atomic),schemas=backend.schemas)
    with store._tx() as db: assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0] == 0
    assert not backend.calls


def test_read_signs_no_write_permission_and_does_not_advance_revision(tmp_path):
    backend,atomic,store,signer,gate = setup(tmp_path,max_writes=0)
    initial = atomic.snapshot()
    signed = signer.issue(observation(atomic,'get_scene_summary',{}),schemas=backend.schemas)
    assert signed['payload']['consent_row_sha256'] is None
    assert gate.execute(signed)['after_state'] == initial
    with store._tx() as db: assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0] == 0


@pytest.mark.parametrize('change',['args','raw','stage','status','repair'])
def test_tampered_observation_not_signed_or_consumed(tmp_path,change):
    backend,atomic,store,signer,gate = setup(tmp_path)
    observed = observation(atomic)
    if change == 'args': observed['arguments']['width'] = 8
    if change == 'raw': observed['calls'][1]['raw'] = '{}'
    if change == 'stage': observed['calls'][1]['stage'] = 'selector'
    if change == 'status': observed['status'] = 'abstained_no_dispatch'
    if change == 'repair': observed['repair_count'] = 1
    with pytest.raises(NativeError): signer.issue(observed,schemas=backend.schemas)
    with store._tx() as db: assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0] == 0
    assert not backend.calls


def test_consumption_interruption_sticky_block_no_automatic_retry(tmp_path,monkeypatch):
    backend,atomic,store,signer,gate = setup(tmp_path)
    def interrupted(*args,**kwargs): raise TimeoutError('synthetic process interruption')
    monkeypatch.setattr(store,'_consume',interrupted)
    with pytest.raises(TimeoutError): signer.issue(observation(atomic),schemas=backend.schemas)
    with pytest.raises(NativeError): signer.issue(observation(atomic),schemas=backend.schemas)
    with store._tx() as db: assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0] == 1
    assert not backend.calls


@pytest.mark.parametrize('change',['scene','task','unbound'])
def test_generation_scene_or_task_drift_denied_before_permission(tmp_path,change):
    backend,atomic,store,signer,gate = setup(tmp_path)
    observed = observation(atomic)
    if change == 'scene': backend.scene['objects'].append({'alias':'A'})
    if change == 'task': observed['user_step_sha256'] = 'f'*64
    if change == 'unbound': observed['scene_binding'] = None
    with pytest.raises(NativeError): signer.issue(observed,schemas=backend.schemas)
    with store._tx() as db: assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0] == 0
    assert not backend.calls


def test_same_model_observation_cannot_reissue_even_reconstructed_signer(tmp_path):
    backend,atomic,store,signer,gate = setup(tmp_path)
    observed = observation(atomic)
    signer.issue(observed,schemas=backend.schemas)
    second = ResearchSigner(store,signer.scene,b'x'*32,'a'*64,TASK,max_writes=2,max_reads=2,clock=lambda:100)
    with pytest.raises(NativeError): second.issue(observed,schemas=backend.schemas)
    with store._tx() as db:
        assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM c5_model_handoff').fetchone()[0] == 1
    assert not backend.calls
