"""Actual local CPU deployment roots: complete byte inventory and negatives."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from training import c5_reuse_deployment as dep

SOURCE = Path(__file__).resolve().parents[1]
INSTANCE = 'cpu-deployment-test'


@pytest.fixture
def staged(tmp_path):
    root = tmp_path / (INSTANCE + '-source')
    state = tmp_path / (INSTANCE + '-state')
    value = dep.manifest(SOURCE, INSTANCE, root)
    anchor = dep.digest(dep.canonical(value))
    result = dep.stage_cpu_public(SOURCE, value, anchor, INSTANCE, state_root=state)
    return root, state, value, anchor, result


def check(staged, **kwargs):
    root, state, value, anchor, _ = staged
    return dep.preflight(kwargs.get('root', root), kwargs.get('value', value),
                         kwargs.get('anchor', anchor), kwargs.get('instance', INSTANCE),
                         state_root=kwargs.get('state', state))


def test_complete_transitive_public_files_and_actual_root(staged):
    root, state, value, _, result = staged
    assert check(staged) == result
    assert result['files_verified'] == len(value['files'])
    assert not result['execution_ready'] and not result['target_code_executed'] and not state.exists()
    assert {'training/__init__.py', 'training/config.py',
            'training/configs/rhinocoder-qwen25-coder-7b-itc-lora-v1.json',
            'requirements-training.txt', 'training/c5_reuse_joint_audit.py',
            'eval/c5/rhino-formal20-public-commitment-v1.json',
            'eval/c5/formal20-v4-public-stop-observation-20261009.json',
            'docs/c5-contract-aligned-qlora-plan.md'} <= set(value['files'])


@pytest.mark.parametrize('name', sorted(dep.closure(SOURCE)))
def test_every_transitive_file_missing_blocks_actual_root(staged, name):
    (staged[0] / name).unlink()
    with pytest.raises((ValueError, OSError)):
        check(staged)


@pytest.mark.parametrize('name', ['training/c5_reuse_joint.py', 'training/__init__.py',
    'eval/c5/formal20-reuse-preparation-draft-20261011.json', 'requirements-training.txt'])
def test_code_configuration_and_import_bytes_drift_rejected(staged, name):
    p = staged[0] / name
    p.write_bytes(p.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='byte_drift'):
        check(staged)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'directory_symlink', 'mode', 'fifo', 'named_fifo',
                                 'extra', 'empty_directory', 'pycache'])
def test_inventory_and_filesystem_negative_controls(staged, tmp_path, kind):
    root = staged[0]
    p = root / 'training/c5_reuse_joint.py'
    if kind == 'symlink':
        p.unlink(); p.symlink_to(SOURCE / 'training/c5_reuse_joint.py')
    elif kind == 'hardlink':
        os.link(p, tmp_path / 'second-name')
    elif kind == 'directory_symlink':
        (root / 'extra-dir').symlink_to(SOURCE / 'training', target_is_directory=True)
    elif kind == 'mode':
        p.chmod(0o666)
    elif kind == 'fifo':
        os.mkfifo(root / 'fifo')
    elif kind == 'named_fifo':
        p.unlink(); os.mkfifo(p)
    elif kind == 'extra':
        (root / 'old-grant.json').write_text('{}')
    elif kind == 'empty_directory':
        (root / 'extra-dir').mkdir()
    else:
        (root / 'training/__pycache__').mkdir()
    with pytest.raises((ValueError, OSError)):
        check(staged)


@pytest.mark.parametrize('kind', ['root', 'instance', 'study', 'protocol', 'state', 'state_source',
                                 'state_identity', 'anchor', 'entrypoint'])
def test_cross_identity_and_used_state_rejected(staged, tmp_path, kind):
    root, state, value, anchor, _ = staged
    kwargs = {}
    if kind == 'root':
        kwargs['root'] = tmp_path / 'other-source'
    elif kind == 'instance':
        kwargs['instance'] = 'cpu-other'
    elif kind in ('study', 'protocol', 'entrypoint'):
        value = copy.deepcopy(value)
        if kind == 'entrypoint':
            value['entrypoints'] = ['tools/run_c5_formal20_worker_v2.py']
        else:
            value['scope']['study_id' if kind == 'study' else 'protocol'] = 'old'
        kwargs = {'value': value, 'anchor': dep.digest(dep.canonical(value))}
    elif kind == 'state':
        state.mkdir()
    elif kind == 'state_source':
        kwargs['state'] = root
    elif kind == 'state_identity':
        kwargs['state'] = tmp_path / 'old-state'
    else:
        kwargs['anchor'] = '0' * 64
    with pytest.raises(ValueError):
        check(staged, **kwargs)


def test_rehashed_manifest_missing_transitive_json_still_rejected(staged):
    root, _, value, _, _ = staged
    value = copy.deepcopy(value)
    name = 'eval/c5/rhino-formal20-public-commitment-v1.json'
    del value['files'][name]
    (root / name).unlink()
    with pytest.raises((ValueError, OSError)):
        check(staged, value=value, anchor=dep.digest(dep.canonical(value)))


def test_staging_and_builder_never_overwrite_existing_root(staged):
    root, state, value, anchor, _ = staged
    before = (root / 'training/c5_reuse_joint.py').read_bytes()
    with pytest.raises(ValueError, match='destination_unavailable'):
        dep.stage_cpu_public(SOURCE, value, anchor, INSTANCE, state_root=state)
    assert (root / 'training/c5_reuse_joint.py').read_bytes() == before
    with pytest.raises(ValueError):
        dep.manifest(SOURCE, INSTANCE, root)


def test_staging_failure_preserved_no_repair_or_retry(tmp_path, monkeypatch):
    root, state = tmp_path / (INSTANCE + '-source'), tmp_path / (INSTANCE + '-state')
    value = dep.manifest(SOURCE, INSTANCE, root)
    anchor = dep.digest(dep.canonical(value))
    def broken(_):
        raise OSError('CPU fsync failure')
    monkeypatch.setattr(os, 'fsync', broken)
    with pytest.raises(OSError):
        dep.stage_cpu_public(SOURCE, value, anchor, INSTANCE, state_root=state)
    assert root.exists() and not state.exists()
    with pytest.raises(ValueError, match='destination_unavailable'):
        dep.stage_cpu_public(SOURCE, value, anchor, INSTANCE, state_root=state)


@pytest.mark.parametrize('code', ['import torch', 'import training.unknown_dependency',
                                 '__import__("training.hidden")', 'exec("pass")'])
def test_unfrozen_or_dynamic_dependency_fails_closed(code):
    if 'unknown_dependency' in code:
        assert 'training/unknown_dependency.py' in dep.dependencies('training/x.py', code.encode())
    else:
        with pytest.raises(ValueError):
            dep.dependencies('training/x.py', code.encode())


@pytest.mark.parametrize('name', ['../private.json', '/tmp/private.json', 'data/training/c5/state.json',
                                 'training/../tools/a.py', 'eval/c5/identity.key'])
def test_private_or_escaping_path_denied_before_open(name):
    with pytest.raises(ValueError):
        dep.read_file(SOURCE, name)


def test_cli_runs_trusted_source_and_never_imports_target(staged, tmp_path):
    root, state, value, anchor, _ = staged
    review = tmp_path / 'review-manifest.json'
    review.write_bytes(dep.canonical(value))
    cmd = [sys.executable, '-I', '-B', str(SOURCE / 'tools/check_c5_reuse_deployment.py'),
           '--root', str(root), '--manifest', str(review), '--manifest-sha256', anchor,
           '--instance', INSTANCE, '--state-root', str(state)]
    good = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert good.returncode == 0, good.stderr
    assert json.loads(good.stdout)['files_verified'] == len(value['files'])
    marker = tmp_path / 'executed'
    (root / 'training/__init__.py').write_text('raise RuntimeError("target executed")\n')
    bad = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert bad.returncode == 1 and not marker.exists()
    assert json.loads(bad.stdout)['status'] == 'cpu_deployment_preflight_rejected'
    assert 'target executed' not in bad.stderr
