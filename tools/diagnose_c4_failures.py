#!/usr/bin/env python3
"""Read-only, aggregate-only C4 failure diagnosis; never opens A5 holdout.

This command loads the pinned tokenizer from the local cache, the existing
train/validation views, and the Git-ignored P2 raw evidence. It does not load
model weights, generate text, contact Rhino, or write output files.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.p2_hard import _is_infrastructure_result  # noqa: E402
from training.config import DEFAULT_CONFIG, EXPECTED_MODEL_REVISION, ReadinessError  # noqa: E402
from training.data import (  # noqa: E402
    expected_tool_calls,
    parse_generated_tool_calls,
    render_training_example,
)
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402

TRAIN = ROOT / "data/training/a5/train/instruction_to_tool_call.jsonl"
VALIDATION = ROOT / "data/training/a5/validation/instruction_to_tool_call.jsonl"
TOKENIZER_SNAPSHOT = (
    ROOT
    / "data/training/tokenizer-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots"
    / EXPECTED_MODEL_REVISION
)
P2_RESULTS = ROOT / "docs/p2-model-comparison-results.json"
P2_PROTOCOL = ROOT / "eval/p2/model-comparison-protocol.json"
P2_RAW = {
    "base": ROOT / "data/training/p2-model-comparison/base-results.jsonl",
    "lora": ROOT / "data/training/p2-model-comparison/lora-results.jsonl",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _runtime_tools() -> list[dict[str, Any]]:
    """Recreate the Agent's MCP-to-OpenAI schema shape without opening Rhino."""
    return load_public_mcp_tools()


