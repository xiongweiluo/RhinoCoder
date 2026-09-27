"""Conservative task compiler for the isolated R v6 candidate.

The compiler never calls a model or Rhino. It accepts complete explicit JSON
steps and a deliberately bounded natural-language grammar; uncertainty returns
a targeted clarification, never a guessed tool or default parameter. Each
step is converted to the v5 explicit contract only immediately before that
step's separately authenticated model/scene/consent cycle.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any, Mapping

from training.explicit_step_gate_candidate import ExplicitStepError, _parse_command


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_SPLIT = re.compile(r"\s*(?:[；;]\s*(?:然后|接着|随后|再)?|然后|接着|随后|再)\s*")
_CREATE = re.compile(r"(?:创建|建立|生成|做|画|create|make|add)", re.I)
_BOX = re.compile(r"(?:盒子|长方体|立方体|box|cuboid)", re.I)
_MOVE = re.compile(r"(?:移动|平移|挪动|move|translate)", re.I)
_READ = re.compile(r"(?:查看|读取|获取|列出|显示|read|show|get|list)", re.I)
_SUMMARY = re.compile(r"(?:场景(?:概况|概要|摘要|信息)?|scene\s*(?:summary|overview))", re.I)
_SELECTED = re.compile(r"(?:选中(?:的)?(?:对象|物体)|selected\s*objects?)", re.I)
_LAST = re.compile(r"(?:刚(?:创建|生成)的(?:盒子|长方体)|新(?:创建|生成)的(?:盒子|长方体)|newly\s*created\s*box)", re.I)
_TARGET = re.compile(r"(?:把|将|move|translate)\s*([A-Za-z][A-Za-z0-9_-]{0,63})\b", re.I)
_DIMENSIONS = {
    "width": re.compile(rf"(?:宽(?:度)?|width)\s*(?:为|是|=|:|：)?\s*({_NUMBER})", re.I),
    "depth": re.compile(rf"(?:深(?:度)?|depth)\s*(?:为|是|=|:|：)?\s*({_NUMBER})", re.I),
    "height": re.compile(rf"(?:高(?:度)?|height)\s*(?:为|是|=|:|：)?\s*({_NUMBER})", re.I),
}
_TRANSLATIONS = {
    "dx": re.compile(rf"(?:沿\s*)?(?<![A-Za-z0-9_-])X\s*(?:轴|方向)?\s*(?:移动|平移|为|是|=|:|：)?\s*({_NUMBER})", re.I),
    "dy": re.compile(rf"(?:沿\s*)?(?<![A-Za-z0-9_-])Y\s*(?:轴|方向)?\s*(?:移动|平移|为|是|=|:|：)?\s*({_NUMBER})", re.I),
    "dz": re.compile(rf"(?:沿\s*)?(?<![A-Za-z0-9_-])Z\s*(?:轴|方向)?\s*(?:移动|平移|为|是|=|:|：)?\s*({_NUMBER})", re.I),
}
_PLACEHOLDERS = re.compile(r"(?:稍后|以后|待定|随便|大概|约|左右|later|about|roughly)", re.I)
_REQUIRED = {
    "get_scene_summary": frozenset({"op"}),
    "get_selected_objects": frozenset({"op"}),
    "create_box": frozenset({"op", "width", "depth", "height"}),
    "move_object": frozenset({"op", "alias", "dx", "dy", "dz"}),
}


class PlanError(ValueError):
    def __init__(self, code: str, needed_fields: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.needed_fields = needed_fields


_FIELD_QUESTIONS = {
    "width": "宽度（毫米）", "depth": "深度（毫米）", "height": "高度（毫米）",
    "dx": "X 轴位移（毫米）", "dy": "Y 轴位移（毫米）", "dz": "Z 轴位移（毫米）",
    "alias": "目标对象的唯一别名", "target_alias": "目标对象的唯一别名",
    "exact_parameters": "确切尺寸或位移（不要使用‘稍后’或约数）",
}


def clarification_prompt(error: PlanError) -> str | None:
    """Return only a field-specific question; malformed actions are refused."""
    if error.code not in {"information_incomplete", "ambiguous_parameter", "created_target_unavailable"}:
        return None
    fields = tuple(dict.fromkeys(_FIELD_QUESTIONS[field] for field in error.needed_fields
                                 if field in _FIELD_QUESTIONS))
    if not fields:
        return None
    zero_guidance = "；如某轴不移动，请明确填写 0" if any(
        field in {"dx", "dy", "dz"} for field in error.needed_fields
    ) else ""
    return "请补充" + "、".join(fields) + zero_guidance + "。"


@dataclass(frozen=True)
class PlannedStep:
    operation: str
    arguments: tuple[tuple[str, Any], ...]
    target_ref: str | None = None
    source_segment_sha256: str = ""

    def explicit_task(self, *, created_alias: str | None = None) -> str:
        value = {"op": self.operation, **dict(self.arguments)}
        if self.target_ref == "last_created":
            if created_alias is None or not _ALIAS.fullmatch(created_alias):
                raise PlanError("created_target_unavailable", ("target_alias",))
            value["alias"] = created_alias
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class TaskPlan:
    original_task_sha256: str
    steps: tuple[PlannedStep, ...]
    source_kind: str


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanError("duplicate_key")
        result[key] = value
    return result


def _parse_number(segment: str, expression: re.Pattern[str], field: str) -> int | float | None:
    matches = expression.findall(segment)
    if len(matches) > 1:
        raise PlanError("ambiguous_parameter", (field,))
    if not matches:
        return None
    raw = matches[0]
    number = float(raw) if "." in raw else int(raw)
    if abs(number) > 100_000:
        raise PlanError("out_of_range_parameter", (field,))
    return number


def _reject_unparsed(text: str, matches: list[re.Match[str] | None]) -> None:
    covered = [False] * len(text)
    for match in matches:
        if match is not None:
            for index in range(*match.span()):
                covered[index] = True
    residue = "".join(char for index, char in enumerate(text) if not covered[index])
    residue = re.sub(r"\b(?:a|an|the|with|by|in|mm|millimeters|and|on)\b", "", residue, flags=re.I)
    residue = re.sub(r"(?:请|一个|个|的|为|是|毫米|把|将|沿|向|在|上)", "", residue)
    residue = re.sub(r"[\s,，、.。:：;；()（）=]+", "", residue)
    if residue:
        raise PlanError("unsupported_or_ambiguous_step", ("explicit_action",))


def _nl_step(segment: str) -> PlannedStep:
    text = segment.strip().strip("。.!！?？ ")
    text = re.sub(r"^(?:(?:请|麻烦|先|please)\s*)+", "", text, flags=re.I)
    if not text:
        raise PlanError("empty_step")
    if _PLACEHOLDERS.search(text):
        raise PlanError("information_incomplete", ("exact_parameters",))
    action_text = _LAST.sub("", text)
    if _READ.search(text) and _SUMMARY.search(text) and not (_CREATE.search(action_text) or _MOVE.search(action_text)):
        _reject_unparsed(text, [_READ.search(text), _SUMMARY.search(text)])
        return PlannedStep("get_scene_summary", ())
    if _READ.search(text) and _SELECTED.search(text) and not (_CREATE.search(action_text) or _MOVE.search(action_text)):
        _reject_unparsed(text, [_READ.search(text), _SELECTED.search(text)])
        return PlannedStep("get_selected_objects", ())
    if _CREATE.search(action_text) and _BOX.search(text) and not _MOVE.search(action_text):
        values = {key: _parse_number(text, expression, key)
                  for key, expression in _DIMENSIONS.items()}
        missing = tuple(key for key, value in values.items() if value is None)
        if missing:
            raise PlanError("information_incomplete", missing)
        if any(value <= 0 for value in values.values()):
            raise PlanError("out_of_range_parameter", tuple(values))
        _reject_unparsed(text, [_CREATE.search(text), _BOX.search(text),
                                *[expression.search(text) for expression in _DIMENSIONS.values()]])
        return PlannedStep("create_box", tuple(values.items()))
    if _MOVE.search(action_text) and not _CREATE.search(action_text):
        target_ref = "last_created" if _LAST.search(text) else None
        target = None if target_ref else _TARGET.search(text)
        alias = None if target is None else target.group(1)
        if target_ref is None and (alias is None or not _ALIAS.fullmatch(alias)):
            raise PlanError("information_incomplete", ("target_alias",))
        values = {key: _parse_number(text, expression, key)
                  for key, expression in _TRANSLATIONS.items()}
        missing = tuple(key for key, value in values.items() if value is None)
        if missing:
            raise PlanError("information_incomplete", missing)
        _reject_unparsed(text, [_MOVE.search(text), _LAST.search(text), target,
                                *[expression.search(text) for expression in _TRANSLATIONS.values()]])
        arguments = (("alias", alias), *values.items()) if target_ref is None else tuple(values.items())
        return PlannedStep("move_object", arguments, target_ref)
    raise PlanError("unsupported_or_ambiguous_step", ("explicit_action",))


def _json_steps(task: str) -> tuple[PlannedStep, ...]:
    try:
        value = json.loads(task, object_pairs_hook=_unique_pairs)
    except (json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise PlanError("invalid_json_task") from exc
    if isinstance(value, dict) and set(value) == {"steps"}:
        values = value["steps"]
    elif isinstance(value, dict):
        values = [value]
    else:
        raise PlanError("invalid_json_task")
    if not isinstance(values, list) or not 1 <= len(values) <= 6:
        raise PlanError("invalid_step_count")
    result = []
    for item in values:
        if not isinstance(item, dict):
            raise PlanError("invalid_step_shape")
        required = _REQUIRED.get(item.get("op")) if isinstance(item.get("op"), str) else None
        if required is not None:
            missing = tuple(sorted(required - item.keys() - {"op"}))
            if missing:
                raise PlanError("information_incomplete", missing)
        try:
            text = json.dumps(item, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise PlanError("invalid_step_shape") from exc
        try:
            name, args = _parse_command(text, {"aliases": [item.get("alias")] if item.get("alias") else []})
        except ExplicitStepError as exc:
            raise PlanError(exc.code) from exc
        if name == "move_object":
            alias = args.pop("object_id")
            args = {"alias": alias, "dx": args["translate_x"],
                    "dy": args["translate_y"], "dz": args["translate_z"]}
        result.append(PlannedStep(
            name, tuple(args.items()),
            source_segment_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        ))
    return tuple(result)


def compile_task(task: str) -> TaskPlan:
    if not isinstance(task, str) or not task.strip() or len(task) > 4096:
        raise PlanError("invalid_task")
    stripped = task.strip()
    if stripped[0] in "{[":
        steps, kind = _json_steps(stripped), "explicit_json"
    else:
        segments = _SPLIT.split(stripped)
        if not 1 <= len(segments) <= 6 or any(not segment.strip() for segment in segments):
            raise PlanError("invalid_step_count")
        steps = tuple(replace(_nl_step(segment), source_segment_sha256=hashlib.sha256(
            segment.strip().encode("utf-8"),
        ).hexdigest()) for segment in segments)
        kind = "bounded_natural_language"
    if not steps:
        raise PlanError("invalid_step_count")
    return TaskPlan(hashlib.sha256(task.encode("utf-8")).hexdigest(), steps, kind)
