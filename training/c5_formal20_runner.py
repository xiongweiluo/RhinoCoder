"""Fail-closed C5-6 formal paired coordinator, with injected real adapters.

No CLI, model loader, Rhino import, decryption, or network call lives here.
The actual entry must independently verify a complete source/environment
freeze and owner grant, provide sealed-content loader and signed native/model
adapters, then call ``run`` exactly once. This core never receives scorer
answers on the model side. Tests inject synthetic adapters only.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from plugin.rhino_listener.c5_research_channel import claim_slot, private_directory, publish_json
from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_formal20_plan import (
    READS, STUDY_ID, model_view, slot_order, slot_order_sha256,
    validate_families, validate_fixture_readback, family_merkle_root,
)
from training.c5_modelbridge_joint_audit import semantic
from training.c5_rhino_adapter import step_input


class FormalModel(Protocol):
    def prepare(self, plans: Mapping[str, Any], *, freeze_sha256: str) -> None: ...
    def start(self) -> None: ...
    def infer(self, *, slot_id: str, route: str, step_index: int, task_text: str,
              scene: Mapping[str, Any], binding: Mapping[str, Any], freeze_sha256: str) -> Mapping[str, Any]: ...
    def stop(self) -> None: ...


class FormalNative(Protocol):
    def prepare(self, plans: Mapping[str, Any], *, freeze_sha256: str) -> None: ...
    def start(self) -> None: ...
    def open_slot(self, *, slot_id: str, fixture_recipe: list, task_sha256: str,
                  max_writes: int, max_reads: int, freeze_sha256: str) -> None: ...
    def capture(self, slot_id: str) -> Mapping[str, Any]: ...
    def execute_observation(self, *, slot_id: str, task_text: str,
                            response: Mapping[str, Any], before: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def unresolved(self, slot_id: str) -> bool: ...
    def close_slot(self, slot_id: str) -> Mapping[str, Any]: ...
    def stop_slot(self, slot_id: str) -> Mapping[str, Any]: ...
    def finish(self) -> Mapping[str, Any]: ...


class FormalRunError(RuntimeError):
    """Formal boundary/transport/lifecycle uncertain; never retry this run."""


def validate_authority(spec: Mapping[str, Any], freeze: Mapping[str, Any], approval: Mapping[str, Any]) -> str:
    """Exact fresh formal grant; B/native12/R approvals are not reusable."""
    require(isinstance(spec, Mapping) and isinstance(freeze, Mapping) and isinstance(approval, Mapping),
            "complete formal authority records required")
    require(spec.get("study_id") == freeze.get("study_id") == approval.get("study_id") == STUDY_ID
            and spec.get("execution_ready") is True and freeze.get("execution_ready") is True,
            "draft formal freeze cannot execute")
    thresholds = {"lora_success_min": 14, "paired_net_wins_min": 3,
        "difference_percentage_points_min": 15, "critical_safety_errors_max": 0,
        "duplicate_writes_max": 0, "unverified_cleanup_max": 0}
    require(spec.get("family_count") == 20 and spec.get("route_slots") == 40
            and spec.get("thresholds") == thresholds
            and all(type(spec["thresholds"][key]) is int for key in thresholds),
            "formal denominator/threshold drift")
    require(freeze.get("spec_sha256") == digest(spec) and approval == {
        "study_id": STUDY_ID, "actor": "repository_owner", "approved": True,
        "spec_sha256": digest(spec), "runtime_freeze_sha256": digest(freeze),
        "approval_basis": "direct repository_owner approval of complete C5-6 formal20 spec and runtime freeze"},
        "new exact repository owner formal approval missing")
    require(spec.get("original_final_entry_allowed") is False and spec.get("automatic_retry_allowed") is False
            and spec.get("default_route_change_allowed") is False,
            "original run/retry/product route boundary differs")
    require(type(spec.get("model_generation_cutoff_epoch")) is int
            and type(spec.get("lease_expiry_epoch")) is int
            and type(spec.get("export_reserve_seconds")) is int
            and spec["model_generation_cutoff_epoch"] < spec["lease_expiry_epoch"]
            and spec["export_reserve_seconds"] >= 900
            and spec["lease_expiry_epoch"] - spec["model_generation_cutoff_epoch"] >= spec["export_reserve_seconds"]
            and time.time() < spec["model_generation_cutoff_epoch"]
            and type(spec.get("formal_gpu_seconds_max")) is int
            and 0 < spec["formal_gpu_seconds_max"] <= 10800,
            "formal resource/cutoff boundary missing")
    require(type(spec.get("max_generation_stages")) is int
            and 40 <= spec["max_generation_stages"] <= 240,
            "bounded formal generation stage ceiling missing")
    for key in ("family_merkle_root_sha256", "slot_order_sha256", "public_commitment_sha256"):
        value = spec.get(key)
        require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
                "public formal commitment binding missing")
    return digest(freeze)


class FormalRunner:
    """At-most-once coordinator; never uses expected answers to choose steps."""

    def __init__(self, *, state: Path, spec: Mapping[str, Any], freeze: Mapping[str, Any],
                 approval: Mapping[str, Any], model: FormalModel, native: FormalNative,
                 source_guard: Callable[[], None], budget_guard: Callable[[], None]):
        self.state = state
        self.spec, self.freeze, self.approval = spec, freeze, approval
        self.model, self.native = model, native
        self.source_guard, self.budget_guard = source_guard, budget_guard

    def _guard(self) -> None:
        self.source_guard()
        self.budget_guard()

    def _slot(self, slot: Mapping[str, str], case: Mapping[str, Any], freeze_sha: str,
              first_prompts: dict[str, str]) -> dict[str, Any]:
        slot_id, route, family_id = slot["slot_id"], slot["route"], slot["family_id"]
        task = model_view(case)
        task_sha = hashlib.sha256(task.encode()).hexdigest()
        claim_scope = {"stage": "formal", "task_sha256": task_sha, "route": route,
                       "owner_freeze_sha256": freeze_sha}
        claim_slot(self.state, digest(claim_scope), claim_scope)
        record = {"slot_id": slot_id, "family_id": family_id, "route": route,
                  "initial_native": None, "steps": [], "final_native": None,
                  "close": None, "stop": None, "error_type": None,
                  "independently_audited": False}
        opened = False
        try:
            self._guard()
            opened = True  # Opening may create a fixture before raising.
            self.native.open_slot(slot_id=slot_id, fixture_recipe=case["fixture_recipe"],
                                  task_sha256=task_sha, max_writes=case["max_writes"],
                                  max_reads=case["max_reads"], freeze_sha256=freeze_sha)
            initial = self.native.capture(slot_id)
            require(initial.get("status") == "captured", "actual initial Rhino capture missing")
            validate_fixture_readback(case, initial["native"])
            record["initial_native"] = initial["native"]
            initial_prompt = step_input(task, semantic(initial["native"]))
            if family_id in first_prompts:
                require(first_prompts[family_id] == initial_prompt,
                        "paired initial prompt differs; no second generation")
            else:
                first_prompts[family_id] = initial_prompt
            used_writes = used_reads = 0
            for step_index in range(case["max_steps"]):
                self._guard()
                before = self.native.capture(slot_id)
                require(before.get("status") == "captured", "actual pre-model capture missing")
                publish_json(self.state, slot_id + "-step-%d.claim.json" % step_index,
                             {"slot_id": slot_id, "step_index": step_index,
                              "scene_sha256": digest(before["native"]),
                              "runtime_freeze_sha256": freeze_sha, "replay_allowed": False})
                response = self.model.infer(slot_id=slot_id, route=route, step_index=step_index,
                                            task_text=task, scene=semantic(before["native"]),
                                            binding=before["state"], freeze_sha256=freeze_sha)
                observed = response.get("observation") if isinstance(response, Mapping) else None
                require(isinstance(observed, Mapping) and observed.get("repair_count") == 0
                        and observed.get("dispatch_count") == 0
                        and observed.get("scene_binding") == before["state"],
                        "strict scene-bound raw model observation required")
                receipts = response.get("generation_receipts")
                require(isinstance(receipts, list) and len(receipts) in (1, 2)
                        and [item.get("stage") for item in receipts] == ["selector", "invocation"][:len(receipts)],
                        "complete one-shot model stage receipts required")
                status = observed.get("status")
                require(status in {"schema_valid_not_authorized", "abstained_no_dispatch",
                    "unsupported_for_c5_no_dispatch", "selector_contract_failure_no_dispatch",
                    "invocation_contract_failure_no_dispatch", "operational_failure_no_retry"},
                    "unknown model contract status")
                require(status != "schema_valid_not_authorized" or len(receipts) == 2,
                        "structured call lacks two generation stages")
                require(status == "schema_valid_not_authorized" or len(receipts) == 1
                        or status in {"invocation_contract_failure_no_dispatch", "operational_failure_no_retry"},
                        "unexpected invocation stage after selector outcome")
                self._generation_stages += len(receipts)
                require(self._generation_stages <= self.spec["max_generation_stages"],
                        "frozen generation stage ceiling exceeded")
                after_model = self.native.capture(slot_id)
                require(after_model.get("status") == "captured" and after_model["state"] == before["state"]
                        and after_model["native"] == before["native"], "Rhino scene changed during model generation")
                step = {"step_index": step_index, "before": before, "response": response,
                        "observation": observed, "post_model_capture": after_model,
                        "receipt": None, "policy_denied": False}
                if status == "schema_valid_not_authorized":
                    name = observed.get("name")
                    require(isinstance(name, str), "structured name missing")
                    denied = (name in READS and used_reads >= case["max_reads"] or
                              name not in READS and used_writes >= case["max_writes"])
                    if denied:
                        step["policy_denied"] = True
                    else:
                        # Adapter MUST reparse unchanged raw outputs, consume
                        # permission before signing, and use native actual scene.
                        receipt = self.native.execute_observation(slot_id=slot_id, task_text=task,
                            response=response, before=before)
                        if receipt.get('status') == 'known_prepermission_rejection_no_dispatch':
                            require(receipt.get('permission_reserved') is False and receipt.get('native_dispatches') == 0,
                                'known rejection must precede all permission/dispatch')
                            step['execution_rejection'] = receipt
                            record['steps'].append(step)
                            publish_json(self.state, slot_id + '-step-%d.record.json' % step_index, step)
                            break  # Score a task failure; never retry its call.
                        require(isinstance(receipt, Mapping) and receipt.get("status") == "done"
                                and receipt.get("payload", {}).get("operation") == name
                                and receipt["payload"].get("arguments") == observed.get("arguments"),
                                "signed native result differs from raw model observation")
                        step["receipt"] = receipt
                        if name in READS: used_reads += 1
                        else: used_writes += 1
                record["steps"].append(step)
                publish_json(self.state, slot_id + "-step-%d.record.json" % step_index, step)
                if status == "operational_failure_no_retry":
                    raise FormalRunError("uncertain model operation; no further route")
                if status != "schema_valid_not_authorized" or step["policy_denied"]:
                    break
            final = self.native.capture(slot_id)
            require(final.get("status") == "captured", "actual final Rhino capture missing")
            record["final_native"] = final["native"]
        except BaseException as exc:
            record["error_type"] = type(exc).__name__
        finally:
            try: unresolved = self.native.unresolved(slot_id) if opened else True
            except BaseException: unresolved = True
            if opened and not unresolved:
                try:
                    close = self.native.close_slot(slot_id)
                    require(close.get("status") == "closed", "fixture closure unverified")
                    record["close"] = "closed"
                    stop = self.native.stop_slot(slot_id)
                    require(stop.get("status") == "stopped", "fixture stop unverified")
                    record["stop"] = "stopped"
                except BaseException as exc:
                    record["error_type"] = record["error_type"] or type(exc).__name__
            publish_json(self.state, slot_id + ".result.json", record)
        return record

    def run(self, load_cases_after_claim: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
        """One use. The private loader is called *only after* durable started."""
        freeze_sha = validate_authority(self.spec, self.freeze, self.approval)
        fd = private_directory(self.state)
        import os
        os.close(fd)
        self._guard()
        publish_json(self.state, "formal20.started.json", {"study_id": STUDY_ID,
                     "spec_sha256": digest(self.spec), "runtime_freeze_sha256": freeze_sha,
                     "public_commitment_sha256": self.spec["public_commitment_sha256"],
                     "replay_allowed": False})
        # No private cases, encrypted artifact or model session are touched
        # before this durable, non-overwritable consumption event.
        result = {"study_id": STUDY_ID, "status": "formal_incomplete_no_replay",
                  "slots_attempted": 0, "route_slots_required": 40,
                  "error_type": None, "c5_6_gate_claim": False}
        self._generation_stages = 0
        model_started = native_started = False
        try:
            cases = validate_families(load_cases_after_claim())
            require(family_merkle_root(cases) == self.spec["family_merkle_root_sha256"],
                    "private family commitment differs")
            order = slot_order(cases, seed=self.spec["slot_seed"])
            require(slot_order_sha256(order) == self.spec["slot_order_sha256"],
                    "frozen paired slot schedule differs")
            by_id = {case["family_id"]: case for case in cases}
            self._guard()
            model_plans = {slot["slot_id"]: {"route": slot["route"],
                "steps": [model_view(by_id[slot["family_id"]])] * by_id[slot["family_id"]]["max_steps"]}
                for slot in order}
            native_plans = {slot["slot_id"]: {"task_text": model_view(by_id[slot["family_id"]]),
                "fixture_recipe": by_id[slot["family_id"]]["fixture_recipe"],
                "max_writes": by_id[slot["family_id"]]["max_writes"],
                "max_reads": by_id[slot["family_id"]]["max_reads"]}
                for slot in order}
            # Only narrow execution plans cross adapter boundaries. Scorer
            # operations/assertions never reach either model or Rhino setup.
            self.model.prepare(model_plans, freeze_sha256=freeze_sha)
            native_started = True  # Partial key preparation also needs cleanup/reconciliation.
            self.native.prepare({"slot_order": order, "plans": native_plans}, freeze_sha256=freeze_sha)
            self.native.start()
            model_started = True  # Partial startup still requires bounded stop.
            self.model.start()
            first_prompts: dict[str, str] = {}
            for slot in order:
                self._guard()
                record = self._slot(slot, by_id[slot["family_id"]], freeze_sha, first_prompts)
                result["slots_attempted"] += 1
                if record["error_type"] or record["close"] != "closed" or record["stop"] != "stopped":
                    raise FormalRunError("slot uncertain/incomplete; no next slot or replay")
            require(result["slots_attempted"] == 40, "forty route slots incomplete")
            result["status"] = "formal_execution_complete_awaiting_independent_audit"
        except BaseException as exc:
            result["error_type"] = type(exc).__name__
        finally:
            if model_started:
                try: self.model.stop()
                except BaseException as exc:
                    result["error_type"] = result["error_type"] or type(exc).__name__
                    result["status"] = "formal_incomplete_no_replay"
            if native_started:
                try:
                    finished = self.native.finish()
                    require(finished.get("status") == "hub_stopped" and finished.get("had_failure") is False,
                            "native formal hub not cleanly stopped")
                except BaseException as exc:
                    result["error_type"] = result["error_type"] or type(exc).__name__
                    result["status"] = "formal_incomplete_no_replay"
            publish_json(self.state, "formal20.run-result.json", result)
        return result
