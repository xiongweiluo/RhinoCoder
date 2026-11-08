"""Injected supervisor failures; never starts a GPU worker or model."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import digest
from training import lora_development_gpu_entry as module
from training.lora_development_scope import field_views
from eval.test_lora_development_wire import PLAN, IDENTITY


@pytest.mark.parametrize('fault,expected_loads', [(None, 1), ('first_load', 2), ('both_loads', 2),
    ('cleanup_unknown', 1), ('after_exposure', 1), ('single_load', 1)])
def test_recovery_is_preexposure_once_and_cleanup_unknown_blocks_it(tmp_path, monkeypatch, fault, expected_loads):
    tmp_path.chmod(0o700)
    package = {'limits': dict(PLAN['limits']), 'lease_end_epoch': 9999999999, 'source_files': {},
        'model_identities': {'base': IDENTITY, 'current_lora': IDENTITY}, 'endpoints': {'gpu': {'python': '/synthetic/python'}},
        'native_scope': {'schedule': field_views(PLAN)['schedule']}}
    if fault == 'single_load': package['limits'].update(max_load_attempts=1, max_infrastructure_recoveries=0)
    key = digest(package)
    ready = {'status': 'ready', 'package_sha256': key, 'model_identities': package['model_identities']}
    messages = [{'action': 'infer', 'request': {'synthetic': True}}, {'action': 'stop', 'package_sha256': key}]
    outputs, children = [], []
    outer = SimpleNamespace(send=lambda v, deadline: outputs.append(v), receive=lambda deadline: messages.pop(0))
    monkeypatch.setattr(module, 'JsonPipe', lambda *args: outer)
    monkeypatch.setattr(module, 'verify_source', lambda *args: None)
    monkeypatch.setattr(module, 'gpu_absent', lambda pid: fault != 'cleanup_unknown')
    monkeypatch.setattr(module, 'sys', SimpleNamespace(stdin=SimpleNamespace(fileno=lambda: 1),
        stdout=SimpleNamespace(fileno=lambda: 2)))
    class Child:
        def __init__(self, *args, **kwargs):
            self.index, self.count, self.closed = len(children), 0, False
            children.append(self)
            self.pipe = self
        def send(self, value, deadline): pass
        def receive(self, deadline):
            self.count += 1
            if self.count == 1:
                if fault in {'both_loads', 'cleanup_unknown', 'single_load'} or (fault == 'first_load' and self.index == 0):
                    raise TimeoutError('synthetic loading timeout')
                return ready
            if fault == 'after_exposure': raise EOFError('synthetic exposed disconnect')
            return {'synthetic_response': True}
        def close(self):
            assert not self.closed; self.closed = True
            return {'pid': 1000 + self.index, 'signals': [], 'exit_observed': True, 'returncode': 0}
    monkeypatch.setattr(module, 'OwnedChild', Child)
    result = module.supervise(tmp_path, package, tmp_path)
    assert len(children) == expected_loads and all(c.closed for c in children)
    assert result['tasks_exposed'] == (fault not in {'both_loads', 'cleanup_unknown', 'single_load'})
    assert (tmp_path / 'gpu-settlement.json').exists()
    if fault == 'cleanup_unknown': assert result['status'] == 'gpu_cleanup_unknown'
    if fault == 'after_exposure': assert (tmp_path / 'tasks-exposed.claim.json').exists()
    if fault is None: assert result['error_type'] is None and outputs[0] == ready
