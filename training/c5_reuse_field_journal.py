"""Scoped, bounded immutable endpoint raw records; not a live entrypoint."""
import os
from pathlib import Path
import stat
import threading

from plugin.rhino_listener.c5_research_channel import private_directory, publish_json
from plugin.rhino_listener.c5_research_native import canonical as public_canonical
from training.c5_reuse_evidence import canonical, exact, require, sha, strict, ZERO
from training.c5_reuse_field_scope import validate_binding

MAX_RECORD = 2 * 1024 * 1024
MAX_BYTES = 64 * 1024 * 1024


def read_record(root, name):
    directory = private_directory(root)
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o600
                and 0 < before.st_size <= MAX_RECORD, 'field_raw_file')
        raw = os.pread(fd, before.st_size + 1, 0)
        after, named = os.fstat(fd), os.stat(name, dir_fd=directory, follow_symlinks=False)
        fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_nlink')
        require(len(raw) == before.st_size and all(getattr(before,k) == getattr(after,k) == getattr(named,k)
                                                  for k in fields), 'field_raw_read_race')
        value = strict(raw, limit=MAX_RECORD)
        require(raw == public_canonical(value).encode() + b'\n', 'field_raw_serialization')
        return value, len(raw)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def read_journal(root, binding, role, final_head):
    """Read-only complete disk population check; anchor provenance is separate."""
    require(final_head is not None, 'field_raw_anchor_required')
    directory = private_directory(root)
    try:
        names = set(os.listdir(directory))
        require(0 < len(names) <= 4096 and names == {'raw-%04d.json' % i for i in range(len(names))},
                'field_raw_disk_population')
        identity = os.fstat(directory)
    finally:
        os.close(directory)
    rows, total = [], 0
    for index in range(len(names)):
        row, size = read_record(root, 'raw-%04d.json' % index)
        rows.append(row); total += size
        require(total <= MAX_BYTES, 'field_raw_total_bytes')
    directory = private_directory(root)
    try:
        current = os.fstat(directory)
        require((identity.st_dev,identity.st_ino) == (current.st_dev,current.st_ino)
                and set(os.listdir(directory)) == names, 'field_raw_directory_drift')
    finally:
        os.close(directory)
    replay_records(rows,binding,role,final_head)
    return rows


class FieldJournal:
    def __init__(self, binding, role, registry):
        validate_binding(binding)
        require(role in ('controller', 'worker') and registry.binding == binding, 'field_journal_role')
        self.binding, self.role = strict(canonical(binding)), role
        self.lock = threading.Lock()
        self.blocked = True
        self.admission = registry.claim(role)
        self.root = Path(binding['paths']['state_root']) / role
        self.root.mkdir(mode=0o700)
        self.root_identity = self.root.stat()
        self.records, self.head, self.bytes = [], ZERO, 0
        self.append('open', {'binding': binding, 'role': role, 'admission': self.admission})
        self.blocked = False

    def append(self, kind, payload):
        require(type(kind) is str and type(payload) is dict and len(self.records) < 4096, 'field_journal_capacity')
        directory = private_directory(self.root)
        try:
            current = os.fstat(directory)
            require((current.st_dev,current.st_ino) == (self.root_identity.st_dev,self.root_identity.st_ino)
                    and set(os.listdir(directory)) == {'raw-%04d.json' % i for i in range(len(self.records))},
                    'field_journal_directory_drift')
        finally:
            os.close(directory)
        if self.records:
            previous, _ = read_record(self.root, 'raw-%04d.json' % (len(self.records)-1))
            require(canonical(previous) == canonical(self.records[-1]), 'field_journal_previous_drift')
        value = {'seq': len(self.records), 'previous_sha256': self.head, 'scope_sha256': sha(self.binding),
                 'kind': kind, 'payload': payload}
        value['record_sha256'] = sha(value)
        value = strict(canonical(value), limit=MAX_RECORD)
        raw = public_canonical(value).encode() + b'\n'
        require(len(raw) <= MAX_RECORD and self.bytes + len(raw) <= MAX_BYTES, 'field_journal_byte_capacity')
        publish_json(self.root, 'raw-%04d.json' % len(self.records), value)
        observed, size = read_record(self.root, 'raw-%04d.json' % len(self.records))
        require(canonical(observed) == canonical(value), 'field_journal_readback')
        self.records.append(value)
        self.head = value['record_sha256']
        self.bytes += size


def replay_records(values, binding, role, final_head=None):
    """Verify immutable raw rows, not counters or producer summaries."""
    validate_binding(binding)
    require(type(values) is list and 1 <= len(values) <= 4096, 'field_raw_population')
    previous = ZERO
    for index, value in enumerate(values):
        exact(value, ('seq', 'previous_sha256', 'scope_sha256', 'kind', 'payload', 'record_sha256'))
        require(type(value['seq']) is int and value['seq'] == index and value['previous_sha256'] == previous
                and value['scope_sha256'] == sha(binding)
                and value['record_sha256'] == sha({k:v for k,v in value.items() if k != 'record_sha256'}),
                'field_raw_chain')
        if index == 0:
            exact(value['payload'], ('binding','role','admission'))
            require(value['kind'] == 'open' and value['payload']['role'] == role
                    and canonical(value['payload']['binding']) == canonical(binding), 'field_raw_scope')
            admission = value['payload']['admission']
            exact(admission, ('study_id','role','scope_sha256','replay_allowed'))
            require(admission == {'study_id':binding['study_id'],'role':role,'scope_sha256':sha(binding),
                                  'replay_allowed':False}, 'field_raw_admission_binding')
        previous = value['record_sha256']
    if final_head is not None:
        require(previous == final_head, 'field_raw_external_head')
    return previous
