"""Frozen offline contract surface for the C5 QLoRA experiment.

This module composes the already-audited v4 selector and v3 bare-JSON
invoker.  It has no model loader, executor, Rhino connection, or product
route.  C5 data builders, validators, and future inference adapters must use
this module rather than duplicating prompts or parsers.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from training.config import EXPECTED_MODEL_REVISION
from training.tool_contract_candidate import (
    INVOCATION_TARGET_RESERVE,
    MAX_SEQUENCE_TOKENS,
    SELECTOR_TARGET_RESERVE,
    TOOL_SUMMARIES,
    ContractError,
    RenderedExample,
    validate_inventory,
)
from training.tool_contract_v3_candidate import (
    INVOCATION_SYSTEM,
    parse_invocation as _parse_invocation,
    render_invocation as _render_invocation,
)
from training.tool_selector_v4_candidate import (
    SELECTOR_SYSTEM,
    parse_selection as _parse_selection,
    render_selection as _render_selection,
)


EXPERIMENT_ID = "rhinocoder-qwen25-coder-7b-c5-contract-qlora-v2"
CONTRACT_ID = "qwen25-v4-selector-v3-json-invoker-c5-v1"
CONTRACT_SCHEMA_VERSION = "1.0"
BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
BASE_MODEL_REVISION = EXPECTED_MODEL_REVISION

# The selector must discriminate the complete public directory.  Invocation
# supervision is intentionally narrower and may not be expanded after the
# final holdout is revealed.
SELECTOR_TOOLS = tuple(sorted(TOOL_SUMMARIES))
CORE_INVOCATION_TOOLS = (
    "boolean_difference",
    "create_box",
    "create_cylinder",
    "create_sphere",
    "get_bounding_box",
    "get_scene_summary",
    "group_objects",
    "move_object",
    "rotate_object",
    "scale_object",
    "set_object_color",
    "set_object_layer",
)

DECODE_CONFIG = {
    "do_sample": False,
    "temperature": 0.0,
    "top_p": 1.0,
    "num_beams": 1,
    "selector_max_new_tokens": SELECTOR_TARGET_RESERVE,
    "invocation_max_new_tokens": INVOCATION_TARGET_RESERVE,
    "stop_on_eos": True,
}


def selector_inventory(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the exact 23-tool selector inventory or fail on drift."""

    inventory = validate_inventory(tools)
    if tuple(sorted(inventory)) != SELECTOR_TOOLS:
        raise ContractError("public selector inventory differs from the C5 freeze")
    return [inventory[name] for name in SELECTOR_TOOLS]


def invocation_inventory(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the frozen invocation subset in deterministic order."""

    inventory = validate_inventory(tools)
    missing = set(CORE_INVOCATION_TOOLS).difference(inventory)
    if missing:
        raise ContractError(f"C5 invocation tools are missing: {sorted(missing)}")
    return [inventory[name] for name in CORE_INVOCATION_TOOLS]


def render_selection(
    tokenizer: Any,
    user_step: str,
    tools: Sequence[Mapping[str, Any]],
    *,
    selected_tool: str | None | object = ...,
) -> RenderedExample:
    return _render_selection(
        tokenizer,
        user_step,
        selector_inventory(tools),
        selected_tool=selected_tool,
    )


def parse_selection(text: str, tools: Sequence[Mapping[str, Any]]) -> str | None:
    return _parse_selection(text, selector_inventory(tools))


def render_invocation(
    tokenizer: Any,
    user_step: str,
    tools: Sequence[Mapping[str, Any]],
    selected_tool: str,
    *,
    arguments: dict[str, Any] | None = None,
) -> RenderedExample:
    if selected_tool not in CORE_INVOCATION_TOOLS:
        raise ContractError("selected tool is outside the frozen C5 invocation scope")
    return _render_invocation(
        tokenizer,
        user_step,
        invocation_inventory(tools),
        selected_tool,
        arguments=arguments,
    )


def parse_invocation(
    text: str,
    selected_tool: str,
    tools: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if selected_tool not in CORE_INVOCATION_TOOLS:
        raise ContractError("selected tool is outside the frozen C5 invocation scope")
    return _parse_invocation(text, selected_tool, invocation_inventory(tools))


def selection_route(selected_tool: str | None) -> str:
    """Classify a parsed selection without granting execution authority."""

    if selected_tool is None:
        return "clarify_or_refuse"
    if selected_tool not in SELECTOR_TOOLS:
        raise ContractError("selection names a tool outside the frozen selector directory")
    if selected_tool not in CORE_INVOCATION_TOOLS:
        return "unsupported_for_c5"
    return "invoke_core_tool"


__all__ = [
    "BASE_MODEL",
    "BASE_MODEL_REVISION",
    "CONTRACT_ID",
    "CONTRACT_SCHEMA_VERSION",
    "CORE_INVOCATION_TOOLS",
    "DECODE_CONFIG",
    "EXPERIMENT_ID",
    "INVOCATION_SYSTEM",
    "MAX_SEQUENCE_TOKENS",
    "SELECTOR_SYSTEM",
    "SELECTOR_TOOLS",
    "parse_invocation",
    "parse_selection",
    "render_invocation",
    "render_selection",
    "selection_route",
]
