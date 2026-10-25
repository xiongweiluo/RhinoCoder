"""Inert development budget/schedule review. No connection, model or host API.

This is a review component, never an execution grant. A complete field package
and an explicit owner approval are separate from these arithmetic checks.
"""
from __future__ import annotations

import math


OUTCOMES = ("success", "task_failure", "engineering_failure", "evidence_unknown", "not_attempted")


def development_schedule(plan: dict) -> list[dict]:
    """Deterministic order proposal only, with no claim or execution side effect."""
    # Validate before compiling the scope, never silently accept extra cells.
    review_plan(plan)
    combinations = [(route, system) for system in plan["systems"] for route in plan["routes"]]
    schedule = []
    for role in ("selection", "acceptance"):
        for index, family in enumerate(f for f in plan["families"] if f["role"] == role):
            order = combinations[index:] + combinations[:index]
            for route, system in order:
                schedule.append({"slot_id": "lora-dev-%02d" % len(schedule), "role": role,
                                 "family_id": family["id"], "route": route, "system": system})
    return schedule


def review_plan(plan: dict) -> dict:
    if plan.get("study_id") != "lora-optimization-development-v1" or plan.get("execution_enabled") is not False:
        raise ValueError("inert new development identity required")
    if plan.get("routes") != ["base", "current_lora"] or plan.get("systems") != ["original", "read_progress_v1"]:
        raise ValueError("exact two weights and two common systems required")
    families = plan["families"]
    if len(families) != 8 or len({f["id"] for f in families}) != 8:
        raise ValueError("eight unique development families required")
    if len({f["template_family"] for f in families}) != 8:
        raise ValueError("template families may not cross selection/acceptance")
    if sorted(f["role"] for f in families) != ["acceptance"] * 4 + ["selection"] * 4:
        raise ValueError("fixed selection/acceptance split required")
    limits = plan["limits"]
    for key, value in limits.items():
        if type(value) is not int or value < 0:
            raise ValueError("integer resource limits required")
    if not (limits["max_steps"] == limits["max_reads"] == 2 and limits["max_writes"] == 0
            and limits["max_load_attempts"] == 2 and limits["max_infrastructure_recoveries"] == 1):
        raise ValueError("bounded read-only development scope required")
    slots = len(families) * len(plan["routes"]) * len(plan["systems"])
    required = (slots * limits["slot_seconds"] + limits["max_load_attempts"] * limits["load_seconds"]
                + limits["cleanup_export_seconds"])
    if limits["slot_seconds"] <= 0 or limits["cleanup_export_seconds"] < 900 or required > limits["gpu_residency_seconds"]:
        raise ValueError("whole-window budget insufficient")
    # Even fully populated metadata cannot grant live execution through this API.
    missing = sorted(key for key, value in plan["required_before_execution"].items() if value is None)
    if plan.get("private_material_access") is not False or plan.get("historical_replay") is not False:
        raise ValueError("private evidence and historical experiments excluded")
    return {"study_id": plan["study_id"], "scope": "inert_development_review_only",
            "slots": slots, "max_step_requests": slots * limits["max_steps"],
            "max_generation_stages": slots * limits["max_steps"] * 2,
            "planned_worst_case_seconds": required,
            "remaining_headroom_seconds": limits["gpu_residency_seconds"] - required,
            "missing_before_execution": missing, "timing_feasibility_observed": False,
            "execution_authorized": False, "phase_one_complete": False}


def outcome_summary(families: list[str], routes: list[str], rows: list[dict], *, primary: tuple[str, str]) -> dict:
    """Fixed-denominator paired counts, never score/repair a task or grant GO.

    Inputs must contain every declared cell, including explicit unknown and
    unattempted outcomes. Engineering failures remain in the denominator.
    Confidence intervals and final preregistration are deliberately separate.
    """
    if (not families or len(set(families)) != len(families) or not 2 <= len(routes) <= 3
            or len(set(routes)) != len(routes) or len(set(primary)) != 2 or not set(primary) <= set(routes)):
        raise ValueError("unique fixed families/routes and primary pair required")
    expected = {(family, route) for family in families for route in routes}
    cells = {}
    for row in rows:
        if set(row) != {"family_id", "route", "outcome"}:
            raise ValueError("aggregate outcome fields only")
        key = row["family_id"], row["route"]
        if key not in expected or key in cells or row["outcome"] not in OUTCOMES:
            raise ValueError("unexpected/duplicate/invalid cell")
        cells[key] = row["outcome"]
    if set(cells) != expected:
        raise ValueError("missing cells must be declared unknown or not_attempted")
    n = len(families)
    counts = {route: {outcome: sum(cells[f, route] == outcome for f in families)
                      for outcome in OUTCOMES} for route in routes}
    first, second = primary
    second_only = sum(cells[f, second] == "success" and cells[f, first] != "success" for f in families)
    first_only = sum(cells[f, first] == "success" and cells[f, second] != "success" for f in families)
    complete = all(value not in {"evidence_unknown", "not_attempted"} for value in cells.values())
    discordant = first_only + second_only
    p = None
    if complete:
        p = min(1.0, 2 * sum(math.comb(discordant, k) for k in range(min(first_only, second_only) + 1))
                / 2 ** discordant) if discordant else 1.0
    return {"fixed_n": n, "counts": counts,
            "end_to_end_success_rate": {r: counts[r]["success"] / n for r in routes},
            "engineering_failure_rate": {r: counts[r]["engineering_failure"] / n for r in routes},
            "primary": list(primary), "second_only": second_only, "first_only": first_only,
            "observed_success_difference": (second_only - first_only) / n,
            "population_complete": complete, "exact_mcnemar_p": p,
            "confidence_interval": None, "confirmatory_improvement_claim": False,
            "scope": "observed_audited_success_counts_not_model_capacity_or_product_go"}
