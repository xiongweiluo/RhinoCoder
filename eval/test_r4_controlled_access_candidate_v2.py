"""Candidate opt-in/invoker integration tests, without SSH or Rhino writes."""

from __future__ import annotations

import hashlib
import json
import time
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def private_optin_test_directory(tmp_path, monkeypatch):
    """Keep Mac-only runner paths out of Linux CI without changing sealed code."""
    import tempfile
    original = tempfile.mkdtemp
    def in_test_directory(*args, **kwargs):
        kwargs["dir"] = str(tmp_path)
        return original(*args, **kwargs)
    monkeypatch.setattr(optin, "tempfile", SimpleNamespace(mkdtemp=in_test_directory))

from tools import r4_controlled_access_candidate_v2 as candidate
from tools import r4_controlled_access_optin_v2 as optin
from tools import r4_controlled_access_remote_guard_v2 as boundary
from tools import r4_v6_formal_quality as core
from tools.r4_v6_live_multistep import Capture
from tools.r4_v5_ssh_no_write_session import _private_publish
from training.tool_controller_candidate import SceneState


TASK = "读取场景概要；查看选中对象"


def _args(tmp_path, task=TASK):
    return SimpleNamespace(
        session_dir=tmp_path, task=task,
        host=core.HOST, port=core.PORT, user=core.USER,
        approved_manifest_sha256=core.MODEL_SHA,
        expected_host_key_sha256=core.HOST_KEY,
        fixture_name="empty", delegated_headless_approval=True,
    )


def _lease(tmp_path, args):
    control = tmp_path / "optin"
    control.mkdir(mode=0o700)
    _private_publish(control, "grant.json", {"test_only": True})
    return optin.OptInLease(
        task_sha256=hashlib.sha256(args.task.encode()).hexdigest(),
        session_dir=tmp_path.resolve(), control_dir=control,
        manifest_sha256=core.MODEL_SHA, host_key_sha256=core.HOST_KEY,
        expires_at=time.monotonic() + 60,
    )


def _capture():
    state = SceneState(0, "a" * 64, {
        "aliases": [], "object_count": 0,
        "unit": "Millimeters", "document_key": "b" * 64,
    })
    return Capture(state, (), ())


def _mock_scene(monkeypatch):
    initial = _capture()
    monkeypatch.setattr(candidate, "_initial", lambda _directory: initial)
    monkeypatch.setattr(candidate, "V6Scene", lambda _directory: SimpleNamespace(
        capture=lambda: initial, snapshot=lambda: initial.state))


