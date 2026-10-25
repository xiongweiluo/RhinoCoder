"""Fail-closed, model-external pre-invoker gate for an opt-in structured route.

Only explicit user-supplied JSON commands in the small supported subset are
accepted. This is not a natural-language completeness detector, an execution
permission, or a Rhino adapter. Unsupported prose and tools are rejected.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from agent.privacy import PrivacyAction, classify_request
from training.tool_contract_candidate import ContractError, validate_arguments, validate_inventory
from training.tool_contract_v3_candidate import parse_invocation
from training.tool_controller_candidate import SceneState, compose_step_input
from training.tool_selector_v4_candidate import parse_selection


MAX_COMMAND_CHARS = 1024
_GUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_ALIASES = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_OPERATIONS = {
    "get_scene_summary": frozenset({"op"}),
    "get_selected_objects": frozenset({"op"}),
    "create_box": frozenset({"op", "width", "depth", "height"}),
    "move_object": frozenset({"op", "alias", "dx", "dy", "dz"}),
}


class ExplicitStepError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SceneProvider(Protocol):
    def snapshot(self) -> SceneState: ...


@dataclass(frozen=True)
class ExpectedStep:
    task_sha256: str
    scene_revision: int
    scene_sha256: str
    summary_sha256: str
    tool_name: str
    arguments_json: str

    @property
    def arguments(self) -> dict[str, Any]:
        return json.loads(self.arguments_json)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ExplicitStepError("duplicate_key")
        value[key] = item
    return value


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ExplicitStepError("non_finite_number")
    return value


def _reject_constant(_raw: str) -> None:
    raise ExplicitStepError("non_finite_number")


def _number(value: Any, *, positive: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExplicitStepError("missing_or_invalid_parameter")
    if not math.isfinite(value) or abs(value) > 100_000 or (positive and value <= 0):
        raise ExplicitStepError("out_of_range_parameter")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_command(text: str, summary: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_COMMAND_CHARS or _GUID.search(text):
        raise ExplicitStepError("untrusted_or_oversized_command")
    try:
        value = json.loads(
            text, object_pairs_hook=_unique_pairs,
            parse_float=_finite_float, parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError, OverflowError) as exc:
        if isinstance(exc, ExplicitStepError):
            raise
        raise ExplicitStepError("invalid_json_command") from exc
    if not isinstance(value, dict) or not isinstance(value.get("op"), str):
        raise ExplicitStepError("invalid_command_shape")
    name = value["op"]
    if name not in _OPERATIONS:
        raise ExplicitStepError("unsupported_command")
    if set(value) != _OPERATIONS[name]:
        raise ExplicitStepError("missing_or_extra_parameter")
    if name in {"get_scene_summary", "get_selected_objects"}:
        return name, {}
    if name == "create_box":
        return name, {axis: _number(value[axis], positive=True) for axis in ("width", "depth", "height")}
    alias = value["alias"]
    if not isinstance(alias, str) or not _ALIASES.fullmatch(alias):
        raise ExplicitStepError("invalid_target_alias")
    aliases = summary.get("aliases")
    if not isinstance(aliases, list) or aliases.count(alias) != 1:
        raise ExplicitStepError("target_not_unique")
    return name, {
        "object_id": alias,
        "translate_x": _number(value["dx"]),
        "translate_y": _number(value["dy"]),
        "translate_z": _number(value["dz"]),
    }


def _same_scene(expected: ExpectedStep, scene: SceneProvider) -> None:
    try:
        current = scene.snapshot()
    except Exception as exc:
        raise ExplicitStepError("scene_unavailable") from exc
    try:
        same = (
            isinstance(current, SceneState)
            and current.revision == expected.scene_revision
            and current.scene_sha256 == expected.scene_sha256
            and _digest(current.summary) == expected.summary_sha256
        )
    except Exception as exc:
        raise ExplicitStepError("scene_unavailable") from exc
    if not same:
        raise ExplicitStepError("scene_changed")


def preflight(
    task: str, *, scene: SceneProvider, tools: Sequence[Mapping[str, Any]],
) -> ExpectedStep:
    """Reject incompleteness and ambiguous targets before any model call."""

    inventory = validate_inventory(tools)
    try:
        state = scene.snapshot()
        current_input = compose_step_input(task, state)
        action = classify_request(current_input).action
        if action not in {
            PrivacyAction.ALLOW_CLOUD, PrivacyAction.MINIMIZE_CLOUD, PrivacyAction.FORCE_LOCAL,
        }:
            raise ExplicitStepError("privacy_rejected")
        name, arguments = _parse_command(task, state.summary)
        if name not in inventory:
            raise ExplicitStepError("tool_unavailable")
        checked = validate_arguments(name, arguments, inventory[name])
        arguments_json = _canonical_json(checked)
        summary_sha256 = _digest(state.summary)
    except ExplicitStepError:
        raise
    except Exception as exc:
        raise ExplicitStepError("preflight_rejected") from exc
    return ExpectedStep(
        hashlib.sha256(task.encode("utf-8")).hexdigest(), state.revision,
        state.scene_sha256, summary_sha256, name, arguments_json,
    )


def before_invoker(
    expected: ExpectedStep, selection_text: str, *, scene: SceneProvider,
    tools: Sequence[Mapping[str, Any]],
) -> ExpectedStep:
    """The model cannot add fields, change tool, or authorize an invocation."""

    _same_scene(expected, scene)
    try:
        selected = parse_selection(selection_text, tools)
    except (ContractError, TypeError, AttributeError) as exc:
        raise ExplicitStepError("invalid_selection_output") from exc
    if selected != expected.tool_name:
        raise ExplicitStepError("selection_mismatch")
    return expected


def after_invoker(
    expected: ExpectedStep, invocation_text: str, *, scene: SceneProvider,
    tools: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Recheck exact arguments and scene before a *separate* consent gate."""

    _same_scene(expected, scene)
    try:
        call = parse_invocation(invocation_text, expected.tool_name, tools)
    except (ContractError, TypeError, AttributeError) as exc:
        raise ExplicitStepError("invalid_invocation_output") from exc
    if call["arguments"] != expected.arguments:
        raise ExplicitStepError("argument_mismatch")
    return call
