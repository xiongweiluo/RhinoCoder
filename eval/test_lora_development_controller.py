"""Synthetic provider + real parser, signed host, SQLite gate and scorer.

No Rhino, weights, old evidence or field state. The scripted provider uses
test expectations solely as a fixture, never as an input to a real model.
"""
import copy
import json
import sqlite3
from pathlib import Path

import pytest

from plugin.rhino_listener.candidate_atomic_gate import RhinoAtomicGate
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_gate import ResearchGate
from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener.lora_development_host import DevelopmentHost
from training.c5_formal20_plan import _schemas
from training.c5_modelbridge_joint_audit import semantic
from training.lora_development_cases import build_cases, fixture_design
from training.lora_development_controller import DevelopmentController
from training.lora_development_scope import DevelopmentJournal
from eval.test_lora_development_wire import PLAN, RUNTIME, IDENTITY, SECRET, TextTokenizer, fixed_response


class MemoryFixture:
    def __init__(self, plan, runtime, secret, directory, fault):
        self.plan, self.directory, self.fault = plan, directory, fault
        _, scene, assertions = fixture_design()
        self.scene = {**scene, 'objects': [dict(alias=alias, **v) for alias, v in assertions['objects'].items()]}
        self.schemas, self.closed = _schemas(), False
        self.atomic = RhinoAtomicGate(directory / 'fixture.sqlite3', plan['slot_id'], lambda: digest(self.scene), create_ledger=True)
        self.gate = ResearchGate(self, self.atomic, secret, runtime,
            task_sha256=plan['task_sha256'], max_reads=plan['max_reads'], max_writes=0)

    def guard(self):
        if self.closed: raise NativeError('closed')

    def target(self, alias, **kwargs):
        assert alias in {'box-1', 'box-2'}
        return alias

    def readback(self): return copy.deepcopy(self.scene)
    def dispatch(self, op, args):
        if self.fault == 'native_unknown': raise TimeoutError('synthetic dispatch interruption')
        if op == 'get_scene_summary': return semantic(self.scene)
        obj = next(o for o in self.scene['objects'] if o['alias'] == args['object_id'])
        return {'object_id': obj['alias'], 'min': obj['min'], 'max': obj['max'],
                'center': [(a + b) / 2 for a, b in zip(obj['min'], obj['max'])]}

    def open(self):
        if self.fault == 'partial_open': raise RuntimeError('synthetic partial opening')
        return {'status': 'opened'}
    def capture(self): return {'status': 'captured', 'state': self.atomic.snapshot(), 'native': self.readback()}
    def execute(self, value): return self.gate.execute(value)
    def close(self):
        if self.fault == 'close_unknown': raise TimeoutError('synthetic close interruption')
        self.closed = True
        return {'status': 'closed', 'fixture_registry_absent': True, 'readback_error': None,
                'fixture_before_close_native': self.readback()}
    def finish(self):
        with sqlite3.connect(self.atomic.path) as db:
            db.row_factory = sqlite3.Row
            ledger = {name: [dict(r) for r in db.execute('SELECT * FROM ' + name)]
                      for name in ['candidate_write', 'c5_read']}
        if self.fault == 'ledger_forgery': ledger['c5_read'] = []
        return {'status': 'stopped', 'ledger': ledger, 'fixture_registry_absent': True}


def setup(tmp_path, fault=None):
    for name in ['journal', 'controller', 'host']:
        (tmp_path / name).mkdir(mode=0o700)
    journal = DevelopmentJournal(tmp_path / 'journal', PLAN, RUNTIME)
    sessions, calls = [], []
    def factory(plan, runtime, secret):
        directory = tmp_path / plan['slot_id']; directory.mkdir(mode=0o700)
        fixture = MemoryFixture(plan, runtime, secret, directory, fault)
        sessions.append(fixture)
        return fixture
    host = DevelopmentHost(state=tmp_path / 'host', runtime=RUNTIME, native_views=journal.views['native'],
        schedule=journal.views['schedule'], secret=SECRET, factory=factory, guard=lambda: None, cleanup_guard=lambda: None)
    cases = {r['case']['family_id']: r['case'] for r in build_cases()}
    def model(sent):
        calls.append(sent)
        if fault == 'model_unknown': raise TimeoutError('synthetic response lost')
        case = cases[journal.views['model'][sent['slot_id']]['family_id']]
        if fault == 'parse_failure': return fixed_response(sent, 'invalid')
        if fault == 'policy_denied':
            return fixed_response(sent, '{"tool":"create_box"}',
                '{"name":"create_box","arguments":{"width":1,"depth":2,"height":3}}')
        if not case['expected_operations']: return fixed_response(sent, '{"tool":null}')
        op = case['expected_operations'][sent['step_index']]
        return fixed_response(sent, json.dumps({'tool': op['name']}),
            json.dumps({'name': op['name'], 'arguments': op['arguments']}))
    controller = DevelopmentController(journal=journal, state=tmp_path / 'controller', runtime=RUNTIME,
        secret=SECRET, schemas=_schemas(), tokenizer=TextTokenizer(), identities={'base': IDENTITY, 'current_lora': IDENTITY},
        host=host.handle, model=model, guard=lambda: None, cleanup_guard=lambda: None)
    return controller, host, sessions, calls


