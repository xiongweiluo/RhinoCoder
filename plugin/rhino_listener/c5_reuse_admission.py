"""Endpoint-local global development admission, independent of state directory.

The frozen trusted entry must pin one persistent registry namespace per host.
This is not a cross-machine distributed transaction or namespace discovery.
A durable O_EXCL tombstone precedes SQLite; any uncertainty forbids retry.
"""
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
import threading
from contextlib import contextmanager

from .c5_reuse_field_scope import canonical, exact, require, sha, strict, STUDY, validate_binding

TABLE = ('CREATE TABLE admission (study TEXT NOT NULL, role TEXT NOT NULL, '
         'scope_sha256 TEXT NOT NULL, tombstone_sha256 TEXT NOT NULL, '
         'PRIMARY KEY(study,role))')
ROLES = ('controller', 'worker', 'host', 'stop')
ENDPOINT_ROLES = {'mac':('controller','host'),'gpu':('worker','stop')}


def valid(binding):
    validate_binding(binding)


class AdmissionRegistry:
    def __init__(self, binding, *, create=False):
        valid(binding)
        root = Path(binding['paths']['admission_root'])
        require(root.is_absolute() and root.resolve() == root and root.name == 'c5-reuse-global-admission-v1',
                'admission_root')
        if create:
            root.mkdir(mode=0o700)
        st = root.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()
                and stat.S_IMODE(st.st_mode) == 0o700, 'admission_directory')
        self.root, self.binding = root, strict(canonical(binding))
        self.mutex=threading.Lock()
        self.dirfd = self.fd = self.dbfd = self.db = None
        try:
            self.dirfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else 0)
            self.fd = os.open('admission.lock', flags, 0o600, dir_fd=self.dirfd)
            with self._locked():
                self.dbfd = os.open('admission.sqlite', flags, 0o600, dir_fd=self.dirfd)
                self._guard()
                self.db = sqlite3.connect(str(root / 'admission.sqlite'))
                self.db.execute('PRAGMA journal_mode=DELETE')
                self.db.execute('PRAGMA synchronous=FULL')
                if create:
                    self.db.execute(TABLE)
                    self.db.commit()
                    os.fsync(self.dirfd)
                self._audit_locked()
        except BaseException:
            self.close()
            raise

    def _guard(self):
        opened, named = os.fstat(self.dirfd), self.root.lstat()
        require((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino)
                and stat.S_IMODE(named.st_mode) == 0o700 and self.root.resolve() == self.root,
                'admission_directory_drift')
        for name, opened in (('admission.sqlite', self.dbfd), ('admission.lock', self.fd)):
            st, fd = os.stat(name, dir_fd=self.dirfd, follow_symlinks=False), os.fstat(opened)
            require((st.st_dev, st.st_ino) == (fd.st_dev, fd.st_ino) and stat.S_ISREG(st.st_mode)
                    and st.st_nlink == 1 and st.st_uid == os.getuid()
                    and stat.S_IMODE(st.st_mode) == 0o600, 'admission_file_drift')

    @contextmanager
    def _locked(self):
        # Hold only the durable transaction, never model/host lifetime. The
        # independent stop actor must be able to enter while a worker is live.
        require(self.mutex.acquire(blocking=False),'admission_operation_active')
        acquired=False
        try:
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB); acquired=True
            yield
        finally:
            if acquired: fcntl.flock(self.fd,fcntl.LOCK_UN)
            self.mutex.release()

    def audit(self):
        with self._locked():
            return self._audit_locked()

    def _audit_locked(self):
        self._guard()
        require(self.db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'admission_integrity')
        require(self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() ==
                [('table', 'admission', TABLE), ('index', 'sqlite_autoindex_admission_1', None)], 'admission_schema')
        rows = self.db.execute('SELECT study,role,scope_sha256,tombstone_sha256 '
                               'FROM admission ORDER BY role').fetchall()
        require(len(rows) <= 4, 'admission_capacity')
        names = set(os.listdir(self.dirfd))
        allowed = {'admission.sqlite', 'admission.lock'} | {role + '.consumed.json' for role in ROLES}
        require(names <= allowed, 'admission_extra_files')
        tombstones = {}
        for role in ROLES:
            name = role + '.consumed.json'
            if name not in names:
                continue
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.dirfd)
            try:
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) == 0o600 and 0 < info.st_size < 8192, 'admission_tombstone_file')
                raw = os.pread(fd, info.st_size + 1, 0)
                value = strict(raw)
                exact(value, ('study_id', 'role', 'scope_sha256', 'replay_allowed'))
                require(raw == canonical(value) + b'\n' and value['study_id'] == STUDY
                        and value['role'] == role and value['replay_allowed'] is False, 'admission_tombstone')
                tombstones[role] = value
            finally:
                os.close(fd)
        for study, role, scope, tombstone in rows:
            require(study == STUDY and role in tombstones
                    and scope == tombstones[role]['scope_sha256'] and tombstone == sha(tombstones[role]),
                    'admission_sql_tombstone_binding')
        # Even a legitimate crash gap poisons this registry for new effects.
        require(set(tombstones) == {r[1] for r in rows}, 'admission_unknown_no_retry')
        return {'rows': rows, 'rows_sha256': sha(rows), 'replay_allowed': False,
                'cross_host_global_coverage_proven': False}

    def claim(self, role, *, fault=lambda boundary: None):
        require(role in ENDPOINT_ROLES[self.binding['endpoint']], 'admission_role')
        with self._locked():
            return self._claim_locked(role,fault)

    def _claim_locked(self,role,fault):
        self._audit_locked()
        value = {'study_id': STUDY, 'role': role, 'scope_sha256': sha(self.binding), 'replay_allowed': False}
        fd = os.open(role + '.consumed.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.dirfd)
        try:
            raw = canonical(value) + b'\n'
            offset = 0
            while offset < len(raw):
                n = os.write(fd, raw[offset:]); require(n > 0, 'admission_write'); offset += n
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.dirfd)
        fault('after_tombstone')
        self.db.execute('INSERT INTO admission VALUES (?,?,?,?)', (STUDY, role, sha(self.binding), sha(value)))
        self.db.commit()
        fault('after_commit')
        self._audit_locked()
        return value

    def close(self):
        if self.db is not None:
            self.db.close(); self.db = None
        for name in ('fd', 'dbfd', 'dirfd'):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd); setattr(self, name, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
