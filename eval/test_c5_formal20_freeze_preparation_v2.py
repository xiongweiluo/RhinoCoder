"""CPU-only admission controls: no deployment, model or private-file access."""
import pytest

from plugin.rhino_listener.c5_research_native import NativeError


def prepare(tmp_path, monkeypatch):
    from tools import prepare_c5_formal20_freeze_v2 as builder
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'MAC_SOURCE', tmp_path / 'source')
    monkeypatch.setattr(builder, 'MAC_STATE', tmp_path / 'state')
    monkeypatch.setattr(builder, 'mac_preflight', lambda: pytest.fail('no CPU renderer/deployment permitted'))
    return builder


@pytest.mark.parametrize('existing', ('source', 'state', 'freeze'))
def test_existing_partial_preparation_never_overwritten(tmp_path, monkeypatch, existing):
    builder = prepare(tmp_path, monkeypatch)
    path = {'source': builder.MAC_SOURCE, 'state': builder.MAC_STATE,
            'freeze': tmp_path / builder.FREEZE_FILE}[existing]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'preserved unknown partial evidence')
    monkeypatch.setattr(builder.subprocess, 'check_output', lambda *a, **k: pytest.fail('no command permitted'))
    with pytest.raises(NativeError): builder.build()
    assert path.read_bytes() == b'preserved unknown partial evidence'


def test_dirty_checkout_rejected_before_public_or_remote_io(tmp_path, monkeypatch):
    builder = prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(builder.subprocess, 'check_output', lambda *a, **k: ' M unrelated.txt\n')
    monkeypatch.setattr(builder, 'public', lambda *a: pytest.fail('no public/deployment processing permitted'))
    with pytest.raises(NativeError): builder.build()
    assert not builder.MAC_SOURCE.exists() and not builder.MAC_STATE.exists()


def test_missing_capacity_acceptance_rejected_before_renderer_or_deployment(tmp_path, monkeypatch):
    builder = prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(builder.subprocess, 'check_output', lambda *a, **k: '')
    monkeypatch.setattr(builder, 'public', lambda *a: {})
    with pytest.raises(NativeError): builder.build()
    assert not builder.MAC_SOURCE.exists() and not builder.MAC_STATE.exists()