def test_complete_32_synthetic_cells_authenticate_reads_and_seal_selection(tmp_path):
    controller, host, sessions, calls = setup(tmp_path)
    rows = controller.run()
    assert len(rows) == 32 and all(r['outcome'] == 'success' for r in rows)
    assert len(calls) == 48 and all(s.closed for s in sessions)
    assert read_json(tmp_path / 'journal', 'selection.json')['selected_system'] == 'original'
    assert host.finish()['owned_fixture_remaining'] is False
    assert all('expected_operations' not in c and 'fixture_recipe' not in c for c in calls)


@pytest.mark.parametrize('fault', ['parse_failure', 'policy_denied'])
def test_quality_failure_is_retained_and_fixed_schedule_continues(tmp_path, fault):
    controller, host, sessions, calls = setup(tmp_path, fault)
    rows = controller.run()
    assert len(rows) == 32 and all(r['outcome'] == 'task_failure' for r in rows)
    assert len(calls) == 32 and all(s.closed for s in sessions)
    for s in sessions:
        with sqlite3.connect(s.atomic.path) as db:
            assert db.execute('SELECT count(*) FROM c5_read').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM candidate_write').fetchone()[0] == 0


@pytest.mark.parametrize('fault', ['partial_open', 'model_unknown', 'native_unknown', 'close_unknown', 'ledger_forgery'])
def test_uncertainty_stops_batch_preserves_evidence_and_attempts_only_owned_cleanup(tmp_path, fault):
    controller, host, sessions, calls = setup(tmp_path, fault)
    rows = controller.run()
    assert len(rows) == len(sessions) == 1 and not rows[0]['may_advance']
    assert rows[0]['outcome'] == 'engineering_failure' and not rows[0]['effect_known']
    assert sessions[0].closed == (fault != 'close_unknown')
    assert not (tmp_path / 'journal' / 'selection.json').exists()
    if fault == 'partial_open': assert not calls
    evidence = read_json(tmp_path / 'controller', 'lora-dev-00.evidence.json')
    assert evidence['score'] is None and evidence['error_type']


def test_host_replay_and_wrong_scope_never_reach_fixture(tmp_path):
    from plugin.rhino_listener.lora_development_host import signed_request
    controller, host, sessions, calls = setup(tmp_path)
    signed = signed_request(SECRET, RUNTIME, 'lora-dev-00', 1, {'action': 'open'})
    host.handle(signed)
    with pytest.raises(NativeError): host.handle(signed)
    wrong = signed_request(SECRET, 'f' * 64, 'lora-dev-00', 2, {'action': 'capture'})
    with pytest.raises(NativeError): host.handle(wrong)
    assert len(sessions) == 1 and not calls


def test_controller_loop_failure_preserves_completed_prefix_for_settlement(tmp_path, monkeypatch):
    controller, host, sessions, calls = setup(tmp_path)
    start = controller.journal.start_slot
    def fail_next(slot):
        if slot == 'lora-dev-01': raise OSError('synthetic journal write failure')
        return start(slot)
    monkeypatch.setattr(controller.journal, 'start_slot', fail_next)
    returned_prefix = controller.results
    with pytest.raises(OSError): controller.run()
    assert len(returned_prefix) == 1 and returned_prefix[0]['outcome'] == 'success'
    assert len(sessions) == 1 and sessions[0].closed and len(calls) == 2
    assert len(list(controller.journal.root.glob('*.claim.json'))) == 3  # one slot plus two steps
