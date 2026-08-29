from __future__ import annotations

import json
import asyncio

import pytest

import agent.trace_store as trace_store
import agent.data_collector as data_collector
from agent.collection_campaign import (
    DEFAULT_CAMPAIGN_MANIFEST,
    batch_id_for_task,
    campaign_summary,
    load_campaign,
    promote_review_batch,
    review_batch_summary,
    task_metadata,
    trace_disposition,
)
from agent.runtime import AgentRunResult, RunMetrics, RunStatus, ToolCallRecord
from agent.trace_store import (
    PARTIAL,
    build_trace_record,
    save_ai_reviewed_candidate,
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


def _configure_batch_paths(monkeypatch, tmp_path):
    golden_path = tmp_path / "golden.jsonl"
    candidate_path = tmp_path / "ai_candidates.jsonl"
    monkeypatch.setattr(trace_store, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(trace_store, "GOLDEN_FILE", golden_path)
    monkeypatch.setattr(trace_store, "AI_REVIEWED_FILE", candidate_path)
    monkeypatch.setattr(trace_store, "FEEDBACK_FILE", tmp_path / "feedback.jsonl")
    return golden_path, candidate_path


def _stage_ai_candidate(campaign, task, tmp_path, run_id):
    evidence = tmp_path / "evidence" / f"{task['id']}.png"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_bytes(b"viewport")
    record = build_trace_record(
        task["instruction"],
        _run(run_id),
        evaluation={"passed": True, "partial": False, "score": 1.0, "failed_reasons": []},
        task=task_metadata(campaign, task),
    )
    return save_ai_reviewed_candidate(
        record,
        batch_id=batch_id_for_task(campaign, task),
        note="程序、轨迹、场景和视口检查均通过",
        visual_evidence=f"evidence/{task['id']}.png",
    )


def test_ai_reviewed_batch_waits_for_one_human_confirmation(monkeypatch, tmp_path):
    campaign = load_campaign(DEFAULT_CAMPAIGN_MANIFEST)
    golden_path, candidate_path = _configure_batch_paths(monkeypatch, tmp_path)

    first = _accepted_record(campaign, campaign.tasks[0], "batch-golden-1")
    save_golden(validate_golden_candidate(first, human_confirmed=True))
    for index, task in enumerate(campaign.tasks[1:5], 2):
        _stage_ai_candidate(campaign, task, tmp_path, f"batch-candidate-{index}")

    summary = review_batch_summary(
        campaign,
        "phase1-30-batch-01",
        candidate_path=candidate_path,
        golden_path=golden_path,
        trace_dir=tmp_path / "traces",
    )
    assert summary["ready_for_human_review"] is True
    assert summary["golden"] == 1
    assert summary["ai_reviewed_candidates"] == 4

    written = promote_review_batch(
        campaign,
        "phase1-30-batch-01",
        human_note="批量确认通过",
        candidate_path=candidate_path,
        golden_path=golden_path,
    )
    assert written == 4
    rows = [json.loads(line) for line in golden_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 5
    promoted = rows[-1]["metadata"]
    assert promoted["feedback"]["mode"] == "batch"
    assert promoted["feedback"]["source"] == "human_review"
    assert promoted["review_history"][0]["source"] == "ai_visual_review"


def test_batch_promotion_prevalidates_every_candidate_before_atomic_write(monkeypatch, tmp_path):
    campaign = load_campaign(DEFAULT_CAMPAIGN_MANIFEST)
    golden_path, candidate_path = _configure_batch_paths(monkeypatch, tmp_path)
    first = _accepted_record(campaign, campaign.tasks[0], "atomic-golden-1")
    save_golden(validate_golden_candidate(first, human_confirmed=True))
    for index, task in enumerate(campaign.tasks[1:5], 2):
        _stage_ai_candidate(campaign, task, tmp_path, f"atomic-candidate-{index}")

    rows = [json.loads(line) for line in candidate_path.read_text(encoding="utf-8").splitlines()]
    rows[-1]["run"]["scene_checks"] = []
    candidate_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    before = golden_path.read_bytes()
    with pytest.raises(ValueError, match="黄金晋级失败"):
        promote_review_batch(
            campaign,
            "phase1-30-batch-01",
            candidate_path=candidate_path,
            golden_path=golden_path,
        )
    assert golden_path.read_bytes() == before
