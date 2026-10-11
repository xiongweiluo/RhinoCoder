"""CPU-only reuse engineering evidence. No grants, private cases or live APIs.

This prototype accepts only explicitly synthetic identities and payloads. Its
independent reducer replays immutable raw events, not producer counters. A hash
chain proves consistency with a supplied anchor, not the anchor's provenance,
physical generation, absence of other sessions, or a filesystem adversary.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading

PROTOCOL = 'c5-reuse-cpu-synthetic-v1'
STUDY = 'c5-rhino-paired-20-reuse-v1-synthetic-engineering'
MAX_FRAME = 65536
MAX_RECORD = 262144
MAX_RECORDS = 4096
MAX_JOURNAL = 64 * 1024 * 1024
ZERO = '0' * 64


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw, limit=MAX_RECORD):
    require(type(raw) is bytes and 0 < len(raw) <= limit, 'json_size')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'schema_keys')


def is_sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def scope(instance):
    require(type(instance) is str and re.fullmatch('cpu-[a-z0-9-]{1,48}', instance), 'synthetic_instance')
    return {'protocol': PROTOCOL, 'study_id': STUDY, 'instance_id': instance,
            'execution_kind': 'cpu_synthetic_not_execution_authority'}


def validate_scope(value):
    exact(value, ('protocol', 'study_id', 'instance_id', 'execution_kind'))
    require(value == scope(value['instance_id']), 'synthetic_scope')


def request(identity, slot, route, step):
    validate_scope(identity)
    require(type(slot) is int and 0 <= slot < 40, 'slot_bound')
    require(route in ('base', 'lora') and type(step) is int and 0 <= step < 3, 'route_step')
    require(route == ('base' if slot % 2 == 0 else 'lora'), 'synthetic_schedule')
    # No arbitrary task/answer/path parameter. These are unrelated CPU fixtures.
    value = {'protocol': PROTOCOL, 'scope_sha256': sha(identity), 'slot': slot,
             'route': route, 'step': step, 'synthetic_case': 'cpu-fixture-%02d' % slot}
    value['request_id'] = sha(value)
    return value


def validate_request(value, identity):
    exact(value, ('protocol', 'scope_sha256', 'slot', 'route', 'step', 'synthetic_case', 'request_id'))
    require(value == request(identity, value['slot'], value['route'], value['step']), 'request_binding')


def wire(value):
    raw = canonical(value) + b'\n'
    require(len(raw) <= MAX_FRAME, 'frame_bound')
    return raw


def response(sent, stages=2):
    """Synthetic peer fixture, not an invocation of any model or tool."""
    require(type(stages) is int and 0 <= stages <= 2, 'stage_bound')
    receipts = []
    for name in ('selector', 'invocation')[:stages]:
        raw = 'SYNTHETIC:' + name
        receipts.append({'stage': name, 'raw': raw, 'output_sha256': raw_sha(raw.encode())})
    return {'protocol': PROTOCOL, 'scope_sha256': sent['scope_sha256'],
            'request_id': sent['request_id'], 'request_sha256': raw_sha(wire(sent)),
            'status': 'synthetic_ack_not_permission', 'receipts': receipts}


def validate_response(value, sent):
    exact(value, ('protocol', 'scope_sha256', 'request_id', 'request_sha256', 'status', 'receipts'))
    require(value['protocol'] == PROTOCOL and value['scope_sha256'] == sent['scope_sha256']
            and value['request_id'] == sent['request_id']
            and value['request_sha256'] == raw_sha(wire(sent))
            and value['status'] == 'synthetic_ack_not_permission', 'response_binding')
    receipts = value['receipts']
    require(type(receipts) is list and len(receipts) <= 2, 'receipt_bound')
    for i, receipt in enumerate(receipts):
        exact(receipt, ('stage', 'raw', 'output_sha256'))
        require(receipt['stage'] == ('selector', 'invocation')[i]
                and type(receipt['raw']) is str and receipt['raw'].startswith('SYNTHETIC:')
                and len(receipt['raw']) <= 1024
                and receipt['output_sha256'] == raw_sha(receipt['raw'].encode()), 'raw_receipt')


def _record(seq, prev, event):
    value = {'seq': seq, 'previous_sha256': prev, 'event': event}
    value['record_sha256'] = sha(value)
    return value


def verify(raw, identity, baseline=None, final=None):
    """Independent raw replay. Never accepts counts supplied by the writer.

    baseline/final are separate externally retained CPU witness inputs. Matching
    them cannot establish that a human actually captured them independently.
    Missing final or any unresolved request remains incomplete, not zero.
    """
    validate_scope(identity)
    require(type(raw) is bytes and len(raw) <= MAX_JOURNAL and raw.endswith(b'\n'), 'journal_incomplete')
    lines = raw.splitlines()
    require(0 < len(lines) <= MAX_RECORDS, 'journal_capacity')
    previous = ZERO
    requests = {}
    retired = sealed = False
    ready = False
    sent_count = ack_count = stages = dispatched = writes = 0
    genesis = None
    for seq, line in enumerate(lines):
        value = strict(line)
        exact(value, ('seq', 'previous_sha256', 'event', 'record_sha256'))
        require(type(value['seq']) is int and value['seq'] == seq
                and value['previous_sha256'] == previous
                and value == _record(seq, previous, value['event']), 'chain_binding')
        event = value['event']
        require(type(event) is dict and type(event.get('kind')) is str, 'event_kind')
        kind = event['kind']
        require(not sealed, 'event_after_seal')
        if seq == 0:
            exact(event, ('kind', 'scope'))
            require(kind == 'open' and event['scope'] == identity, 'journal_scope')
            genesis = value['record_sha256']
        elif kind == 'baseline':
            exact(event, ('kind', 'witness'))
            require(not ready and not requests and not retired, 'baseline_order')
            expected = {'kind': 'external_cpu_readiness', 'scope_sha256': sha(identity),
                        'genesis_sha256': genesis}
            require(event['witness'] == expected, 'baseline_binding')
            ready = True
        elif kind == 'intent':
            exact(event, ('kind', 'request_raw'))
            require(ready and not retired and all(r['ack'] for r in requests.values()), 'intent_admission')
            require(type(event['request_raw']) is str, 'request_raw_type')
            raw_request = event['request_raw'].encode()
            req = strict(raw_request, MAX_FRAME)
            validate_request(req, identity)
            require(raw_request == wire(req) and req['request_id'] not in requests, 'request_replay')
            if req['step']:
                prior = request(identity, req['slot'], req['route'], req['step'] - 1)['request_id']
                require(prior in requests and requests[prior]['ack'], 'step_predecessor')
            require(len(requests) < 56, 'request_capacity')
            requests[req['request_id']] = {'request': req, 'sent': False, 'ack': False,
                                          'dispatch': False, 'received': b''}
        elif kind in ('sent', 'received', 'ack', 'dispatch'):
            keys = {'sent': ('kind', 'request_id', 'bytes'),
                    'received': ('kind', 'request_id', 'raw_hex'),
                    'ack': ('kind', 'request_id', 'response_raw'),
                    'dispatch': ('kind', 'request_id', 'effect', 'synthetic_permission_sha256')}
            exact(event, keys[kind])
            require(not retired and event['request_id'] in requests, 'event_request')
            entry = requests[event['request_id']]
            require(not entry['ack'] or kind == 'dispatch', 'duplicate_ack_or_sent')
            if kind == 'sent':
                require(not entry['sent'] and type(event['bytes']) is int
                        and event['bytes'] == len(wire(entry['request'])), 'sent_evidence')
                entry['sent'] = True
                sent_count += 1
            elif kind == 'received':
                require(entry['sent'] and type(event['raw_hex']) is str
                        and re.fullmatch('[0-9a-f]+', event['raw_hex']) is not None
                        and len(event['raw_hex']) % 2 == 0
                        and len(event['raw_hex']) <= (MAX_FRAME + 1) * 2, 'received_raw')
                entry['received'] += bytes.fromhex(event['raw_hex'])
                # Keep the first over-limit chunk as original failure evidence.
                require(len(entry['received']) <= 2 * MAX_FRAME + 1, 'received_capacity')
            elif kind == 'ack':
                require(entry['sent'] and type(event['response_raw']) is str, 'ack_order')
                reply_raw = event['response_raw'].encode()
                reply = strict(reply_raw, MAX_FRAME)
                validate_response(reply, entry['request'])
                require(reply_raw == wire(reply) == entry['received'], 'response_serialization')
                entry['ack'] = True
                ack_count += 1
                stages += len(reply['receipts'])
                require(stages <= 112, 'stage_capacity')
            else:
                require(entry['ack'] and not entry['dispatch'] and all(r['ack'] for r in requests.values())
                        and event['effect'] in ('read', 'write')
                        and is_sha(event['synthetic_permission_sha256']), 'dispatch_evidence')
                entry['dispatch'] = True
                dispatched += 1
                writes += event['effect'] == 'write'
                require(dispatched <= 40, 'dispatch_capacity')
        elif kind == 'retire':
            exact(event, ('kind', 'reason'))
            require(not retired and event['reason'] in ('transport_unknown', 'manual_cpu_stop'), 'retire_event')
            retired = True
        elif kind == 'seal':
            exact(event, ('kind', 'coverage'))
            require(ready and event['coverage'] == 'synthetic_recorded_session_only', 'seal_coverage')
            sealed = True
        else:
            raise ValueError('unknown_event')
        previous = value['record_sha256']
    expected_baseline = {'kind': 'external_cpu_readiness', 'scope_sha256': sha(identity),
                         'genesis_sha256': genesis}
    expected_final = {'kind': 'external_cpu_final_seal', 'scope_sha256': sha(identity),
                      'last_record_sha256': previous, 'records': len(lines)}
    if baseline is not None:
        require(ready and baseline == expected_baseline, 'external_baseline')
    if final is not None:
        require(type(final) is dict and type(final.get('records')) is int
                and sealed and final == expected_final, 'external_final')
    complete = sealed and not retired and ack_count == len(requests) and baseline is not None and final is not None
    return {'status': 'synthetic_chain_consistent_not_live_authority',
            'scope_sha256': sha(identity), 'records': len(lines), 'head_sha256': previous,
            'genesis_sha256': genesis, 'baseline_recorded': ready, 'sealed': sealed, 'retired': retired,
            'request_intents': len(requests), 'complete_frames_recorded_sent': sent_count,
            'acknowledged_requests': ack_count, 'confirmed_synthetic_generation_receipts': stages,
            'recorded_response_bytes': sum(len(r['received']) for r in requests.values()),
            'synthetic_dispatch_observations': dispatched, 'synthetic_write_observations': writes,
            'unresolved_requests': len(requests) - ack_count,
            'synthetic_recorded_coverage_complete': complete,
            'actual_model_generation_total': None, 'actual_rhino_dispatch_total': None,
            'external_witness_origin_verified': False, 'execution_ready': False,
            'request_ids': list(requests)}


class SyntheticJournal:
    """Private test directory; O_EXCL creation, flock, fsync, no repair/truncate.

    An intent survives reopening and forbids replay even under a changed request
    label. A torn append poisons the whole chain. No cross-directory global
    admission, signed remote completeness or live execution is provided here.
    """
    def __init__(self, root, identity, *, create=False):
        validate_scope(identity)
        root = Path(root)
        require(root.is_absolute() and root.resolve() == root, 'journal_path')
        if create:
            root.mkdir(mode=0o700)
        st = root.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()
                and stat.S_IMODE(st.st_mode) == 0o700, 'journal_directory')
        self.identity, self.root, self.poisoned = identity, root, False
        self.exchange_lock = threading.Lock()
        self.append_lock = threading.Lock()
        self.dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fd = None
        try:
            opened = os.fstat(self.dirfd)
            require((opened.st_dev, opened.st_ino) == (st.st_dev, st.st_ino), 'journal_directory_race')
            flags = os.O_RDWR | os.O_NOFOLLOW
            if create:
                flags |= os.O_CREAT | os.O_EXCL
            self.fd = os.open('synthetic-journal.jsonl', flags, 0o600, dir_fd=self.dirfd)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = os.fstat(self.fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600, 'journal_file')
            require(os.listdir(self.dirfd) == ['synthetic-journal.jsonl'], 'journal_extra_files')
            self.raw = self._read()
            if create:
                require(not self.raw, 'journal_existing')
                self._persist(_record(0, ZERO, {'kind': 'open', 'scope': identity}))
                os.fsync(self.dirfd)
            self.summary = verify(self.raw, identity)
        except BaseException:
            self.close()
            raise

    def _read(self):
        info = os.fstat(self.fd)
        named = os.stat('synthetic-journal.jsonl', dir_fd=self.dirfd, follow_symlinks=False)
        directory, named_dir = os.fstat(self.dirfd), self.root.lstat()
        require((directory.st_dev, directory.st_ino) == (named_dir.st_dev, named_dir.st_ino)
                and stat.S_IMODE(named_dir.st_mode) == 0o700
                and named_dir.st_uid == os.getuid(), 'journal_directory_changed')
        require((info.st_dev, info.st_ino) == (named.st_dev, named.st_ino)
                and stat.S_ISREG(named.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1, 'journal_file_changed')
        require(os.listdir(self.dirfd) == ['synthetic-journal.jsonl'], 'journal_extra_files')
        size = info.st_size
        require(size <= MAX_JOURNAL, 'journal_size')
        raw = os.pread(self.fd, size, 0)
        require(len(raw) == size, 'journal_read')
        return raw

    def _persist(self, record):
        encoded = canonical(record) + b'\n'
        require(len(encoded) <= MAX_RECORD and len(self.raw) + len(encoded) <= MAX_JOURNAL, 'journal_size')
        require(self._read() == self.raw, 'journal_external_change')
        self.poisoned = True
        os.lseek(self.fd, 0, os.SEEK_END)
        offset = 0
        while offset < len(encoded):
            count = os.write(self.fd, encoded[offset:])
            require(count > 0, 'journal_write')
            offset += count
        os.fsync(self.fd)
        require(self._read() == self.raw + encoded, 'journal_readback')
        self.raw += encoded
        self.poisoned = False

    def append(self, event):
        with self.append_lock:
            self._append_locked(event)

    def _append_locked(self, event):
        require(self.fd is not None and not self.poisoned, 'journal_poisoned_or_closed')
        require(self.summary['records'] < MAX_RECORDS, 'journal_capacity')
        record = _record(self.summary['records'], self.summary['head_sha256'], event)
        # Independently verify the candidate before any mutation or dispatch.
        candidate = self.raw + canonical(record) + b'\n'
        summary = verify(candidate, self.identity)
        self._persist(record)
        self.summary = summary

    def close(self):
        if getattr(self, 'fd', None) is not None:
            os.close(self.fd)
            self.fd = None
        if getattr(self, 'dirfd', None) is not None:
            os.close(self.dirfd)
            self.dirfd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
