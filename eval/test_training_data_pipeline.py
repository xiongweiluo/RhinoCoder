from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from data_pipeline.training_views import (
    SPLITS,
    VIEWS,
    audit_training_dataset,
    build_training_dataset,
    numeric_template_signature,
)


def _task(index: int, *, instruction: str | None = None) -> dict[str, Any]:
    family = chr(ord("A") + index)
    text = instruction or f"创建 Family{family} 构件，高度 {10 + index}。"
    asserts: list[dict[str, Any]] = [{"kind": "count", "selector": {"type": "Brep"}, "n": 1}]
    if index == 2:
        text += " 放入图层：ClientSecretLayer。"
        asserts[0]["selector"]["layer"] = "ClientSecretLayer"
    return {
        "id": f"task-{index:02d}",
        "instruction": text,
        "tags": ["synthetic", f"family-{family}"],
        "difficulty": index % 5 + 1,
        "asserts": asserts,
    }


def _trace(task: dict[str, Any], index: int, *, include_error: bool) -> dict[str, Any]:
    run_id = f"run-{index:02d}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "runtime prompt"},
        {"role": "user", "content": task["instruction"]},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "private chain of thought",
            "latency_ms": 12,
            "tool_calls": [
                {
                    "id": f"volatile-create-{index}",
                    "type": "function",
                    "index": 0,
                    "function": {
                        "name": "create_box",
                        "arguments": json.dumps(
                            {"width": index + 1, "layer": "ClientSecretLayer" if index == 2 else "Default"}
                        ),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": f"volatile-create-{index}",
            "content": "成功：对象 GUID = <GUID_REDACTED>",
        },
    ]
    if include_error:
        messages.extend(
            [
                {
                    "role": "assistant",
                    "reasoning_content": "try an invalid argument",
                    "tool_calls": [
                        {
                            "id": f"volatile-error-{index}",
                            "type": "function",
                            "function": {"name": "move_object", "arguments": "{\"distance\": \"bad\"}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": f"volatile-error-{index}",
                    "content": "参数错误：distance 必须是三维向量",
                },
                {
                    "role": "assistant",
                    "reasoning_content": "correct the vector",
                    "tool_calls": [
                        {
                            "id": f"volatile-correction-{index}",
                            "type": "function",
                            "function": {"name": "move_object", "arguments": "{\"distance\": [1, 0, 0]}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": f"volatile-correction-{index}",
                    "content": "成功：已移动对象",
                },
            ]
        )
    messages.extend(
        [
            {
                "role": "assistant",
                "reasoning_content": "inspect",
                "tool_calls": [
                    {
                        "id": f"volatile-scene-{index}",
                        "type": "function",
                        "function": {"name": "get_scene_summary", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": f"volatile-scene-{index}",
                "content": "场景中共有 1 个对象，尺寸为 1 × 1 × 1。",
            },
            {"role": "assistant", "content": "完成并核验。", "reasoning_content": "hidden"},
        ]
    )
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "messages": messages,
        "metadata": {
            "prompt_version": "test-prompt-v1",
            "tool_schema_version": "1.0",
            "task": {
                "campaign_id": "synthetic-a5",
                "task_id": task["id"],
                "tags": task["tags"],
                "difficulty": task["difficulty"],
            },
        },
    }


def _write_source(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_numeric_template_signature_groups_adjacent_number_variants() -> None:
    assert numeric_template_signature("创建4个半径10.5的球") == numeric_template_signature(
        "创建8个半径22的球"
    )


def test_a5_build_is_reproducible_private_traceable_and_holdout_locked(tmp_path: Path) -> None:
    tasks = [_task(index) for index in range(20)]
    tasks[1] = _task(1, instruction="创建 FamilyA 构件，高度 999。")
    rows = [_trace(task, index, include_error=index % 4 == 0) for index, task in enumerate(tasks)]
    rows[0]["messages"][2]["tool_calls"][0]["function"]["arguments"] = (
        '{"center": <COORD_REDACTED>}'
    )
    catalog = {task["id"]: task for task in tasks}
    source = tmp_path / "golden.jsonl"
    output_a = tmp_path / "dataset-a"
    output_b = tmp_path / "dataset-b"
    _write_source(source, rows)

    first = build_training_dataset(source, output_a, task_catalog=catalog)
    second = build_training_dataset(source, output_b, task_catalog=catalog)

    assert first == second
    assert (output_a / "manifest.json").read_bytes() == (output_b / "manifest.json").read_bytes()
    assert first["stats"]["split_task_counts"] == {"holdout": 3, "train": 14, "validation": 3}
    assert first["task_splits"]["task-00"] == first["task_splits"]["task-01"]
    assert first["stats"]["repaired_tool_arguments"] == 1
    assert all(sum(first["stats"]["view_counts"][split][view] for split in SPLITS) > 0 for view in VIEWS)

    audit = audit_training_dataset(output_a, source)
    assert audit.passed, audit.findings
    payload = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(output_a.glob("**/*.jsonl"))
    )
    assert "reasoning_content" not in payload
    assert "private chain of thought" not in payload
    assert "ClientSecretLayer" not in payload
    assert "volatile-" not in payload
    assert re.search(r'"id":"call_001"', payload)

    old_holdout = next(task_id for task_id, split in first["task_splits"].items() if split == "holdout")
    old_task = catalog[old_holdout]
    variant_instruction = re.sub(r"\d+(?=[^\d]*$)", "7777", old_task["instruction"])
    new_task = {
        **_task(20, instruction=variant_instruction),
        "id": "task-new-holdout-variant",
        "tags": ["synthetic", "future-variant"],
        "asserts": old_task["asserts"],
    }
    rows.append(_trace(new_task, 20, include_error=True))
    catalog[new_task["id"]] = new_task
    _write_source(source, rows)
    incremental = build_training_dataset(source, output_a, task_catalog=catalog)

    assert incremental["task_splits"][old_holdout] == "holdout"
    assert incremental["task_splits"][new_task["id"]] == "holdout"
    assert incremental["stats"]["split_task_counts"] == {"holdout": 4, "train": 14, "validation": 3}
    incremental_audit = audit_training_dataset(output_a, source)
    assert incremental_audit.passed, incremental_audit.findings


def test_a5_audit_detects_artifact_tampering(tmp_path: Path) -> None:
    tasks = [_task(index) for index in range(20)]
    rows = [_trace(task, index, include_error=index == 0) for index, task in enumerate(tasks)]
    source = tmp_path / "golden.jsonl"
    output = tmp_path / "dataset"
    _write_source(source, rows)
    build_training_dataset(source, output, task_catalog={task["id"]: task for task in tasks})

    artifact = output / "train" / "instruction_to_tool_call.jsonl"
    artifact.write_text(artifact.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    audit = audit_training_dataset(output, source)

    assert not audit.passed
    assert any("hash/size mismatch" in finding for finding in audit.findings)
