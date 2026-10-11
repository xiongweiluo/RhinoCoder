"""Synthetic CPU evidence only. No original cases, live grants or connections."""
import copy
import ast
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from training import c5_reuse_evidence as ev
from training.c5_reuse_transport import PipeEndpoint, SyntheticTransport


def ready(journal):
    witness = {'kind': 'external_cpu_readiness', 'scope_sha256': ev.sha(journal.identity),
               'genesis_sha256': journal.summary['genesis_sha256']}
    journal.append({'kind': 'baseline', 'witness': witness})
    return witness


def finish(journal):
    journal.append({'kind': 'seal', 'coverage': 'synthetic_recorded_session_only'})
    return {'kind': 'external_cpu_final_seal', 'scope_sha256': ev.sha(journal.identity),
            'last_record_sha256': journal.summary['head_sha256'], 'records': journal.summary['records']}


class Peer:
    """Small injected fake: capture exact bytes and synthesize a bounded reply."""
    def __init__(self, *, chunk=17, failure=None, reply=None):
        self.chunk, self.failure, self.reply = chunk, failure, reply
        self.sent = b''
        self.writes = self.reads = 0

    def write(self, remaining, deadline):
        self.writes += 1
        if self.failure == 'broken_before_write':
            raise BrokenPipeError()
        if self.failure == 'partial_then_broken' and self.writes > 1:
            raise BrokenPipeError()
        if self.failure == 'zero_write':
            return 0
        if self.failure == 'invalid_write_count':
            return len(remaining) + 1
        n = min(self.chunk, len(remaining))
        self.sent += remaining[:n]
        return n

    def read(self, deadline):
        self.reads += 1
        if self.failure == 'read_timeout':
            raise TimeoutError()
        if self.failure == 'eof':
            return b''
        if self.failure == 'partial_eof':
            return b'{"protocol":' if self.reads == 1 else b''
        if self.failure == 'oversize':
            return b'x' * (ev.MAX_FRAME + 1)
        if self.failure == 'wrong_type':
            return 'not bytes'
        reply = self.reply if self.reply is not None else ev.wire(ev.response(ev.strict(self.sent)))
        self.reply, chunk = reply[self.chunk:], reply[:self.chunk]
        return chunk


@pytest.fixture
def journal(tmp_path):
    with ev.SyntheticJournal(tmp_path / 'cpu', ev.scope('cpu-test'), create=True) as j:
        ready(j)
        yield j


def test_partial_writes_exactly_once_and_independent_raw_replay(journal):
    peer = Peer(chunk=7)
    answer = SyntheticTransport(journal, peer).exchange(0, 'base')
    assert peer.sent == ev.wire(ev.request(journal.identity, 0, 'base', 0))
    assert len(answer['receipts']) == 2
    r = ev.verify(journal.raw, journal.identity)
    assert (r['request_intents'], r['complete_frames_recorded_sent'], r['acknowledged_requests']) == (1, 1, 1)
    assert r['confirmed_synthetic_generation_receipts'] == 2
    assert r['actual_model_generation_total'] is r['actual_rhino_dispatch_total'] is None
    assert not r['synthetic_recorded_coverage_complete']


@pytest.mark.parametrize('failure', ['broken_before_write', 'partial_then_broken', 'zero_write',
    'invalid_write_count', 'read_timeout', 'eof', 'partial_eof', 'oversize', 'wrong_type'])
def test_unknown_blocks_all_requests_even_different_slot_after_reopen(journal, failure):
    peer = Peer(failure=failure)
    transport = SyntheticTransport(journal, peer)
    with pytest.raises((ValueError, BrokenPipeError, TimeoutError)):
        transport.exchange(0, 'base')
    calls = peer.writes
    r = ev.verify(journal.raw, journal.identity)
    assert r['retired'] and r['unresolved_requests'] == 1
    assert r['acknowledged_requests'] == 0 and r['actual_model_generation_total'] is None
    with pytest.raises(ValueError, match='no_retry'):
        transport.exchange(1, 'lora')
    assert peer.writes == calls
    root, identity = journal.root, journal.identity
    journal.close()
    with ev.SyntheticJournal(root, identity) as restored:
        with pytest.raises(ValueError, match='no_retry'):
            SyntheticTransport(restored, peer).exchange(2, 'base')
    assert peer.writes == calls


