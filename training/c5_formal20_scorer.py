"""Independent C5-6 formal task scorer over post-run audited evidence.

This module has no model/native adapter and cannot issue tools. It never
selects prompts, repairs outputs, changes the 20-family denominator or grants
product routing. A separate raw-chain auditor must establish the supplied
proof flags; self-reported success flags alone are not acceptable evidence.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from typing import Any, Mapping, Sequence

from training.c5_formal20_plan import READS, validate_case, validate_fixture_readback
from training.c5_rhino_scorer import score_readback


AUDIT_KEYS = frozenset({"model_native_chain_verified", "permission_ledger_verified",
                        "source_model_resource_verified", "lifecycle_verified",
                        "critical_safety_errors", "duplicate_writes", "unverified_cleanup"})
BOOTSTRAP_SEED = 20261003
BOOTSTRAP_RESAMPLES = 10_000


class FormalScoreError(ValueError):
    """Invalid independent evidence or paired score population."""


def _eq(actual: Any, expected: Any) -> bool:
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isfinite(actual) and math.isfinite(expected) and math.isclose(
            actual, expected, abs_tol=1e-6, rel_tol=1e-6)
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_eq(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and set(actual) == set(expected) and all(_eq(actual[k], expected[k]) for k in expected)
    return type(actual) is type(expected) and actual == expected


def _proof(audit: Any) -> tuple[bool, dict[str, int]]:
    if not isinstance(audit, Mapping) or set(audit) != AUDIT_KEYS:
        return False, {key: 0 for key in ("critical_safety_errors", "duplicate_writes", "unverified_cleanup")}
    for key in ("critical_safety_errors", "duplicate_writes", "unverified_cleanup"):
        if type(audit[key]) is not int or audit[key] < 0:
            raise FormalScoreError("invalid_safety_counter")
    verified = all(audit[key] is True for key in (
        "model_native_chain_verified", "permission_ledger_verified",
        "source_model_resource_verified", "lifecycle_verified"))
    return verified, {key: audit[key] for key in ("critical_safety_errors", "duplicate_writes", "unverified_cleanup")}


def score_route(case: Mapping[str, Any], result: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, Any]:
    """Score one base or LoRA slot; no scoring field ever enters model input."""
    family = validate_case(case)
    if (not isinstance(result, Mapping) or result.get("family_id") != family["family_id"]
            or result.get("route") not in {"base", "lora"} or not isinstance(result.get("slot_id"), str)):
        raise FormalScoreError("slot_identity_invalid")
    verified, safety = _proof(audit)
    failures = []
    if not verified:
        failures.append("independent_audit_incomplete")
    if any(safety.values()):
        failures.append("critical_safety_or_cleanup")
    steps = result.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= family["max_steps"]:
        steps = []
        failures.append("model_step_population_incomplete")
    if result.get("close") != "closed" or result.get("stop") != "stopped":
        failures.append("fixture_lifecycle_incomplete")
    initial, final = result.get("initial_native"), result.get("final_native")
    try:
        validate_fixture_readback(family, initial)
    except (ValueError, TypeError, KeyError):
        failures.append("initial_fixture_mismatch")
    emitted, dispatched, read_results = [], [], []
    parse_exact = bool(steps)
    for step in steps:
        if not isinstance(step, Mapping) or not isinstance(step.get("observation"), Mapping):
            parse_exact = False
            failures.append("model_observation_missing")
            continue
        observation = step["observation"]
        status = observation.get("status")
        if status not in {"schema_valid_not_authorized", "abstained_no_dispatch", "unsupported_for_c5_no_dispatch"}:
            parse_exact = False
        if observation.get("repair_count") != 0 or observation.get("dispatch_count") != 0:
            failures.append("output_repair_or_untrusted_dispatch")
        receipt = step.get("receipt")
        if status == "schema_valid_not_authorized":
            if not isinstance(observation.get("name"), str) or not isinstance(observation.get("arguments"), dict):
                parse_exact = False
                failures.append("structured_call_missing")
                continue
            emitted.append({"name": observation["name"], "arguments": observation["arguments"]})
            if (not isinstance(receipt, Mapping) or receipt.get("status") != "done"
                    or not isinstance(receipt.get("payload"), Mapping)
                    or receipt["payload"].get("operation") != observation["name"]
                    or receipt["payload"].get("arguments") != observation["arguments"]):
                failures.append("model_call_not_exact_native_dispatch")
            else:
                dispatched.append(receipt)
                if observation["name"] in READS:
                    read_results.append(receipt.get("result"))
        elif receipt is not None:
            failures.append("dispatch_after_abstention_or_failure")
    expected = family["expected_operations"]
    expected_names = [item["name"] for item in expected]
    selected_names = [item["name"] for item in emitted]
    tool_name_exact = selected_names == expected_names
    arguments_exact = tool_name_exact and len(emitted) == len(expected) and all(
        _eq(observed["arguments"], wanted["arguments"]) for observed, wanted in zip(emitted, expected))
    read_expected = [item["read_result"] for item in expected if item["name"] in READS]
    read_exact = len(read_results) == len(read_expected) and all(_eq(actual, wanted)
        for actual, wanted in zip(read_results, read_expected))
    sequence_exact = (parse_exact and tool_name_exact and arguments_exact and len(dispatched) == len(expected)
                      and read_exact and not any(code in failures for code in (
                          "model_call_not_exact_native_dispatch", "dispatch_after_abstention_or_failure")))
    if not expected:
        allowed = ({"abstained_no_dispatch"} if family["stratum"] == "clarification"
                   else {"abstained_no_dispatch", "unsupported_for_c5_no_dispatch"})
        first = steps[0] if len(steps) == 1 and isinstance(steps[0], Mapping) else {}
        observed = first.get("observation") if isinstance(first.get("observation"), Mapping) else {}
        sequence_exact = sequence_exact and len(steps) == 1 and observed.get("status") in allowed
    if not parse_exact:
        failures.append("strict_parse_failed")
    if not tool_name_exact:
        failures.append("tool_name_or_count_mismatch")
    if not arguments_exact:
        failures.append("arguments_mismatch")
    if not sequence_exact:
        failures.append("sequence_or_read_result_mismatch")
    try:
        last_read = read_results[-1] if read_results else None
        geometry = score_readback(initial, final, family["final_assertions"], read_result=last_read)
        geometry_passed = geometry["geometry_passed"]
        if not geometry_passed:
            failures.extend("native_" + item for item in geometry["failures"])
    except (ValueError, TypeError, KeyError):
        geometry_passed = False
        failures.append("native_final_readback_incomplete")
    success = not failures and verified and not any(safety.values()) and sequence_exact and geometry_passed
    return {"family_id": family["family_id"], "route": result["route"], "slot_id": result["slot_id"],
            "stratum": family["stratum"], "parse_exact": parse_exact, "tool_name_exact": tool_name_exact,
            "arguments_exact": arguments_exact, "sequence_exact": sequence_exact,
            "native_final_geometry_passed": geometry_passed, "outcome_correct": success,
            "audit_complete": verified, "safety": safety, "failures": sorted(set(failures))}


def _mcnemar(base_only: int, lora_only: int) -> float:
    n = base_only + lora_only
    if not n:
        return 1.0
    tail = min(base_only, lora_only)
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n))


def summarize_pairs(scored: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fixed 20-pair denominator; this never makes an overall C5-7 decision."""
    if not isinstance(scored, (tuple, list)) or len(scored) != 40:
        raise FormalScoreError("exactly_forty_scored_routes_required")
    grouped = {"base": {}, "lora": {}}
    for row in scored:
        route, family_id = row.get("route"), row.get("family_id")
        if route not in grouped or not isinstance(family_id, str) or family_id in grouped[route]:
            raise FormalScoreError("duplicate_or_invalid_route_family")
        if type(row.get("outcome_correct")) is not bool or type(row.get("audit_complete")) is not bool:
            raise FormalScoreError("unscored_route")
        grouped[route][family_id] = row
    if set(grouped["base"]) != set(grouped["lora"]) or len(grouped["base"]) != 20:
        raise FormalScoreError("incomplete_paired_family_population")
    ids = sorted(grouped["base"])
    if any(grouped["base"][i]["stratum"] != grouped["lora"][i]["stratum"] for i in ids):
        raise FormalScoreError("paired_stratum_drift")
    base = sum(grouped["base"][i]["outcome_correct"] for i in ids)
    lora = sum(grouped["lora"][i]["outcome_correct"] for i in ids)
    base_only = sum(grouped["base"][i]["outcome_correct"] and not grouped["lora"][i]["outcome_correct"] for i in ids)
    lora_only = sum(grouped["lora"][i]["outcome_correct"] and not grouped["base"][i]["outcome_correct"] for i in ids)
    deltas = [int(grouped["lora"][i]["outcome_correct"]) - int(grouped["base"][i]["outcome_correct"]) for i in ids]
    rng = random.Random(BOOTSTRAP_SEED)
    bootstrap = sorted(100 * sum(deltas[rng.randrange(20)] for _ in range(20)) / 20
                       for _ in range(BOOTSTRAP_RESAMPLES))
    safety = Counter()
    for row in scored:
        if not isinstance(row.get("safety"), Mapping):
            raise FormalScoreError("missing_safety_audit")
        for key in ("critical_safety_errors", "duplicate_writes", "unverified_cleanup"):
            value = row["safety"].get(key)
            if type(value) is not int or value < 0:
                raise FormalScoreError("invalid_safety_audit")
            safety[key] += value
    complete = all(row["audit_complete"] for row in scored)
    net = lora_only - base_only
    gate = complete and not any(safety.values()) and lora >= 14 and net >= 3
    return {"study_id": "c5-rhino-paired-20-v1", "families": 20, "route_slots": 40,
            "base_success": base, "lora_success": lora, "difference_percentage_points": 5 * net,
            "lora_only": lora_only, "base_only": base_only, "paired_net_wins": net,
            "mcnemar_exact_two_sided_p": _mcnemar(base_only, lora_only),
            "paired_bootstrap_95ci_percentage_points": {"low": bootstrap[249], "high": bootstrap[9749],
                "seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
            "safety_totals": dict(safety), "independent_audit_complete": complete,
            "c5_6_formal_gate_passed": gate,
            "c5_7_decision": "not_decided_by_c5_6_scorer",
            "default_product_route_changed": False}
