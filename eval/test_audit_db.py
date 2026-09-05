from __future__ import annotations

import json
import stat
from pathlib import Path

from agent.db import AuditDatabase, SCHEMA_VERSION, import_golden_dataset


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _admission() -> dict:
    return {
        "run_status": "completed",
        "human_confirmed": True,
        "assertions_passed": True,
        "partial": False,
        "scene_check_count": 1,
        "successful_get_scene_summary": True,
        "feedback_label": "accepted",
        "feedback_source": "human_review",
        "sanitization_applied": True,
    }


def _trace(index: int) -> dict:
    run_id = f"run-{index}"
    task = {
        "campaign_id": "fixture-2",
        "task_id": f"task-{index}",
        "difficulty": index + 1,
        "tags": ["box", f"level-{index + 1}"],
    }
    feedback = {
        "label": "accepted",
        "source": "human_review",
        "timestamp": f"2026-09-04T00:00:0{index}+00:00",
        "note": "verified",
    }
    return {
        "schema_version": "1.0",
        "app_version": "0.2.0",
        "prompt_version": "fixture",
        "tool_schema_version": "fixture",
        "run_id": run_id,
        "instruction": f"create fixture {index}",
        "task": task,
        "feedback": feedback,
        "evaluation": {
            "passed": True,
            "partial": False,
            "results": [
                {
                    "spec": {"kind": "count", "selector": {"type": "Surface"}, "n": 1},
                    "ok": True,
                    "reason": "",
                }
            ],
            "failed_reasons": [],
        },
        "run": {
            "run_id": run_id,
            "status": "completed",
            "messages": [{"role": "user", "content": f"fixture {index}"}],
            "events": [
                {
                    "type": "run.started",
                    "run_id": run_id,
                    "seq": 1,
                    "timestamp": "2026-09-04T00:00:00+00:00",
                    "payload": {"model": "deepseek-fixture"},
                }
            ],
            "tool_calls": [
                {
                    "call_id": f"call-{index}",
                    "name": "create_box",
                    "arguments": {"width": 2},
                    "round_index": 1,
                    "success": True,
                    "output": "created",
                }
            ],
            "scene_checks": [
                {
                    "call_id": f"scene-{index}",
                    "round": 2,
                    "timestamp": "2026-09-04T00:00:01+00:00",
                    "success": True,
                    "output": "one object",
                    "scene_summary": {"total": 1},
                }
            ],
            "metrics": {
                "started_at": "2026-09-04T00:00:00+00:00",
                "completed_at": "2026-09-04T00:00:02+00:00",
                "duration_ms": 2000,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.001,
                "cost_estimate_status": "exact",
            },
            "final_text": "done",
            "created_object_ids": [],
        },
    }


def _golden_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "data/traces").mkdir(parents=True)
    (root / "data/review_batches/batch").mkdir(parents=True)
    (root / "data/collection_reports").mkdir(parents=True)
    (root / "eval/collection").mkdir(parents=True)

    golden_rows = []
    feedback_rows = []
    reviewed_rows = []
    for index in range(2):
        trace = _trace(index)
        run_id = trace["run_id"]
        (root / f"data/traces/{run_id}.json").write_text(
            json.dumps(trace, ensure_ascii=False), encoding="utf-8"
        )
        screenshot = Path(f"data/review_batches/batch/task-{index}.png")
        (root / screenshot).write_bytes(b"PNG")
        golden_rows.append(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "messages": trace["run"]["messages"],
                "metadata": {
                    "app_version": "0.2.0",
                    "prompt_version": "fixture",
                    "tool_schema_version": "fixture",
                    "task": trace["task"],
                    "evaluation": trace["evaluation"],
                    "feedback": trace["feedback"],
                    "admission": _admission(),
                },
            }
        )
        feedback_rows.append(
            {
                **trace["feedback"],
                "run_id": run_id,
                "instruction": trace["instruction"],
                "task": trace["task"],
            }
        )
        reviewed_rows.append(
            {
                "run_id": run_id,
                "task": trace["task"],
                "feedback": {"review": {"visual_evidence": screenshot.as_posix()}},
            }
        )

    _write_jsonl(root / "data/golden_traces_v2.jsonl", golden_rows)
    _write_jsonl(root / "data/feedback.jsonl", feedback_rows)
    _write_jsonl(root / "data/ai_reviewed_candidates.jsonl", reviewed_rows)
    (root / "data/collection_reports/fixture-quality.json").write_text(
        "{}\n", encoding="utf-8"
    )
    for name in ("phase1_30.json", "phase2_100.json", "phase3_300.json"):
        (root / "eval/collection" / name).write_text("{}\n", encoding="utf-8")
    return root


