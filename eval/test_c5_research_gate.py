"""Real SQLite/durable fake-native controls; never runs Rhino or a model."""
import copy
import sqlite3
from contextlib import closing

import pytest

from plugin.rhino_listener.candidate_atomic_gate import RhinoAtomicGate
from plugin.rhino_listener.c5_research_gate import ResearchGate, signature
from plugin.rhino_listener.c5_research_native import NativeError, digest
from eval.test_c5_research_native import schemas


class Backend:
    def __init__(self):
        self.schemas = schemas()
        self.scene = {"unit":"Millimeters","objects":[]}
        self.calls = []
        self.fail = False
        self.mutate_read = False
        self.changed_scope = False

    def guard(self):
        if self.changed_scope: raise NativeError('wrong active document')

    def target(self, alias, **kwargs):
        if alias != 'A': raise NativeError('unknown alias')
        return 'fake-native-id-never-on-wire'

    def readback(self): return copy.deepcopy(self.scene)

    def dispatch(self, op, args):
        self.calls.append(op)
        if op == 'create_box' or self.mutate_read:
            self.scene['objects'].append({'alias':'A'})
        if self.fail: raise TimeoutError('simulated failure after mutation')
        return {'done':True,'operation':op}


def fixture(tmp_path, *, max_writes=2, max_reads=2):
    backend = Backend()
    atomic = RhinoAtomicGate(tmp_path/'ledger.sqlite3','fake-disposable-fixture',lambda:digest(backend.scene),create_ledger=True)
    gate = ResearchGate(backend,atomic,b'x'*32,'a'*64,task_sha256='b'*64,max_writes=max_writes,max_reads=max_reads,clock=lambda:100)
    return backend,atomic,gate


def envelope(atomic, **changes):
    payload = {'version':1,'request_id':'request-12345678901234567890','task_sha256':'b'*64,'owner_freeze_sha256':'a'*64,
               'expected':atomic.snapshot(),'operation':'create_box','arguments':{'width':2,'depth':3,'height':4},
               'consent_row_sha256':'c'*64,'expires_at':200}
    payload.update(changes)
    return {'payload':payload,'signature':signature(b'x'*32,payload)}


def rows(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute('SELECT state FROM candidate_write').fetchall(),db.execute('SELECT state FROM c5_read').fetchall()


def test_zero_revision_one_write_done_and_no_replay(tmp_path):
    backend,atomic,gate = fixture(tmp_path)
    value = envelope(atomic)
    assert value['payload']['expected']['revision'] == 0
    result = gate.execute(value)
    assert result['ledger_row']['state'] == 'done' and result['before_state']['revision'] == 0
    assert result['after_state']['revision'] > 0 and not result['permission_and_cleanup_independently_audited']
    with pytest.raises(NativeError): gate.execute(value)
    assert backend.calls == ['create_box'] and rows(atomic.path) == ([('done',)],[])


@pytest.mark.parametrize('change',[{'owner_freeze_sha256':'d'*64},{'expires_at':99},{'expires_at':401},
    {'expires_at':True},{'consent_row_sha256':None},{'version':True},{'operation':'delete_objects'},
    {'arguments':{'width':0,'depth':3,'height':4}},{'task_sha256':'bad'},{'task_sha256':'d'*64}])
def test_signed_but_wrong_scope_values_no_reservation(tmp_path,change):
    backend,atomic,gate = fixture(tmp_path)
    with pytest.raises(NativeError): gate.execute(envelope(atomic,**change))
    assert not backend.calls and rows(atomic.path) == ([],[])


def test_unsigned_tamper_stale_scene_and_unknown_alias_no_write(tmp_path):
    backend,atomic,gate = fixture(tmp_path)
    signed = envelope(atomic)
    signed['payload']['arguments']['width'] += 1
    with pytest.raises(NativeError): gate.execute(signed)
    stale = envelope(atomic)
    backend.scene['objects'].append({'alias':'A'})
    with pytest.raises(NativeError): gate.execute(stale)
    invalid = envelope(atomic,operation='move_object',arguments={'object_id':'unknown','translate_x':1,'translate_y':0,'translate_z':0})
    with pytest.raises(NativeError): gate.execute(invalid)
    assert not backend.calls and rows(atomic.path) == ([],[])


def test_reads_zero_write_rows_and_independent_repeat_block(tmp_path):
    backend,atomic,gate = fixture(tmp_path,max_writes=0)
    read = envelope(atomic,operation='get_scene_summary',arguments={},consent_row_sha256=None)
    result = gate.execute(read)
    assert result['ledger_row'] is None and rows(atomic.path) == ([],[('done',)])
    with pytest.raises(NativeError): gate.execute(read)
    with pytest.raises(NativeError): gate.execute(envelope(atomic,request_id='newrequest-12345678901234567890'))
    assert backend.calls == ['get_scene_summary']


@pytest.mark.parametrize('read',[False,True])
def test_uncertain_work_permanently_blocks_later_calls_even_new_gate(tmp_path,read):
    backend,atomic,gate = fixture(tmp_path)
    if read:
        backend.mutate_read = True
        first = envelope(atomic,operation='get_scene_summary',arguments={},consent_row_sha256=None)
    else:
        backend.fail = True
        first = envelope(atomic)
    with pytest.raises((NativeError,TimeoutError)): gate.execute(first)
    next_call = envelope(atomic,request_id='newrequest-12345678901234567890')
    with pytest.raises(NativeError): gate.execute(next_call)
    reconstructed = ResearchGate(backend,atomic,b'x'*32,'a'*64,task_sha256='b'*64,max_writes=2,max_reads=2,clock=lambda:100)
    with pytest.raises(NativeError): reconstructed.execute(next_call)
    assert len(backend.calls) == 1


def test_per_fixture_call_budget_and_active_guard(tmp_path):
    backend,atomic,gate = fixture(tmp_path,max_writes=1)
    gate.execute(envelope(atomic))
    with pytest.raises(NativeError): gate.execute(envelope(atomic,request_id='newrequest-12345678901234567890'))
    backend.changed_scope = True
    with pytest.raises(NativeError): gate.execute(envelope(atomic,operation='get_scene_summary',arguments={},consent_row_sha256=None))
    assert len(backend.calls) == 1
