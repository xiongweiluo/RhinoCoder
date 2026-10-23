"""Fixed schedule coordinator with per-slot raw proof before continuation."""

import os, time
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_research_channel import (
    publish_json,
    read_json,
    private_directory,
)
from plugin.rhino_listener.c5_slot_protocol import (
    validate_protocol,
    select_schedule,
    decide,
)
from training.c5_formal_reuse_runner import FormalRunner, validate_authority
from training.c5_formal20_plan import (
    validate_families,
    family_merkle_root,
    slot_order,
    slot_order_sha256,
    model_view,
)


class GlobalFault(RuntimeError):
    slot_scope = "global"

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def raw_slot_proof(state, case, slot, result, freeze, tokenizer, source_guard, native):
    # Original raw validators read their SQLite snapshot; retain a disposable copy
    # so even read-only SQLite sidecars cannot mutate the producer record.
    import tempfile, shutil
    from training.c5_formal_reuse_joint_audit_base import audit_slot
    from training.c5_formal_reuse_partial_audit import failed_pre_model_slot
    from training.c5_formal_reuse_partial_audit import partial_signatures
    from training.c5_lifecycle_joint_audit import audit_native_timing

    source_guard()
    with tempfile.TemporaryDirectory(prefix="slot-audit-") as name:
        copy = __import__("pathlib").Path(name).resolve() / "evidence"
        copy.mkdir(mode=0o700)
        # Copy only public-to-owner evidence for THIS attempted slot, never other cases.
        for p in state.iterdir():
            if p.is_file() and (
                p.name.startswith(slot["slot_id"])
                or p.name.endswith(
                    (
                        "-model-request.json",
                        "-model-response.json",
                        "-remote-evidence.json",
                    )
                )
            ):
                shutil.copy2(p, copy / p.name)
        shutil.copytree(state / slot["slot_id"], copy / slot["slot_id"])
        if result.get("fault", {}).get("code") == "fixture_readback_rejected":
            proof = failed_pre_model_slot(copy, case, slot, result, freeze, tokenizer)
            require(
                proof["initial_fixture_validation_rejection_reproduced"],
                "slot_fixture_local_failure_must_reproduce",
            )
            score = {
                "outcome_correct": False,
                "reason": "initial_fixture_readback_rejected",
            }
        else:
            proof, chain = audit_slot(copy, case, slot, result, freeze, tokenizer)
            from training.c5_formal20_scorer import score_route

            score = score_route(case, result, proof)
        exports = []
        for i, step in enumerate(result["steps"]):
            from training.c5_slot_worker import audit_exported_step

            exports.append(audit_exported_step(copy, slot["slot_id"], i, freeze))
        timing = audit_native_timing(copy / slot["slot_id"], digest(freeze))
    # Per-slot HMAC control/execute requests, exact population, no unknown dispatch.
    from plugin.rhino_listener.c5_research_gate import signature
    import hmac

    directory = state / slot["slot_id"]
    key = bytes.fromhex(
        read_json(state / "audit-key-custody", slot["slot_id"] + ".json")["key_hex"]
    )
    requests = sorted(directory.glob("request-*.json"))
    for path in requests:
        envelope = read_json(directory, path.name)["envelope"]
        require(
            hmac.compare_digest(
                envelope["signature"], signature(key, envelope["payload"])
            ),
            "slot_original_hmac_changed",
        )
    health = native.shared_health(slot["slot_id"])
    source_guard()
    anchor = digest(
        {
            "result": result,
            "raw": proof,
            "remote_exports": exports,
            "timing": timing,
            "health": health,
            "request_sha256": [
                __import__("hashlib").sha256(p.read_bytes()).hexdigest()
                for p in requests
            ],
        }
    )
    return {
        "raw_slot_audit_verified": True,
        "cleanup_verified": True,
        "fresh_shared_health_verified": True,
        "source_unchanged": True,
        "evidence_chain_verified": True,
        "proof_sha256": anchor,
    }, score


