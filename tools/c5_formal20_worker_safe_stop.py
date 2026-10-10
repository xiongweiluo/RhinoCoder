#!/usr/bin/env python3
"""One exact pidfd-bound SIGTERM; fresh owner grant required. No model I/O.

Standalone system-Python stdlib entry, not a formal20 recovery/runner. Import
has no field effects. Never reads stdin/model pipes/private evidence/keys.
"""
import hashlib
import json
import os
import selectors
import signal
import stat
import sys
import time
from pathlib import Path

ID = 'C5SAFE-FORMAL20-V4-WORKER-20261009-A'
SOURCE = Path('/data/c5-formal20-worker-stop-source-20261009-A')
STATE = Path('/data/c5-formal20-worker-stop-state-20261009-A')
FILE = 'c5_formal20_worker_safe_stop.py'
STUDY = 'c5-rhino-paired-20-v1'
SHA = '9f72a0491b49bbb5f21dd83e6c87bb16530218a375593e0308e69caee134f1a3'


class Refusal(RuntimeError):
    pass


def require(ok):
    if not ok:
        raise Refusal('safe-stop guard failed')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path):
    path = Path(path)
    require(path.is_file() and path.resolve() == path and not path.is_symlink())
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def pairs(items):
    value = {}
    for key, item in items:
        require(key not in value)
        value[key] = item
    return value


def read_json(path):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and 0 < info.st_size <= 1048576)
        raw = os.read(fd, info.st_size + 1)
        require(len(raw) == info.st_size)
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refusal()))
    finally:
        os.close(fd)


def publish(directory, name, value):
    require(directory.resolve() == directory and directory.is_dir()
            and directory.stat().st_uid == os.getuid()
            and stat.S_IMODE(directory.stat().st_mode) == 0o700
            and '/' not in name and name not in {'.', '..'})
    raw = canonical(value) + b'\n'
    fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        count = 0
        while count < len(raw):
            n = os.write(fd, raw[count:])
            require(n > 0)
            count += n
        os.fsync(fd)
    finally:
        os.close(fd)
    root = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(root)
    finally:
        os.close(root)


def identity(pid):
    root = Path('/proc') / str(pid)
    data = (root / 'cmdline').read_bytes().split(b'\0')
    argv = [x.decode() for x in data if x]
    text = (root / 'stat').read_text()
    fields = text[text.rfind(')') + 2:].split()
    exe = Path(os.readlink(root / 'exe'))
    return {'pid': pid, 'uid': root.stat().st_uid,
            'start_ticks': int(fields[19]),
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'cwd': os.readlink(root / 'cwd'), 'argv': argv,
            'executable_path': str(exe), 'executable_sha256': file_sha(exe)}


def environment():
    """Readable system-runtime bytes, not proof of opaque kernel/mappings."""
    require(sys.platform == 'linux' and sys.flags.isolated and sys.flags.no_site
            and sys.dont_write_bytecode and Path(sys.executable).resolve() == Path('/usr/bin/python3.10'))
    root = Path('/usr/lib/python3.10')
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.pyc', '.so'}:
            resolved = path.resolve(strict=True)
            files[str(resolved)] = file_sha(resolved)
    # hashlib may load native dependencies during hashing; capture afterward.
    mapped = {}
    opaque = set()
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6:
            continue
        name = fields[5]
        if name.startswith('/'):
            path = Path(name).resolve(strict=True)
            mapped[str(path)] = file_sha(path)
        elif name.startswith('['):
            opaque.add(name)
    path_files = {str(Path(p).resolve()): file_sha(Path(p).resolve())
                  for p in sys.path if Path(p).is_file()}
    return {'python': sys.version, 'sys_path': list(sys.path), 'existing_sys_path_files': path_files,
            'executable': '/usr/bin/python3.10',
            'executable_sha256': file_sha(Path('/usr/bin/python3.10')),
            'stdlib_files': files, 'mapped_files': mapped,
            'opaque_mapping_labels': sorted(opaque), 'kernel_trusted_not_byte_proven': True}