@pytest.mark.parametrize('mutation', ['study', 'request', 'digest', 'status', 'raw_hash', 'stage',
                                      'extra_key', 'extra_frame', 'partial_tail', 'duplicate_key', 'nan'])
def test_bad_or_unsolicited_ack_not_accepted(journal, mutation):
    sent = ev.request(journal.identity, 0, 'base', 0)
    reply = ev.response(sent)
    if mutation == 'study':
        reply['scope_sha256'] = ev.sha(ev.scope('cpu-other'))
    elif mutation == 'request':
        reply['request_id'] = ev.sha('late-other-request')
    elif mutation == 'digest':
        reply['request_sha256'] = ev.ZERO
    elif mutation == 'status':
        reply['status'] = 'permission_to_write'
    elif mutation == 'raw_hash':
        reply['receipts'][0]['output_sha256'] = ev.ZERO
    elif mutation == 'stage':
        reply['receipts'][0]['stage'] = 'invocation'
    elif mutation == 'extra_key':
        reply['repair_allowed'] = True
    raw = ev.wire(reply)
    if mutation == 'extra_frame':
        raw += raw
    elif mutation == 'partial_tail':
        raw += b'{'
    elif mutation == 'duplicate_key':
        raw = b'{"a":1,"a":2}\n'
    elif mutation == 'nan':
        raw = b'{"a":NaN}\n'
    # One read contains the whole malformed frame, including trailing bytes.
    peer = Peer(chunk=ev.MAX_FRAME, reply=raw)
    with pytest.raises(ValueError):
        SyntheticTransport(journal, peer).exchange(0, 'base')
    assert journal.summary['retired'] and journal.summary['acknowledged_requests'] == 0
    assert journal.summary['recorded_response_bytes'] == len(raw)


def test_intent_is_fsynced_before_any_io(journal, monkeypatch):
    peer = Peer()
    original = os.fsync
    calls = []
    def sync(fd):
        calls.append(fd)
        assert peer.writes == 0
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(os, 'fsync', sync)
    with pytest.raises(OSError):
        SyntheticTransport(journal, peer).exchange(0, 'base')
    assert calls and peer.writes == 0 and journal.poisoned
    monkeypatch.setattr(os, 'fsync', original)
    with pytest.raises(ValueError, match='poisoned'):
        journal.append({'kind': 'retire', 'reason': 'manual_cpu_stop'})
    root, identity = journal.root, journal.identity
    journal.close()
    # Even a fully visible append whose fsync ACK failed consumes the intent.
    with ev.SyntheticJournal(root, identity) as reopened:
        assert reopened.summary['unresolved_requests'] == 1
        assert SyntheticTransport(reopened, peer).blocked


def test_crash_after_intent_before_sent_is_unknown_not_zero(journal):
    sent = ev.request(journal.identity, 0, 'base', 0)
    journal.append({'kind': 'intent', 'request_raw': ev.wire(sent).decode()})
    root, identity = journal.root, journal.identity
    journal.close()
    with ev.SyntheticJournal(root, identity) as recovered:
        r = recovered.summary
        assert r['complete_frames_recorded_sent'] == 0 and r['unresolved_requests'] == 1
        assert r['actual_model_generation_total'] is None
        assert SyntheticTransport(recovered, Peer()).blocked


def test_crash_after_ack_does_not_replay_consumed_request(journal):
    SyntheticTransport(journal, Peer()).exchange(0, 'base')
    root, identity = journal.root, journal.identity
    journal.close()
    with ev.SyntheticJournal(root, identity) as recovered:
        peer = Peer()
        with pytest.raises(ValueError, match='request_replay'):
            SyntheticTransport(recovered, peer).exchange(0, 'base')
        assert peer.writes == 0


