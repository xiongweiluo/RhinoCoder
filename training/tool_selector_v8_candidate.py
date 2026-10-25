"""Versioned v8 selector prompt; the frozen v4 parser and safety gate remain intact."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from training.tool_contract_candidate import (
    ContractError, MAX_SEQUENCE_TOKENS, SELECTOR_TARGET_RESERVE, RenderedExample,
)
from training.tool_selector_v4_candidate import SELECTOR_SYSTEM, compact_catalog


SELECTOR_SYSTEM_V8 = SELECTOR_SYSTEM + (
    "当前目录里，用户说‘选中对象’或‘选中的物体’并要求查看、读取、列出或显示，"
    "只对应 get_selected_objects；不要仅因‘显示’二字改选场景摘要。"
    "用户明确要求场景摘要、场景概况或场景信息时，只对应 get_scene_summary。"
    "创建盒体仍需明确宽、深、高；移动仍需唯一目标和 X、Y、Z 位移。"
    "如语义或必要参数不明确，继续按上述规则输出 {\"tool\":null}，不可猜测。"
)


def render_selection_v8(tokenizer: Any, user_step: str,
                        tools: Sequence[Mapping[str, Any]]) -> RenderedExample:
    """Only replace the prompt; preserve the locked tokenizer budget and schema."""

    if not isinstance(user_step, str) or not user_step.strip():
        raise ContractError("current-step user input must be nonempty")
    messages = [
        {"role": "system", "content": SELECTOR_SYSTEM_V8 + "\n" + compact_catalog(tools)},
        {"role": "user", "content": user_step},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False,
                                           add_generation_prompt=True)
    if not isinstance(prompt, str):
        raise ContractError("tokenizer did not render a text prompt")
    prompt_tokens = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    if prompt_tokens + SELECTOR_TARGET_RESERVE > MAX_SEQUENCE_TOKENS:
        raise ContractError("prompt exceeds locked sequence budget; no truncation permitted")
    return RenderedExample(prompt, None, prompt_tokens, None)