def validate_spec(spec):
    require(set(spec) == {'cleanup_id', 'study_id', 'retired_runtime_sha256', 'target',
            'source_root', 'state_root', 'not_after_epoch', 'signal', 'signals_max',
            'exit_wait_seconds', 'model_or_holdout_calls_max',
            'disk_evidence_modified', 'retry_allowed', 'sigkill_allowed', 'kernel_trusted_not_byte_proven'})
    require(spec['cleanup_id'] == ID and spec['study_id'] == STUDY
            and spec['retired_runtime_sha256'] == SHA and spec['source_root'] == str(SOURCE)
            and spec['state_root'] == str(STATE) and type(spec['not_after_epoch']) is int
            and spec['not_after_epoch'] == 1791504000)
    require(spec['signal'] == 'SIGTERM' and type(spec['signals_max']) is int and spec['signals_max'] == 1
            and type(spec['exit_wait_seconds']) is int and spec['exit_wait_seconds'] == 30
            and type(spec['model_or_holdout_calls_max']) is int and spec['model_or_holdout_calls_max'] == 0)
    require(all(spec[k] is False for k in ('disk_evidence_modified', 'retry_allowed', 'sigkill_allowed'))
            and spec['kernel_trusted_not_byte_proven'] is True)
    target = spec['target']
    require(set(target) == {'pid', 'uid', 'start_ticks', 'boot_id', 'cwd', 'argv',
                           'executable_path', 'executable_sha256'})
    require(target['pid'] == 43776 and type(target['pid']) is int
            and target['uid'] == 1000 and type(target['uid']) is int
            and target['start_ticks'] == 451535 and type(target['start_ticks']) is int
            and target['boot_id'] == 'c8ec6a1e-7d0b-4ef1-bfd3-1e4ed0fe5777'
            and target['cwd'] == '/data/RhinoCoder-c5-formal20-v4'
            and target['argv'] == ['/data/conda-envs/rhinocoder/bin/python', '-B', '-m',
                                  'tools.run_c5_formal20_worker_v2', 'serve']
            and target['executable_path'] == '/data/conda-envs/rhinocoder/bin/python3.11'
            and target['executable_sha256'] == '1b473ff72cfa63de341095fa5192c0d030ac06a56c995d77de3626098f81e055')


def stop_once(spec, ops, journal):
    """Separate injected effect boundary for CPU negative controls."""
    validate_spec(spec)
    fd = None
    result = {'cleanup_id': ID, 'status': 'refused_or_unknown_no_retry',
              'signals_attempted': 0, 'pidfd_exit_observed': False,
              'target_absent_from_gpu': None, 'error_type': None,
              'model_or_holdout_calls': 0, 'replay_allowed': False}
    # Admission refusal must not append a new result to an uncertain old attempt.
    ops.guard()
    journal('admission.json', {'cleanup_id': ID, 'replay_allowed': False})
    try:
        fd = ops.pin(spec['target']['pid'])
        require(ops.identity(spec['target']['pid']) == spec['target'])
        require(not ops.exited(fd))
        ops.guard()
        journal('signal-attempt.json', {'cleanup_id': ID, 'pid': spec['target']['pid'],
                                       'signal': 'SIGTERM', 'attempts_max': 1})
        result['signals_attempted'] = 1  # Includes unknown syscall outcomes.
        ops.send(fd)
        result['pidfd_exit_observed'] = ops.wait(fd, 30)
        if result['pidfd_exit_observed']:
            # A different read-only observer checks GPU absence afterward. No
            # subprocess timeout can implicitly SIGKILL a diagnostic child.
            result['status'] = 'target_exit_observed_pending_independent_gpu_check'
        else:
            result['status'] = 'termination_unconfirmed_no_retry'
    except BaseException as exc:
        result['error_type'] = type(exc).__name__
    finally:
        if fd is not None:
            ops.close(fd)
    journal('result.json', result)
    return result


class Operations:
    def __init__(self, guard):
        self.guard = guard

    def pin(self, pid):
        require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'))
        return os.pidfd_open(pid, 0)

    identity = staticmethod(identity)

    def exited(self, fd):
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            return bool(selector.select(0))

    def send(self, fd):
        signal.pidfd_send_signal(fd, signal.SIGTERM, None, 0)

    def wait(self, fd, seconds):
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            return bool(selector.select(seconds))

    close = staticmethod(os.close)


def main():
    if sys.argv[1:] == ['inspect-runtime']:
        print(json.dumps(environment(), sort_keys=True))
        return 0
    require(sys.argv[1:] == ['execute'] and Path(__file__).resolve().parent == SOURCE)
    spec, freeze = read_json(SOURCE / 'spec.json'), read_json(SOURCE / 'runtime.json')
    validate_spec(spec)
    grant = read_json(STATE / 'owner-approval.json')
    require(grant == {'cleanup_id': ID, 'actor': 'repository_owner', 'approved': True,
                     'spec_sha256': digest(spec), 'runtime_sha256': digest(freeze)})
    require(freeze['cleanup_id'] == ID and freeze['spec_sha256'] == digest(spec))
    def guard():
        require(time.time() < spec['not_after_epoch'] and os.getuid() == 1000)
        require(read_json(STATE / 'owner-approval.json') == grant
                and digest(read_json(SOURCE / 'spec.json')) == digest(spec)
                and digest(read_json(SOURCE / 'runtime.json')) == digest(freeze)
                and file_sha(SOURCE / 'spec.json') == freeze['spec_file_sha256']
                and (SOURCE / 'runtime.json').read_bytes() == json.dumps(freeze, sort_keys=True,
                    ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n'
                and file_sha(SOURCE / FILE) == freeze['source_sha256']
                and environment() == freeze['system_environment'])
        require(time.time() < spec['not_after_epoch'])
    result = stop_once(spec, Operations(guard), lambda n, v: publish(STATE, n, v))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'target_exit_observed_pending_independent_gpu_check' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'cleanup_id': ID, 'status': 'entry_refused_no_retry',
                          'error_type': type(exc).__name__, 'private_content_included': False}))
        raise SystemExit(1)
