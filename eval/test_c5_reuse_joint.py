"""CPU-only raw joint chain, corruption and unknown-result controls."""
import ast
import copy
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

from training import c5_reuse_evidence as ev
from training import c5_reuse_joint as joint
from training import c5_reuse_joint_audit as independent

KEY = bytes(range(32))  # Public CPU fixture key, never a live secret.
IDENTITY = ev.scope('cpu-joint-test')


@pytest.fixture(scope='module')
def complete(tmp_path_factory):
    root = tmp_path_factory.mktemp('joint') / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as session:
        final = session.run40()
        ready = session.readiness
        with pytest.raises(ValueError, match='no_retry'):
            session.run40()
    result = independent.audit_root(root, IDENTITY, KEY, readiness=ready, final=final)
    assert result['synthetic_joint_complete']
    with sqlite3.connect((root / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        rows = independent.ledger_rows(db)
    return {'root': root, 'transport': (root / 'transport/synthetic-journal.jsonl').read_bytes(),
            'native': (root / 'native.jsonl').read_bytes(), 'rows': rows,
            'readiness': ready, 'final': final, 'result': result}


def database(rows):
    db = sqlite3.connect(':memory:')
    db.execute(independent.TABLE)
    db.executemany('INSERT INTO consumed VALUES (?,?,?,?,?)', rows)
    db.commit()
    return db


def replay(bundle, *, native=None, transport=None, rows=None, readiness=True, final=True, key=KEY, identity=IDENTITY):
    with database(bundle['rows'] if rows is None else rows) as db:
        return independent.audit(bundle['transport'] if transport is None else transport,
            bundle['native'] if native is None else native, db, identity, key,
            readiness=bundle['readiness'] if readiness is True else readiness,
            final=bundle['final'] if final is True else final)


def events(raw):
    return [ev.strict(line)['event'] for line in raw.splitlines()]


def chain(values):
    result = b''
    previous = ev.ZERO
    for i, event in enumerate(values):
        r = {'seq': i, 'previous_sha256': previous, 'event': event}
        r['record_sha256'] = ev.sha(r)
        result += ev.canonical(r) + b'\n'
        previous = r['record_sha256']
    return result


def test_complete_40_slots_raw_hmac_sqlite_geometry_and_cleanup(complete):
    r = complete['result']
    assert r['synthetic_slots_cleaned'] == r['synthetic_write_effects'] == 40
    assert r['synthetic_permits_consumed'] == 120 and r['unknown_effects'] == 0
    assert r['synthetic_scores'] == {'base': 20, 'lora': 20, 'paired_net_wins': 0}
    assert r['actual_model_generation_total'] is r['actual_rhino_dispatch_total'] is None
    assert not r['execution_ready'] and not r['external_witness_origin_verified']
    assert replay(complete) == r


@pytest.mark.parametrize('missing', ['readiness', 'final', 'both'])
def test_missing_external_anchor_cannot_certify_coverage(complete, missing):
    r = replay(complete, readiness=None if missing in ('readiness', 'both') else True,
               final=None if missing in ('final', 'both') else True)
    assert not r['synthetic_joint_complete'] and r['synthetic_scores'] is None


@pytest.mark.parametrize('field', ['scope_sha256', 'transport_head_sha256', 'native_head_sha256',
                                  'ledger_rows_sha256', 'transport_records', 'native_records', 'kind'])
def test_final_anchor_cross_binding_rejected(complete, field):
    final = copy.deepcopy(complete['final'])
    final[field] = ev.ZERO if 'sha256' in field else -1
    with pytest.raises(ValueError, match='joint_final_anchor'):
        replay(complete, final=final)


@pytest.mark.parametrize('field', ['scope_sha256', 'spec_sha256', 'runtime_sha256', 'request_id',
    'request_sha256', 'fixture_id', 'slot', 'route', 'operation', 'before_sha256', 'ordinal', 'use_limit', 'kind'])
def test_even_resigned_wrong_permit_identity_or_effect_is_rejected(complete, field):
    values = events(complete['native'])
    p = values[2]['permit']
    p['body'][field] = 99 if type(p['body'][field]) is int else 'wrong'
    # A hostile producer can sign/rechain: the independent expected body still wins.
    p['hmac_sha256'] = joint.hmac.new(KEY, ev.canonical(p['body']), joint.hashlib.sha256).hexdigest()
    p['permit_id'] = ev.sha({k: p[k] for k in ('body', 'hmac_sha256')})
    with pytest.raises(ValueError, match='permit_binding'):
        replay(complete, native=chain(values), final=None)


@pytest.mark.parametrize('kind', ['hmac', 'readback', 'cleanup', 'reorder', 'duplicate', 'missing',
                                 'ack_binding', 'pair_input', 'freeze', 'extra_event', 'receipt_before_consume'])
def test_rehashed_native_tamper_rejected(complete, kind):
    values = events(complete['native'])
    if kind == 'hmac':
        values[2]['permit']['hmac_sha256'] = ev.ZERO
    elif kind == 'readback':
        values[3]['readback'] = []
    elif kind == 'cleanup':
        values[7]['after'] = values[7]['before']
    elif kind == 'reorder':
        values[2], values[4] = values[4], values[2]
    elif kind == 'duplicate':
        values.insert(4, copy.deepcopy(values[3]))
    elif kind == 'missing':
        del values[4]
    elif kind == 'ack_binding':
        values[1]['ack_sha256'] = ev.ZERO
    elif kind == 'pair_input':
        values[1]['paired_input'] = 'different'
    elif kind == 'freeze':
        values[0]['freeze']['runtime_sha256'] = ev.ZERO
    elif kind == 'extra_event':
        values.append({'kind': 'retire', 'reason': 'joint_unknown_no_retry'})
    else:
        del values[2]
    with pytest.raises(ValueError):
        replay(complete, native=chain(values), final=None)


@pytest.mark.parametrize('kind', ['missing', 'extra', 'changed', 'table', 'trigger'])
def test_sqlite_independent_state_disagreement_rejected(complete, kind):
    rows = list(complete['rows'])
    if kind == 'missing':
        rows.pop()
    elif kind == 'extra':
        rows.append((120, 'fake', '{}', 'fake', 'write'))
    elif kind == 'changed':
        row = list(rows[0]); row[3] = 'other'; rows[0] = tuple(row)
    with database(rows) as db:
        if kind == 'table':
            db.execute('CREATE TABLE summary(passed INTEGER)')
        elif kind == 'trigger':
            db.execute('CREATE TRIGGER hidden AFTER INSERT ON consumed BEGIN SELECT 1; END')
        with pytest.raises(ValueError):
            independent.audit(complete['transport'], complete['native'], db, IDENTITY, KEY,
                              readiness=complete['readiness'], final=complete['final'])


@pytest.mark.parametrize('boundary', ['before_permit', 'before_consume', 'after_commit',
                                    'before_effect', 'after_effect', 'after_receipt'])
@pytest.mark.parametrize('operation', ['write', 'read', 'cleanup'])
def test_fault_boundaries_retire_preserve_raw_and_never_retry(tmp_path, boundary, operation):
    root = tmp_path / 'cpu-joint-test-joint'
    def fail(b, slot, op):
        if b == boundary and op == operation:
            raise OSError('CPU injected crash')
    with joint.JointSession(root, IDENTITY, KEY) as s:
        with pytest.raises(OSError):
            s.run40(fault=fail)
        ready = s.readiness
        with pytest.raises(ValueError, match='no_retry'):
            s.run40()
    r = independent.audit_root(root, IDENTITY, KEY, readiness=ready)
    assert r['retired'] and not r['synthetic_joint_complete'] and r['synthetic_scores'] is None
    assert r['unknown_effects'] == int(boundary in ('after_commit', 'before_effect', 'after_effect'))
    before = (root / 'native.jsonl').read_bytes()
    with pytest.raises(FileExistsError):
        joint.JointSession(root, IDENTITY, KEY)
    assert (root / 'native.jsonl').read_bytes() == before


def test_transport_unknown_cannot_issue_any_permit(tmp_path):
    class EOFPeer(joint.SyntheticPeer):
        def read(self, deadline):
            return b''
    root = tmp_path / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as s:
        with pytest.raises(ValueError):
            s.run40(endpoint_factory=EOFPeer)
        ready = s.readiness
    r = independent.audit_root(root, IDENTITY, KEY, readiness=ready)
    assert r['synthetic_permits_consumed'] == 0 and r['retired']
    assert r['actual_model_generation_total'] is None


def test_legal_wrong_geometry_scores_failure_without_repair(complete):
    values = events(complete['native'])
    # Change both routes for pair zero. All permit/DB/HMAC records are rebuilt
    # consistently, so only independent geometric goal comparison finds failure.
    for i, event in enumerate(values):
        if i > 14:
            break
        for k in ('before', 'after', 'readback'):
            if event.get(k):
                event[k][0]['edges'][0] = 99
    for event in values:
        if event['kind'] == 'consume' and event['permit']['body']['slot'] < 2:
            p = event['permit']; old = p['permit_id']
            if p['body']['operation'] != 'write':
                p['body']['before_sha256'] = ev.sha([{'id': p['body']['fixture_id'], 'kind': 'box',
                                                     'units': 'mm', 'edges': [99, 2, 3]}])
            p['hmac_sha256'] = joint.hmac.new(KEY, ev.canonical(p['body']), joint.hashlib.sha256).hexdigest()
            p['permit_id'] = ev.sha({k: p[k] for k in ('body', 'hmac_sha256')})
            for receipt in values:
                if receipt.get('permit_id') == old:
                    receipt['permit_id'] = p['permit_id']
    rows = [(e['permit']['body']['ordinal'], e['permit']['permit_id'], ev.canonical(e['permit']).decode(),
             e['permit']['body']['request_id'], e['permit']['body']['operation'])
            for e in values if e['kind'] == 'consume']
    native = chain(values)
    final = dict(complete['final'], native_head_sha256=ev.strict(native.splitlines()[-1])['record_sha256'],
                 ledger_rows_sha256=ev.sha(rows))
    r = replay(complete, native=native, rows=rows, final=final)
    assert r['synthetic_joint_complete'] and r['synthetic_scores'] == {'base': 19, 'lora': 19, 'paired_net_wins': 0}


@pytest.mark.parametrize('mutation', ['truncate', 'byte', 'identity', 'key', 'summary'])
def test_no_producer_summary_or_missing_bytes_can_replace_raw(complete, mutation):
    native = complete['native']
    kwargs = {}
    if mutation == 'truncate':
        native = native[:-1]
    elif mutation == 'byte':
        native = native.replace(b'cpu-box-00', b'cpu-box-99', 1)
    elif mutation == 'identity':
        kwargs['identity'] = ev.scope('cpu-other')
    elif mutation == 'key':
        kwargs['key'] = b'x' * 32
    else:
        native = ev.canonical({'passed': True, 'slots': 40}) + b'\n'
    with pytest.raises(ValueError):
        replay(complete, native=native, **kwargs)


@pytest.mark.parametrize('bad_scope', ['old', 'formal', 'protocol'])
def test_wrong_scope_rejected_before_mkdir(tmp_path, bad_scope):
    identity = dict(IDENTITY)
    identity['study_id' if bad_scope != 'protocol' else 'protocol'] = {
        'old': 'c5-rhino-paired-20-v1', 'formal': 'c5-rhino-paired-20-reuse-v1', 'protocol': 'old'}[bad_scope]
    root = tmp_path / 'no-create'
    with pytest.raises(ValueError):
        joint.JointSession(root, identity, KEY)
    assert not root.exists()


@pytest.mark.parametrize('drift', ['symlink', 'hardlink', 'mode', 'extra', 'replace'])
def test_native_or_ledger_drift_blocks_effects(tmp_path, drift):
    root = tmp_path / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as s:
        def mutate(b, slot, op):
            if b != 'before_effect' or op != 'write':
                return
            p = root / 'native.jsonl'
            if drift == 'symlink':
                p.rename(root / 'outside'); p.symlink_to(root / 'outside')
            elif drift == 'hardlink':
                os.link(p, tmp_path / 'link')
            elif drift == 'mode':
                p.chmod(0o644)
            elif drift == 'extra':
                (root / 'extra').write_text('x')
            else:
                raw = p.read_bytes(); p.unlink(); p.write_bytes(raw); p.chmod(0o600)
        with pytest.raises(ValueError):
            s.run40(fault=mutate)
        assert not any(e['kind'] == 'effect' for e in events(s.native))


def test_real_threads_cannot_interleave_joint_operations(tmp_path):
    entered, release = threading.Event(), threading.Event()
    failures = []
    with joint.JointSession(tmp_path / 'cpu-joint-test-joint', IDENTITY, KEY) as s:
        def fault(boundary, slot, operation):
            if boundary == 'before_effect':
                entered.set()
                assert release.wait(5)
                raise OSError('CPU stop')
        def run():
            try:
                s.run40(fault=fault)
            except OSError:
                pass
            except BaseException as e:
                failures.append(e)
        thread = threading.Thread(target=run)
        thread.start()
        assert entered.wait(5)
        try:
            with pytest.raises(ValueError, match='already_active'):
                s.run40()
        finally:
            release.set(); thread.join(5)
        assert not thread.is_alive() and not failures
        assert independent.ledger_rows(s.db)[0][0] == 0


def test_independent_auditor_never_imports_producer():
    tree = ast.parse(Path(independent.__file__).read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert 'training.c5_reuse_joint' not in imports
    assert 'training.c5_reuse_transport' not in imports


@pytest.mark.parametrize('drift', ['native_bytes', 'ledger_row', 'ledger_schema'])
def test_logical_drift_detected_before_geometry_effect(tmp_path, drift):
    root = tmp_path / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as s:
        def mutate(boundary, slot, operation):
            if boundary != 'before_effect':
                return
            if drift == 'native_bytes':
                p = root / 'native.jsonl'
                p.write_bytes(p.read_bytes().replace(b'cpu-box-00', b'cpu-box-99'))
            elif drift == 'ledger_row':
                s.db.execute("UPDATE consumed SET request_id='wrong'")
                s.db.commit()
            else:
                s.db.execute('CREATE TABLE rogue(x INTEGER)')
                s.db.commit()
        with pytest.raises(ValueError):
            s.run40(fault=mutate)
        assert not any(e['kind'] == 'effect' for e in events(s.native))


@pytest.mark.parametrize('boundary,operation', [('after_commit', 'write'), ('before_effect', 'write'),
                                              ('after_effect', 'write'), ('after_effect', 'cleanup')])
def test_real_cpu_process_death_keeps_consumption_and_unknown(tmp_path, boundary, operation):
    root = tmp_path / 'cpu-joint-test-joint'
    code = '''
import os, sys
from pathlib import Path
from training.c5_reuse_evidence import scope
from training.c5_reuse_joint import JointSession
def die(boundary, slot, operation):
    if boundary == sys.argv[2] and operation == sys.argv[3]:
        os._exit(71)
with JointSession(Path(sys.argv[1]), scope('cpu-joint-test'), bytes(range(32))) as s:
    s.run40(fault=die)
'''
    r = subprocess.run([sys.executable, '-B', '-c', code, str(root), boundary, operation],
                       cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=10)
    assert r.returncode == 71, r.stderr
    result = independent.audit_root(root, IDENTITY, KEY)
    assert result['unknown_effects'] == 1 and result['synthetic_scores'] is None
    assert not result['synthetic_joint_complete'] and result['actual_rhino_dispatch_total'] is None
    assert result['synthetic_permits_consumed'] == (3 if operation == 'cleanup' else 1)
    with pytest.raises(FileExistsError):
        joint.JointSession(root, IDENTITY, KEY)


def test_torn_native_append_is_never_repaired_or_retried(tmp_path, monkeypatch):
    root = tmp_path / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as s:
        original = os.write
        calls = 0
        def torn(fd, raw):
            nonlocal calls
            if fd == s.fd:
                calls += 1
                if calls == 1:
                    return original(fd, raw[:11])
                raise OSError('CPU storage failure')
            return original(fd, raw)
        monkeypatch.setattr(os, 'write', torn)
        with pytest.raises(OSError):
            s.run40()
        with pytest.raises(ValueError, match='no_retry'):
            s.run40()
    raw = (root / 'native.jsonl').read_bytes()
    assert not raw.endswith(b'\n')
    with pytest.raises(ValueError, match='incomplete'):
        independent.audit_root(root, IDENTITY, KEY)
    assert (root / 'native.jsonl').read_bytes() == raw


def test_sqlite_uniqueness_permit_consumption_cannot_repeat(tmp_path):
    root = tmp_path / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as s:
        def stop(boundary, slot, operation):
            if boundary == 'before_effect':
                raise OSError('CPU stop')
        with pytest.raises(OSError):
            s.run40(fault=stop)
        row = independent.ledger_rows(s.db)[0]
        with pytest.raises(sqlite3.IntegrityError):
            s.db.execute('INSERT INTO consumed VALUES (?,?,?,?,?)', row)
        s.db.rollback()
        assert independent.ledger_rows(s.db) == [row]


def test_scene_readbacks_are_copies_and_wrong_geometry_stays_failure(tmp_path):
    scene = joint.CpuBoxScene(0)
    scene.write_box()
    readback = scene.snapshot()
    readback[0]['edges'][0] = 99
    assert scene.snapshot()[0]['edges'][0] == 1
    class WrongBox(joint.CpuBoxScene):
        def write_box(self):
            super().write_box()
            self.objects[0]['edges'][0] = 99
    root = tmp_path / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as s:
        final = s.run40(geometry_factory=WrongBox)
        ready = s.readiness
    r = independent.audit_root(root, IDENTITY, KEY, readiness=ready, final=final)
    assert r['synthetic_joint_complete'] and r['synthetic_scores'] == {'base': 0, 'lora': 0, 'paired_net_wins': 0}


@pytest.mark.parametrize('kind', ['readback', 'cleanup'])
def test_scene_readback_or_cleanup_failure_never_continues(tmp_path, kind):
    class BrokenScene(joint.CpuBoxScene):
        reads = 0
        def snapshot(self):
            self.reads += 1
            if kind == 'readback' and self.reads == 4:
                return []
            return super().snapshot()
        def cleanup(self):
            if kind != 'cleanup':
                super().cleanup()
    root = tmp_path / 'cpu-joint-test-joint'
    with joint.JointSession(root, IDENTITY, KEY) as s:
        with pytest.raises(ValueError, match='cpu_scene_'):
            s.run40(geometry_factory=BrokenScene)
        assert len(independent.ledger_rows(s.db)) == (1 if kind == 'readback' else 3)
        with pytest.raises(ValueError, match='no_retry'):
            s.run40()
    with pytest.raises(ValueError, match='geometry_readback|cleanup_not_empty'):
        independent.audit_root(root, IDENTITY, KEY)
