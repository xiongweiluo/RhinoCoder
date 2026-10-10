"""Private C5-6 task contract and fixed paired schedule; no execution or I/O.

The owner keeps these 20 cases sealed. Validation is run only by the owner
after a separately approved one-time claim. Public preparation never imports
or opens a real task file. Expected outputs are *never* returned by
``model_view`` and must only be passed to the independent post-run scorer.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from plugin.rhino_listener.c5_research_native import NativeError, validate_native_arguments
from training.c5_contract import CORE_INVOCATION_TOOLS
from training.c5_rhino_scorer import FIELDS, score_readback
from training.c5_rhino_adapter import step_input


STUDY_ID = "c5-rhino-paired-20-v1"
STRATA = {"core_tool": 12, "multistep": 2, "clarification": 2,
          "refusal": 2, "error_recovery": 2}
READS = frozenset({"get_bounding_box", "get_scene_summary"})
SEED_OPERATIONS = frozenset({"create_box", "create_cylinder", "create_sphere",
                             "move_object", "rotate_object", "scale_object",
                             "set_object_color", "set_object_layer", "group_objects"})
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{3,79}\Z")
CASE_KEYS = frozenset({"schema_version", "family_id", "template_family", "stratum",
                       "primary_tool", "task_text", "fixture_recipe", "initial_assertions",
                       "max_steps", "max_writes", "max_reads", "expected_operations",
                       "final_assertions"})
ASSERTION_KEYS = frozenset({"object_count", "objects", "unchanged", "read_result"})


class FormalPlanError(ValueError):
    """Private family or schedule violates the preregistered formal protocol."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _bounded_assertions(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != ASSERTION_KEYS:
        raise FormalPlanError(label + "_assertion_fields")
    if type(value["object_count"]) is not int or not 0 <= value["object_count"] <= 16:
        raise FormalPlanError(label + "_object_count")
    if not isinstance(value["objects"], dict) or not isinstance(value["unchanged"], list):
        raise FormalPlanError(label + "_assertion_shape")
    if len(value["objects"]) > 16 or len(value["unchanged"]) > 16:
        raise FormalPlanError(label + "_assertion_budget")
    if any(not isinstance(alias, str) or not 1 <= len(alias) <= 80
           for alias in list(value["objects"]) + value["unchanged"]):
        raise FormalPlanError(label + "_alias_shape")
    if len(set(value["unchanged"])) != len(value["unchanged"]):
        raise FormalPlanError(label + "_unchanged_alias_reuse")
    for fields in value["objects"].values():
        if not isinstance(fields, dict) or not {"volume", "solid", "face_count"} <= set(fields) or set(fields) - FIELDS:
            raise FormalPlanError(label + "_solid_evidence_fields")
    # The existing independent native scorer performs the full assertion
    # check after execution. Here only reject structurally incomplete plans.


def _schemas() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "eval/c5/rhino-runtime-schema-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))["core_parameters"]


