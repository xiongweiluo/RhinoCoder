"""C5 source-isolation, grouping, determinism, and tamper tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.c5_freeze import (
    C5FreezeError,
    SourceTask,
    assert_development_source,
    build_families,
    build_source_manifest,
    load_source_tasks,
    validate_public_manifest,
)


def _task(index: int, instruction: str, tools: tuple[str, ...]) -> SourceTask:
    return SourceTask(
        task_id=f"task-{index}",
        run_id=f"run-{index}",
        campaign_id="synthetic",
        tags=(f"family-{index // 2}",),
        instruction=instruction,
        tool_names=tools,
    )


def test_numeric_and_semantic_variants_never_cross_families() -> None:
    tasks = [
        _task(0, "创建 2 个盒子", ("create_box",)),
        _task(1, "创建 9 个盒子", ("create_box",)),
        _task(2, "读取场景", ("get_scene_summary",)),
    ]
    families = build_families(tasks)
    assert sorted(family["size"] for family in families) == [1, 2]
    all_hashes = [value for family in families for value in family["task_hashes"]]
    assert len(all_hashes) == len(set(all_hashes)) == 3


def test_only_approved_source_path_can_be_used(tmp_path: Path) -> None:
    project = tmp_path / "project"
    approved = project / "data/golden_traces_v2.jsonl"
    approved.parent.mkdir(parents=True)
    approved.write_text("", encoding="utf-8")
    assert_development_source(approved, project_root=project)
    forbidden = project / "data/training/a5/holdout/tasks.jsonl"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_text("", encoding="utf-8")
    with pytest.raises(C5FreezeError):
        assert_development_source(forbidden, project_root=project)


def test_manifest_is_deterministic_and_contains_no_raw_content(tmp_path: Path) -> None:
    source = tmp_path / "golden.jsonl"
    rows = []
    for index in range(4):
        rows.append({
            "run_id": f"run-{index}",
            "messages": [
                {"role": "user", "content": f"private instruction {index}"},
                {"role": "assistant", "tool_calls": [{
                    "function": {"name": "create_box", "arguments": "{}"}
                }]},
            ],
            "metadata": {"task": {
                "task_id": f"task-{index}",
                "campaign_id": "synthetic",
                "tags": [f"family-{index}"],
            }},
        })
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    tasks = load_source_tasks(source, expected_rows=4)
    first = build_source_manifest(source, tasks, source_path_label="synthetic.jsonl")
    second = build_source_manifest(source, tasks, source_path_label="synthetic.jsonl")
    assert first == second
    payload = json.dumps(first)
    assert "private instruction" not in payload
    assert '"arguments"' not in payload
    assert first["candidate_source_assignment"]["accepted_into_dataset_v2"] is False
    assert first["candidate_source_assignment"]["historical_eval_overlap_status"].startswith(
        "not_resolved"
    )
    assert validate_public_manifest(first) == []


def test_public_manifest_audit_detects_isolation_tampering(tmp_path: Path) -> None:
    source = tmp_path / "golden.jsonl"
    source.write_text(json.dumps({
        "run_id": "run-1",
        "messages": [
            {"role": "user", "content": "synthetic"},
            {"role": "assistant", "tool_calls": [{
                "function": {"name": "create_box", "arguments": "{}"}
            }]},
        ],
        "metadata": {"task": {
            "task_id": "task-1", "campaign_id": "synthetic", "tags": ["one"]
        }},
    }) + "\n", encoding="utf-8")
    manifest = build_source_manifest(
        source, load_source_tasks(source, expected_rows=1), source_path_label="synthetic.jsonl"
    )
    manifest["isolation"]["final_holdout_read"] = True
    assert "isolation declaration is missing or unsafe" in validate_public_manifest(manifest)
