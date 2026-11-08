"""CPU regressions for observed pre-exposure failures; no model/Rhino execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener.lora_development_admission import sessions_available
from training.lora_development_assets import verify_model_paths
from training.lora_development_export import read_stable


def asset_fixture(tmp_path):
    base, adapter, blobs = [tmp_path / n for n in ('base', 'adapter', 'blobs')]
    for p in (base, adapter, blobs): p.mkdir()
    target = blobs / 'pinned'; target.write_bytes(b'synthetic weights')
    logical = base / 'model'; logical.symlink_to(target)
    direct = adapter / 'adapter'; direct.write_bytes(b'synthetic adapter')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assets = {'snapshot_dir': str(base), 'adapter_root': str(adapter),
              'base_files': {'model': sha(target)}, 'adapter_files': {'adapter': sha(direct)}}
    bindings = {str(p): {'resolved_path': str(p.resolve()), 'sha256': sha(p)} for p in (logical, direct)}
    return assets, bindings, logical, target


def test_bound_hf_style_link_and_direct_adapter_pass_without_model_import(tmp_path):
    assets, bindings, logical, target = asset_fixture(tmp_path)
    files, check = verify_model_paths(assets, bindings)
    assert str(logical) in files and str(target) in files
    check()
    # An equally hashed but unregistered link target is still forbidden.
    other = target.with_name('other'); other.write_bytes(target.read_bytes())
    logical.unlink(); logical.symlink_to(other)
    with pytest.raises(NativeError): check()
    with pytest.raises(NativeError): verify_model_paths(assets, bindings)


def test_same_bound_path_with_changed_bytes_or_postcheck_drift_is_refused(tmp_path):
    assets, bindings, logical, target = asset_fixture(tmp_path)
    _, check = verify_model_paths(assets, bindings)
    target.write_bytes(b'changed bytes')
    with pytest.raises(NativeError): check()
    with pytest.raises(NativeError): verify_model_paths(assets, bindings)


@pytest.mark.parametrize('fault', ['missing', 'unbound_alias'])
def test_model_binding_must_be_complete_and_exact(tmp_path, fault):
    assets, bindings, logical, target = asset_fixture(tmp_path)
    if fault == 'missing': bindings.pop(str(logical))
    else: bindings[str(logical)]['resolved_path'] = str(logical)
    with pytest.raises(NativeError): verify_model_paths(assets, bindings)


@pytest.mark.parametrize('changed', ['atime_only', 'mtime'])
def test_export_read_ignores_access_time_but_not_content_metadata(tmp_path, monkeypatch, changed):
    path = tmp_path / 'new-evidence'; path.write_bytes(b'new private evidence')
    original, calls = os.fstat, []
    def observe(fd):
        value = original(fd); calls.append(fd)
        if len(calls) != 2: return value
        names = ['st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size',
                 'st_mtime_ns','st_ctime_ns','st_atime_ns']
        fields = {k: getattr(value, k) for k in names}
        fields['st_atime_ns' if changed == 'atime_only' else 'st_mtime_ns'] += 1
        return SimpleNamespace(**fields)
    monkeypatch.setattr(os, 'fstat', observe)
    if changed == 'atime_only': assert read_stable(path) == b'new private evidence'
    else:
        with pytest.raises(NativeError): read_stable(path)


@pytest.mark.parametrize('fault', [None, 'live', 'unrelated', 'undettached', 'key_remaining'])
def test_only_exact_retired_predecessor_session_can_remain(tmp_path, fault):
    tmp_path.chmod(0o700); host = tmp_path / 'host'; host.mkdir(mode=0o700)
    runtime = 'a' * 64; source = '/synthetic/prior/source'
    settled = {'runtime_sha256': runtime, 'status': 'host_stopped', 'exact_delegate_remove_returned': True}
    if fault == 'undettached': settled['exact_delegate_remove_returned'] = False
    publish_json(host, 'host-settlement.json', settled)
    if fault == 'key_remaining': publish_json(tmp_path, 'host-secret.json', {'synthetic': True})
    session = SimpleNamespace(state=host, runtime=runtime, stopped=fault != 'live', host=SimpleNamespace(current=None))
    module = SimpleNamespace(__path__=[source if fault != 'unrelated' else '/other'], _SESSION=session)
    package = {'continuation': {'prior_package_sha256': runtime,
        'prior_endpoints': {'mac': {'source_root': source, 'state_root': str(tmp_path)}}}}
    if fault is None: sessions_available({'rhino_lora_old': module}, package)
    else:
        with pytest.raises(NativeError): sessions_available({'rhino_lora_old': module}, package)


@pytest.mark.parametrize('terminal', ['gpu_stopped', 'gpu_cleanup_unknown', 'local_setup_failed'])
def test_mac_retains_early_terminal_settlement_and_never_resends_stop(tmp_path, monkeypatch, terminal):
    from tools import run_lora_development_mac as mac
    from training import lora_development_local_tokenizer as tokenizer, lora_development_authority as authority
    from training import lora_development_process as process, lora_development_export as exporter
    from plugin.rhino_listener import c5_research_channel as channel
    root = tmp_path / 'source'; root.mkdir(); state = tmp_path / 'state-lora-development'; state.mkdir(mode=0o700)
    from eval.test_lora_development_wire import PLAN
    package = {'assets': {}, 'source_files': {}, 'limits': PLAN['limits'], 'lease_end_epoch': 9999999999,
        'endpoints': {'mac': {'state_root': str(state), 'python': str(Path(mac.sys.executable).resolve()),
                             'environment_sha256': digest({})},
                      'gpu': {'python': '/synthetic/python', 'state_root': '/synthetic/state', 'source_root': '/synthetic/source'}},
        'model_identities': {'base': 'a'*64, 'current_lora': 'b'*64}}
    runtime = digest(package); settlement = {'status': terminal, 'package_sha256': runtime, 'tasks_exposed': False}
    (root/'lora-development-package.json').write_text(json.dumps(package))
    (root/'lora-development-mac-environment.json').write_text('{}')
    publish_json(state, 'owner-approval.json', {'synthetic': True})
    monkeypatch.setattr(mac, 'ROOT', root); monkeypatch.setattr(mac.sys, 'argv', ['test', '--ssh-control', '/synthetic/control'])
    monkeypatch.setattr(tokenizer, 'load_tokenizer', lambda _: None)
    monkeypatch.setattr(tokenizer, 'verify_environment', lambda _: None)
    monkeypatch.setattr(authority, 'verify_approval', lambda *a, **k: runtime)
    monkeypatch.setattr(authority, 'verify_source', lambda *a: None)
    monkeypatch.setattr(mac.shutil, 'disk_usage', lambda _: SimpleNamespace(free=3*1024**3))
    def publish(directory, name, value):
        publish_json(directory, name, value)
        if name == 'host-secret.json':
            publish_json(state/'host', 'host-ready.json', {'status':'ready','runtime_sha256':runtime,'entry_return_release_observed':True})
        if name == 'shutdown.request.json':
            publish_json(state/'host', 'host-settlement.json', {'status':'host_stopped'})
    monkeypatch.setattr(channel, 'publish_json', publish)
    sent = []
    monkeypatch.setattr(process, 'JsonPipe', lambda *a: SimpleNamespace(
        receive=lambda deadline: settlement, send=lambda *a: sent.append(a)))
    # This test injects transport/lifecycle outcomes. The real preparation is
    # exercised separately against the shipped bundle, without this stub.
    from training import lora_development_preflight as preflight
    from plugin.rhino_listener.lora_development_runtime import configuration
    from training.lora_development_scope import field_views
    monkeypatch.setattr(preflight, 'prepare', lambda *a: {'config': configuration(package),
        'tokenizer': None, 'check_environment': lambda: None, 'controller': None, 'journal': None,
        'pipe': process.JsonPipe, 'schedule': field_views(PLAN)['schedule'], 'schemas': {}})
    if terminal == 'local_setup_failed':
        def reject_start(directory, name, value):
            if name == 'mac-started.claim.json': raise OSError('synthetic local setup failure')
            return publish(directory, name, value)
        monkeypatch.setattr(channel, 'publish_json', reject_start)
    calls = []
    def popen(command, **kwargs):
        import tempfile
        calls.append(command)
        if len(calls) == 1:
            return SimpleNamespace(stdin=tempfile.TemporaryFile(), stdout=tempfile.TemporaryFile(), wait=lambda **kw: 0)
        read, write = os.pipe(); os.write(write, b'synthetic archive'); os.close(write)
        return SimpleNamespace(stdout=os.fdopen(read,'rb'), wait=lambda **kw:0, poll=lambda:0)
    monkeypatch.setattr(mac.subprocess, 'Popen', popen)
    monkeypatch.setattr(exporter, 'verify_archive', lambda *a: {'verified':True})
    mac.main()
    result = read_json(state, 'development-result.json')
    if terminal == 'local_setup_failed':
        assert not calls and not sent and result['gpu_launch_attempted'] is False
        assert result['host'] == {'status': 'not_started', 'capability_published': False}
        assert result['failures'][0]['stage'] == 'local_setup'
        assert result['failures'][0]['message'] == 'synthetic local setup failure'
        assert result['key_removal']['actual_absence_checked']
        return
    assert result['gpu'] == settlement and result['rows'] == [] and not sent
    assert len(calls) == (2 if terminal == 'gpu_stopped' else 1)
    assert (result['gpu_export'] is not None) == (terminal == 'gpu_stopped')
    assert result['key_removal']['actual_absence_checked']
