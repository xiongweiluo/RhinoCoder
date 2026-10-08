#!/usr/bin/env python3
"""Create a separate public owner-audit package; never read private records.

Single preparation attempt, no overwrite. Environment inspection only.
Machine-generated review metadata is not authority to run an experiment.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-failure-audit-source-v2')
STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-failure-audit-state-v2')
OUT = ROOT / 'eval/c5/formal20-v4-incomplete-audit-review-runtime-v2-20261009-a.json'
FILES = {'c5_formal20_owner_failure_audit.py': 'tools/c5_formal20_owner_failure_audit.py',
         'c5_formal20_incomplete_audit.py': 'training/c5_formal20_incomplete_audit.py'}


def sha(raw): return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def main():
    assert sys.argv[1:] == ['prepare'] and not os.path.lexists(SOURCE)
    assert not os.path.lexists(STATE) and not OUT.exists()
    assert SOURCE.parent.resolve() == SOURCE.parent
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    raws = {name: (ROOT / rel).read_bytes() for name, rel in FILES.items()}
    assert all(subprocess.check_output(['git', 'show', revision + ':' + rel], cwd=ROOT) == raws[name]
        for name, rel in FILES.items())
    SOURCE.mkdir(mode=0o700)
    for name, raw in raws.items(): write_new(SOURCE / name, raw)
    executable = Path(sys.executable).resolve(strict=True)
    inspected = json.loads(subprocess.check_output([str(executable), '-I', '-S', '-B',
        str(SOURCE / 'c5_formal20_owner_failure_audit.py'), 'inspect-runtime'], timeout=50))
    assert inspected['private_evidence_reads'] == 0 and not STATE.exists()
    freeze = {'audit_id': inspected['audit_id'], 'source_revision': revision,
        'source_files': {name: sha(raw) for name, raw in raws.items()},
        'original_spec_sha256': '1ce7dba2a75a853a6a2b8d81027235c442586f30718f05dc177f64a04b002fa7',
        'original_runtime_sha256': '9f72a0491b49bbb5f21dd83e6c87bb16530218a375593e0308e69caee134f1a3',
        'environment': inspected['environment'], 'private_evidence_reads_during_preparation': 0,
        'model_or_rhino_calls': 0, 'formal_execution_authority': False,
        'full_joint_audit_capability_claim': False, 'external_host_receipt_captured': False,
        'original_source_or_evidence_modified': False, 'replay_allowed': False}
    raw = json.dumps(freeze, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n'
    write_new(SOURCE / 'review-runtime.json', raw)
    write_new(OUT, raw)
    assert all((SOURCE / name).read_bytes() == v for name, v in raws.items())
    print(json.dumps({'audit_id': freeze['audit_id'], 'status': 'public_audit_package_prepared_not_run',
        'review_runtime_sha256': sha(canonical(freeze)), 'source_files': freeze['source_files'],
        'loaded_external_file_count': len(freeze['environment']['readable_loaded_external_files']),
        'private_evidence_reads': 0, 'model_or_rhino_calls': 0}, sort_keys=True))


if __name__ == '__main__': main()
