"""Isolated v4 selector with explicit completeness/abstention contract.

No model loader, executor, consent, Rhino, or live Agent route is imported.
The v3 bare-JSON invoker remains separately frozen and unchanged.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from training.tool_contract_candidate import (
    ContractError, MAX_SEQUENCE_TOKENS, SELECTOR_TARGET_RESERVE,
    TOOL_SUMMARIES, RenderedExample, parse_selection as _parse_v2_selection,
    validate_inventory,
)


CONTRACT_ID = "qwen25-selector-v4-json-required-candidate"
MAX_SELECTION_CHARS = 1024
SELECTOR_SYSTEM = (
    "你是 RhinoCoder 的单步工具选择器，只做选择，不调用工具、不生成参数。"
    "目录中的 required 字段列出该工具需要的输入。只有当前一步任务与安全场景摘要"
    "已经明确给出所有必需输入、目标对象也能唯一确定时，才选择该工具。"
    "缺少数值、尺寸、对象、方向、距离等必需输入，或用户说稍后决定、代词指向不明、"
    "存在多种合理工具时，必须弃权请求澄清，输出 {\"tool\":null}。"
    "不得自行补默认值或猜测参数；场景中出现一个对象也不代表‘那个东西’已唯一授权。"
    "只输出一个严格裸 JSON 对象，恰好一个 tool 字段，其值是目录中的工具名或 null。"
    "此阶段绝不能输出 radius、height、object_id 或任何其他参数字段，哪怕任务里已经给了参数；"
    "参数属于下一阶段，不属于选择结果。"
    "第一个字符必须是 {，最后一个字符必须是 }；禁止 Markdown 代码围栏、解释、"
    "第二个对象或其他字段。选择不等于用户批准，更不等于执行。"
    "例：‘先做个圆柱，尺寸以后给’→{\"tool\":null}；"
    "‘创建半径为 6、高 8 的圆柱’→{\"tool\":\"create_cylinder\"}；"
    "‘做一个半径为 4 的球’→{\"tool\":\"create_sphere\"}，不要在 JSON 中附加 radius。"
)


def compact_catalog(tools: Sequence[Mapping[str, Any]]) -> str:
    inventory = validate_inventory(tools)
    lines = []
    for name in sorted(inventory):
        required = inventory[name]["function"]["parameters"].get("required", [])
        if not isinstance(required, list) or any(not isinstance(value, str) for value in required):
            raise ContractError("invalid required fields in tool schema")
        fields = ", ".join(required) if required else "无"
        lines.append(f"{name}: {TOOL_SUMMARIES[name]}；required: {fields}")
    return "可选工具：\n" + "\n".join(lines)


def parse_selection(text: str, tools: Sequence[Mapping[str, Any]]) -> str | None:
    if not isinstance(text, str) or len(text) > MAX_SELECTION_CHARS:
        raise ContractError("selection output is absent or oversized")
    return _parse_v2_selection(text, tools)


def render_selection(
    tokenizer: Any,
    user_step: str,
    tools: Sequence[Mapping[str, Any]],
    *,
    selected_tool: str | None | object = ...,
) -> RenderedExample:
    inventory = validate_inventory(tools)
    if not isinstance(user_step, str) or not user_step.strip():
        raise ContractError("current-step user input must be nonempty")
    messages = [
        {"role": "system", "content": SELECTOR_SYSTEM + "\n" + compact_catalog(tools)},
        {"role": "user", "content": user_step},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    if not isinstance(prompt, str):
        raise ContractError("tokenizer did not render a text prompt")
    prompt_tokens = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    if prompt_tokens + SELECTOR_TARGET_RESERVE > MAX_SEQUENCE_TOKENS:
        raise ContractError("prompt exceeds locked sequence budget; no truncation permitted")
    if selected_tool is ...:
        return RenderedExample(prompt, None, prompt_tokens, None)
    if selected_tool is not None and (
        not isinstance(selected_tool, str) or selected_tool not in inventory
    ):
        raise ContractError("selector target names an unavailable tool")
    target_text = json.dumps(
        {"tool": selected_tool}, ensure_ascii=False, separators=(",", ":"),
    )
    full = tokenizer.apply_chat_template(
        [*messages, {"role": "assistant", "content": target_text}],
        tokenize=False, add_generation_prompt=False,
    )
    if not isinstance(full, str) or not full.startswith(prompt):
        raise ContractError("target rendering does not preserve prompt prefix")
    full_tokens = len(tokenizer(full, add_special_tokens=False)["input_ids"])
    if full_tokens > MAX_SEQUENCE_TOKENS:
        raise ContractError("target exceeds locked sequence budget; no truncation permitted")
    if parse_selection(full[len(prompt):], tools) != selected_tool:
        raise ContractError("selector target did not round-trip")
    return RenderedExample(prompt, full, prompt_tokens, full_tokens)
