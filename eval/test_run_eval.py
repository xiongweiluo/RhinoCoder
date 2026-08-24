from __future__ import annotations

from agent.runtime import AgentRunResult, RunError, RunMetrics, RunStatus
from eval.run_eval import build_summary, classify_failure, render_markdown


def _result(mode: str, passed: bool, repeat: int = 1) -> dict:
    return {
        "id": "task-1",
        "instruction": "test",
        "tags": ["single"],
        "difficulty": 1,
        "mode": mode,
        "repeat": repeat,
        "passed": passed,
        "partial": not passed,
        "score": 1.0 if passed else 0.5,
        "assertions": [],
        "failed_reasons": [] if passed else ["size mismatch"],
        "failure_category": None if passed else "spatial_error",
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


def test_classify_spatial_verification_failure_after_scene_check():
    run = AgentRunResult(
        run_id="run-1",
        status=RunStatus.COMPLETED,
        metrics=RunMetrics(started_at="now"),
        scene_checks=[{"output": "scene"}],
    )
    verification = {"passed": False, "failed_reasons": ["中心未对齐"]}
    assert classify_failure(run, verification) == "spatial_error"
