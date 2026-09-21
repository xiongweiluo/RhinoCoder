#!/usr/bin/env python3
"""Offline CPU-only audit of a future tool-call contract using synthetic inputs."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.config import EXPECTED_MODEL_REVISION  # noqa: E402
from training.tool_controller_candidate import SceneState, compose_step_input  # noqa: E402
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402
from training.tool_contract_candidate import (  # noqa: E402
    CONTRACT_ID,
    INVOCATION_SYSTEM,
    INVOCATION_TARGET_RESERVE,
    MAX_SEQUENCE_TOKENS,
    SELECTOR_TARGET_RESERVE,
    TOOL_SUMMARIES,
    render_invocation,
    render_selection,
    validate_inventory,
)

TOKENIZER_SNAPSHOT = (
    ROOT
    / "data/training/tokenizer-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots"
    / EXPECTED_MODEL_REVISION
)
EXPECTED_TOOL_SCHEMA_SHA256 = "151c5453bf92f83343e93e53013bfc8f3518e5b6a7e9e2fc49e97ba863b0637d"


def main() -> int:
    from transformers import AutoTokenizer

    if not TOKENIZER_SNAPSHOT.is_dir():
        raise SystemExit("pinned tokenizer is unavailable locally; no download attempted")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)
    tools = load_public_mcp_tools()
    inventory = validate_inventory(tools)
    if set(inventory) != set(TOOL_SUMMARIES) or len(inventory) != 23:
        raise SystemExit("public MCP inventory differs from candidate contract")

    synthetic_step = "在全新合成场景中，创建宽 20、深 10、高 5 毫米的长方体。"
    selector_prompt = render_selection(tokenizer, synthetic_step, tools)
    selector_target = render_selection(
        tokenizer, synthetic_step, tools, selected_tool="create_box"
    )
    selector_abstention = render_selection(tokenizer, synthetic_step, tools, selected_tool=None)
    if (
        selector_prompt.prompt != selector_target.prompt
        or selector_prompt.prompt != selector_abstention.prompt
    ):
        raise SystemExit("selector train/inference prompt mismatch")

    token_counts: dict[str, int] = {}
    for name in sorted(inventory):
        example = render_invocation(tokenizer, synthetic_step, tools, name)
        token_counts[name] = example.prompt_tokens

    cases = [
        ("create_box", {"width": 20, "depth": 10, "height": 5}),
        ("get_scene_summary", {}),
        (
            "move_object",
            {
                "object_id": "synthetic-object",
                "translate_x": 1,
                "translate_y": 0,
                "translate_z": 0,
            },
        ),
    ]
    target_tokens = []
    for name, arguments in cases:
        prompt = render_invocation(tokenizer, synthetic_step, tools, name)
        target = render_invocation(
            tokenizer, synthetic_step, tools, name, arguments=arguments
        )
        if prompt.prompt != target.prompt or target.full_tokens is None:
            raise SystemExit("invocation train/inference prompt mismatch")
        target_tokens.append(target.full_tokens)

    synthetic_summary = {"object_count": 1, "aliases": ["synthetic-1"], "unit": "mm"}
    state_sha = hashlib.sha256(
        json.dumps(synthetic_summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    stateful_input = compose_step_input(
        "读取合成场景摘要", SceneState(1, state_sha, synthetic_summary)
    )
    stateful_selector_tokens = render_selection(tokenizer, stateful_input, tools).prompt_tokens
    stateful_invocation_max_tokens = max(
        render_invocation(tokenizer, stateful_input, tools, name).prompt_tokens
        for name in inventory
    )

    baseline = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": INVOCATION_SYSTEM},
            {"role": "user", "content": synthetic_step},
        ],
        tools=tools,
        tokenize=False,
        add_generation_prompt=True,
    )
    baseline_tokens = len(tokenizer(baseline, add_special_tokens=False)["input_ids"])
    schema_hash = hashlib.sha256(
        json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if schema_hash != EXPECTED_TOOL_SCHEMA_SHA256:
        raise SystemExit("public MCP schema drifted from the candidate audit")
    result = {
        "contract_id": CONTRACT_ID,
        "tokenizer_revision": EXPECTED_MODEL_REVISION,
        "tool_schema_sha256": schema_hash,
        "tool_count": len(inventory),
        "locked_sequence_tokens": MAX_SEQUENCE_TOKENS,
        "selector_target_reserve": SELECTOR_TARGET_RESERVE,
        "invocation_target_reserve": INVOCATION_TARGET_RESERVE,
        "selector_prompt_tokens": selector_prompt.prompt_tokens,
        "selector_training_target_tokens": selector_target.full_tokens,
        "selector_abstention_target_tokens": selector_abstention.full_tokens,
        "all_23_full_schemas_prompt_tokens": baseline_tokens,
        "single_full_schema_prompt_min_tokens": min(token_counts.values()),
        "single_full_schema_prompt_max_tokens": max(token_counts.values()),
        "single_full_schema_over_budget": sum(
            tokens + INVOCATION_TARGET_RESERVE > MAX_SEQUENCE_TOKENS
            for tokens in token_counts.values()
        ),
        "stateful_selector_prompt_tokens": stateful_selector_tokens,
        "stateful_single_schema_prompt_max_tokens": stateful_invocation_max_tokens,
        "synthetic_roundtrips": len(target_tokens),
        "synthetic_target_max_tokens": max(target_tokens),
        "synthetic_contract_passed": True,
        "production_enabled": False,
        "dataset_v2_authorized": False,
        "model_inference_run": False,
        "holdout_read": False,
        "raw_content_exported": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
