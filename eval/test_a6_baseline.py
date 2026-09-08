from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from agent.router import select_route
from eval import a6_baseline
from eval.a6_baseline import (
    SCENARIOS,
    _profiles,
    _frozen_backup_source_hash,
    analyze_golden_offline,
    build_run_contract,
    iter_schedule,
    load_fixed_suite,
    run_live_benchmark,
    summarize_live_results,
)


def test_frozen_backup_source_hash_requires_verified_archive(tmp_path: Path) -> None:
    backup = tmp_path / "data" / "backups" / "golden-set-300"
    backup.mkdir(parents=True)
    archive = backup / "golden-set-300.tar.gz"
    archive.write_bytes(b"locked-backup")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(b"golden-source").hexdigest()
    (backup / "SHA256SUMS").write_text(
        f"{source_hash}  data/golden_traces_v2.jsonl\n",
        encoding="utf-8",
    )
    (backup / "RESTORE_VERIFICATION.json").write_text(
        json.dumps(
            {
                "passed": True,
                "source_and_restored_hashes_match": True,
                "archive_sha256": archive_hash,
            }
        ),
        encoding="utf-8",
    )

    assert _frozen_backup_source_hash(tmp_path) == source_hash
    archive.write_bytes(b"tampered")
    assert _frozen_backup_source_hash(tmp_path) is None


def _golden_row(index: int) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": f"golden-{index}",
        "messages": [
            {"role": "user", "content": f"创建半径 {index + 1} 的球体"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "create_sphere", "arguments": "{\"radius\": 1}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "成功"},
        ],
        "metadata": {
            "evaluation": {"passed": True, "partial": False},
            "feedback": {"label": "accepted", "source": "human_review"},
            "admission": {
                "run_status": "completed",
                "human_confirmed": True,
                "assertions_passed": True,
                "partial": False,
                "scene_check_count": 1,
                "successful_get_scene_summary": True,
                "feedback_label": "accepted",
                "feedback_source": "human_review",
                "sanitization_applied": True,
            },
            "task": {
                "campaign_id": "test",
                "task_id": f"task-{index}",
                "tags": ["sphere"],
                "difficulty": index % 5 + 1,
            },
        },
    }


def _fake_result(task: dict, repeat: int, scenario: str) -> dict:
    return {
        "id": task["id"],
        "mode": scenario,
        "scenario": scenario,
        "repeat": repeat,
        "passed": True,
        "score": 1.0,
        "failure_category": None,
        "infrastructure_error_code": None,
        "failed_reasons": [],
        "timings": {"total_ms": 1000 + repeat},
        "run": {
            "run_id": f"{scenario}-{repeat}-{task['id']}",
            "route_decision": {"selected_backend": scenario, "degraded": False},
            "privacy_decision": {"risk": "low", "action": "allow_cloud"},
            "tool_calls": [{"name": "create_sphere", "success": True}],
            "metrics": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
                "estimated_cost_lower_bound_usd": 0.001,
                "estimated_cost_upper_bound_usd": 0.001,
                "estimated_cost_usd": 0.001,
                "cost_estimate_status": "exact",
                "pricing_schedule": "off_peak",
                "corrections": 1,
                "scene_checks": 1,
            },
        },
    }


def test_fixed_suite_and_schedule_are_exact_and_deterministic() -> None:
    tasks = load_fixed_suite()
    schedule = list(iter_schedule(tasks))

    assert len(tasks) == 30
    assert len({task["id"] for task in tasks}) == 30
    assert len(schedule) == 270
    assert len({(scenario, repeat, task["id"]) for scenario, repeat, task in schedule}) == 270
    assert [item[0] for item in schedule[:3]] == list(SCENARIOS)
    assert build_run_contract() == build_run_contract()


