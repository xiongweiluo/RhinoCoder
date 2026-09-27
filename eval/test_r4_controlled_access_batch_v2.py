"""Local one-shot lifecycle tests; all external calls are synthetic."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import closing
from types import SimpleNamespace

from tools import r4_controlled_access_batch_v2 as batch
from tools import r4_controlled_access_optin_v2 as optin
from tools import r4_controlled_access_verify_candidate_v2 as verifier
from tools import r4_v6_formal_quality as core
from tools.r4_v5_ssh_no_write_session import _private_publish, _private_read


def _setup(tmp_path, monkeypatch, *, approve=True, hidden_done=False):
    # This unit suite exercises the one-shot state machine with synthetic data.
    # The immutable private v8 run archive is deliberately not published in the
    # review branch; live runs still require _verify_historical_baseline().
    monkeypatch.setattr(batch, "_verify_historical_baseline", lambda: None)
    session = tmp_path / "session"
    session.mkdir(mode=0o700)
    (session / "channel").mkdir(mode=0o700)
    _private_publish(session, "initial.json", {"fixture": "empty"})
    ledger = session / "fixture.sqlite3"
    with closing(sqlite3.connect(ledger)) as db:
        db.execute("CREATE TABLE candidate_write(state TEXT)")
        if hidden_done:
            db.execute("INSERT INTO candidate_write VALUES ('done')")
        db.commit()
    ledger.chmod(0o600)
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir(mode=0o700)
    calls = []

    def fake_batch(_directory, seq, action, case_id, fixture):
        calls.append(action)
        _private_publish(batch_dir, f"request-{seq:03d}.json", {
            "action": action, "case_id": case_id})
        result = ({"status": "opened", "case_id": case_id, "fixture": "empty",
                   "session_dir": str(session)} if action == "open" else
                  {"status": "closed", "case_id": case_id, "session_dir": str(session),
                   "key_removed": True} if action == "close" else
                  {"status": "stopped", "case_id": case_id})
        _private_publish(batch_dir, f"response-{seq:03d}.json", result)
        return result

    monkeypatch.setattr(batch.core, "_batch_request", fake_batch)
    ssh = SimpleNamespace(host=core.HOST, port=core.PORT, user=core.USER,
                          approved_manifest_sha256=core.MODEL_SHA,
                          expected_host_key_sha256=core.HOST_KEY)

    def fake_approve(args):
        if not approve:
            raise optin.OptInError("operator_did_not_opt_in")
        control = tmp_path / "control"
        control.mkdir(mode=0o700)
        return optin.PendingOptIn(
            task_sha256=hashlib.sha256(args.task.encode()).hexdigest(),
            control_dir=control,
            manifest_sha256=core.MODEL_SHA, host_key_sha256=core.HOST_KEY,
            expires_at=time.monotonic() + 60)

    monkeypatch.setattr(batch, "interactive_preflight_opt_in", fake_approve)

    def fake_candidate(args, lease):
        plan = session / "v6-plan-synthetic"
        plan.mkdir(mode=0o700)
        step = plan / "step-1"
        step.mkdir(mode=0o700)
        explicit_sha = hashlib.sha256(b'{"op":"get_scene_summary"}').hexdigest()
        scene_sha = "a" * 64
        _private_publish(step, "remote-result.json", {
            "status": "contract_passed_no_execution", "no_dispatch": True,
            "no_consent": True, "approved_manifest_sha256": core.MODEL_SHA,
            "task_sha256": explicit_sha, "scene_sha256": scene_sha,
        })
        _private_publish(step, "resource-metrics.json", {
            "model_roundtrip_seconds": 1.0})
        record = {"index": 1, "operation": "get_scene_summary",
                  "readback_verified": True, "tool_result": {"object_count": 0},
                  "explicit_task_sha256": explicit_sha,
                  "before_scene_sha256": scene_sha,
                  "remote_result_sha256": hashlib.sha256(
                      (step / "remote-result.json").read_bytes()).hexdigest()}
        _private_publish(step, "record.json", record)
        receipt = {"status": "controlled_access_candidate_v2_completed_not_formal_quality",
                   "active_document_unchanged": True, "step_count": 1, "steps": [record],
                   "approved_manifest_sha256": core.MODEL_SHA,
                   "host_key_sha256": core.HOST_KEY,
                   "original_task_sha256": hashlib.sha256(args.task.encode()).hexdigest(),
                   "operator_opt_in_grant_sha256": hashlib.sha256(
                       (lease.control_dir / "grant.json").read_bytes()).hexdigest()}
        _private_publish(plan, "receipt.json", receipt)
        return plan, receipt

    monkeypatch.setattr(batch, "run_candidate", fake_candidate)
    return batch_dir, ssh, calls


def test_one_shot_closes_archives_and_stops_on_success(tmp_path, monkeypatch):
    batch_dir, ssh, calls = _setup(tmp_path, monkeypatch)
    output = tmp_path / "output"
    result = batch.run_one(batch_dir, output, "RCA2-READ", "读取场景概要", ssh)
    assert result["status"] == "candidate_recorded_unverified"
    assert result["ledger"] == result["expected_ledger"] == {}
    assert calls == ["open", "close", "stop"]
    assert (output / "cases/RCA2-READ/fixture.sqlite3").is_file()
    assert (output / "evidence-manifest.json").is_file()
    assert (output / "operator-grant.json").is_file()
    assert verifier.verify_archive(output)["status"] == (
        "candidate_evidence_verified_not_formal_quality")


def test_declined_opt_in_never_opens_fixture_and_stops_controller(tmp_path, monkeypatch):
    batch_dir, ssh, calls = _setup(tmp_path, monkeypatch, approve=False)
    monkeypatch.setattr(batch, "run_candidate", lambda *_a: (_ for _ in ()).throw(
        AssertionError("candidate should not run")))
    output = tmp_path / "output"
    result = batch.run_one(batch_dir, output, "RCA2-DECLINE", "读取场景概要", ssh)
    assert result["status"] == "candidate_fail"
    assert "operator_did_not_opt_in" in result["error"]
    assert calls == ["stop"]
    assert result["fixture_opened"] is False
    assert result["fixture_closed"] is False and result["controller_stopped"] is True


def test_late_open_after_timeout_is_reconciled_and_closed(tmp_path, monkeypatch):
    batch_dir, ssh, calls = _setup(tmp_path, monkeypatch)
    normal_batch = batch.core._batch_request

    def late_batch(directory, seq, action, case_id, fixture):
        if action == "open":
            calls.append("open_timeout")
            _private_publish(batch_dir, "request-001.json", {
                "action": "open", "case_id": case_id})
            _private_publish(batch_dir, "response-001.json", {
                "status": "opened", "case_id": case_id, "fixture": "empty",
                "session_dir": str(tmp_path / "session")})
            raise RuntimeError("rhino_formal_batch_timeout")
        return normal_batch(directory, seq, action, case_id, fixture)

    monkeypatch.setattr(batch.core, "_batch_request", late_batch)
    monkeypatch.setattr(batch, "run_candidate", lambda *_a: (_ for _ in ()).throw(
        AssertionError("late-open failure must not run candidate")))
    result = batch.run_one(batch_dir, tmp_path / "late", "RCA2-LATE", "读取场景概要", ssh)
    assert result["status"] == "candidate_fail"
    assert "rhino_formal_batch_timeout" in result["error"]
    assert result["late_open_reconciled"] is True
    assert result["cleanup_queued_unverified"] is False
    assert result["fixture_closed"] and result["key_removed"] and result["controller_stopped"]
    assert calls == ["open_timeout", "close", "stop"]
    assert _private_read(batch_dir / "request-002.json")["action"] == "close"
    assert _private_read(batch_dir / "request-003.json")["action"] == "stop"


def test_unresolved_open_queues_ordered_cleanup_without_false_success(tmp_path, monkeypatch):
    batch_dir, ssh, calls = _setup(tmp_path, monkeypatch)

    def timeout_batch(_directory, seq, action, case_id, _fixture):
        assert seq == 1 and action == "open"
        calls.append("open_timeout")
        _private_publish(batch_dir, "request-001.json", {
            "action": "open", "case_id": case_id})
        raise RuntimeError("rhino_formal_batch_timeout")

    monkeypatch.setattr(batch.core, "_batch_request", timeout_batch)
    monkeypatch.setattr(batch, "_reconcile_late_open", lambda *_a, **_k: None)
    result = batch.run_one(batch_dir, tmp_path / "unresolved", "RCA2-UNRESOLVED",
                           "读取场景概要", ssh)
    assert result["status"] == "candidate_fail"
    assert result["late_open_reconciled"] is False
    assert result["cleanup_queued_unverified"] is True
    assert not result["fixture_closed"] and not result["controller_stopped"]
    assert calls == ["open_timeout"]
    assert _private_read(batch_dir / "request-002.json")["action"] == "close"
    assert _private_read(batch_dir / "request-003.json")["action"] == "stop"


def test_hidden_done_transaction_blocks_success_but_still_stops(tmp_path, monkeypatch):
    batch_dir, ssh, calls = _setup(tmp_path, monkeypatch, hidden_done=True)
    output = tmp_path / "output"
    result = batch.run_one(batch_dir, output, "RCA2-MISMATCH", "读取场景概要", ssh)
    assert result["status"] == "candidate_fail"
    assert "archived_ledger_disagrees_with_run" in result["error"]
    assert calls == ["open", "close", "stop"]
    assert not (output / "cases/RCA2-MISMATCH/fixture.sqlite3").exists()


def test_invalid_case_id_rejected_before_any_fixture_open(tmp_path, monkeypatch):
    batch_dir, ssh, calls = _setup(tmp_path, monkeypatch)
    try:
        batch.run_one(batch_dir, tmp_path / "output", "../escape", "读取场景概要", ssh)
    except ValueError as exc:
        assert "candidate_case_id_invalid" in str(exc)
    else:
        raise AssertionError("invalid ID accepted")
    assert calls == []


def test_verifier_rejects_tampered_remote_evidence(tmp_path, monkeypatch):
    batch_dir, ssh, _calls = _setup(tmp_path, monkeypatch)
    output = tmp_path / "output"
    batch.run_one(batch_dir, output, "RCA2-TAMPER", "读取场景概要", ssh)
    remote = output / "cases/RCA2-TAMPER/step-1-remote-result.json"
    remote.write_bytes(b"{}")
    try:
        verifier.verify_archive(output)
    except verifier.CandidateEvidenceError as exc:
        assert "manifest_file_mismatch" in str(exc)
    else:
        raise AssertionError("tampered remote evidence accepted")
