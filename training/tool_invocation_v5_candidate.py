"""Candidate invoker schema with target identity bound outside the model.

For move_object the model only echoes the three requested translations. It
cannot propose an object ID; a later trusted Rhino-side resolver must map the
preflight alias to a unique object and recheck the same scene. This module
does not dispatch or authorize anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from training.explicit_step_gate_candidate import (
    ExpectedStep, ExplicitStepError, SceneProvider, _same_scene,
)
from training.tool_contract_candidate import ContractError, validate_inventory
from training.tool_contract_v3_candidate import (
    parse_invocation as parse_v3_invocation,
    render_invocation as render_v3_invocation,
)


CONTRACT_ID = "qwen25-v5-model-external-target-candidate"
_MOVE_FIELDS = frozenset({"translate_x", "translate_y", "translate_z"})


@dataclass(frozen=True)
class CheckedInvocation:
    name: str
    model_arguments: Mapping[str, Any]
    target_alias: str | None


def _scoped_tools(name: str, tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    inventory = validate_inventory(tools)
    if name not in inventory:
        raise ContractError("selected tool is unavailable")
    original = inventory[name]["function"]
    schema = original["parameters"]
    if name == "move_object":
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, dict) or set(properties) != _MOVE_FIELDS | {"object_id"} or (
            not isinstance(required, list) or set(required) != _MOVE_FIELDS | {"object_id"}
        ):
            raise ContractError("move schema changed unexpectedly")
        schema = {
            "type": "object",
            "properties": {field: properties[field] for field in sorted(_MOVE_FIELDS)},
            "required": sorted(_MOVE_FIELDS),
            "additionalProperties": False,
        }
    return [{"type": "function", "function": {
        "name": name,
        "description": (
            "目标对象已由可信外部门绑定；只输出三轴位移，不输出对象 ID、GUID 或占位符。"
            if name == "move_object" else original.get("description", "")
        ),
        "parameters": schema,
    }}]


def render_invocation(tokenizer: Any, current_input: str, name: str,
                      tools: Sequence[Mapping[str, Any]]) -> str:
    """Use the v3 strict JSON framing with a target-free move schema."""

    return render_v3_invocation(tokenizer, current_input, _scoped_tools(name, tools), name).prompt


def check_invocation(expected: ExpectedStep, text: str, *, scene: SceneProvider,
                     tools: Sequence[Mapping[str, Any]]) -> CheckedInvocation:
    _same_scene(expected, scene)
    try:
        call = parse_v3_invocation(text, expected.tool_name, _scoped_tools(expected.tool_name, tools))
    except (ContractError, TypeError, AttributeError) as exc:
        raise ExplicitStepError("invalid_invocation_output") from exc
    model_arguments = call["arguments"]
    expected_arguments = expected.arguments
    target_alias = None
    if expected.tool_name == "move_object":
        target_alias = expected_arguments.pop("object_id")
    if model_arguments != expected_arguments:
        raise ExplicitStepError("argument_mismatch")
    return CheckedInvocation(expected.tool_name, model_arguments, target_alias)
