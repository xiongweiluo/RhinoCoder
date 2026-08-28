from __future__ import annotations

import json
import asyncio

import pytest

import agent.trace_store as trace_store
import agent.data_collector as data_collector
from agent.collection_campaign import (
    DEFAULT_CAMPAIGN_MANIFEST,
    campaign_summary,
    load_campaign,
    task_metadata,
    trace_disposition,
)
from agent.runtime import AgentRunResult, RunMetrics, RunStatus, ToolCallRecord
from agent.trace_store import (
    PARTIAL,
    build_trace_record,
    save_golden,
    save_rejected_trace,
    validate_golden_candidate,
)


def _run(run_id: str = "campaign-run-1") -> AgentRunResult:
    return AgentRunResult(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        messages=[
            {"role": "user", "content": "create a box"},
            {"role": "assistant", "content": "done"},
        ],
        metrics=RunMetrics(started_at="now", total_tokens=120),
        scene_checks=[{"status": "ok"}],
        tool_calls=[
            ToolCallRecord(
                call_id="call-1",
                name="get_scene_summary",
                arguments={},
                round_index=1,
                started_at="now",
                success=True,
            )
        ],
    )


def _accepted_record(campaign, task, run_id: str = "campaign-run-1"):
    return build_trace_record(
        task["instruction"],
        _run(run_id),
        evaluation={"passed": True, "partial": False, "failed_reasons": []},
        feedback={"label": "accepted", "source": "human_review"},
        task=task_metadata(campaign, task),
    )


def test_phase1_campaign_has_30_diverse_unique_tasks():
    campaign = load_campaign(DEFAULT_CAMPAIGN_MANIFEST)
    assert campaign.target == 30
    assert len(campaign.tasks) == 30
    assert len({task["instruction"] for task in campaign.tasks}) == 30
    assert len({tag for task in campaign.tasks for tag in task["tags"]}) >= 20
    assert sum(task["difficulty"] >= 4 for task in campaign.tasks) >= 9
    tags = {tag for task in campaign.tasks for tag in task["tags"]}
    assert {"rotate", "move", "distribute", "align", "undo", "place"} <= tags


def test_human_partial_feedback_is_physically_partial(monkeypatch, tmp_path):
    campaign = load_campaign(DEFAULT_CAMPAIGN_MANIFEST)
    record = _accepted_record(campaign, campaign.tasks[0])
    record["feedback"]["label"] = "partial"
    assert trace_disposition(record) == PARTIAL
    gate = validate_golden_candidate(record, human_confirmed=False)
    monkeypatch.setattr(trace_store, "PARTIAL_FILE", tmp_path / "partial.jsonl")
    disposition, path = save_rejected_trace(record, gate)
    assert disposition == PARTIAL
    assert json.loads(path.read_text(encoding="utf-8"))["disposition"] == PARTIAL


def test_golden_campaign_task_cannot_be_saved_twice(monkeypatch, tmp_path):
    campaign = load_campaign(DEFAULT_CAMPAIGN_MANIFEST)
    record = _accepted_record(campaign, campaign.tasks[0])
    gate = validate_golden_candidate(record, human_confirmed=True)
    monkeypatch.setattr(trace_store, "GOLDEN_FILE", tmp_path / "golden.jsonl")

    save_golden(gate)
    with pytest.raises(ValueError, match="黄金任务重复"):
        save_golden(gate)


def test_campaign_summary_supports_resume_and_cost_tracking(tmp_path):
    campaign = load_campaign(DEFAULT_CAMPAIGN_MANIFEST)
    task = campaign.tasks[0]
    record = _accepted_record(campaign, task)
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "campaign-run-1.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )
    golden_path = tmp_path / "golden.jsonl"
    golden_path.write_text(
        json.dumps({"metadata": {"task": task_metadata(campaign, task)}}) + "\n",
        encoding="utf-8",
    )

    summary = campaign_summary(campaign, golden_path=golden_path, trace_dir=trace_dir)
    assert summary["attempts"] == 1
    assert summary["attempted_tasks"] == 1
    assert summary["golden"] == 1
    assert summary["remaining"] == 29
    assert summary["total_tokens"] == 120
    assert task["id"] not in summary["pending_task_ids"]


def test_collector_refuses_to_reset_nonempty_scene_by_default(monkeypatch):
    async def scene():
        return {"status": "ok", "total": 2, "objects": [{}, {}]}

    monkeypatch.setattr(data_collector, "_scene_summary", scene)
    with pytest.raises(RuntimeError, match="含 2 个对象"):
        asyncio.run(data_collector._preflight(allow_nonempty_reset=False))
