"""Fail-closed outbound scope for any future remote-GPU opt-in adapter."""

from types import SimpleNamespace

import pytest

from tools import r4_v6_formal_quality as core
from tools import r4_controlled_access_remote_guard_v2 as boundary
from tools.r4_controlled_access_remote_guard_v2 import (
    RemoteScopeError, require_remote_scope,
)
from training.tool_controller_candidate import SceneState


def test_review_checkout_requires_explicit_remote_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "HOST", "unconfigured.invalid")
    monkeypatch.setattr(core, "PORT", 0)
    monkeypatch.setattr(core, "KNOWN_HOSTS", tmp_path / "missing-known-hosts")
    monkeypatch.setattr(core, "CONTROL", tmp_path / "missing-control")
    with pytest.raises(RuntimeError, match="approved_remote_config_required"):
        core.require_remote_config()


def _args(**overrides):
    value = dict(approved_manifest_sha256=core.MODEL_SHA,
                 expected_host_key_sha256=core.HOST_KEY,
                 host=core.HOST, port=core.PORT, user=core.USER,
                 fixture_name="empty", delegated_headless_approval=True)
    value.update(overrides)
    return SimpleNamespace(**value)


def _scene(*, aliases=()):
    return SceneState(0, "0" * 64, {"aliases": list(aliases),
                                   "object_count": len(aliases),
                                   "unit": "Millimeters"})


def _check(args=None, *, explicit_task='{"op":"create_box","width":2,"depth":3,"height":4}',
           model_task=None, scene=None):
    require_remote_scope(args or _args(), explicit_task=explicit_task,
                         model_task=model_task, scene=scene or _scene())


def test_only_low_risk_fully_pinned_disposable_scope_is_permitted():
    _check()


@pytest.mark.parametrize("payload", (
    "仅本地处理，不要上传",
    "联系 me@example.com 后创建盒子",
    "password: abcdefghijklmnop",
))
def test_medium_high_and_critical_payloads_are_rejected_before_remote(payload):
    with pytest.raises(RemoteScopeError, match="remote_gpu_privacy_rejected"):
        _check(model_task=payload)


def test_sensitive_scene_alias_is_rejected_even_if_task_is_benign():
    with pytest.raises(RemoteScopeError, match="remote_gpu_privacy_rejected"):
        _check(scene=_scene(aliases=("client:Acme",)))


@pytest.mark.parametrize("override", (
    {"approved_manifest_sha256": "0" * 64},
    {"expected_host_key_sha256": "SHA256:other"},
    {"host": "different.example"},
    {"fixture_name": "seeded_one"},
    {"delegated_headless_approval": False},
))
def test_identity_and_scope_downgrades_are_rejected(override):
    with pytest.raises(RemoteScopeError):
        _check(args=_args(**override))


def test_guarded_invoker_never_dispatches_rejected_payload(monkeypatch):
    calls = []
    monkeypatch.setattr(boundary, "_remote_result", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(RemoteScopeError, match="remote_gpu_privacy_rejected"):
        boundary.guarded_remote_result(_args(), None, _scene(), None,
                                       task='{"op":"create_box"}',
                                       model_task="仅本地处理，不要上传")
    assert calls == []


def test_guarded_invoker_dispatches_low_risk_payload_once(monkeypatch):
    calls = []
    monkeypatch.setattr(boundary, "_remote_result", lambda *a, **k: calls.append((a, k)))
    boundary.guarded_remote_result(_args(), "fixture", _scene(), "audit",
                                   task='{"op":"create_box"}', model_task=None)
    assert len(calls) == 1