def validate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a private case without constructing a model prompt."""
    if not isinstance(case, Mapping) or set(case) != CASE_KEYS or type(case["schema_version"]) is not int or case["schema_version"] != 1:
        raise FormalPlanError("case_version_or_fields")
    for key in ("family_id", "template_family"):
        if not isinstance(case[key], str) or not NAME.fullmatch(case[key]):
            raise FormalPlanError(key + "_invalid")
    if not isinstance(case["stratum"], str) or case["stratum"] not in STRATA:
        raise FormalPlanError("stratum_invalid")
    if not isinstance(case["task_text"], str) or not case["task_text"].strip() or len(case["task_text"].encode()) > 4096:
        raise FormalPlanError("task_text_invalid")
    try:
        step_input(case["task_text"], {"unit": "Millimeters", "objects": [], "groups": {}})
    except (ValueError, TypeError) as exc:
        raise FormalPlanError("task_text_not_alias_safe") from exc
    if not isinstance(case["fixture_recipe"], list) or len(case["fixture_recipe"]) > 8:
        raise FormalPlanError("fixture_recipe_budget")
    schemas = _schemas()
    for row in case["fixture_recipe"]:
        if not isinstance(row, dict) or set(row) != {"operation", "arguments"} or row["operation"] not in SEED_OPERATIONS or not isinstance(row["arguments"], dict):
            raise FormalPlanError("fixture_seed_operation_invalid")
        try:
            validate_native_arguments(row["operation"], row["arguments"], schemas)
        except (NativeError, ValueError, TypeError) as exc:
            raise FormalPlanError("fixture_seed_arguments_invalid") from exc
    _bounded_assertions(case["initial_assertions"], "initial")
    _bounded_assertions(case["final_assertions"], "final")
    if case["initial_assertions"]["read_result"] is not None:
        raise FormalPlanError("initial_read_result_must_be_null")
    for key, maximum in (("max_steps", 3), ("max_writes", 3), ("max_reads", 3)):
        if type(case[key]) is not int or not 0 <= case[key] <= maximum:
            raise FormalPlanError(key + "_invalid")
    if case["max_steps"] == 0:
        raise FormalPlanError("zero_model_steps")
    operations = case["expected_operations"]
    if not isinstance(operations, list) or len(operations) > case["max_steps"]:
        raise FormalPlanError("expected_sequence_budget")
    for item in operations:
        if (not isinstance(item, dict) or set(item) != {"name", "arguments", "read_result"}
                or item["name"] not in CORE_INVOCATION_TOOLS or not isinstance(item["arguments"], dict)):
            raise FormalPlanError("expected_operation_invalid")
        if item["name"] not in READS and item["read_result"] is not None:
            raise FormalPlanError("write_expected_read_result")
        if item["name"] in READS and item["read_result"] is None:
            raise FormalPlanError("read_expected_result_missing")
        try:
            validate_native_arguments(item["name"], item["arguments"], schemas)
        except (NativeError, ValueError, TypeError) as exc:
            raise FormalPlanError("expected_arguments_invalid") from exc
    names = [item["name"] for item in operations]
    if (sum(name not in READS for name in names) != case["max_writes"]
            or sum(name in READS for name in names) != case["max_reads"]
            or case["max_steps"] != max(1, len(names))):
        raise FormalPlanError("dispatch_or_step_budget_differs_from_expected_sequence")
    if case["stratum"] == "core_tool":
        if (case["primary_tool"] not in CORE_INVOCATION_TOOLS or names != [case["primary_tool"]]
                or case["max_steps"] != 1):
            raise FormalPlanError("core_tool_case_shape")
    elif case["stratum"] in {"clarification", "refusal"}:
        if case["primary_tool"] is not None or names or case["max_steps"] != 1 or case["max_writes"] or case["max_reads"]:
            raise FormalPlanError("abstention_case_shape")
    elif case["stratum"] == "multistep":
        if case["primary_tool"] is not None or len(names) < 2 or case["max_steps"] < 2:
            raise FormalPlanError("multistep_case_shape")
    else:  # error_recovery: a pre-existing factual error is part of task_text.
        if case["primary_tool"] is not None or not names:
            raise FormalPlanError("recovery_case_shape")
    # Detach caller-owned mutable data; non-finite values and unserializable
    # objects are rejected here, before any owner-side private commitment.
    try:
        return json.loads(_canonical(case))
    except (TypeError, ValueError, RecursionError) as exc:
        raise FormalPlanError("case_not_canonical_json") from exc


def validate_families(families: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(families, (tuple, list)) or len(families) != 20:
        raise FormalPlanError("exactly_twenty_families_required")
    cases = [validate_case(item) for item in families]
    if len(_canonical(cases)) > 512 * 1024:
        raise FormalPlanError('private_family_package_exceeds_channel_budget')
    if Counter(case["stratum"] for case in cases) != STRATA:
        raise FormalPlanError("formal_strata_mismatch")
    core = [case["primary_tool"] for case in cases if case["stratum"] == "core_tool"]
    if Counter(core) != Counter(CORE_INVOCATION_TOOLS):
        raise FormalPlanError("core_tool_coverage_mismatch")
    for key in ("family_id", "template_family"):
        if len({case[key] for case in cases}) != 20:
            raise FormalPlanError(key + "_reuse")
    if len({case["task_text"] for case in cases}) != 20:
        raise FormalPlanError("task_text_reuse")
    return cases


def slot_order(families: Sequence[Mapping[str, Any]], *, seed: int) -> list[dict[str, str]]:
    """Adjacent pairs, 10 base-first and 10 LoRA-first; never outcome-adaptive."""
    cases = validate_families(families)
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise FormalPlanError("frozen_schedule_seed_required")
    ids = sorted(case["family_id"] for case in cases)
    random.Random(seed).shuffle(ids)
    result = []
    for index, family_id in enumerate(ids):
        first = "base" if index < 10 else "lora"
        second = "lora" if index < 10 else "base"
        result.extend({"slot_id": f"F{index+1:02d}-{route}", "family_id": family_id,
                       "route": route} for route in (first, second))
    return result


def slot_order_sha256(order: Sequence[Mapping[str, str]]) -> str:
    return hashlib.sha256(_canonical(order)).hexdigest()


def family_merkle_root(families: Sequence[Mapping[str, Any]]) -> str:
    """Commit private full cases without revealing them in public metadata."""
    cases = validate_families(families)
    nodes = sorted(hashlib.sha256(_canonical(case)).digest() for case in cases)
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[index] + nodes[index + 1]).digest()
                 for index in range(0, len(nodes), 2)]
    return nodes[0].hex()


def model_view(case: Mapping[str, Any]) -> str:
    """Only original natural-language task reaches model prompt construction."""
    validated = validate_case(case)
    return validated["task_text"]


def validate_fixture_readback(case: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    validated = validate_case(case)
    scored = score_readback(actual, actual, validated["initial_assertions"], read_result=None)
    if not scored["geometry_passed"]:
        raise FormalPlanError("actual_seed_fixture_differs_from_private_frozen_assertions")
