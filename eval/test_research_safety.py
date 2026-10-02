from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugin.rhino_listener.research_safety import (ResearchSafetyError, canonical_hash, cleanup_plan,
    verify_exact_transition, verify_final_active_capture, verify_loaded_sources, verify_write_binding)


def test_unknown_late_open_never_targets_a_guessed_session():
    for receipt in (None, {}, {"status": "opened", "case_id": "OTHER", "session_dir": "/tmp/other"}):
        plan = cleanup_plan(open_published=True, case_id="CASE", opened=receipt)
        assert plan["state"] == "identity_unknown_manual_cleanup"
        assert plan["actions"] == [] and not plan["cleanup_verified"]


def test_verified_open_and_close_timeout_keep_cleanup_pending():
    opened = {"status": "opened", "case_id": "CASE", "fixture": "empty", "session_dir": "/tmp/session"}
    plan = cleanup_plan(open_published=True, case_id="CASE", opened=opened, closed=None)
    assert plan["actions"] == ["close", "stop"] and not plan["cleanup_verified"]
    closed = {"status": "closed", "case_id": "CASE", "session_dir": "/tmp/session", "key_removed": True}
    assert cleanup_plan(open_published=True, case_id="CASE", opened=opened, closed=closed)["actions"] == ["stop"]


def test_final_capture_compares_raw_digests_and_exact_session():
    capture = {"case_id": "CASE", "session_dir": "/tmp/session", "on_rhino_main_thread": True,
               "capture_scope": "same_ui_callback_before_and_after_fixture_close", "close_seq": 2,
               "fixture_closed": True, "key_removed": True,
               **{k: "a"*64 for k in ("initial_active_sha256", "before_close_active_sha256", "after_close_active_sha256")}}
    assert verify_final_active_capture(capture, case_id="CASE", session_dir="/tmp/session", initial_sha256="a"*64)
    capture["after_close_active_sha256"] = "b"*64
    with pytest.raises(ResearchSafetyError):
        verify_final_active_capture(capture, case_id="CASE", session_dir="/tmp/session", initial_sha256="a"*64)


def test_exact_geometry_and_no_unsupported_tool_scope_claim():
    before = {"objects": []}
    after = {"objects": [{"alias": "box-1", "min": [0, 0, 0], "max": [11, 13, 17]}]}
    assert verify_exact_transition("create_box", {"width": 11, "depth": 13, "height": 17}, before, after)
    moved = {"objects": [{"alias": "box-1", "min": [2, -3, 5], "max": [13, 10, 22]}]}
    args = {"alias": "box-1", "translate_x": 2, "translate_y": -3, "translate_z": 5}
    assert verify_exact_transition("move_object", args, after, moved)
    moved["objects"][0]["max"][0] += 1
    with pytest.raises(ResearchSafetyError): verify_exact_transition("move_object", args, after, moved)
    with pytest.raises(ResearchSafetyError): verify_exact_transition("create_sphere", {}, before, after)


def test_loaded_untracked_dependency_or_source_drift_is_rejected(tmp_path):
    file = tmp_path/"module.py"
    file.write_text("pass\n")
    import hashlib
    inventory = {"module.py": hashlib.sha256(file.read_bytes()).hexdigest()}
    verify_loaded_sources(tmp_path, inventory, [SimpleNamespace(__file__=str(file))])
    with pytest.raises(ResearchSafetyError):
        verify_loaded_sources(tmp_path, inventory, [SimpleNamespace(__file__=str(tmp_path/"undeclared.py"))])
    file.write_text("changed\n")
    with pytest.raises(ResearchSafetyError): verify_loaded_sources(tmp_path, inventory, [])


@pytest.mark.parametrize("tamper", [None, "request_sha256", "idempotency_key", "result_sha256", "consent_arguments", "task_sha256"])
def test_execution_consent_scene_and_ledger_are_cross_bound(tamper):
    import hashlib
    request_id = "request-12345678901234567890"
    key = hashlib.sha256(request_id.encode()).hexdigest()
    record = {"request_id": request_id, "operation": "create_box", "before_scene_sha256": "a"*64,
              "after_scene_sha256": "b"*64, "signed_arguments": {"width": 11, "depth": 13, "height": 17},
              "before_revision": 1, "document_key": "d"*64, "task_sha256": "e"*64}
    execution = {**{k: record[k] for k in ("operation", "before_scene_sha256", "after_scene_sha256")},
                 "ledger_state": "done", "status": "done", "result_sha256": "f"*64,
                 "idempotency_key_sha256": hashlib.sha256(key.encode()).hexdigest()}
    ledger = {"idempotency_key": key, "expected_sha256": "a"*64, "expected_revision": 1, "state": "done",
              "document_key": "d"*64, "result_sha256": "f"*64,
              "request_sha256": canonical_hash({"operation": record["operation"], "arguments": record["signed_arguments"]})}
    consent = {"request_id": request_id, "tool_name": "create_box", "status": "consumed",
               "arguments_sha256": canonical_hash(record["signed_arguments"]), "task_sha256": record["task_sha256"],
               "scene_revision": 1, "scene_sha256": "a"*64}
    payload = {"request_id": request_id, "operation": "create_box", "arguments": record["signed_arguments"],
               "scene_revision": 1, "scene_sha256": "a"*64, "document_key": "d"*64, "task_sha256": record["task_sha256"]}
    events = [{"request_id": request_id, "event_type": e} for e in
              ("requested", "approved", "consumed", "signed_handoff_issued")]
    if tamper in {"request_sha256", "idempotency_key", "result_sha256"}: ledger[tamper] = "c"*64
    if tamper == "consent_arguments": consent["arguments_sha256"] = "c"*64
    if tamper == "task_sha256": payload["task_sha256"] = "c"*64
    kwargs = dict(record=record, execution=execution, ledger_row=ledger, consent_events=events,
                  consent_request=consent, envelope_payload=payload)
    if tamper:
        with pytest.raises(ResearchSafetyError): verify_write_binding(**kwargs)
    else:
        assert verify_write_binding(**kwargs)


@pytest.mark.parametrize("name", ["../outside.py", "/outside.py"])
def test_source_inventory_cannot_escape_root(tmp_path, name):
    with pytest.raises(ResearchSafetyError): verify_loaded_sources(tmp_path, {name: "a"*64}, [])
