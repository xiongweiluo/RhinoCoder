from __future__ import annotations

import asyncio

from agent.runtime import AgentRunResult, RunError, RunMetrics, RunStatus
from eval import run_eval
from eval.run_eval import (
    build_summary,
    classify_failure,
    infrastructure_error_code,
    is_fatal_infrastructure_result,
    render_markdown,
)


def _result(mode: str, passed: bool, repeat: int = 1) -> dict:
    return {
        "id": "task-1",
        "instruction": "test",
        "tags": ["single"],
        "difficulty": 1,
        "mode": mode,
        "repeat": repeat,
        "attempted": True,
        "passed": passed,
        "partial": not passed,
        "score": 1.0 if passed else 0.5,
        "assertions": [],
        "failed_reasons": [] if passed else ["size mismatch"],
        "failure_category": None if passed else "spatial_error",
        "infrastructure_error_code": None,
        "scene_summary": {},
        "scene_check_count": 1,
        "correction_count": 0,
        "timings": {"total_ms": 1000.0},
        "run": {"metrics": {"estimated_cost_usd": 0.01}},
    }


def test_build_summary_and_closed_loop_delta():
    results = [_result("baseline", False), _result("closed_loop", True)]
    summary = build_summary(results)
    assert summary["modes"]["baseline"]["pass_rate"] == 0.0
    assert summary["modes"]["closed_loop"]["pass_rate"] == 1.0
    assert summary["comparison"]["pass_rate_delta"] == 1.0
    assert "Closed-loop delta" in render_markdown(summary, results)


def test_build_summary_groups_tool_metrics():
    result = _result("closed_loop", True)
    result["run"]["tool_calls"] = [
        {"name": "create_box", "success": True, "duration_ms": 12.0},
        {"name": "get_scene_summary", "success": False, "duration_ms": 8.0},
    ]
    summary = build_summary([result])
    assert summary["by_tool"]["create_box"]["success_rate"] == 1.0
    assert summary["by_tool"]["get_scene_summary"]["failed_calls"] == 1
    assert "## By tool" in render_markdown(summary, [result])


def test_classify_infrastructure_failure():
    run = AgentRunResult(
        run_id="run-1",
        status=RunStatus.FAILED,
        metrics=RunMetrics(started_at="now"),
        error=RunError("llm.connection", "offline", recoverable=True),
    )
    assert classify_failure(run, None) == "infra_error"


def test_insufficient_balance_is_fatal_and_has_stable_subtype():
    run = AgentRunResult(
        run_id="run-1",
        status=RunStatus.FAILED,
        metrics=RunMetrics(started_at="now"),
        error=RunError("llm.api_status", "402 Insufficient Balance", recoverable=False),
    )
    assert infrastructure_error_code(run) == "llm.insufficient_balance"
    result = _result("baseline", False)
    result["failure_category"] = "infra_error"
    result["infrastructure_error_code"] = "llm.insufficient_balance"
    result["run"]["error"] = {
        "code": run.error.code,
        "message": run.error.message,
        "recoverable": run.error.recoverable,
    }
    assert is_fatal_infrastructure_result(result)


def test_benchmark_skips_remaining_schedule_after_fatal_error(monkeypatch):
    calls = 0

    async def fake_eval_one(task, *, closed_loop, repeat_index):
        nonlocal calls
        calls += 1
        result = _result("closed_loop" if closed_loop else "baseline", False, repeat_index)
        result["failure_category"] = "infra_error"
        result["infrastructure_error_code"] = "llm.insufficient_balance"
        result["run"]["error"] = {
            "code": "llm.api_status",
            "message": "402 Insufficient Balance",
            "recoverable": False,
        }
        return result

    monkeypatch.setattr(run_eval, "eval_one", fake_eval_one)
    tasks = [
        {"id": "task-1", "instruction": "one", "tags": [], "difficulty": 1},
        {"id": "task-2", "instruction": "two", "tags": [], "difficulty": 1},
    ]
    results = asyncio.run(run_eval.run_benchmark(tasks, modes=["baseline", "closed_loop"], repeats=1))
    summary = build_summary(results)

    assert calls == 1
    assert len(results) == 4
    assert sum(not result["attempted"] for result in results) == 3
    assert summary["modes"]["baseline"]["attempts"] == 1
    assert summary["modes"]["closed_loop"]["attempts"] == 0
    assert summary["comparison"] is None
    assert summary["comparable"] is False
    assert "Comparison unavailable" in render_markdown(summary, results)


def test_classify_spatial_verification_failure_after_scene_check():
    run = AgentRunResult(
        run_id="run-1",
        status=RunStatus.COMPLETED,
        metrics=RunMetrics(started_at="now"),
        scene_checks=[{"output": "scene"}],
    )
    verification = {"passed": False, "failed_reasons": ["中心未对齐"]}
    assert classify_failure(run, verification) == "spatial_error"
