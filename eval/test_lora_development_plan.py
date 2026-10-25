"""Synthetic budget and aggregate accounting; no task data or field execution."""
import copy
import json
from pathlib import Path

import pytest

from training.lora_development_plan import development_schedule, outcome_summary, review_plan
from training.lora_development_cases import build_cases, fixture_design
from training.c5_formal20_privacy import allowed
from training.c5_rhino_scorer import score_readback


PLAN = Path(__file__).resolve().parents[1] / "eval/lora-development/proposed-development-plan.json"


def test_review_has_a_whole_window_but_no_execution_authority():
    result = review_plan(json.loads(PLAN.read_text()))
    assert result["slots"] == 32 and result["max_generation_stages"] == 128
    assert result["planned_worst_case_seconds"] == 6900
    assert result["remaining_headroom_seconds"] == 300
    assert result["missing_before_execution"] and not result["execution_authorized"]


def test_development_schedule_keeps_acceptance_after_selection_and_counterbalances_each_cell():
    plan = json.loads(PLAN.read_text())
    schedule = development_schedule(plan)
    assert schedule == development_schedule(plan)
    assert len(schedule) == len({r["slot_id"] for r in schedule}) == 32
    assert [r["role"] for r in schedule] == ["selection"] * 16 + ["acceptance"] * 16
    combinations = {(r, s) for r in plan["routes"] for s in plan["systems"]}
    for family in plan["families"]:
        assert {(r["route"], r["system"]) for r in schedule if r["family_id"] == family["id"]} == combinations
    for offset in (0, 16):
        for position in range(4):
            assert {(schedule[i]["route"], schedule[i]["system"])
                    for i in range(offset + position, offset + 16, 4)} == combinations


def test_public_development_cases_match_review_scope_and_do_not_authorize_model_writes():
    plan = json.loads(PLAN.read_text())
    cases = build_cases()
    assert [(r["case"]["family_id"], r["role"], r["case"]["template_family"]) for r in cases] == [
        (r["id"], r["role"], r["template_family"]) for r in plan["families"]]
    recipe, scene, assertions = fixture_design()
    # Analytic fixture check, explicitly not a real host geometry observation.
    native = {**scene, "objects": [{"alias": alias, **fields} for alias, fields in assertions["objects"].items()]}
    assert score_readback(native, native, assertions)["geometry_passed"]
    for row in cases:
        case = row["case"]
        assert allowed(case["task_text"], scene)
        assert case["max_writes"] == 0 and case["max_steps"] <= 2 and len(recipe) == 7
        assert all(op["name"] in {"get_bounding_box", "get_scene_summary"} for op in case["expected_operations"])
        last_read = case["expected_operations"][-1]["read_result"] if case["expected_operations"] else None
        assert score_readback(native, native, case["final_assertions"], read_result=last_read)["geometry_passed"]


@pytest.mark.parametrize("change", ["budget", "boolean_limit", "template_leak", "execution", "writes"])
def test_development_review_rejects_budget_or_scope_expansion(change):
    plan = json.loads(PLAN.read_text())
    if change == "budget": plan["limits"]["gpu_residency_seconds"] = 6899
    if change == "boolean_limit": plan["limits"]["slot_seconds"] = True
    if change == "template_leak": plan["families"][-1]["template_family"] = plan["families"][0]["template_family"]
    if change == "execution": plan["execution_enabled"] = True
    if change == "writes": plan["limits"]["max_writes"] = 1
    with pytest.raises(ValueError): review_plan(plan)


def rows(outcomes, routes=("base", "current_lora")):
    return [{"family_id": f"aggregate-{i}", "route": r, "outcome": value}
            for i, pair in enumerate(outcomes) for r, value in zip(routes, pair)]


def summary(data, routes=("base", "current_lora")):
    return outcome_summary(sorted({r["family_id"] for r in data}), list(routes), data,
                           primary=(routes[0], routes[1]))


def test_engineering_failures_stay_in_paired_denominator():
    result = summary(rows([("engineering_failure", "success"), ("success", "task_failure"),
                           ("task_failure", "success"), ("task_failure", "task_failure")]))
    assert result["fixed_n"] == 4
    assert result["end_to_end_success_rate"] == {"base": .25, "current_lora": .5}
    assert result["engineering_failure_rate"]["base"] == .25
    assert (result["second_only"], result["first_only"]) == (2, 1)
    assert result["exact_mcnemar_p"] == 1.0


def test_unknowns_preserve_coverage_but_cannot_support_confirmatory_statistics():
    result = summary(rows([("evidence_unknown", "success"), ("not_attempted", "task_failure")]))
    assert result["fixed_n"] == 2 and result["end_to_end_success_rate"]["current_lora"] == .5
    assert result["exact_mcnemar_p"] is None and not result["population_complete"]
    assert result["confidence_interval"] is None and not result["confirmatory_improvement_claim"]


def test_pair_order_swaps_direction_and_preserves_exact_p():
    data = rows([("task_failure", "success")] * 6 + [("success", "success")])
    result = summary(data)
    reversed_result = summary(data, ("current_lora", "base"))
    assert result["exact_mcnemar_p"] == reversed_result["exact_mcnemar_p"] == .03125
    assert result["observed_success_difference"] == -reversed_result["observed_success_difference"]
    assert not result["confirmatory_improvement_claim"]


def test_all_ties_and_complete_three_route_accounting():
    routes = ("base", "current_lora", "candidate_lora")
    result = summary(rows([("success", "success", "success")] * 3, routes), routes)
    assert result["fixed_n"] == 3 and result["exact_mcnemar_p"] == 1.0
    assert result["observed_success_difference"] == 0


@pytest.mark.parametrize("change", ["missing", "duplicate", "unexpected", "unclassified"])
def test_missing_or_changed_population_is_rejected(change):
    data = rows([("success", "success"), ("task_failure", "success")])
    if change == "missing": data.pop()
    if change == "duplicate": data.append(copy.deepcopy(data[0]))
    if change == "unexpected": data[0]["route"] = "extra"
    if change == "unclassified": data[0]["outcome"] = None
    with pytest.raises(ValueError):
        outcome_summary(["aggregate-0", "aggregate-1"], ["base", "current_lora"], data,
                        primary=("base", "current_lora"))