def test_interactive_opt_in_requires_tty_and_exact_challenge(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(optin.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    with pytest.raises(optin.OptInError, match="interactive_terminal_required"):
        optin.interactive_opt_in(args)
    monkeypatch.setattr(optin.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(optin.secrets, "token_hex", lambda _size: "abcd1234")
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    with pytest.raises(optin.OptInError, match="operator_did_not_opt_in"):
        optin.interactive_opt_in(args)
    monkeypatch.setattr("builtins.input", lambda _prompt: "APPROVE-R4-ABCD1234")
    lease = optin.interactive_opt_in(args)
    lease.claim(args)
    with pytest.raises(optin.OptInError, match="already_consumed"):
        lease.claim(args)
    optin.request_stop(lease.control_dir)
    with pytest.raises(optin.OptInError, match="operator_stop_requested"):
        lease.check(args)


def test_preflight_opt_in_requires_human_reply_before_session_grant(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(optin.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(optin.secrets, "token_hex", lambda _size: "abcd1234")
    monkeypatch.setattr("builtins.input", lambda _prompt: "APPROVE-R4-ABCD1234")
    pending = optin.interactive_preflight_opt_in(args)
    assert not (pending.control_dir / "grant.json").exists()
    lease = pending.bind(args)
    assert json.loads((pending.control_dir / "grant.json").read_text())["session_dir"] == (
        str(tmp_path.resolve()))
    lease.claim(args)
    with pytest.raises(optin.OptInError, match="pending_opt_in_scope_inactive_or_changed"):
        pending.bind(args)


def test_preflight_stop_or_scope_change_blocks_fixture_binding(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(optin.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(optin.secrets, "token_hex", lambda _size: "abcd1234")
    monkeypatch.setattr("builtins.input", lambda _prompt: "APPROVE-R4-ABCD1234")
    pending = optin.interactive_preflight_opt_in(args)
    args.host = "other"
    with pytest.raises(optin.OptInError, match="pending_opt_in_scope_inactive_or_changed"):
        pending.bind(args)
    args.host = core.HOST
    optin.request_stop(pending.control_dir)
    with pytest.raises(optin.OptInError, match="operator_stop_requested"):
        pending.bind(args)
    assert not (pending.control_dir / "grant.json").exists()


def test_candidate_calls_real_outbound_guard_on_each_read_step(tmp_path, monkeypatch):
    args = _args(tmp_path)
    lease = _lease(tmp_path, args)
    _mock_scene(monkeypatch)
    sent = []

    def fake_remote(_args, _directory, _state, step_dir, *, task, model_task=None):
        sent.append(task)
        _private_publish(step_dir, "remote-result.json", {"synthetic": True})
        return {}, {}, "f" * 64

    monkeypatch.setattr(boundary, "_remote_result", fake_remote)
    monkeypatch.setattr(candidate, "verify_no_dispatch_result",
                        lambda _result, *, task, **_kwargs:
                        SimpleNamespace(name=json.loads(task)["op"]))
    monkeypatch.setattr(candidate, "_execute", lambda *_args: pytest.fail("Rhino write"))
    _run_dir, receipt = candidate.run(args, lease)
    assert receipt["step_count"] == 2
    assert receipt["status"] == "controlled_access_candidate_v2_completed_not_formal_quality"
    assert [json.loads(task)["op"] for task in sent] == [
        "get_scene_summary", "get_selected_objects"]
    assert all(row["readback_verified"] is True for row in receipt["steps"])


def test_stop_after_first_model_response_prevents_next_step_and_write(tmp_path, monkeypatch):
    args = _args(tmp_path)
    lease = _lease(tmp_path, args)
    _mock_scene(monkeypatch)
    sent = []

    def fake_remote(_args, _directory, _state, step_dir, *, task, model_task=None):
        sent.append(task)
        _private_publish(step_dir, "remote-result.json", {"synthetic": True})
        optin.request_stop(lease.control_dir)
        return {}, {}, "f" * 64

    monkeypatch.setattr(boundary, "_remote_result", fake_remote)
    monkeypatch.setattr(candidate, "_execute", lambda *_args: pytest.fail("Rhino write"))
    with pytest.raises(optin.OptInError, match="operator_stop_requested"):
        candidate.run(args, lease)
    assert len(sent) == 1


def test_stop_during_write_model_call_prevents_consent_and_rhino_dispatch(tmp_path, monkeypatch):
    args = _args(tmp_path, task='{"op":"create_box","width":2,"depth":3,"height":4}')
    lease = _lease(tmp_path, args)
    _mock_scene(monkeypatch)

    class FakeConsent:
        def __init__(self, *_args):
            pass

        def prepare(self, *_args, **_kwargs):
            pytest.fail("consent preparation")

    monkeypatch.setattr(candidate, "ConsentStore", FakeConsent)
    monkeypatch.setattr(candidate, "_execute", lambda *_a: pytest.fail("Rhino write"))

    def fake_remote(_args, _directory, _state, step_dir, *, task, model_task=None):
        _private_publish(step_dir, "remote-result.json", {"synthetic": True})
        optin.request_stop(lease.control_dir)
        return {}, {}, "f" * 64

    monkeypatch.setattr(boundary, "_remote_result", fake_remote)
    with pytest.raises(optin.OptInError, match="operator_stop_requested"):
        candidate.run(args, lease)


def test_candidate_rejects_high_privacy_before_remote(tmp_path, monkeypatch):
    args = _args(tmp_path, task="读取场景概要；查看选中对象，仅本地处理")
    lease = _lease(tmp_path, args)
    _mock_scene(monkeypatch)
    monkeypatch.setattr(boundary, "_remote_result", lambda *_a, **_k: pytest.fail("SSH"))
    result = candidate.run(args, lease)
    assert result[1]["model_calls"] == 0


@pytest.mark.parametrize("change", (
    {"host": "other"}, {"fixture_name": "seeded_one"},
    {"delegated_headless_approval": False},
))
def test_lease_rejects_scope_changes_before_scene_or_remote(tmp_path, monkeypatch, change):
    args = _args(tmp_path)
    lease = _lease(tmp_path, args)
    for key, value in change.items():
        setattr(args, key, value)
    monkeypatch.setattr(candidate, "_initial", lambda _directory: pytest.fail("Rhino capture"))
    with pytest.raises(optin.OptInError, match="opt_in_scope_inactive_or_changed"):
        candidate.run(args, lease)
