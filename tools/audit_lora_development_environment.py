#!/usr/bin/env python3
"""Read-only GPU Python/package byte inventory. No model backend import.

This script is also usable through stdin under -I -S -B; no remote source
installation, package installation, corpus read or CUDA call is required.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sys

NATIVE = Path('/data/c5-reuse-compatible-python-20261012-d/runtime')
PACKAGES = Path('/data/conda-envs/rhinocoder')
SITE = PACKAGES / 'lib/python3.11/site-packages'


def sha(path):
    path = Path(path)
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    after = path.stat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, k) != getattr(after, k) for k in keys): raise RuntimeError('asset changed during hash')
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def inventory():
    if Path(sys.executable).resolve() != NATIVE / 'bin/python3.11': raise RuntimeError('fixed compatible Python required')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'): raise RuntimeError('pidfd unavailable')
    files, versions, missing = {}, {}, []
    for dist in importlib.metadata.distributions(path=[str(SITE)]):
        name = dist.metadata['Name'].lower().replace('_', '-')
        if name in versions or not dist.files: raise RuntimeError('duplicate or incomplete distribution')
        versions[name] = dist.version
        for item in dist.files:
            path = Path(os.path.normpath(str(dist.locate_file(item))))
            if path.suffix in {'.pyc', '.pyo'} or '__pycache__' in path.parts: continue
            if name == 'pip' and str(item) == '../../../bin/pip3.13' and not path.exists():
                missing.append('pip:../../../bin/pip3.13'); continue
            if not path.is_relative_to(PACKAGES) or path.resolve() != path: raise RuntimeError('package path escape')
            files[str(path)] = sha(path)
    if missing != ['pip:../../../bin/pip3.13']: raise RuntimeError('unexpected missing distribution assets')
    for path in sorted(NATIVE.rglob('*')):
        if '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'} or not path.is_file() or path.is_symlink(): continue
        files[str(path)] = sha(path)
    report = {'python': sys.version.split()[0], 'python_path': str(NATIVE / 'bin/python3.11'),
        'python_sha256': files[str(NATIVE / 'bin/python3.11')], 'packages': versions,
        'file_count': len(files), 'inventory_sha256': digest(files), 'missing_record_entries': missing,
        'pidfd_open': True, 'pidfd_send_signal': True,
        'external_dynamic_libraries_byte_closed': False, 'model_packages_imported': False,
        'model_calls': 0, 'private_material_reads': 0}
    return report, files


if __name__ == '__main__':
    print(json.dumps(inventory()[0], sort_keys=True))