def test_live_summary_records_quality_cost_latency_and_privacy() -> None:
    task = load_fixed_suite()[0]
    rows = [
        _fake_result(task, repeat, scenario)
        for scenario in SCENARIOS
        for repeat in range(1, 4)
    ]
    summary = summarize_live_results(rows)

    assert not summary["complete"]
    for scenario in SCENARIOS:
        item = summary["scenarios"][scenario]
        assert item["pass_at_1"] == 1.0
        assert item["final_pass_rate"] == 1.0
        assert item["stable_tasks"] == 1
        assert item["tokens"]["total"] == 36
        assert item["cost_usd"]["estimated"] == 0.003
        assert item["privacy_risks"] == {"low": 3}


def test_offline_analysis_is_deterministic_and_requires_300_rows(tmp_path: Path) -> None:
    source = tmp_path / "golden.jsonl"
    output = tmp_path / "offline.json"
    rows = [_golden_row(index) for index in range(2)]
    source.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    first = analyze_golden_offline(source, output)
    second = analyze_golden_offline(source, output)

    assert first == second
    assert not first["replay"]["passed"]
    assert first["replay"]["unique_tasks"] == 2
    assert first["route_analysis"]["cloud-main"]["backend_distribution"] == {"cloud-main": 2}


def test_live_checkpoint_resumes_without_duplicate_runs(tmp_path: Path, monkeypatch) -> None:
    counter = 0

    async def fake_eval_one(
        task,
        *,
        closed_loop,
        repeat_index,
        mode_name,
        route_context,
        router_config,
    ):
        nonlocal counter
        counter += 1
        decision = select_route(
            task["instruction"],
            _profiles(),
            context=route_context,
            config=router_config,
        )
        row = _fake_result(task, repeat_index, mode_name)
        row["run"]["run_id"] = f"fake-run-{counter}"
        row["run"]["route_decision"] = decision.to_dict()
        return row

    monkeypatch.setattr(a6_baseline, "eval_one", fake_eval_one)
    first = asyncio.run(run_live_benchmark(tmp_path, limit=3))
    second = asyncio.run(run_live_benchmark(tmp_path, limit=2))
    rows = a6_baseline._read_jsonl(tmp_path / a6_baseline.RESULTS_FILE)

    assert first == {"completed": 3, "expected": 270, "new_runs": 3}
    assert second == {"completed": 5, "expected": 270, "new_runs": 2}
    assert len(rows) == 5
    assert len({_key for _key in map(a6_baseline._result_key, rows)}) == 5


def test_fatal_infrastructure_attempt_remains_traceable_and_cell_is_retried(
    tmp_path: Path,
    monkeypatch,
) -> None:
    attempts = 0

    async def fake_eval_one(
        task,
        *,
        closed_loop,
        repeat_index,
        mode_name,
        route_context,
        router_config,
    ):
        nonlocal attempts
        attempts += 1
        row = _fake_result(task, repeat_index, mode_name)
        row["run"]["run_id"] = f"attempt-{attempts}"
        if attempts == 1:
            row.update(
                passed=False,
                failure_category="infra_error",
                infrastructure_error_code="llm.insufficient_balance",
            )
            row["run"]["error"] = {
                "code": "llm.api_status",
                "message": "Insufficient Balance",
                "recoverable": False,
            }
        return row

    monkeypatch.setattr(a6_baseline, "eval_one", fake_eval_one)

    with pytest.raises(a6_baseline.A6Error, match="insufficient_balance"):
        asyncio.run(run_live_benchmark(tmp_path, limit=1))

    assert a6_baseline._read_jsonl(tmp_path / a6_baseline.RESULTS_FILE) == []
    infrastructure = a6_baseline._read_jsonl(tmp_path / a6_baseline.INFRA_ATTEMPTS_FILE)
    assert len(infrastructure) == 1
    assert infrastructure[0]["id"] == load_fixed_suite()[0]["id"]

    resumed = asyncio.run(run_live_benchmark(tmp_path, limit=1))
    rows = a6_baseline._read_jsonl(tmp_path / a6_baseline.RESULTS_FILE)

    assert resumed == {"completed": 1, "expected": 270, "new_runs": 1}
    assert len(rows) == 1
    assert rows[0]["run"]["run_id"] == "attempt-2"