def test_schema_migrations_are_versioned_and_reentrant(tmp_path):
    path = tmp_path / "audit" / "audit.sqlite3"
    with AuditDatabase(path) as database:
        assert database.schema_version == SCHEMA_VERSION
        rows = database._rows("SELECT version, name FROM schema_migrations ORDER BY version")
        assert [row["version"] for row in rows] == [1, 2]
        expected_tables = {
            "runs",
            "tasks",
            "models",
            "route_decisions",
            "tool_calls",
            "scene_checks",
            "assertions",
            "feedback",
            "admissions",
            "cost_usage",
            "artifacts",
        }
        assert expected_tables.issubset(database.table_counts())

    with AuditDatabase(path) as reopened:
        assert reopened.schema_version == SCHEMA_VERSION
        assert reopened.table_counts()["runs"] == 0
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_import_is_idempotent_and_lineage_is_complete(tmp_path):
    root = _golden_fixture(tmp_path)
    with AuditDatabase(tmp_path / "audit.sqlite3") as database:
        first = import_golden_dataset(database, root=root, expected_count=2)
        counts = database.table_counts()
        second = import_golden_dataset(database, root=root, expected_count=2)

        assert first.golden_runs == first.golden_tasks == 2
        assert second.counts_unchanged_on_repeat
        assert database.table_counts() == counts
        assert database.audit().passed

        lineage = database.get_run_lineage("run-0")
        assert lineage["task"]["task_id"] == "task-0"
        assert lineage["model"]["name"] == "deepseek-fixture"
        assert len(lineage["tool_calls"]) == 1
        assert len(lineage["scene_checks"]) == 1
        assert len(lineage["assertions"]) == 1
        assert any(row["label"] == "accepted" for row in lineage["feedback"])
        assert lineage["admission"]["admitted"] == 1
        assert lineage["cost_usage"]["total_tokens"] == 15
        assert {row["kind"] for row in lineage["artifacts"]} == {"trace", "screenshot"}

        summary = database.summary()
        assert summary["by_model"][0]["runs"] == 2
        assert {row["tag"] for row in summary["by_tag"]} == {
            "box",
            "level-1",
            "level-2",
        }


def test_writes_sanitize_sensitive_fields_before_audit(tmp_path):
    record = _trace(0)
    record["instruction"] = "open /Users/customer/private/model.3dm"
    record["run"]["tool_calls"][0]["arguments"] = {
        "api_key": "top-secret-value",
        "center": [1, 2, 3],
    }
    record["run"]["tool_calls"][0]["output"] = (
        "object 22222222-2222-4222-8222-222222222222"
    )

    with AuditDatabase(tmp_path / "audit.sqlite3") as database:
        database.ingest_trace(record)
        result = database.audit()
        lineage = database.get_run_lineage("run-0")

    assert result.passed
    assert "<PATH_REDACTED>" in lineage["run"]["instruction"]
    assert "<SECRET_REDACTED>" in lineage["tool_calls"][0]["arguments_json"]
    assert "<COORD_REDACTED>" in lineage["tool_calls"][0]["arguments_json"]
    assert "<GUID_REDACTED>" in lineage["tool_calls"][0]["output"]


def test_route_decision_and_json_exports(tmp_path):
    with AuditDatabase(tmp_path / "audit.sqlite3") as database:
        database.ingest_trace(_trace(0))
        route_id = database.record_route_decision(
            "run-0",
            {
                "route_id": "route-0",
                "selected_backend": "cloud",
                "privacy_level": "low",
                "reason": "reliable backend",
            },
        )
        lineage_path = tmp_path / "exports" / "lineage.json"
        summary_path = tmp_path / "exports" / "summary.json"
        database.export_json(database.get_run_lineage("run-0"), lineage_path)
        database.export_json(database.summary(), summary_path)

    assert route_id == "route-0"
    assert json.loads(lineage_path.read_text())["route_decisions"][0][
        "selected_backend"
    ] == "cloud"
    assert json.loads(summary_path.read_text())["counts"]["route_decisions"] == 1
    assert stat.S_IMODE(lineage_path.stat().st_mode) == 0o600


def test_trace_store_mirrors_trace_and_feedback_to_realtime_audit(monkeypatch, tmp_path):
    import agent.db as db_module
    import agent.trace_store as trace_store

    captured_traces = []
    captured_feedback = []
    monkeypatch.setattr(trace_store, "TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(trace_store, "FEEDBACK_FILE", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(
        db_module,
        "record_live_trace",
        lambda record, *, artifact_path=None: captured_traces.append(
            (record, artifact_path)
        ),
    )
    monkeypatch.setattr(
        db_module,
        "record_live_feedback",
        captured_feedback.append,
    )

    record = _trace(0)
    trace_path = trace_store.save_trace(record)
    feedback = {**record["feedback"], "run_id": record["run_id"]}
    trace_store.save_feedback(feedback)

    assert trace_path.is_file()
    assert captured_traces[0][0]["run_id"] == "run-0"
    assert captured_traces[0][1] == trace_path
    assert captured_feedback == [feedback]


def test_realtime_audit_failure_does_not_fail_completed_run(monkeypatch, caplog):
    import agent.db as db_module

    class BrokenAuditDatabase:
        def __init__(self, _path):
            raise OSError("read-only audit directory")

    monkeypatch.setenv("RHINOCODER_AUDIT_ENABLED", "1")
    monkeypatch.setattr(db_module, "AuditDatabase", BrokenAuditDatabase)

    db_module.record_live_trace({"run_id": "completed-run"})

    assert "SQLite audit trace write failed for completed-run" in caplog.text
