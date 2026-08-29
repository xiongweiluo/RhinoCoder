from __future__ import annotations

import json

import pytest

import agent.trace_store as trace_store
from agent.runtime import AgentRunResult, RunMetrics, RunStatus, ToolCallRecord
from agent.sanitizer import contains_sensitive_data, sanitize_structure, sanitize_text
from agent.trace_store import (
    CANDIDATE,
    ERROR_ANALYSIS,
    GOLDEN,
    PARTIAL,
    build_trace_record,
    classify_trace_disposition,
    save_golden,
    save_candidate,
    save_rejected_trace,
    validate_saved_golden_record,
    validate_golden_candidate,
)


def _run(
    with_scene_check: bool = True,
    *,
    successful_summary: bool = True,
    status: RunStatus = RunStatus.COMPLETED,
) -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        status=status,
        messages=[{"role": "user", "content": "create object"}],
        metrics=RunMetrics(started_at="now"),
        scene_checks=[{"output": "ok"}] if with_scene_check else [],
        tool_calls=[
            ToolCallRecord(
                call_id="call-1",
                name="get_scene_summary",
                arguments={},
                round_index=1,
                started_at="now",
                success=successful_summary,
            )
        ],
    )


def _record(
    *,
    evaluation=None,
    run=None,
    feedback_label: str = "accepted",
):
    return build_trace_record(
        "task",
        run or _run(),
        evaluation=evaluation or {"passed": True, "partial": False},
        feedback={"label": feedback_label, "source": "human_review"},
    )


def test_sanitize_secret_path_coordinate_and_layer():
    text = "key sk-abcdefghijklmnop at /Users/alice/project and (1, 2, 3), layer 'SecretProject'"  # secret-scan: allow
    sanitized = sanitize_text(text)
    assert "sk-abcdefghijklmnop" not in sanitized  # secret-scan: allow
    assert "/Users/alice" not in sanitized
    assert "(1, 2, 3)" not in sanitized
    assert "SecretProject" not in sanitized
    assert not contains_sensitive_data(sanitized)


def test_redaction_marker_does_not_join_numbered_lines_into_coordinate():
    sanitized = sanitize_text("move z=5\n4. verify the scene")

    assert "z=<COORD_REDACTED>" in sanitized
    assert not contains_sensitive_data(sanitized)


def test_sanitize_structured_coordinate_and_token():
    data = {
        "center": [1, 2, 3],
        "api_key": "secret-value-123",
        "size": [10, 10, 10],
        "total_tokens": 42,
        "center_x": 1,
        "center_y": 2,
        "center_z": 3,
    }
    sanitized = sanitize_structure(data)
    assert sanitized["center"] == "<COORD_REDACTED>"
    assert sanitized["api_key"] == "<SECRET_REDACTED>"
    assert sanitized["size"] == [10, 10, 10]
    assert sanitized["total_tokens"] == 42
    assert sanitized["center_x"] == "<COORD_REDACTED>"
    assert not contains_sensitive_data(sanitized)


def test_sanitize_object_guid_project_layer_and_group_but_keep_run_id():
    data = {
        "run_id": "11111111-1111-4111-8111-111111111111",
        "object_id": "22222222-2222-4222-8222-222222222222",
        "layer": "Client-Alpha",
        "groups": ["Private Assembly"],
    }
    sanitized = sanitize_structure(data)
    assert sanitized["run_id"] == data["run_id"]
    assert sanitized["object_id"] == "<GUID_REDACTED>"
    assert sanitized["layer"] == "<LAYER_REDACTED>"
    assert sanitized["groups"] == ["<GROUP_REDACTED>"]
    assert not contains_sensitive_data(sanitized)


def test_golden_gate_requires_all_conditions():
    record = _record()
    gate = validate_golden_candidate(record, human_confirmed=True)
    assert gate.accepted
    assert classify_trace_disposition(record, gate) == GOLDEN

    no_check = _record(run=_run(False))
    gate = validate_golden_candidate(no_check, human_confirmed=True)
    assert not gate.accepted
    assert "missing_scene_check" in gate.reasons

    failed_tool = _record(run=_run(successful_summary=False))
    gate = validate_golden_candidate(failed_tool, human_confirmed=True)
    assert "missing_successful_get_scene_summary" in gate.reasons


