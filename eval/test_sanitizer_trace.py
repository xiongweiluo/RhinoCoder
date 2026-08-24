from __future__ import annotations

from agent.runtime import AgentRunResult, RunMetrics, RunStatus
from agent.sanitizer import contains_sensitive_data, sanitize_structure, sanitize_text
from agent.trace_store import build_trace_record, validate_golden_candidate


def _run(with_scene_check: bool = True) -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        status=RunStatus.COMPLETED,
        messages=[{"role": "user", "content": "create object"}],
        metrics=RunMetrics(started_at="now"),
        scene_checks=[{"output": "ok"}] if with_scene_check else [],
    )


def test_sanitize_secret_path_coordinate_and_layer():
    text = "key sk-abcdefghijklmnop at /Users/alice/project and (1, 2, 3), layer 'SecretProject'"  # secret-scan: allow
    sanitized = sanitize_text(text)
    assert "sk-abcdefghijklmnop" not in sanitized  # secret-scan: allow
    assert "/Users/alice" not in sanitized
    assert "(1, 2, 3)" not in sanitized
    assert "SecretProject" not in sanitized
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


def test_golden_gate_requires_all_conditions():
    record = build_trace_record("task", _run(), evaluation={"passed": True})
    gate = validate_golden_candidate(record, human_confirmed=True)
    assert gate.accepted

    no_check = build_trace_record("task", _run(False), evaluation={"passed": True})
    gate = validate_golden_candidate(no_check, human_confirmed=True)
    assert not gate.accepted
    assert "missing_scene_check" in gate.reasons


def test_golden_gate_rejects_partial_and_missing_human_confirmation():
    record = build_trace_record("task", _run(), evaluation={"passed": False, "partial": True})
    gate = validate_golden_candidate(record, human_confirmed=False)
    assert "programmatic_assertions_not_passed" in gate.reasons
    assert "human_not_confirmed" in gate.reasons
