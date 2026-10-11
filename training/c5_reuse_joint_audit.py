"""Independent CPU raw replay; never imports the joint-chain producer.

HMAC and SQLite here authenticate only synthetic fixtures. Supplied witnesses
prove byte binding, not independent origin or real model/Rhino coverage.
"""
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import stat

from training import c5_reuse_evidence as ev

MAX_NATIVE = 1024 * 1024
TABLE = ('CREATE TABLE consumed (ordinal INTEGER PRIMARY KEY, '
         'permit_id TEXT UNIQUE NOT NULL, permit_raw TEXT NOT NULL, '
         'request_id TEXT NOT NULL, operation TEXT NOT NULL)')


def freeze(identity):
    ev.validate_scope(identity)
    return {'scope': identity, 'kind': 'cpu_joint_fixture_not_execution_freeze',
            'spec_sha256': ev.sha({'scope': identity, 'synthetic_slots': 40}),
            'runtime_sha256': ev.sha({'scope': identity, 'geometry': 'cpu-box-mm-v1'}),
            'operations': ['write', 'read', 'cleanup'], 'max_permits': 120}


def body(identity, req, operation, before):
    ev.validate_request(req, identity)
    ev.require(req['step'] == 0 and operation in ('write', 'read', 'cleanup'), 'joint_request')
    f = freeze(identity)
    return {'kind': 'cpu_hmac_permit_not_live_grant', 'scope_sha256': ev.sha(identity),
            'spec_sha256': f['spec_sha256'], 'runtime_sha256': f['runtime_sha256'],
            'request_id': req['request_id'], 'request_sha256': ev.raw_sha(ev.wire(req)),
            'fixture_id': 'cpu-box-%02d' % req['slot'], 'slot': req['slot'],
            'route': req['route'], 'operation': operation, 'before_sha256': ev.sha(before),
            'ordinal': req['slot'] * 3 + ('write', 'read', 'cleanup').index(operation),
            'use_limit': 1}


def check_key(key):
    ev.require(type(key) is bytes and len(key) == 32, 'cpu_audit_key')


def check_permit(permit, expected, key):
    check_key(key)
    ev.exact(permit, ('body', 'hmac_sha256', 'permit_id'))
    mac = hmac.new(key, ev.canonical(expected), hashlib.sha256).hexdigest()
    ev.require(ev.canonical(permit['body']) == ev.canonical(expected) and type(permit['hmac_sha256']) is str
               and hmac.compare_digest(permit['hmac_sha256'], mac)
               and permit['permit_id'] == ev.sha({'body': expected, 'hmac_sha256': mac}), 'permit_binding')


def ledger_rows(db):
    """Caller supplies a read-only connection to the bounded CPU evidence DB."""
    ev.require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'ledger_integrity')
    objects = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall()
    ev.require(objects == [('table', 'consumed', TABLE),
                           ('index', 'sqlite_autoindex_consumed_1', None)], 'ledger_schema')
    rows = db.execute('SELECT ordinal,permit_id,permit_raw,request_id,operation '
                      'FROM consumed ORDER BY ordinal').fetchall()
    ev.require(len(rows) <= 120, 'ledger_capacity')
    return rows