@pytest.mark.parametrize('point', ['during_write', 'after_write', 'after_read', 'after_ack'])
def test_whole_exchange_deadline_not_just_first_byte(journal, point):
    now = [0.0]
    peer = Peer(chunk=ev.MAX_FRAME)
    old_write, old_read, old_append = peer.write, peer.read, journal.append
    def write(data, deadline):
        if point == 'during_write':
            now[0] = 1.1
        result = old_write(data, deadline)
        if point == 'after_write':
            now[0] = 1.1
        return result
    def read(deadline):
        result = old_read(deadline)
        if point == 'after_read':
            now[0] = 1.1
        return result
    def append(event):
        old_append(event)
        if point == 'after_ack' and event['kind'] == 'ack':
            now[0] = 1.1
    peer.write, peer.read, journal.append = write, read, append
    with pytest.raises(ValueError):
        SyntheticTransport(journal, peer, clock=lambda: now[0]).exchange(0, 'base')
    assert journal.summary['retired']
    assert journal.summary['acknowledged_requests'] == (1 if point == 'after_ack' else 0)


def test_backward_clock_retires_without_send(journal):
    times = iter([2.0, 1.0])
    peer = Peer()
    with pytest.raises(ValueError):
        SyntheticTransport(journal, peer, clock=lambda: next(times)).exchange(0, 'base')
    assert peer.writes == 0 and journal.summary['retired']


def test_baseline_and_final_are_distinct_and_coverage_remains_synthetic(journal):
    baseline = {'kind': 'external_cpu_readiness', 'scope_sha256': ev.sha(journal.identity),
                'genesis_sha256': journal.summary['genesis_sha256']}
    SyntheticTransport(journal, Peer()).exchange(0, 'base')
    final = finish(journal)
    r = ev.verify(journal.raw, journal.identity, baseline, final)
    assert r['synthetic_recorded_coverage_complete']
    assert not r['external_witness_origin_verified'] and not r['execution_ready']
    assert r['actual_model_generation_total'] is None
    with pytest.raises(ValueError):
        ev.verify(journal.raw, journal.identity, baseline, baseline)
    with pytest.raises(ValueError):
        ev.verify(journal.raw, journal.identity, final, final)
    with pytest.raises(ValueError, match='event_after_seal'):
        journal.append({'kind': 'retire', 'reason': 'manual_cpu_stop'})


def test_deleted_final_tail_cannot_pass_external_anchor(journal):
    SyntheticTransport(journal, Peer()).exchange(0, 'base')
    final = finish(journal)
    truncated = b'\n'.join(journal.raw.splitlines()[:-1]) + b'\n'
    with pytest.raises(ValueError, match='external_final'):
        ev.verify(truncated, journal.identity, final=final)
    assert not ev.verify(truncated, journal.identity)['synthetic_recorded_coverage_complete']


@pytest.mark.parametrize('mutation', ['modify', 'delete_middle', 'reorder', 'torn', 'duplicate', 'other_scope'])
def test_raw_chain_tamper_or_loss_refused(journal, mutation):
    SyntheticTransport(journal, Peer()).exchange(0, 'base')
    lines = journal.raw.splitlines()
    identity = journal.identity
    if mutation == 'modify':
        obj = ev.strict(lines[2]); obj['event']['request_raw'] = '{}\n'
        lines[2] = ev.canonical(obj)
    elif mutation == 'delete_middle':
        del lines[2]
    elif mutation == 'reorder':
        lines[2], lines[3] = lines[3], lines[2]
    elif mutation == 'duplicate':
        lines.append(lines[-1])
    elif mutation == 'other_scope':
        identity = ev.scope('cpu-another')
    raw = b'\n'.join(lines) + b'\n'
    if mutation == 'torn':
        raw = raw[:-5]
    with pytest.raises(ValueError):
        ev.verify(raw, identity)


def test_rehashed_forgery_still_checked_against_raw_state_machine(journal):
    SyntheticTransport(journal, Peer()).exchange(0, 'base')
    events = [ev.strict(line)['event'] for line in journal.raw.splitlines()]
    events.append(copy.deepcopy(events[-1]))  # duplicate ACK even after recomputing every hash
    previous = ev.ZERO
    raw = b''
    for i, event in enumerate(events):
        item = ev._record(i, previous, event)
        raw += ev.canonical(item) + b'\n'
        previous = item['record_sha256']
    with pytest.raises(ValueError, match='duplicate_ack'):
        ev.verify(raw, journal.identity)


