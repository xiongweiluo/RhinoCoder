"""CPU-only candidate for a *future* Qwen tool-call experiment.

This module is deliberately not imported by the frozen C0–C4 training,
evaluation, or live Agent paths. It renders the same prompt for a future
selector/invocation training example and its corresponding inference request.
It never loads weights, executes a tool, or accesses an evaluation dataset.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, ValidationError


CONTRACT_ID = "qwen25-single-tool-two-stage-v2-candidate"
MAX_SEQUENCE_TOKENS = 2048
SELECTOR_TARGET_RESERVE = 128
INVOCATION_TARGET_RESERVE = 512

SELECTOR_SYSTEM = (
    "你是 RhinoCoder 的工具选择器。根据用户当前一步任务，从目录中选择一个工具。"
    "只输出 JSON 对象 {\"tool\":\"工具名\"}；不要生成参数、解释或工具调用。"
    "如果请求含糊、缺少必要参数或需要确认，输出 {\"tool\":null}，由控制器向用户澄清；"
    "选择不等于执行。"
)
INVOCATION_SYSTEM = (
    "你是 RhinoCoder 的单步工具调用器。只能调用本轮提供的唯一工具。"
    "严格输出一个 <tool_call> JSON </tool_call>，JSON 仅含 name 和 arguments；"
    "arguments 必须满足工具 schema。不要输出自然语言或第二个调用。"
)

# Short, versioned selector descriptions, never substituted for invocation schemas.
TOOL_SUMMARIES = {
    "align_objects": "对齐对象",
    "boolean_difference": "布尔减去几何体",
    "create_box": "创建长方体",
    "create_circle": "创建圆曲线",
    "create_cylinder": "创建圆柱",
    "create_line": "创建线段",
    "create_sphere": "创建球体",
    "delete_objects": "删除指定对象",
    "distribute_objects": "分布多个对象",
    "extrude_curve_straight": "直线拉伸曲线",
    "get_bounding_box": "只读对象包围盒",
    "get_object_info": "只读对象属性",
    "get_objects_by_name": "按名称查找对象",
    "get_scene_summary": "只读场景摘要",
    "get_selected_objects": "只读当前选择",
    "group_objects": "对象分组",
    "move_object": "平移对象",
    "place_on_at": "将对象放置到目标位置",
    "rotate_object": "旋转对象",
    "scale_object": "缩放对象",
    "set_object_color": "修改对象颜色",
    "set_object_layer": "修改对象图层",
    "undo_last_action": "撤销最近操作",
}

_TOOL_CALL = re.compile(r"\s*<tool_call>\s*(\{.*\})\s*</tool_call>(?:<\|im_end\|>)?\s*", re.DOTALL)
_UNSET = object()


class ContractError(ValueError):
    """Candidate contract rejected the prompt, schema, or model text."""


@dataclass(frozen=True)
class RenderedExample:
    prompt: str
    full: str | None
    prompt_tokens: int
    full_tokens: int | None


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant {value} is forbidden")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key")
        result[key] = value
    return result


def _strict_json(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ContractError("invalid JSON") from exc


def validate_inventory(tools: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if not tools:
        raise ContractError("tool inventory is empty")
    inventory: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if tool.get("type") != "function" or not isinstance(tool.get("function"), Mapping):
            raise ContractError("expected OpenAI function tool schema")
        function = tool["function"]
        name = function.get("name")
        schema = function.get("parameters")
        if not isinstance(name, str) or name not in TOOL_SUMMARIES or name in inventory:
            raise ContractError("unknown or duplicate tool name")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ContractError("tool parameters must be an object JSON schema")
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise ContractError("invalid tool JSON schema") from exc
        inventory[name] = dict(tool)
    return inventory


def catalog_text(tools: Sequence[Mapping[str, Any]]) -> str:
    inventory = validate_inventory(tools)
    return "可选工具：\n" + "\n".join(
        f"{name}: {TOOL_SUMMARIES[name]}" for name in sorted(inventory)
    )


def _user_message(user_step: str) -> dict[str, str]:
    if not isinstance(user_step, str) or not user_step.strip():
        raise ContractError("current-step user input must be nonempty")
    return {"role": "user", "content": user_step}


def _token_count(tokenizer: Any, rendered: str) -> int:
    return len(tokenizer(rendered, add_special_tokens=False)["input_ids"])


def _render(
    tokenizer: Any,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
    target: dict[str, Any] | None,
    reserve: int,
) -> RenderedExample:
    kwargs = {"tools": tools} if tools is not None else {}
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, **kwargs
    )
    if not isinstance(prompt, str):
        raise ContractError("tokenizer did not render a text prompt")
    prompt_tokens = _token_count(tokenizer, prompt)
    if prompt_tokens + reserve > MAX_SEQUENCE_TOKENS:
        raise ContractError("prompt exceeds locked sequence budget; no truncation permitted")
    if target is None:
        return RenderedExample(prompt, None, prompt_tokens, None)
    full = tokenizer.apply_chat_template(
        [*messages, target], tokenize=False, add_generation_prompt=False, **kwargs
    )
    if not isinstance(full, str) or not full.startswith(prompt):
        raise ContractError("target rendering does not preserve prompt prefix")
    full_tokens = _token_count(tokenizer, full)
    if full_tokens > MAX_SEQUENCE_TOKENS:
        raise ContractError("target exceeds locked sequence budget; no truncation permitted")
    return RenderedExample(prompt, full, prompt_tokens, full_tokens)


def parse_selection(text: str, tools: Sequence[Mapping[str, Any]]) -> str | None:
    inventory = validate_inventory(tools)
    cleaned = text.strip()
    if cleaned.endswith("<|im_end|>"):
        cleaned = cleaned[: -len("<|im_end|>")].strip()
    value = _strict_json(cleaned)
    if not isinstance(value, dict) or set(value) != {"tool"}:
        raise ContractError("selection must contain exactly one tool field")
    if value["tool"] is not None and (
        not isinstance(value["tool"], str) or value["tool"] not in inventory
    ):
        raise ContractError("selection must name a known tool or abstain")
    return value["tool"]


def render_selection(
    tokenizer: Any,
    user_step: str,
    tools: Sequence[Mapping[str, Any]],
    *,
    selected_tool: str | None | object = _UNSET,
) -> RenderedExample:
    inventory = validate_inventory(tools)
    messages = [
        {"role": "system", "content": SELECTOR_SYSTEM + "\n" + catalog_text(tools)},
        _user_message(user_step),
    ]
    target = None
    if selected_tool is not _UNSET:
        if selected_tool is not None and (
            not isinstance(selected_tool, str) or selected_tool not in inventory
        ):
            raise ContractError("selector target names an unavailable tool")
        target = {
            "role": "assistant",
            "content": json.dumps({"tool": selected_tool}, ensure_ascii=False, separators=(",", ":")),
        }
    rendered = _render(tokenizer, messages, tools=None, target=target, reserve=SELECTOR_TARGET_RESERVE)
    if rendered.full is not None and parse_selection(rendered.full[len(rendered.prompt) :], tools) != selected_tool:
        raise ContractError("selector target did not round-trip")
    return rendered


def validate_arguments(name: str, arguments: Any, tool: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ContractError("tool arguments must be a JSON object")
    schema = tool["function"]["parameters"]
    allowed = set(schema.get("properties") or {})
    if set(arguments) - allowed:
        raise ContractError("unknown top-level tool argument")
    try:
        Draft202012Validator(schema).validate(arguments)
    except ValidationError as exc:
        raise ContractError(f"arguments do not satisfy {name} schema") from exc
    return arguments


def parse_invocation(
    text: str, selected_tool: str, tools: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    inventory = validate_inventory(tools)
    if selected_tool not in inventory:
        raise ContractError("selected tool is unavailable")
    match = _TOOL_CALL.fullmatch(text)
    if match is None:
        raise ContractError("expected one complete Qwen tool-call tag and no other text")
    value = _strict_json(match.group(1))
    if not isinstance(value, dict) or set(value) != {"name", "arguments"}:
        raise ContractError("tool call must contain exactly name and arguments")
    if value["name"] != selected_tool:
        raise ContractError("tool call name differs from selected tool")
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
    inventory = validate_inventory(tools)
    if selected_tool not in inventory:
        raise ContractError("selected tool is unavailable")
    selected = inventory[selected_tool]
    target = None
    if arguments is not None:
        validate_arguments(selected_tool, arguments, selected)
        target = {
            "role": "assistant",
            "tool_calls": [{
                "type": "function",
                "function": {"name": selected_tool, "arguments": arguments},
            }],
        }
    messages = [
        {"role": "system", "content": INVOCATION_SYSTEM},
        _user_message(user_step),
    ]
    rendered = _render(
        tokenizer, messages, tools=[selected], target=target, reserve=INVOCATION_TARGET_RESERVE
    )
    if rendered.full is not None:
        parsed = parse_invocation(rendered.full[len(rendered.prompt) :], selected_tool, tools)
        if parsed["arguments"] != arguments:
            raise ContractError("invocation target did not round-trip")
    return rendered
