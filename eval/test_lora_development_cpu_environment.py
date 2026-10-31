"""CPU audit must not activate lazy modules; actual origin checks remain strict."""
import hashlib
from types import ModuleType, SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_native import NativeError
from training import lora_development_local_tokenizer as audit


@pytest.fixture
def environment(tmp_path, monkeypatch):
    site = tmp_path / 'site-packages'; site.mkdir()
    source = site / 'known.py'; source.write_bytes(b'known public CPU source')
    binary = tmp_path / 'python'; binary.write_bytes(b'synthetic CPU executable')
    module = ModuleType('known'); module.__file__ = str(source)
    modules = {'known': module, 'torch': None}
    monkeypatch.setattr(audit, 'SITE', str(site))
    monkeypatch.setattr(audit, 'sys', SimpleNamespace(modules=modules, executable=str(binary), version='synthetic'))
    return site, source, modules


def test_repeated_audit_does_not_materialize_lazy_alias(environment):
    site, source, modules = environment
    target = site / 'late.py'; target.write_bytes(b'not imported')
    calls = []
    alias = ModuleType('lazy_alias')
    def activate(name):
        calls.append(name)
        added = ModuleType('late'); added.__file__ = str(target); modules['late'] = added
        return str(target)
    alias.__getattr__ = activate; modules['lazy_alias'] = alias
    expected = audit.observed_environment()
    assert calls == [] and 'late' not in modules
    assert expected['loaded_package_files'] == {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    audit.verify_environment(expected); audit.verify_environment(expected)
    assert calls == [] and 'late' not in modules


@pytest.mark.parametrize('fault', ['new_origin', 'changed_bytes', 'foreign_origin', 'model_backend'])
def test_real_changes_remain_rejected(environment, fault):
    site, source, modules = environment; expected = audit.observed_environment()
    if fault == 'changed_bytes': source.write_bytes(b'changed')
    elif fault == 'model_backend': modules['torch'] = ModuleType('torch')
    else:
        target = (site if fault == 'new_origin' else site.parent / 'other/site-packages') / 'late.py'
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b'new public code')
        added = ModuleType('late'); added.__file__ = str(target); modules['late'] = added
    with pytest.raises(NativeError): audit.verify_environment(expected)