def test_ack_without_original_received_bytes_is_not_reconstruction(journal):
    req = ev.request(journal.identity, 0, 'base', 0)
    journal.append({'kind': 'intent', 'request_raw': ev.wire(req).decode()})
    journal.append({'kind': 'sent', 'request_id': req['request_id'], 'bytes': len(ev.wire(req))})
    with pytest.raises(ValueError, match='response_serialization'):
        journal.append({'kind': 'ack', 'request_id': req['request_id'],
                        'response_raw': ev.wire(ev.response(req)).decode()})
    assert journal.summary['unresolved_requests'] == 1


def test_preexisting_sent_without_ack_is_never_replayed(journal):
    req = ev.request(journal.identity, 0, 'base', 0)
    journal.append({'kind': 'intent', 'request_raw': ev.wire(req).decode()})
    journal.append({'kind': 'sent', 'request_id': req['request_id'], 'bytes': len(ev.wire(req))})
    peer = Peer()
    with pytest.raises(ValueError, match='no_retry'):
        SyntheticTransport(journal, peer).exchange(1, 'lora')
    assert peer.writes == 0 and journal.summary['actual_model_generation_total'] is None


@pytest.mark.parametrize('field', ['head', 'scope', 'count', 'boolean_count'])
def test_final_witness_binding_drift(journal, field):
    final = finish(journal)
    if field == 'head': final['last_record_sha256'] = ev.ZERO
    if field == 'scope': final['scope_sha256'] = ev.ZERO
    if field == 'count': final['records'] += 1
    if field == 'boolean_count': final['records'] = True
    with pytest.raises(ValueError, match='external_final'):
        ev.verify(journal.raw, journal.identity, final=final)


def test_manual_cpu_stop_is_durable_and_not_a_remote_release_claim(journal):
    journal.append({'kind': 'retire', 'reason': 'manual_cpu_stop'})
    final = finish(journal)
    r = ev.verify(journal.raw, journal.identity, final=final)
    assert r['retired'] and not r['synthetic_recorded_coverage_complete']
    assert r['actual_model_generation_total'] is r['actual_rhino_dispatch_total'] is None
    with pytest.raises(ValueError, match='no_retry'):
        SyntheticTransport(journal, Peer()).exchange(0, 'base')


def test_live_dispatch_before_ack_is_refused(journal):
    req = ev.request(journal.identity, 0, 'base', 0)
    journal.append({'kind': 'intent', 'request_raw': ev.wire(req).decode()})
    with pytest.raises(ValueError, match='dispatch_evidence'):
        journal.append({'kind': 'dispatch', 'request_id': req['request_id'], 'effect': 'write',
                        'synthetic_permission_sha256': ev.sha('synthetic')})


@pytest.mark.parametrize('mutation', ['file_mode', 'hardlink', 'replace', 'directory_mode', 'extra_file'])
def test_live_store_metadata_drift_blocks_before_io(journal, tmp_path, mutation):
    path = journal.root / 'synthetic-journal.jsonl'
    if mutation == 'file_mode': path.chmod(0o644)
    if mutation == 'hardlink': os.link(path, tmp_path / 'link')
    if mutation == 'replace':
        path.rename(journal.root / 'original'); path.write_bytes(journal.raw); path.chmod(0o600)
    if mutation == 'directory_mode': journal.root.chmod(0o755)
    if mutation == 'extra_file': (journal.root / 'extra').write_bytes(b'')
    peer = Peer()
    with pytest.raises(ValueError):
        SyntheticTransport(journal, peer).exchange(0, 'base')
    assert peer.writes == 0


def test_capacity_stops_without_repair_or_send(journal, monkeypatch):
    monkeypatch.setattr(ev, 'MAX_RECORDS', journal.summary['records'])
    peer = Peer()
    with pytest.raises(ValueError, match='journal_capacity'):
        SyntheticTransport(journal, peer).exchange(0, 'base')
    assert peer.writes == 0


