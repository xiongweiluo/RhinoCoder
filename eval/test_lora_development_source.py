"""Public CPU imports from the exact shipped files, without repo fallback."""
import subprocess
import sys

import pytest

from tools.build_lora_development_package import ROOT, source_manifest
from tools.check_lora_development_source import probe_source
from training import lora_development_loader as loader


def test_isolated_imports_find_missing_dependency_and_repaired_closure():
    files = source_manifest()
    missing = {k: v for k, v in files.items() if not k.startswith('data_pipeline/')}
    rejected = probe_source(ROOT, missing)
    assert rejected['status'] == 'rejected'
    assert rejected['error_tail'][-1] == "ModuleNotFoundError: No module named 'data_pipeline'"
    passed = probe_source(ROOT, files)
    assert passed['status'] == 'passed'
    assert 'data_pipeline/training_views.py' in passed['origins']
    assert passed['backend_imports'] == passed['runtime_entries_called'] == 0
    assert passed['model_or_host_readiness_proven'] is False


def test_helper_import_failure_precedes_gpu_or_backend_work(monkeypatch):
    calls = []
    def missing():
        calls.append('helpers')
        raise ModuleNotFoundError('synthetic missing public dependency')
    monkeypatch.setattr(loader, 'cpu_dependencies', missing)
    monkeypatch.setattr(loader, 'preflight', lambda _: calls.append('gpu'))
    with pytest.raises(ModuleNotFoundError):
        loader.load(ROOT, {'loader_policy': loader.POLICY}, lambda: calls.append('guard'))
    assert calls == ['helpers']


def test_consumed_r2_builder_does_not_emit_another_package(tmp_path):
    output = tmp_path / 'must-not-exist.json'
    result = subprocess.run([sys.executable, str(ROOT / 'tools/build_lora_development_package.py'),
                             '--output', str(output)], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'R2 is consumed' in result.stderr
    assert not output.exists()
