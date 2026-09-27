"""Isolated v3 bare-JSON invocation contract; no executor or product route.

The v2 selector and tool inventory stay unchanged. This module deliberately
does not accept v2 tool-call tags or repair Markdown/partial model output.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence

from training.tool_contract_candidate import (
    ContractError,
    INVOCATION_TARGET_RESERVE,
    MAX_SEQUENCE_TOKENS,
    RenderedExample,
    validate_arguments,
    validate_inventory,
)


CONTRACT_ID = "qwen25-single-tool-two-stage-v3-json-candidate"
MAX_INVOCATION_CHARS = 8192
INVOCATION_SYSTEM = (
    "你是 RhinoCoder 的单步工具调用器，只能使用本轮提供的唯一工具。"
    "只输出一个严格 JSON 对象，恰好包含 name 和 arguments 两个字段；"
    "name 是工具的准确名称，arguments 是满足该工具完整 schema 的对象。"
    "输出首字符必须是 {，最后一个字符必须是 }。"
    "禁止 Markdown 代码围栏、<tool_call> 标签、解释、第二个对象或额外字段。"
    "不得猜测任务未给出的必需参数。"
)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            raise ContractError("duplicate JSON key")
        value[name] = item
    return value


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ContractError("non-finite JSON number")
    return value


def _reject_constant(_raw: str) -> None:
    raise ContractError("non-finite JSON constant")


def parse_invocation(
    text: str, selected_tool: str, tools: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Accept one complete schema-valid JSON object and nothing else."""

    inventory = validate_inventory(tools)
    if selected_tool not in inventory:
        raise ContractError("selected tool is unavailable")
    if not isinstance(text, str) or len(text) > MAX_INVOCATION_CHARS:
        raise ContractError("invocation output is absent or oversized")
    cleaned = text.strip()
    if cleaned.endswith("<|im_end|>"):
        cleaned = cleaned[: -len("<|im_end|>")].strip()
    if not cleaned.startswith("{") or not cleaned.endswith("}"):
        raise ContractError("expected one bare JSON object")
    try:
        value = json.loads(
            cleaned,
            object_pairs_hook=_unique_pairs,
            parse_float=_finite_float,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError, OverflowError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != {"name", "arguments"}:
        raise ContractError("invocation must contain exactly name and arguments")
    if value["name"] != selected_tool:
        raise ContractError("invocation name differs from selected tool")
    return {
        "name": selected_tool,
        "arguments": validate_arguments(selected_tool, value["arguments"], inventory[selected_tool]),
    }


def render_invocation(
    tokenizer: Any,
    user_step: str,
    tools: Sequence[Mapping[str, Any]],
    selected_tool: str,
    *,
    arguments: dict[str, Any] | None = None,
) -> RenderedExample:
    """Render the identical prompt prefix for training labels and inference."""

    inventory = validate_inventory(tools)
    if selected_tool not in inventory:
        raise ContractError("selected tool is unavailable")
    if not isinstance(user_step, str) or not user_step.strip():
        raise ContractError("current-step user input must be nonempty")
    messages = [
        {"role": "system", "content": INVOCATION_SYSTEM},
        {"role": "user", "content": user_step},
    ]
    selected_schema = [inventory[selected_tool]]
    prompt = tokenizer.apply_chat_template(
        messages, tools=selected_schema, tokenize=False, add_generation_prompt=True,
    )
    if not isinstance(prompt, str):
        raise ContractError("tokenizer did not render a text prompt")
    prompt_tokens = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    if prompt_tokens + INVOCATION_TARGET_RESERVE > MAX_SEQUENCE_TOKENS:
        raise ContractError("prompt exceeds locked sequence budget; no truncation permitted")
    if arguments is None:
        return RenderedExample(prompt, None, prompt_tokens, None)
    checked = validate_arguments(selected_tool, arguments, inventory[selected_tool])
    target_text = json.dumps(
        {"name": selected_tool, "arguments": checked},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    full = tokenizer.apply_chat_template(
        [*messages, {"role": "assistant", "content": target_text}],
        tools=selected_schema, tokenize=False, add_generation_prompt=False,
    )
    if not isinstance(full, str) or not full.startswith(prompt):
        raise ContractError("target rendering does not preserve prompt prefix")
    full_tokens = len(tokenizer(full, add_special_tokens=False)["input_ids"])
    if full_tokens > MAX_SEQUENCE_TOKENS:
        raise ContractError("target exceeds locked sequence budget; no truncation permitted")
    if parse_invocation(full[len(prompt):], selected_tool, tools)["arguments"] != checked:
        raise ContractError("invocation target did not round-trip")
    return RenderedExample(prompt, full, prompt_tokens, full_tokens)