def test_step_without_confirmed_predecessor_cannot_send(journal):
    peer = Peer()
    with pytest.raises(ValueError, match='step_predecessor'):
        SyntheticTransport(journal, peer).exchange(0, 'base', 1)
    assert peer.writes == 0


def test_route_cannot_be_changed_to_relabel_same_slot(journal):
    SyntheticTransport(journal, Peer()).exchange(0, 'base')
    peer = Peer()
    with pytest.raises(ValueError, match='synthetic_schedule'):
        SyntheticTransport(journal, peer).exchange(0, 'lora')
    assert peer.writes == 0


def test_modules_do_not_import_live_or_parent_implementation():
    root = Path(__file__).resolve().parents[1]
    allowed = {'fcntl', 'hashlib', 'json', 'os', 'pathlib', 're', 'stat', 'threading', 'selectors', 'time',
               'training.c5_reuse_evidence'}
    for name in ('training/c5_reuse_evidence.py', 'training/c5_reuse_transport.py'):
        for node in ast.walk(ast.parse((root / name).read_text())):
            if isinstance(node, ast.Import):
                assert {a.name for a in node.names} <= allowed
            if isinstance(node, ast.ImportFrom):
                assert node.module in allowed


def test_producer_counters_cannot_hide_unresolved_raw_intent(journal):
    req = ev.request(journal.identity, 0, 'base', 0)
    journal.append({'kind': 'intent', 'request_raw': ev.wire(req).decode()})
    # Deliberately forge only the producer's in-memory convenience summary.
    journal.summary['unresolved_requests'] = 0
    peer = Peer()
    with pytest.raises(ValueError, match='intent_admission'):
        SyntheticTransport(journal, peer).exchange(1, 'lora')
    assert peer.writes == 0
    assert ev.verify(journal.raw, journal.identity)['unresolved_requests'] == 1


def test_invalid_utf8_original_is_retained_before_rejection(journal):
    peer = Peer(chunk=ev.MAX_FRAME, reply=b'\xff\n')
    with pytest.raises(UnicodeDecodeError):
        SyntheticTransport(journal, peer).exchange(0, 'base')
    assert journal.summary['recorded_response_bytes'] == 2
    assert journal.summary['retired']


def test_large_noncanonical_json_is_not_repaired(journal):
    req = ev.request(journal.identity, 0, 'base', 0)
    raw = ev.canonical(ev.response(req)).replace(b',', b', ') + b'\n'
    with pytest.raises(ValueError, match='response_serialization'):
        SyntheticTransport(journal, Peer(chunk=ev.MAX_FRAME, reply=raw)).exchange(0, 'base')
    assert journal.summary['recorded_response_bytes'] == len(raw)


def test_torn_disk_append_is_not_repaired_or_sent(journal, monkeypatch):
    original = os.write
    writes = [0]
    def partial(fd, raw):
        writes[0] += 1
        if writes[0] == 1:
            return original(fd, raw[:5])
        raise OSError('synthetic storage interruption')
    monkeypatch.setattr(os, 'write', partial)
    peer = Peer()
    with pytest.raises(OSError):
        SyntheticTransport(journal, peer).exchange(0, 'base')
    assert peer.writes == 0 and journal.poisoned
    root, identity = journal.root, journal.identity
    journal.close()
    with pytest.raises(ValueError, match='journal_incomplete'):
        ev.SyntheticJournal(root, identity)


@pytest.mark.parametrize('wrapper', ['same', 'another'])
def test_reentrant_or_concurrent_wrapper_cannot_send_second_request(journal, wrapper):
    peer = Peer(chunk=ev.MAX_FRAME)
    transport = SyntheticTransport(journal, peer)
    other_peer = Peer()
    other = transport if wrapper == 'same' else SyntheticTransport(journal, other_peer)
    original = peer.write
    def write(data, deadline):
        with pytest.raises(ValueError, match='exchange_already_active'):
            other.exchange(1, 'lora')
        return original(data, deadline)
    peer.write = write
    transport.exchange(0, 'base')
    assert journal.summary['request_intents'] == 1 and other_peer.writes == 0


