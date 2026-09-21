"""Synthetic-only tests for the read-only, aggregate C4 post-hoc audit."""

from __future__ import annotations

import pytest

from tools.diagnose_c4_failures import summarize_attempts
from training.config import ReadinessError


def _row(task: str, *, infrastructure: bool = False, passed: bool = False) -> dict:
    return {
        "task_id": task,
        "model_lane": "lora",
        "holdout_read": 0,
        "infrastructure_error": "synthetic transport interruption" if infrastructure else "",
        "automated_pass": passed,
        "failure_category": None if passed else "planning_error",
        "tool_calls": [],
        "runs": [] if infrastructure else [{"error": {"code": "agent.max_rounds"}}],
        "before_scene": {"objects": 0},
        "after_scene": {"objects": 0},
        "before_fixture": {"fault_remaining": 0},
        "after_fixture": {"fault_remaining": 0},
    }


def test_aggregate_detects_retry_contract_deviation_without_identifiers() -> None:
    rows = [
        _row("private-a", infrastructure=True),
        _row("private-a", infrastructure=True),
        _row("private-a"),
        _row("private-b", passed=True),
    ]
    summary = summarize_attempts(rows, lane="lora", expected_tasks=2)

    assert summary["filled_slots"] == 2
    assert summary["passed"] == 1
    assert summary["infrastructure_interruptions"] == 2
    assert summary["tasks_with_more_than_one_infrastructure_attempt"] == 1
    assert summary["failed_without_tool_calls_at_max_rounds"] == 1
    assert "private-a" not in str(summary)
    assert "private-b" not in str(summary)


def test_holdout_and_duplicate_filled_slots_are_rejected() -> None:
    row = _row("private-a")
    with pytest.raises(ReadinessError, match="holdout boundary"):
        summarize_attempts([{**row, "holdout_read": 1}], lane="lora", expected_tasks=1)
    with pytest.raises(ReadinessError, match="one filled result"):
        summarize_attempts([row, row], lane="lora", expected_tasks=1)