def test_golden_gate_rejects_partial_and_missing_human_confirmation():
    record = _record(evaluation={"passed": False, "partial": True}, feedback_label="partial")
    gate = validate_golden_candidate(record, human_confirmed=False)
    assert "programmatic_assertions_not_passed" in gate.reasons
    assert "partial_pass_not_golden" in gate.reasons
    assert "human_not_confirmed" in gate.reasons
    assert "accepted_feedback_missing" in gate.reasons
    assert classify_trace_disposition(record, gate) == PARTIAL


def test_failed_and_human_rejected_traces_have_separate_dispositions():
    failed = _record(
        evaluation={"passed": False, "partial": False},
        run=_run(status=RunStatus.FAILED),
        feedback_label="rejected",
    )
    failed_gate = validate_golden_candidate(failed, human_confirmed=False)
    assert classify_trace_disposition(failed, failed_gate) == ERROR_ANALYSIS

    human_rejected = _record(feedback_label="rejected")
    rejected_gate = validate_golden_candidate(human_rejected, human_confirmed=False)
    assert classify_trace_disposition(human_rejected, rejected_gate) == CANDIDATE


def test_rejected_trace_is_written_to_partial_or_error_file(monkeypatch, tmp_path):
    monkeypatch.setattr(trace_store, "PARTIAL_FILE", tmp_path / "partial.jsonl")
    monkeypatch.setattr(trace_store, "ERROR_ANALYSIS_FILE", tmp_path / "error.jsonl")

    partial = _record(evaluation={"passed": False, "partial": True}, feedback_label="partial")
    partial_gate = validate_golden_candidate(partial, human_confirmed=False)
    disposition, path = save_rejected_trace(partial, partial_gate)
    assert disposition == PARTIAL and path == trace_store.PARTIAL_FILE
    assert json.loads(path.read_text(encoding="utf-8"))["disposition"] == PARTIAL
    with pytest.raises(ValueError, match="Partial Trace"):
        save_candidate(partial)

    failed = _record(
        evaluation={"passed": False, "partial": False},
        run=_run(status=RunStatus.FAILED),
        feedback_label="rejected",
    )
    failed_gate = validate_golden_candidate(failed, human_confirmed=False)
    disposition, path = save_rejected_trace(failed, failed_gate)
    assert disposition == ERROR_ANALYSIS and path == trace_store.ERROR_ANALYSIS_FILE
    with pytest.raises(ValueError, match="失败 Trace"):
        save_candidate(failed)


def test_golden_write_boundary_rechecks_audit_and_writes_sanitized_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(trace_store, "GOLDEN_FILE", tmp_path / "golden.jsonl")
    record = _record()
    record["run"]["messages"].append(
        {
            "role": "assistant",
            "content": "object 22222222-2222-4222-8222-222222222222 on layer: 'Client'",
        }
    )
    gate = validate_golden_candidate(record, human_confirmed=True)
    assert gate.accepted

    save_golden(gate)

    saved = json.loads(trace_store.GOLDEN_FILE.read_text(encoding="utf-8"))
    assert saved["run_id"] == "run-1"
    assert saved["metadata"]["app_version"]
    assert saved["metadata"]["admission"]["run_status"] == "completed"
    assert saved["metadata"]["admission"]["human_confirmed"] is True
    assert "22222222-2222-4222-8222-222222222222" not in json.dumps(saved)
    assert validate_saved_golden_record(saved) == []

    gate.sanitized_record["admission"]["human_confirmed"] = False
    with pytest.raises(ValueError, match="准入审计不完整"):
        save_golden(gate)


def test_legacy_golden_row_is_not_admissible():
    reasons = validate_saved_golden_record({"messages": [{"role": "user", "content": "legacy"}]})
    assert "missing_run_id" in reasons
    assert "evaluation_not_full_pass" in reasons
    assert "accepted_feedback_missing" in reasons
    assert "admission_successful_get_scene_summary_invalid" in reasons