def test_exchange_lock_released_after_failure_but_durable_retirement_remains(journal):
    transport = SyntheticTransport(journal, Peer(failure='eof'))
    with pytest.raises(ValueError):
        transport.exchange(0, 'base')
    assert not journal.exchange_lock.locked()
    with pytest.raises(ValueError, match='no_retry'):
        SyntheticTransport(journal, Peer()).exchange(1, 'lora')


def test_actual_cpu_threads_share_one_outstanding_exchange(journal):
    entered, release = threading.Event(), threading.Event()
    peer = Peer(chunk=ev.MAX_FRAME)
    original = peer.write
    errors = []
    def write(data, deadline):
        entered.set()
        assert release.wait(3)
        return original(data, deadline)
    peer.write = write
    def worker():
        try:
            SyntheticTransport(journal, peer, timeout=5).exchange(0, 'base')
        except BaseException as exc:
            errors.append(type(exc).__name__)
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(3)
        second = Peer()
        with pytest.raises(ValueError, match='exchange_already_active'):
            SyntheticTransport(journal, second).exchange(1, 'lora')
        assert second.writes == 0
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive() and not errors
    assert journal.summary['request_intents'] == journal.summary['acknowledged_requests'] == 1


def test_synthetic_permission_and_write_observation_cannot_dispatch_twice(journal):
    reply = SyntheticTransport(journal, Peer()).exchange(0, 'base')
    event = {'kind': 'dispatch', 'request_id': reply['request_id'], 'effect': 'write',
             'synthetic_permission_sha256': ev.sha('not a live HMAC permission')}
    journal.append(event)
    with pytest.raises(ValueError, match='dispatch_evidence'):
        journal.append(event)
    assert journal.summary['synthetic_write_observations'] == 1
    assert journal.summary['actual_rhino_dispatch_total'] is None


def test_missing_readiness_blocks_before_io(tmp_path):
    with ev.SyntheticJournal(tmp_path / 'cpu', ev.scope('cpu-no-ready'), create=True) as j:
        peer = Peer()
        with pytest.raises(ValueError, match='intent_admission'):
            SyntheticTransport(j, peer).exchange(0, 'base')
        assert peer.writes == 0


def test_exact_scope_survives_restart_and_exclusive_lock(journal):
    with pytest.raises(BlockingIOError):
        ev.SyntheticJournal(journal.root, journal.identity)
    root = journal.root
    journal.close()
    with pytest.raises(ValueError, match='journal_scope'):
        ev.SyntheticJournal(root, ev.scope('cpu-new-label'))
    with pytest.raises(FileExistsError):
        ev.SyntheticJournal(root, ev.scope('cpu-new-label'), create=True)


@pytest.mark.parametrize('mutation', ['directory_mode', 'file_mode', 'hardlink', 'symlink', 'extra_file', 'torn'])
def test_private_synthetic_store_drift_refused(journal, tmp_path, mutation):
    root, identity = journal.root, journal.identity
    journal.close()
    path = root / 'synthetic-journal.jsonl'
    if mutation == 'directory_mode':
        root.chmod(0o755)
    elif mutation == 'file_mode':
        path.chmod(0o644)
    elif mutation == 'hardlink':
        os.link(path, tmp_path / 'link')
    elif mutation == 'symlink':
        path.rename(tmp_path / 'original'); path.symlink_to(tmp_path / 'original')
    elif mutation == 'extra_file':
        (root / 'unknown.json').write_bytes(b'{}')
    else:
        with path.open('ab') as stream:
            stream.write(b'{')
    with pytest.raises((ValueError, OSError)):
        ev.SyntheticJournal(root, identity)


@pytest.mark.parametrize('slot,route,step', [(True, 'base', 0), (40, 'base', 0), (-1, 'base', 0),
    (0, 'other', 0), (0, 'base', True), (0, 'base', 3), (0, 'base', -1)])
def test_bounded_synthetic_request_only(journal, slot, route, step):
    peer = Peer()
    with pytest.raises(ValueError):
        SyntheticTransport(journal, peer).exchange(slot, route, step)
    assert peer.writes == 0


