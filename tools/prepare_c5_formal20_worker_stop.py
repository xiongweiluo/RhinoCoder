#!/usr/bin/env python3
"""Public two-file deployment/runtime inventory ONLY; never executes stop.

Generates a reviewable manifest. No process handle, signal, model call, private
state read or owner grant is performed. Unknown transfer outcomes stop here.
"""
import base64
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'eval/c5/formal20-v4-worker-stop-spec-20261009-a.json'
CODE = ROOT / 'tools/c5_formal20_worker_safe_stop.py'
OUT = ROOT / 'eval/c5/formal20-v4-worker-stop-runtime-20261009-a.json'
REMOTE = '/data/c5-formal20-worker-stop-source-20261009-A'
STATE = '/data/c5-formal20-worker-stop-state-20261009-A'
PIN = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/known-hosts-22159')
SOCKET = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/ssh-22159.control')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def ssh():
    assert SOCKET.is_socket()
    assert sha(PIN.read_bytes()) == 'ae41a99e39f76b1be352f0098439b126fe5b8465c358b8dabbb7a71e53d2d1a9'
    return ['ssh', '-T', '-S', str(SOCKET), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(PIN), '-o', 'HostKeyAlgorithms=ssh-ed25519',
            '-p', '22159', 'linux@175.155.64.171']


RECEIVE = r'''
import os,sys,json,hashlib,base64
from pathlib import Path
v=json.load(sys.stdin);root=Path('/data/c5-formal20-worker-stop-source-20261009-A')
assert root.resolve()==root and not Path('/data/c5-formal20-worker-stop-state-20261009-A').exists()
if v['phase']=='new-source':
 assert not root.exists() and set(v['files'])=={'c5_formal20_worker_safe_stop.py','spec.json'}
 root.mkdir(mode=0o700)
else:
 assert v['phase']=='new-runtime' and root.is_dir() and set(v['files'])=={'runtime.json'}
 assert sorted(p.name for p in root.iterdir())==['c5_formal20_worker_safe_stop.py','spec.json']
result={}
for name,row in v['files'].items():
 raw=base64.b64decode(row['base64'],validate=True)
 assert 0<len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==row['sha256']
 fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False) as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 finally:os.close(fd)
 result[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
print(json.dumps({'public_files':result,'signals_sent':0,'private_reads':0},sort_keys=True),flush=True)
'''


def transfer(phase, files):
    payload = {'phase': phase, 'files': {n: {'base64': base64.b64encode(raw).decode(), 'sha256': sha(raw)}
                                      for n, raw in files.items()}}
    receipt = json.loads(subprocess.check_output(ssh() + ['/usr/bin/python3.10 -I -S -B -c ' + shlex.quote(RECEIVE)],
                        input=canonical(payload), timeout=60))
    assert receipt == {'public_files': {n: sha(raw) for n, raw in files.items()}, 'signals_sent': 0, 'private_reads': 0}


def main():
    assert not OUT.exists() and sys.argv[1:] == ['prepare']
    code, spec_raw = CODE.read_bytes(), SPEC.read_bytes()
    spec = json.loads(spec_raw)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for name, raw in [('tools/' + CODE.name, code), ('eval/c5/' + SPEC.name, spec_raw)]:
        assert subprocess.check_output(['git', 'show', revision + ':' + name], cwd=ROOT) == raw
    transfer('new-source', {CODE.name: code, 'spec.json': spec_raw})
    # Strict read-only mode; execute branch cannot run without a new real grant.
    env = json.loads(subprocess.check_output(ssh() + ['/usr/bin/python3.10 -I -S -B ' + REMOTE + '/' + CODE.name + ' inspect-runtime'], timeout=120))
    freeze = {'cleanup_id': spec['cleanup_id'], 'spec_sha256': sha(canonical(spec)),
              'spec_file_sha256': sha(spec_raw), 'source_sha256': sha(code),
              'source_git_revision': revision, 'system_environment': env,
              'caller_ssh_executable_sha256': sha(Path('/usr/bin/ssh').read_bytes()),
              'original_formal_source_or_private_data_modified': False,
              'signals_sent_during_preparation': 0, 'model_or_holdout_calls': 0}
    raw = json.dumps(freeze, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n'
    # Machine-generated review artifact, never a manually edited freeze.
    with OUT.open('xb') as stream:
        stream.write(raw)
    transfer('new-runtime', {'runtime.json': raw})
    print(json.dumps({'status': 'public_stop_runtime_prepared_not_authorized',
        'cleanup_id': spec['cleanup_id'], 'spec_sha256': sha(canonical(spec)),
        'runtime_sha256': sha(canonical(freeze)), 'source_sha256': sha(code),
        'source_revision': revision, 'stdlib_files': len(env['stdlib_files']),
        'mapped_files': len(env['mapped_files']), 'signals_sent': 0, 'model_calls': 0,
        'private_reads': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
