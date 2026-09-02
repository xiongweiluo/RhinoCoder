from pathlib import Path
from types import SimpleNamespace

import tools.report_golden_dataset_quality as report_module


def _attempt(task_id: str, passed: bool) -> dict:
    return {
        "task": {"task_id": task_id},
        "run": {
            "status": "completed",
            "metrics": {"started_at": task_id, "total_tokens": 10},
            "tool_calls": [],
        },
        "evaluation": {"passed": passed, "partial": False},
    }


def test_quality_report_uses_only_new_collection_target_for_pass_rates(monkeypatch):
    campaign = SimpleNamespace(
        campaign_id="phase2",
        title="Phase 2",
        target=3,
        tasks=[
            {"id": "inherited", "difficulty": 1, "tags": ["base"]},
            {"id": "new-1", "difficulty": 2, "tags": ["new"]},
            {"id": "new-2", "difficulty": 3, "tags": ["new"]},
        ],
    )
    attempts = [_attempt("new-1", True), _attempt("new-2", False), _attempt("new-2", True)]
    monkeypatch.setattr(report_module, "load_campaign", lambda _manifest: campaign)
    monkeypatch.setattr(report_module, "campaign_attempts", lambda _campaign_id: attempts)
    monkeypatch.setattr(
        report_module,
        "campaign_golden_task_ids",
        lambda _campaign: {"inherited", "new-1", "new-2"},
    )
    monkeypatch.setattr(
        report_module,
        "golden_task_ids",
        lambda _campaign_id: {"new-1", "new-2"},
    )

    summary = report_module.summarize(Path("phase2.json"))

    assert summary["inherited_golden"] == 1
    assert summary["collection_target"] == 2
    assert summary["collected_golden"] == 2
    assert summary["first_attempt_full_pass"] == 1
    assert summary["first_attempt_full_pass_rate"] == 50.0
    assert summary["eventual_full_pass_rate"] == 100.0