class SlotRunner(FormalRunner):
    def __init__(self, *args, campaign, tokenizer, proof_fn=raw_slot_proof, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign = campaign
        self.tokenizer = tokenizer
        self.proof_fn = proof_fn

    def _prior_prompts(self, order, by_id):
        from training.c5_rhino_adapter import step_input
        from training.c5_modelbridge_joint_audit import semantic

        prompts = {}
        plan = self.spec["run_package"]["slot_protocol"]
        observed = self.campaign.observation()
        records = []
        if (
            plan["kind"] == "interrupted_continuation"
            and "original_private_attempt_root" in self.spec["run_package"]
        ):
            root = __import__("pathlib").Path(
                self.spec["run_package"]["original_private_attempt_root"]
            )
            records.extend(
                (order[i], read_json(root, order[i]["slot_id"] + ".result.json"))
                for i in range(7)
            )
        if plan["kind"] == "interrupted_continuation":
            for index, anchor in observed.get("slot_first_attempt_records", {}).items():
                slot = order[int(index)]
                parent = __import__("pathlib").Path(anchor["state_root"]) / (
                    "preload-" + str(anchor["attempt"])
                )
                value = read_json(parent, slot["slot_id"] + ".result.json")
                require(
                    digest(value) == anchor["result_sha256"],
                    "slot_global_first_result_bytes_changed",
                )
                records.append((slot, value))
        if plan["kind"] == "engineering_regression" and observed.get("slot_results"):
            for row in observed["slot_results"]:
                slot = order[row["index"]]
                matches = []
                for n in range(
                    observed["slot_package_start_attempt"] + 1, observed["attempts"]
                ):
                    parent = self.state.parent / ("preload-" + str(n))
                    if (parent / (slot["slot_id"] + ".result.json")).exists():
                        value = read_json(parent, slot["slot_id"] + ".result.json")
                        require(
                            digest(value) == row["result_sha256"],
                            "slot_prior_phase_result_changed",
                        )
                        matches.append(value)
                require(len(matches) == 1, "slot_prior_phase_result_population")
                records.append((slot, matches[0]))
        for slot, record in records:
            if record["initial_native"] is None:
                continue
            prompt = step_input(
                model_view(by_id[slot["family_id"]]), semantic(record["initial_native"])
            )
            if slot["family_id"] in prompts:
                require(
                    prompts[slot["family_id"]] == prompt,
                    "slot_prior_paired_prompt_changed",
                )
            prompts[slot["family_id"]] = prompt
        return prompts

    def run(self, load_cases_after_claim):
        freeze_sha = validate_authority(self.spec, self.freeze, self.approval)
        plan = validate_protocol(self.spec["run_package"]["slot_protocol"])
        os.close(private_directory(self.state))
        self._guard()
        publish_json(
            self.state,
            "formal20.started.json",
            {
                "study_id": self.spec["study_id"],
                "spec_sha256": digest(self.spec),
                "runtime_freeze_sha256": freeze_sha,
                "public_commitment_sha256": self.spec["public_commitment_sha256"],
                "replay_allowed": False,
            },
        )
        self._generation_stages = 0
        attempted = []
        scores = []
        schedule = []
        decision = "CONTINUE_FIXED_ORDER"
        fault = None
        model_started = native_started = False
        cleanup = []
        try:
            cases = validate_families(load_cases_after_claim())
            require(
                family_merkle_root(cases) == self.spec["family_merkle_root_sha256"],
                "slot_original_case_commitment",
            )
            order = slot_order(cases, seed=self.spec["slot_seed"])
            require(
                slot_order_sha256(order) == self.spec["slot_order_sha256"],
                "slot_original_order_commitment",
            )
            by_id = {c["family_id"]: c for c in cases}
            observation = self.campaign.observation()
            schedule = select_schedule(
                order, plan, observation["slot_attempted_indices"]
            )
            self._guard()
            self.model.prepare(
                {
                    s["slot_id"]: {
                        "route": s["route"],
                        "steps": [model_view(by_id[s["family_id"]])]
                        * by_id[s["family_id"]]["max_steps"],
                    }
                    for s in order
                },
                freeze_sha256=freeze_sha,
            )
            native_started = True
            self.native.prepare(
                {
                    "slot_order": order,
                    "plans": {
                        s["slot_id"]: {
                            "task_text": model_view(by_id[s["family_id"]]),
                            "fixture_recipe": by_id[s["family_id"]]["fixture_recipe"],
                            "max_writes": by_id[s["family_id"]]["max_writes"],
                            "max_reads": by_id[s["family_id"]]["max_reads"],
                        }
                        for s in order
                    },
                },
                freeze_sha256=freeze_sha,
            )
            self.native.start()
            model_started = True
            self.model.start()
            prompts = self._prior_prompts(order, by_id)
            for position, (index, slot) in enumerate(schedule):
                self._guard()
                policy = self.spec["run_package"].get("policy")
                if policy is not None:
                    try:
                        remaining = self.budget_guard()
                    except BaseException as error:
                        raise GlobalFault("resource_window_insufficient") from error
                    if (
                        remaining
                        < (len(schedule) - position) * policy["slot_work_upper_seconds"]
                    ):
                        raise GlobalFault("resource_window_insufficient")
                case = by_id[slot["family_id"]]
                record = self._slot(slot, case, freeze_sha, prompts)
                attempted.append(index)
                fault = record.get("fault")
                proof = None
                score = None
                if (
                    record["close"] == "closed"
                    and record["stop"] == "stopped"
                    and (
                        record["error_type"] is None
                        or fault
                        and fault["scope"] == "local"
                    )
                ):
                    try:
                        self.model.export_completed_slot(slot["slot_id"])
                        proof, score = self.proof_fn(
                            self.state,
                            case,
                            slot,
                            record,
                            self.freeze,
                            self.tokenizer,
                            self.source_guard,
                            self.native,
                        )
                    except BaseException as error:
                        # Preserve known stop/cancel semantics even when they
                        # arrive during export or the fresh shared-health proof.
                        # The slot remains consumed; never replay it on recovery.
                        if isinstance(error, KeyboardInterrupt):
                            fault = {"scope": "owner_pause", "code": "owner_cancelled"}
                        elif isinstance(error, PermissionError):
                            fault = {"scope": "global", "code": "permission_or_safety"}
                        elif getattr(error, "slot_scope", None) == "global":
                            fault = {"scope": "global", "code": error.code}
                        else:
                            fault = {
                                "scope": "unknown",
                                "code": "raw_audit_or_shared_health_unconfirmed",
                            }
                decision = decide(fault, proof)
                payload = {
                    "index": index,
                    "result_sha256": digest(record),
                    "decision": decision,
                    "proof_sha256": (
                        proof["proof_sha256"]
                        if proof
                        else digest(
                            {"unverified": True, "result_sha256": digest(record)}
                        )
                    ),
                }
                self.campaign._event("slot_attempt_recorded", payload)
                outcome = {
                    "index": index,
                    "kind": plan["kind"],
                    "result_sha256": digest(record),
                    "proof": proof,
                    "score": score,
                    "decision": decision,
                    "fault": fault,
                }
                publish_json(self.state, "slot-outcome-%02d.json" % index, outcome)
                scores.append(outcome)
                publish_json(
                    self.state,
                    "slot-public-progress-%02d.json" % index,
                    {
                        "study_id": self.spec["study_id"],
                        "phase": plan["kind"],
                        "attempted_count": len(attempted),
                        "fixed_denominator": 40,
                        "decision": decision,
                        "confirmed_generation_stages": self._generation_stages,
                        "private_content_included": False,
                    },
                )
                if decision != "CONTINUE_FIXED_ORDER":
                    break
        except BaseException as error:
            fault = {
                "scope": (
                    "owner_pause"
                    if isinstance(error, KeyboardInterrupt)
                    else getattr(error, "slot_scope", "unknown")
                ),
                "code": (
                    "owner_cancelled"
                    if isinstance(error, KeyboardInterrupt)
                    else getattr(error, "code", "unclassified_phase_exception")
                ),
            }
            decision = decide(fault, None)
        finally:
            if model_started:
                try:
                    self.model.stop()
                except BaseException as error:
                    cleanup.append(
                        {"role": "model", "error_type": type(error).__name__}
                    )
            if native_started:
                try:
                    finished = self.native.finish()
                    require(
                        finished.get("status") == "hub_stopped"
                        and finished.get("had_failure") is False,
                        "slot_phase_native_cleanup",
                    )
                except BaseException as error:
                    cleanup.append(
                        {"role": "native", "error_type": type(error).__name__}
                    )
        if cleanup:
            decision = "PAUSED_RECONCILIATION"
        complete = decision == "CONTINUE_FIXED_ORDER" and len(attempted) == len(
            schedule
        )
        status = (
            "SLOT_PHASE_COMPLETE"
            if complete
            else (
                "SLOT_STOPPED_GLOBAL"
                if decision == "STOP_GLOBAL"
                else "SLOT_PAUSED_RECONCILIATION"
            )
        )
        result = {
            "schema_version": 1,
            "study_id": self.spec["study_id"],
            "kind": plan["kind"],
            "status": status,
            "attempted_indices": attempted,
            "fixed_denominator": 40,
            "generation_stages": self._generation_stages,
            "cleanup_errors": cleanup,
            "global_fault": fault if decision != "CONTINUE_FIXED_ORDER" else None,
            "first_result_overwritten": False,
            "uninterrupted_initial_full40_claimed": False,
            "new_blind_holdout_claimed": False,
            "c5_no_go_changed": False,
            "outcomes_sha256": digest(scores),
        }
        publish_json(self.state, "slot-phase-result.json", result)
        return result