def audit(transport_raw, native_raw, db, identity, key, *, readiness=None, final=None):
    """Rebuild permitted effects, paired scores and cleanup from raw artifacts.

    Missing coverage is incomplete/unknown. Corrupt or contradictory evidence
    raises; no counter defaults, transcript repair or producer summaries.
    """
    ev.validate_scope(identity)
    check_key(key)
    t = ev.verify(transport_raw, identity)
    ev.require(type(native_raw) is bytes and 0 < len(native_raw) <= MAX_NATIVE
               and native_raw.endswith(b'\n'), 'native_incomplete')
    lines = native_raw.splitlines()
    ev.require(len(lines) <= 512, 'native_capacity')
    acknowledgements = {}
    transport_genesis = None
    for line in transport_raw.splitlines():
        record = ev.strict(line)
        e = record['event']
        if record['seq'] == 0:
            transport_genesis = record['record_sha256']
        if e['kind'] == 'intent':
            req = ev.strict(e['request_raw'].encode())
            acknowledgements[req['request_id']] = [req, None]
        if e['kind'] == 'ack':
            acknowledgements[e['request_id']][1] = ev.raw_sha(e['response_raw'].encode())
    previous = ev.ZERO
    expected_rows = []
    slot = 0
    phase = 'slot'
    geometry = []
    pending = None
    completed = []
    write_count = 0
    retired = sealed = False
    genesis = None
    for seq, raw in enumerate(lines):
        r = ev.strict(raw)
        ev.exact(r, ('seq', 'previous_sha256', 'event', 'record_sha256'))
        ev.require(type(r['seq']) is int and r['seq'] == seq and r['previous_sha256'] == previous
                   and r['record_sha256'] == ev.sha({k: r[k] for k in r if k != 'record_sha256'})
                   and raw == ev.canonical(r), 'native_chain')
        e = r['event']
        ev.require(type(e) is dict and type(e.get('kind')) is str and not sealed, 'native_event')
        kind = e['kind']
        if seq == 0:
            ev.exact(e, ('kind', 'freeze', 'transport_genesis_sha256'))
            ev.require(kind == 'open' and ev.canonical(e['freeze']) == ev.canonical(freeze(identity))
                       and e['transport_genesis_sha256'] == transport_genesis, 'joint_identity')
            genesis = r['record_sha256']
        elif kind == 'retire':
            ev.exact(e, ('kind', 'reason'))
            ev.require(not retired and e['reason'] == 'joint_unknown_no_retry', 'joint_retirement')
            retired = True
        elif kind == 'seal':
            ev.exact(e, ('kind', 'coverage'))
            ev.require(e['coverage'] == 'cpu_joint_recorded_only', 'joint_seal')
            sealed = True
        else:
            ev.require(not retired and slot < 40, 'joint_no_retry')
            if kind == 'slot':
                ev.exact(e, ('kind', 'request_id', 'ack_sha256', 'baseline', 'paired_input'))
                req = ev.request(identity, slot, 'base' if slot % 2 == 0 else 'lora', 0)
                entry = acknowledgements.get(req['request_id'])
                ev.require(phase == 'slot' and entry is not None and entry[1] is not None
                           and e['request_id'] == req['request_id'] and e['ack_sha256'] == entry[1]
                           and e['baseline'] == [] and e['paired_input'] == 'cpu-pair-%02d' % (slot // 2),
                           'slot_transport_binding')
                geometry = []
                phase = 'write'
            elif kind == 'consume':
                ev.exact(e, ('kind', 'permit'))
                ev.require(phase in ('write', 'read', 'cleanup') and pending is None, 'permit_order')
                expected = body(identity, req, phase, geometry)
                check_permit(e['permit'], expected, key)
                p = e['permit']
                expected_rows.append((expected['ordinal'], p['permit_id'], ev.canonical(p).decode(),
                                      req['request_id'], phase))
                pending = p
            elif kind == 'effect':
                ev.exact(e, ('kind', 'permit_id', 'operation', 'before', 'after', 'readback'))
                ev.require(pending is not None and e['permit_id'] == pending['permit_id']
                           and e['operation'] == phase and ev.canonical(e['before']) == ev.canonical(geometry), 'effect_admission')
                if phase == 'write':
                    # Independent semantic validity, not producer helper import.
                    after = e['after']
                    ev.require(type(after) is list and len(after) == 1, 'geometry_shape')
                    box = after[0]
                    ev.exact(box, ('id', 'kind', 'units', 'edges'))
                    ev.require(box['id'] == 'cpu-box-%02d' % slot and box['kind'] == 'box'
                               and box['units'] == 'mm' and type(box['edges']) is list
                               and len(box['edges']) == 3
                               and all(type(x) is int and 1 <= x <= 100 for x in box['edges']), 'geometry_validity')
                    geometry = after
                    write_count += 1
                    phase = 'read'
                elif phase == 'read':
                    ev.require(ev.canonical(e['after']) == ev.canonical(geometry), 'read_mutation')
                    # Independent fixture goal: pair-equivalent box [pair+1,2,3].
                    expected_box = [{'id': 'cpu-box-%02d' % slot, 'kind': 'box',
                                     'units': 'mm', 'edges': [slot // 2 + 1, 2, 3]}]
                    completed.append({'slot': slot, 'route': req['route'],
                                      'success': geometry == expected_box})
                    phase = 'cleanup'
                else:
                    ev.require(e['after'] == [], 'cleanup_not_empty')
                    geometry = []
                    slot += 1
                    phase = 'slot'
                ev.require(ev.canonical(e['after']) == ev.canonical(geometry)
                           and ev.canonical(e['readback']) == ev.canonical(geometry), 'geometry_readback')
                pending = None
            else:
                raise ValueError('joint_event_unknown')
        previous = r['record_sha256']
    rows = ledger_rows(db)
    # A DB commit with no matching durable native event is an unknown gap,
    # never a dispatch count of zero. Every row must itself still authenticate.
    ev.require(rows[:len(expected_rows)] == expected_rows, 'ledger_raw_mismatch')
    gap = rows[len(expected_rows):]
    ev.require(not gap or (len(gap) == 1 and (retired or not sealed)), 'ledger_unrecorded')
    if gap:
        ev.require(phase in ('write', 'read', 'cleanup') and pending is None, 'ledger_gap_order')
        p = ev.strict(gap[0][2].encode())
        expected = body(identity, req, phase, geometry)
        check_permit(p, expected, key)
        ev.require(gap[0] == (expected['ordinal'], p['permit_id'], ev.canonical(p).decode(),
                             req['request_id'], phase), 'ledger_gap_binding')
    expected_readiness = {'kind': 'external_cpu_joint_readiness', 'scope_sha256': ev.sha(identity),
                          'transport_genesis_sha256': transport_genesis, 'native_genesis_sha256': genesis}
    expected_final = {'kind': 'external_cpu_joint_final', 'scope_sha256': ev.sha(identity),
                      'transport_head_sha256': t['head_sha256'], 'transport_records': t['records'],
                      'native_head_sha256': previous, 'native_records': len(lines),
                      'ledger_rows_sha256': ev.sha(rows)}
    if readiness is not None:
        ev.require(readiness == expected_readiness, 'joint_readiness_anchor')
    if final is not None:
        ev.require(sealed and t['sealed'] and final == expected_final, 'joint_final_anchor')
    complete = (sealed and t['sealed'] and not retired and not t['retired'] and slot == 40
                and phase == 'slot' and pending is None and not gap
                and t['request_intents'] == t['acknowledged_requests'] == 40
                and t['confirmed_synthetic_generation_receipts'] == 80
                and readiness is not None and final is not None)
    base = sum(x['success'] for x in completed if x['route'] == 'base')
    lora = sum(x['success'] for x in completed if x['route'] == 'lora')
    return {'status': 'cpu_joint_raw_recomputed_not_live_authority',
            'synthetic_joint_complete': complete, 'synthetic_slots_cleaned': slot,
            'synthetic_permits_consumed': len(rows), 'synthetic_write_effects': write_count,
            'synthetic_scores': {'base': base, 'lora': lora, 'paired_net_wins': lora - base}
                if complete else None,
            'unknown_effects': int(pending is not None) + len(gap),
            'retired': retired or t['retired'] or pending is not None or bool(gap),
            'retirement_recorded': retired or t['retired'], 'admission_consumed': True,
            'replay_allowed': False, 'native_head_sha256': previous,
            'native_genesis_sha256': genesis, 'native_records': len(lines),
            'ledger_rows_sha256': ev.sha(rows), 'actual_model_generation_total': None,
            'actual_rhino_dispatch_total': None, 'external_witness_origin_verified': False,
            'execution_ready': False}


def audit_root(root, identity, key, *, readiness=None, final=None):
    """Read only the three fixed CPU artifacts; do not open arbitrary evidence."""
    ev.validate_scope(identity)
    check_key(key)
    root = Path(root)
    ev.require(root.is_absolute() and root.resolve() == root
               and root.name == identity['instance_id'] + '-joint', 'joint_audit_root')
    ev.require(set(os.listdir(root)) == {'native.jsonl', 'ledger.sqlite', 'transport'}, 'joint_audit_inventory')
    for directory in (root, root / 'transport'):
        st = directory.lstat()
        ev.require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()
                   and stat.S_IMODE(st.st_mode) == 0o700, 'joint_audit_directory')
    ev.require(os.listdir(root / 'transport') == ['synthetic-journal.jsonl'], 'joint_audit_inventory')
    raw = []
    held = []
    try:
        for name, limit in (('native.jsonl', MAX_NATIVE), ('transport/synthetic-journal.jsonl', ev.MAX_JOURNAL),
                            ('ledger.sqlite', 4 * 1024 * 1024)):
            path = root / name
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            held.append((path, fd, os.fstat(fd)))
            st = os.fstat(fd)
            ev.require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid()
                       and stat.S_IMODE(st.st_mode) == 0o600 and 0 < st.st_size <= limit, 'joint_audit_file')
            if name != 'ledger.sqlite':
                value = os.pread(fd, st.st_size + 1, 0)
                ev.require(len(value) == st.st_size, 'joint_audit_read')
                raw.append(value)
        with sqlite3.connect((root / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            result = audit(raw[1], raw[0], db, identity, key, readiness=readiness, final=final)
        for path, fd, before in held:
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            after, named = os.fstat(fd), path.lstat()
            ev.require(all(getattr(before, f) == getattr(after, f) == getattr(named, f) for f in fields),
                       'joint_audit_file_drift')
        return result
    finally:
        for _, fd, _ in held:
            os.close(fd)