@pytest.mark.parametrize('field,value', [('study_id', 'c5-rhino-paired-20-v1'),
    ('study_id', 'c5-rhino-paired-20-reuse-v1'), ('protocol', 'c5-modelbridge-development-v1'),
    ('execution_kind', 'formal'), ('instance_id', 'live-host')])
def test_formal_or_old_identity_cannot_create_store(tmp_path, field, value):
    identity = ev.scope('cpu-test'); identity[field] = value
    with pytest.raises(ValueError):
        ev.SyntheticJournal(tmp_path / 'cpu', identity, create=True)
    assert not (tmp_path / 'cpu').exists()


@pytest.mark.parametrize('timeout', [True, 0, -1, 181, float('nan'), float('inf')])
def test_timeout_invalid(journal, timeout):
    with pytest.raises(ValueError):
        SyntheticTransport(journal, Peer(), timeout=timeout)


def test_40_slot_cpu_chain_counts_and_distinct_routes(journal):
    baseline = {'kind': 'external_cpu_readiness', 'scope_sha256': ev.sha(journal.identity),
                'genesis_sha256': journal.summary['genesis_sha256']}
    transport = SyntheticTransport(journal, Peer(chunk=ev.MAX_FRAME))
    for slot in range(40):
        transport.endpoint = Peer(chunk=ev.MAX_FRAME)
        reply = transport.exchange(slot, 'base' if slot % 2 == 0 else 'lora')
        journal.append({'kind': 'dispatch', 'request_id': reply['request_id'], 'effect': 'read',
                        'synthetic_permission_sha256': ev.sha({'slot': slot})})
    final = finish(journal)
    r = ev.verify(journal.raw, journal.identity, baseline, final)
    assert r['request_intents'] == r['acknowledged_requests'] == r['synthetic_dispatch_observations'] == 40
    assert r['confirmed_synthetic_generation_receipts'] == 80
    assert r['synthetic_recorded_coverage_complete'] and r['actual_model_generation_total'] is None


def test_request_capacity_refuses_57th_without_send(journal):
    transport = SyntheticTransport(journal, Peer(chunk=ev.MAX_FRAME))
    for i in range(56):
        transport.endpoint = Peer(chunk=ev.MAX_FRAME)
        transport.exchange(i // 3, 'base' if (i // 3) % 2 == 0 else 'lora', i % 3)
    transport.endpoint = Peer()
    with pytest.raises(ValueError, match='request_capacity'):
        transport.exchange(19, 'lora', 0)
    assert transport.endpoint.writes == 0


@pytest.mark.parametrize('mode', ['good', 'half_eof', 'wrong_binding', 'duplicate', 'late'])
def test_real_framed_cpu_subprocess_faults(journal, mode):
    # Explicit synthetic fixture, standard-library interpreter only. Not SSH.
    script = '''import json,sys,time
from training.c5_reuse_evidence import strict,response,wire
req = strict(sys.stdin.buffer.readline())
raw = wire(response(req))
mode = sys.argv[1]
if mode == 'half_eof': raw = raw[:20]
if mode == 'wrong_binding':
    value = response(req); value['request_id'] = '0'*64; raw = wire(value)
if mode == 'duplicate': raw += raw
if mode == 'late': time.sleep(0.3)
sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
'''
    proc = subprocess.Popen([sys.executable, '-S', '-B', '-c', script, mode],
        cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    try:
        endpoint = PipeEndpoint(proc.stdin.fileno(), proc.stdout.fileno())
        transport = SyntheticTransport(journal, endpoint, timeout=0.15 if mode == 'late' else 3)
        if mode == 'good':
            assert transport.exchange(0, 'base')['status'] == 'synthetic_ack_not_permission'
        else:
            with pytest.raises(ValueError):
                transport.exchange(0, 'base')
            assert journal.summary['retired'] and journal.summary['actual_model_generation_total'] is None
    finally:
        proc.stdin.close()
        proc.wait(timeout=5)
        proc.stdout.close(); proc.stderr.close()
