"""One-shot HMAC/SQLite/geometry CPU surrogate; no real execution adapter.

Only creates a new private CPU fixture directory. Existing directories cannot
be reopened for production or recovery; audit separately through read-only DB.
Unknown operations permanently consume admission. No live grants or keys.
"""
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import stat
import threading

from training import c5_reuse_evidence as ev
from training.c5_reuse_joint_audit import TABLE, body, check_key, check_permit, freeze, ledger_rows
from training.c5_reuse_transport import SyntheticTransport


class SyntheticPeer:
    """Deterministic bytes only; unrelated to the sealed cases or real models."""
    def __init__(self):
        self.buffer = b''

    def write(self, raw, deadline):
        self.buffer += raw
        return len(raw)

    def read(self, deadline):
        reply = ev.wire(ev.response(ev.strict(self.buffer)))
        self.buffer = b''
        return reply


class CpuBoxScene:
    """Separate in-memory scene state with copied readbacks, no Rhino API."""
    def __init__(self, slot):
        ev.require(type(slot) is int and 0 <= slot < 40, 'cpu_scene_slot')
        self.slot = slot
        self.objects = []

    def snapshot(self):
        return ev.strict(ev.canonical(self.objects))

    def write_box(self):
        ev.require(self.objects == [], 'cpu_scene_duplicate_write')
        self.objects = [{'id': 'cpu-box-%02d' % self.slot, 'kind': 'box', 'units': 'mm',
                         'edges': [self.slot // 2 + 1, 2, 3]}]

    def cleanup(self):
        self.objects = []


class JointSession:
    def __init__(self, root, identity, key):
        ev.validate_scope(identity)
        check_key(key)
        root = Path(root)
        ev.require(root.is_absolute() and root.resolve() == root
                   and root.name == identity['instance_id'] + '-joint', 'joint_root')
        root.mkdir(mode=0o700)  # Permanent one-shot admission; never reuse.
        self.root, self.identity, self.key = root, identity, key
        self.poisoned = False
        self.lock = threading.Lock()
        self.db = self.journal = None
        self.fd = self.dirfd = self.dbfd = None
        try:
            self.dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fd = os.open('native.jsonl', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              0o600, dir_fd=self.dirfd)
            self.dbfd = os.open('ledger.sqlite', os.O_RDONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=self.dirfd)
            # All mutations are serialized by the session lock, including CPU
            # callers on another thread; SQLite's default thread affinity is
            # not used as the admission control.
            self.db = sqlite3.connect(str(root / 'ledger.sqlite'), check_same_thread=False)
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute(TABLE)
            self.db.commit()
            self.rows = []
            self.journal = ev.SyntheticJournal(root / 'transport', identity, create=True)
            baseline = {'kind': 'external_cpu_readiness', 'scope_sha256': ev.sha(identity),
                        'genesis_sha256': self.journal.summary['genesis_sha256']}
            self.journal.append({'kind': 'baseline', 'witness': baseline})
            self.native = b''
            self.head = ev.ZERO
            self.count = 0
            self._append({'kind': 'open', 'freeze': freeze(identity),
                          'transport_genesis_sha256': baseline['genesis_sha256']})
            self.readiness = {'kind': 'external_cpu_joint_readiness', 'scope_sha256': ev.sha(identity),
                              'transport_genesis_sha256': baseline['genesis_sha256'],
                              'native_genesis_sha256': self.head}
            os.fsync(self.dirfd)
        except BaseException:
            self.close()
            raise

    def _append(self, event):
        self._guard()
        ev.require(self.count < 512, 'native_capacity')
        r = {'seq': self.count, 'previous_sha256': self.head, 'event': event}
        r['record_sha256'] = ev.sha(r)
        raw = ev.canonical(r) + b'\n'
        offset = 0
        while offset < len(raw):
            n = os.write(self.fd, raw[offset:])
            ev.require(n > 0, 'native_write')
            offset += n
        os.fsync(self.fd)
        self._guard(check_native=False)
        ev.require(os.pread(self.fd, len(self.native) + len(raw) + 1, 0) == self.native + raw, 'native_readback')
        self.native += raw
        self.count += 1
        self.head = r['record_sha256']

    def _guard(self, *, check_native=True):
        opened, named = os.fstat(self.dirfd), self.root.lstat()
        ev.require((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino)
                   and self.root.resolve() == self.root and stat.S_IMODE(named.st_mode) == 0o700
                   and named.st_uid == os.getuid(), 'joint_directory_drift')
        ev.require(set(os.listdir(self.dirfd)) == {'native.jsonl', 'ledger.sqlite', 'transport'}, 'joint_extra_files')
        for name, fd in (('native.jsonl', self.fd), ('ledger.sqlite', self.dbfd)):
            st = os.stat(name, dir_fd=self.dirfd, follow_symlinks=False)
            info = os.fstat(fd)
            ev.require((st.st_dev, st.st_ino) == (info.st_dev, info.st_ino)
                       and stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                       and stat.S_IMODE(st.st_mode) == 0o600 and st.st_uid == os.getuid(), 'joint_file_drift')
        if self.journal is not None:
            ev.require(self.journal._read() == self.journal.raw, 'joint_transport_drift')
        if check_native and hasattr(self, 'native'):
            ev.require(os.pread(self.fd, len(self.native) + 1, 0) == self.native, 'joint_native_drift')
        ev.require(ledger_rows(self.db) == self.rows, 'joint_ledger_drift')

    def run40(self, *, endpoint_factory=SyntheticPeer, geometry_factory=CpuBoxScene,
              fault=lambda boundary, slot, operation: None):
        ev.require(self.lock.acquire(blocking=False), 'joint_already_active')
        try:
            ev.require(not self.poisoned, 'joint_no_retry')
            self.poisoned = True  # Also blocks a second successful run.
            try:
                for slot in range(40):
                    route = 'base' if slot % 2 == 0 else 'lora'
                    req = ev.request(self.identity, slot, route, 0)
                    reply = SyntheticTransport(self.journal, endpoint_factory()).exchange(slot, route)
                    scene = geometry_factory(slot)
                    geometry = scene.snapshot()
                    ev.require(geometry == [], 'cpu_scene_baseline')
                    self._append({'kind': 'slot', 'request_id': req['request_id'],
                                  'ack_sha256': ev.raw_sha(ev.wire(reply)), 'baseline': geometry,
                                  'paired_input': 'cpu-pair-%02d' % (slot // 2)})
                    for operation in ('write', 'read', 'cleanup'):
                        b = body(self.identity, req, operation, geometry)
                        mac = hmac.new(self.key, ev.canonical(b), hashlib.sha256).hexdigest()
                        p = {'body': b, 'hmac_sha256': mac}
                        p['permit_id'] = ev.sha(p)
                        fault('before_permit', slot, operation)
                        check_permit(p, b, self.key)
                        fault('before_consume', slot, operation)
                        self._guard()
                        row = (b['ordinal'], p['permit_id'], ev.canonical(p).decode(), req['request_id'], operation)
                        self.db.execute('INSERT INTO consumed VALUES (?,?,?,?,?)', row)
                        self.db.commit()  # Durable consumption BEFORE any effect.
                        self.rows.append(row)
                        fault('after_commit', slot, operation)
                        self._append({'kind': 'consume', 'permit': p})
                        fault('before_effect', slot, operation)
                        self._guard()
                        ev.require(ev.canonical(scene.snapshot()) == ev.canonical(geometry), 'cpu_scene_drift')
                        before = geometry
                        if operation == 'write':
                            scene.write_box()
                        elif operation == 'cleanup':
                            scene.cleanup()
                        geometry = scene.snapshot()
                        fault('after_effect', slot, operation)
                        readback = scene.snapshot()
                        self._append({'kind': 'effect', 'permit_id': p['permit_id'], 'operation': operation,
                                      'before': before, 'after': geometry, 'readback': readback})
                        ev.require(ev.canonical(readback) == ev.canonical(geometry), 'cpu_scene_readback')
                        ev.require(operation != 'cleanup' or readback == [], 'cpu_scene_cleanup')
                        fault('after_receipt', slot, operation)
                self.journal.append({'kind': 'seal', 'coverage': 'synthetic_recorded_session_only'})
                self._append({'kind': 'seal', 'coverage': 'cpu_joint_recorded_only'})
            except BaseException:
                # A torn append is never repaired. A failed retire remains an
                # incomplete raw artifact, with permanent root admission.
                try:
                    self._append({'kind': 'retire', 'reason': 'joint_unknown_no_retry'})
                except BaseException:
                    pass
                raise
            rows = self.db.execute('SELECT * FROM consumed ORDER BY ordinal').fetchall()
            return {'kind': 'external_cpu_joint_final', 'scope_sha256': ev.sha(self.identity),
                    'transport_head_sha256': self.journal.summary['head_sha256'],
                    'transport_records': self.journal.summary['records'],
                    'native_head_sha256': self.head, 'native_records': self.count,
                    'ledger_rows_sha256': ev.sha(rows)}
        finally:
            self.lock.release()

    def close(self):
        if self.journal is not None:
            self.journal.close()
        if self.db is not None:
            self.db.close()
            self.db = None
        for name in ('fd', 'dbfd', 'dirfd'):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