def summarize_split(path: Path, tokenizer: Any, tools: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _jsonl(path)
    names: Counter[str] = Counter()
    plain_tokens: list[int] = []
    with_tools_tokens: list[int] = []
    target_parse = target_exact = targets_with_content = 0
    for row in rows:
        messages = row["messages"]
        prompt, full = render_training_example(tokenizer, messages)
        expected = expected_tool_calls(row)
        actual = parse_generated_tool_calls(full[len(prompt) :])
        target_parse += actual is not None
        target_exact += actual == expected
        targets_with_content += bool(messages[-1].get("content"))
        names.update(call["name"] for call in expected)
        plain_tokens.append(len(tokenizer(prompt, add_special_tokens=False)["input_ids"]))
        tool_prompt = tokenizer.apply_chat_template(
            messages[:-1], tools=tools, tokenize=False, add_generation_prompt=True
        )
        with_tools_tokens.append(
            len(tokenizer(tool_prompt, add_special_tokens=False)["input_ids"])
        )
    return {
        "rows": len(rows),
        "input_sha256": _sha256(path),
        "target_parse_count": target_parse,
        "target_exact_count": target_exact,
        "targets_with_natural_language_content": targets_with_content,
        "distinct_target_tools": len(names),
        "target_tool_counts": dict(sorted(names.items())),
        "prompt_without_tool_schemas_median_tokens": statistics.median(plain_tokens),
        "prompt_with_23_tool_schemas_median_tokens": statistics.median(with_tools_tokens),
        "prompt_with_tool_schemas_min_tokens": min(with_tools_tokens),
        "prompt_with_tool_schemas_max_tokens": max(with_tools_tokens),
        "prompts_with_tool_schemas_over_locked_max": sum(
            tokens > 2048 for tokens in with_tools_tokens
        ),
        "tool_schema_median_token_delta": statistics.median(
            tool - plain for tool, plain in zip(with_tools_tokens, plain_tokens, strict=True)
        ),
    }


def summarize_attempts(
    rows: list[dict[str, Any]], *, lane: str, expected_tasks: int = 30
) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("model_lane") != lane or row.get("holdout_read") != 0:
            raise ReadinessError(f"{lane}: model lane or holdout boundary changed")
        by_task[row["task_id"]].append(row)
    if len(by_task) != expected_tasks:
        raise ReadinessError(f"{lane}: expected {expected_tasks} P2 task slots")
    filled = [row for row in rows if not _is_infrastructure_result(row)]
    if len(filled) != expected_tasks or len({row["task_id"] for row in filled}) != expected_tasks:
        raise ReadinessError(f"{lane}: expected one filled result per task")
    infra = [row for row in rows if _is_infrastructure_result(row)]
    infra_counts = Counter(row["task_id"] for row in infra)
    failed_no_tools = [
        row for row in filled if not row.get("automated_pass") and not row.get("tool_calls")
    ]
    return {
        "raw_rows": len(rows),
        "filled_slots": len(filled),
        "passed": sum(bool(row.get("automated_pass")) for row in filled),
        "infrastructure_interruptions": len(infra),
        "infrastructure_attempts_per_affected_task": dict(
            sorted(Counter(infra_counts.values()).items())
        ),
        "tasks_with_more_than_one_infrastructure_attempt": sum(
            count > 1 for count in infra_counts.values()
        ),
        "maximum_infrastructure_attempts_for_one_task": max(infra_counts.values(), default=0),
        "infrastructure_with_tool_calls": sum(bool(row.get("tool_calls")) for row in infra),
        "infrastructure_with_scene_change": sum(
            row.get("before_scene") != row.get("after_scene") for row in infra
        ),
        "infrastructure_with_fixture_change": sum(
            row.get("before_fixture") != row.get("after_fixture") for row in infra
        ),
        "failed_without_tool_calls": len(failed_no_tools),
        "failed_without_tool_calls_by_category": dict(
            sorted(Counter(row.get("failure_category") for row in failed_no_tools).items())
        ),
        "failed_without_tool_calls_at_max_rounds": sum(
            any((run.get("error") or {}).get("code") == "agent.max_rounds" for run in row.get("runs") or [])
            for row in failed_no_tools
        ),
        "failure_categories": dict(
            sorted(Counter(row.get("failure_category") for row in filled if not row.get("automated_pass")).items())
        ),
    }


def main() -> int:
    from transformers import AutoTokenizer

    if not TOKENIZER_SNAPSHOT.is_dir():
        raise ReadinessError("pinned tokenizer snapshot is unavailable locally; no download attempted")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    max_length = int(config["training"]["max_sequence_length"])
    if max_length != 2048:
        raise ReadinessError("locked maximum sequence length changed")
    tools = _runtime_tools()
    if len(tools) != 23:
        raise ReadinessError("runtime MCP tool count changed")
    published = json.loads(P2_RESULTS.read_text(encoding="utf-8"))
    protocol = json.loads(P2_PROTOCOL.read_text(encoding="utf-8"))
    if _sha256(P2_PROTOCOL) != published["freeze"]["protocol_sha256"]:
        raise ReadinessError("P2 protocol hash differs from published C4")
    if protocol["execution"]["attempts_per_task_per_lane"] != 1:
        raise ReadinessError("P2 retry contract changed")
    lanes: dict[str, Any] = {}
    for lane, path in P2_RAW.items():
        if _sha256(path) != published["evidence"][f"{lane}_raw_sha256"]:
            raise ReadinessError(f"{lane}: P2 raw evidence hash differs from published C4")
        lanes[lane] = summarize_attempts(_jsonl(path), lane=lane)
        if lanes[lane]["passed"] != published[lane]["passed"]:
            raise ReadinessError(f"{lane}: pass count differs from published C4")
    splits = {
        "train": summarize_split(TRAIN, tokenizer, tools),
        "validation": summarize_split(VALIDATION, tokenizer, tools),
    }
    for split, summary in splits.items():
        locked = config["data"][split]
        if summary["rows"] != locked["rows"] or summary["input_sha256"] != locked["sha256"]:
            raise ReadinessError(f"{split}: input differs from locked C0 configuration")
    result = {
        "kind": "read-only-c4-failure-diagnosis",
        "tokenizer_revision": EXPECTED_MODEL_REVISION,
        "runtime_tool_count": len(tools),
        "locked_max_sequence_length": max_length,
        "p2_single_infrastructure_fill_limit_per_task": 1,
        "splits": splits,
        "p2": lanes,
        "holdout_read": False,
        "model_inference_run": False,
        "raw_content_exported": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
