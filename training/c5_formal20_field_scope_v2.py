"""Mac public/source/environment gate. Does not inspect sealed task content."""
from __future__ import annotations

import sys
from pathlib import Path

from plugin.rhino_listener.c5_formal20_scope_v2 import MAC_STATE, SPEC_FILE, FREEZE_FILE, authority
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import require, digest
from plugin.rhino_listener.c5_research_provenance import SourceGuard
from training.c5_model_transport import strict_json, LIMIT
from training.c5_modelbridge_runtime import file_sha

ROOT = Path(__file__).resolve().parents[1]


def public(path):
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= LIMIT, 'formal public path/size differs')
    return strict_json(path.read_bytes())


def external_origins():
    import importlib.util
    files = {}
    for name, module in tuple(sys.modules.items()):
        origin = getattr(module, '__file__', None)
        if not origin or str(origin).startswith('<'): continue
        if name in {'torch.ops', 'torch.classes'} and origin in {'_ops.py', '_classes.py'}: continue
        path = Path(origin)
        require(path.is_absolute(), 'formal unresolved external module origin')
        if path.suffix == '.pyc': path = Path(importlib.util.source_from_cache(str(path)))
        path = path.resolve(strict=True)
        if path.is_relative_to(ROOT): continue
        files[str(path)] = file_sha(path)
    executable = Path(sys.executable).resolve(strict=True)
    files[str(executable)] = file_sha(executable)
    return {'python': sys.version, 'file_sha256': files, 'inventory_sha256': digest(files)}


def scope(*, check_time=True):
    spec, freeze = public(ROOT / SPEC_FILE), public(ROOT / FREEZE_FILE)
    approval = read_json(MAC_STATE, 'owner-approval.json')
    authority(spec, freeze, approval, check_time=check_time)
    require(str(ROOT) == freeze.get('mac_source_root') and file_sha(ROOT / SPEC_FILE) == freeze['spec_file_sha256'],
        'formal Mac source/spec path differs')
    project = SourceGuard(ROOT, freeze['source_files'], freeze['source_inventory_sha256'],
        project_prefixes=('agent', 'training', 'tools', 'plugin', 'data_pipeline'))
    def guard():
        project()
        require(file_sha(ROOT/SPEC_FILE)==freeze['spec_file_sha256']
            and digest(public(ROOT/FREEZE_FILE))==digest(freeze)
            and read_json(MAC_STATE,'owner-approval.json')==approval,
            'new formal spec/runtime/grant changed after admission')
        require(all(file_sha(Path(n)) == sha for n,sha in freeze['rhino_environment_files'].items()),
            'known readable host file drift; opaque host remains explicitly trusted')
        from plugin.rhino_listener.c5_formal20_environment import verify_project_origins
        verify_project_origins(ROOT, freeze['source_files'])
        require(all(file_sha(ROOT / n) == sha for n, sha in freeze['fixed_public_files'].items()), 'formal public configuration drift')
        actual = external_origins(); frozen = freeze['mac_environment']
        require(actual['python'] == frozen['python'] and digest(frozen['file_sha256']) == frozen['inventory_sha256']
            and all(frozen['file_sha256'].get(n) == sha for n, sha in actual['file_sha256'].items())
            and all(file_sha(Path(n)) == sha for n, sha in frozen['file_sha256'].items()), 'formal Mac import/environment drift')
        return freeze['source_inventory_sha256']
    guard()
    return spec, freeze, approval, guard
