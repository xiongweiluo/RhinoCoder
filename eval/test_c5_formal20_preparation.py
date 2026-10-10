"""Synthetic-only C5-6 plan, coordinator and independent score tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plugin.rhino_listener.c5_research_native import digest
from training.c5_contract import CORE_INVOCATION_TOOLS
from training.c5_formal20_plan import (
    FormalPlanError, family_merkle_root, model_view, slot_order, slot_order_sha256,
    validate_families,
)
from training.c5_formal20_runner import FormalRunner
from training.c5_formal20_scorer import FormalScoreError, score_route, summarize_pairs
from tools.c5_formal20_freeze_preflight import report as public_freeze_report


EMPTY = {"unit": "Millimeters", "objects": [], "groups": {}}
EMPTY_ASSERTIONS = {"object_count": 0, "objects": {}, "unchanged": [], "read_result": None}
ARGS = {
    "boolean_difference": {"input0_ids": ["box-1"], "input1_ids": ["box-2"]},
    "create_box": {"width": 2, "depth": 3, "height": 4},
    "create_cylinder": {"radius": 2, "height": 3},
    "create_sphere": {"radius": 2},
    "get_bounding_box": {"object_id": "box-1"},
    "get_scene_summary": {},
    "group_objects": {"object_ids": ["box-1"], "group_name": "GroupA"},
    "move_object": {"object_id": "box-1", "translate_x": 1, "translate_y": 2, "translate_z": 3},
    "rotate_object": {"object_id": "box-1", "angle_degrees": 30},
    "scale_object": {"object_id": "box-1", "scale_factor": [1.1, 1.2, 1.3]},
    "set_object_color": {"object_ids": ["box-1"], "r": 10, "g": 20, "b": 30},
    "set_object_layer": {"object_id": "box-1", "layer_name": "Demo"},
}


def cases20():
    result = []
    strata = (["core_tool"] * 12 + ["multistep"] * 2 + ["clarification"] * 2 +
              ["refusal"] * 2 + ["error_recovery"] * 2)
    for index, stratum in enumerate(strata):
        if stratum == "core_tool":
            name = CORE_INVOCATION_TOOLS[index]
            ops = [{"name": name, "arguments": ARGS[name], "read_result": EMPTY if name == "get_scene_summary" else
                    {"object_id": "box-1", "min": [0, 0, 0], "max": [1, 1, 1], "center": [0.5, 0.5, 0.5]}
                    if name == "get_bounding_box" else None}]
        elif stratum == "multistep":
            ops = [{"name": "create_box", "arguments": ARGS["create_box"], "read_result": None},
                   {"name": "move_object", "arguments": ARGS["move_object"], "read_result": None}]
        elif stratum == "error_recovery":
            ops = [{"name": "get_scene_summary", "arguments": ARGS["get_scene_summary"], "read_result": EMPTY}]
        else:
            ops = []
        writes = sum(item["name"] not in {"get_bounding_box", "get_scene_summary"} for item in ops)
        reads = len(ops) - writes
        result.append({"schema_version": 1, "family_id": f"synthetic-family-{index:02d}",
                       "template_family": f"synthetic-template-{index:02d}", "stratum": stratum,
                       "primary_tool": CORE_INVOCATION_TOOLS[index] if index < 12 else None,
                       "task_text": f"Synthetic only, case {index} with a distinct purpose token {chr(65+index)}.",
                       "fixture_recipe": [], "initial_assertions": EMPTY_ASSERTIONS,
                       "max_steps": max(1, len(ops)), "max_writes": writes, "max_reads": reads,
                       "expected_operations": ops, "final_assertions": EMPTY_ASSERTIONS})
    return result


class SyntheticModel:
    def __init__(self):
        self.calls = []
        self.starts = self.stops = 0
        self.fail = False
        self.plans = None

    def prepare(self, plans, *, freeze_sha256): self.plans = plans
    def start(self): self.starts += 1
    def stop(self): self.stops += 1

    def infer(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail: raise RuntimeError("synthetic model interruption")
        return {"observation": {"status": "abstained_no_dispatch", "name": None,
                                "arguments": None, "repair_count": 0, "dispatch_count": 0,
                                "scene_binding": kwargs["binding"]},
                "generation_receipts": [{"stage": "selector"}]}


class SyntheticNative:
    def __init__(self): self.opened = self.closed = self.stopped = 0; self.plans = None; self.hub_starts = 0
    def prepare(self, plans, *, freeze_sha256): self.plans = plans
    def start(self): self.hub_starts += 1
    def open_slot(self, **kwargs): self.opened += 1
    def capture(self, slot_id):
        return {"status": "captured", "state": {"document_key": "0" * 64, "revision": 0,
                "scene_sha256": "1" * 64}, "native": json.loads(json.dumps(EMPTY))}
    def execute_observation(self, **kwargs): raise AssertionError("abstention must never dispatch")
    def unresolved(self, slot_id): return False
    def close_slot(self, slot_id): self.closed += 1; return {"status": "closed"}
    def stop_slot(self, slot_id): self.stopped += 1; return {"status": "stopped"}
    def finish(self): return {"status": "hub_stopped", "had_failure": False}


def authority(cases):
    spec = {"study_id": "c5-rhino-paired-20-v1", "execution_ready": True,
            "family_count": 20, "route_slots": 40,
            "thresholds": {"lora_success_min": 14, "paired_net_wins_min": 3,
                           "difference_percentage_points_min": 15, "critical_safety_errors_max": 0,
                           "duplicate_writes_max": 0, "unverified_cleanup_max": 0},
            "original_final_entry_allowed": False, "automatic_retry_allowed": False,
            "default_route_change_allowed": False, "model_generation_cutoff_epoch": 9999990000,
            "lease_expiry_epoch": 9999999999, "export_reserve_seconds": 900,
            "formal_gpu_seconds_max": 10800, "max_generation_stages": 160, "slot_seed": 20261003,
            "family_merkle_root_sha256": family_merkle_root(cases),
            "slot_order_sha256": slot_order_sha256(slot_order(cases, seed=20261003)),
            "public_commitment_sha256": "2" * 64}
    freeze = {"study_id": spec["study_id"], "execution_ready": True, "spec_sha256": digest(spec)}
    approval = {"study_id": spec["study_id"], "actor": "repository_owner", "approved": True,
                "spec_sha256": digest(spec), "runtime_freeze_sha256": digest(freeze),
                "approval_basis": "direct repository_owner approval of complete C5-6 formal20 spec and runtime freeze"}
    return spec, freeze, approval


class Formal20PreparationTests(unittest.TestCase):
    def test_public_freeze_preflight_cannot_claim_execution_ready(self):
        value = public_freeze_report()
        self.assertFalse(value["execution_ready"])
        self.assertFalse(value["actual_mac_rhino_gpu_import_closure_verified"])
        self.assertEqual(value["private_task_files_opened"], 0)
        self.assertEqual(value["gpu_model_calls"], 0)

    def test_complete_plan_and_counterbalanced_schedule(self):
        cases = validate_families(cases20())
        order = slot_order(cases, seed=20261003)
        self.assertEqual(len(order), 40)
        self.assertEqual(sum(order[i]["route"] == "base" for i in range(0, 40, 2)), 10)
        self.assertEqual(order, slot_order(cases, seed=20261003))
        self.assertEqual(model_view(cases[0]), cases[0]["task_text"])
        self.assertNotIn("expected_operations", model_view(cases[0]))

    def test_private_case_shape_and_reuse_fail_closed(self):
        cases = cases20()
        cases[1]["template_family"] = cases[0]["template_family"]
        with self.assertRaisesRegex(FormalPlanError, "template_family_reuse"):
            validate_families(cases)
        cases = cases20(); cases[0]["max_steps"] = 2
        with self.assertRaisesRegex(FormalPlanError, "dispatch_or_step_budget"):
            validate_families(cases)

    def test_run_claim_precedes_private_loader_and_is_not_reusable(self):
        cases = cases20()
        spec, freeze, approval = authority(cases)
        model, native = SyntheticModel(), SyntheticNative()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve() / "private-state"; state.mkdir(mode=0o700)
            def load():
                self.assertTrue((state / "formal20.started.json").exists())
                return cases
            runner = FormalRunner(state=state, spec=spec, freeze=freeze, approval=approval,
                                  model=model, native=native, source_guard=lambda: None,
                                  budget_guard=lambda: None)
            result = runner.run(load)
            self.assertEqual(result["status"], "formal_execution_complete_awaiting_independent_audit")
            self.assertFalse(result["c5_6_gate_claim"])
            self.assertEqual(result["slots_attempted"], 40)
            self.assertEqual((model.starts, model.stops, len(model.calls)), (1, 1, 40))
            self.assertEqual((native.opened, native.closed, native.stopped), (40, 40, 40))
            self.assertEqual(native.hub_starts, 1)
            self.assertNotIn("expected_operations", json.dumps(model.plans))
            self.assertNotIn("final_assertions", json.dumps(native.plans))
            with self.assertRaises(FileExistsError):
                runner.run(lambda: self.fail("private loader must not run on replay"))

    def test_unknown_model_failure_stops_global_sequence_and_preserves_claim(self):
        cases = cases20(); spec, freeze, approval = authority(cases)
        model, native = SyntheticModel(), SyntheticNative(); model.fail = True
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve() / "private-state"; state.mkdir(mode=0o700)
            runner = FormalRunner(state=state, spec=spec, freeze=freeze, approval=approval,
                                  model=model, native=native, source_guard=lambda: None,
                                  budget_guard=lambda: None)
            result = runner.run(lambda: cases)
            self.assertEqual(result["status"], "formal_incomplete_no_replay")
            self.assertEqual(result["slots_attempted"], 1)
            self.assertEqual((model.starts, model.stops), (1, 1))
            self.assertEqual((native.opened, native.closed, native.stopped), (1, 1, 1))
            self.assertTrue((state / "formal20.started.json").exists())

    def test_draft_never_claims_or_loads(self):
        cases = cases20(); spec, freeze, approval = authority(cases)
        spec["execution_ready"] = False
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve() / "private-state"; state.mkdir(mode=0o700)
            runner = FormalRunner(state=state, spec=spec, freeze=freeze, approval=approval,
                                  model=SyntheticModel(), native=SyntheticNative(),
                                  source_guard=lambda: None, budget_guard=lambda: None)
            with self.assertRaisesRegex(Exception, "draft formal freeze"):
                runner.run(lambda: self.fail("no private loader under draft"))
            self.assertFalse((state / "formal20.started.json").exists())


class Formal20ScorerTests(unittest.TestCase):
    def _audit(self):
        return {"model_native_chain_verified": True, "permission_ledger_verified": True,
                "source_model_resource_verified": True, "lifecycle_verified": True,
                "critical_safety_errors": 0, "duplicate_writes": 0, "unverified_cleanup": 0}

    def test_real_geometry_and_strict_call_both_required(self):
        case = cases20()[1]
        case["primary_tool"] = "create_box"
        case["expected_operations"] = [{"name": "create_box", "arguments": {"width": 2, "depth": 3, "height": 4}, "read_result": None}]
        case["final_assertions"] = {"object_count": 1, "objects": {"box-1": {
            "min": [0, 0, 0], "max": [2, 3, 4], "volume": 24, "centroid": [1, 1.5, 2],
            "solid": True, "face_count": 6}}, "unchanged": [], "read_result": None}
        final = {"unit": "Millimeters", "objects": [{"alias": "box-1", "min": [0, 0, 0],
                 "max": [2, 3, 4], "volume": 24.0, "centroid": [1, 1.5, 2],
                 "solid": True, "face_count": 6}], "groups": {}}
        obs = {"status": "schema_valid_not_authorized", "name": "create_box",
               "arguments": {"width": 2, "depth": 3, "height": 4},
               "repair_count": 0, "dispatch_count": 0}
        result = {"family_id": case["family_id"], "route": "lora", "slot_id": "F01-lora",
                  "initial_native": EMPTY, "final_native": final, "close": "closed", "stop": "stopped",
                  "steps": [{"observation": obs, "receipt": {"status": "done", "payload": {
                      "operation": "create_box", "arguments": obs["arguments"]}, "result": {"created_alias": "box-1"}}}]}
        self.assertTrue(score_route(case, result, self._audit())["outcome_correct"])
        final["objects"][0]["volume"] = 12.0
        bad = score_route(case, result, self._audit())
        self.assertFalse(bad["outcome_correct"])
        self.assertFalse(bad["native_final_geometry_passed"])

    def test_clarification_abstention_and_contract_failure(self):
        case = cases20()[14]
        result = {"family_id": case["family_id"], "route": "base", "slot_id": "F02-base",
                  "initial_native": EMPTY, "final_native": EMPTY, "close": "closed", "stop": "stopped",
                  "steps": [{"observation": {"status": "abstained_no_dispatch", "repair_count": 0,
                                               "dispatch_count": 0}, "receipt": None}]}
        self.assertTrue(score_route(case, result, self._audit())["outcome_correct"])
        result["steps"][0]["observation"]["status"] = "selector_contract_failure_no_dispatch"
        self.assertFalse(score_route(case, result, self._audit())["outcome_correct"])

    def test_fixed_paired_threshold_and_safety(self):
        rows = []
        for index in range(20):
            for route in ("base", "lora"):
                rows.append({"family_id": f"paired-{index:02d}", "route": route,
                             "stratum": "core_tool", "outcome_correct": index < (11 if route == "base" else 14),
                             "audit_complete": True,
                             "safety": {"critical_safety_errors": 0, "duplicate_writes": 0, "unverified_cleanup": 0}})
        summary = summarize_pairs(rows)
        self.assertEqual((summary["base_success"], summary["lora_success"], summary["paired_net_wins"]), (11, 14, 3))
        self.assertTrue(summary["c5_6_formal_gate_passed"])
        rows[0]["safety"]["duplicate_writes"] = 1
        self.assertFalse(summarize_pairs(rows)["c5_6_formal_gate_passed"])
        with self.assertRaises(FormalScoreError): summarize_pairs(rows[:-1])


if __name__ == "__main__": unittest.main()
