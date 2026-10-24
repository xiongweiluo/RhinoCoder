"""Owner-only retrospective checks for a single bounded phase (no field I/O)."""

import tempfile, shutil, os, hashlib
from pathlib import Path
from plugin.rhino_listener.c5_research_native import require, digest
from plugin.rhino_listener.c5_research_channel import read_json
from training.c5_formal_reuse_partial_audit import (
    audit_partial_remote,
    partial_signatures,
)
from training.c5_formal_reuse_evidence_audit import (
    audit_supervisor,
    audit_residency_join,
    audit_resource,
)
from training.c5_host_assurance_audit import (
    audit_host_continuity,
    audit_request_checkpoint_bindings,
)
from training.c5_formal20_plan import (
    validate_families,
    slot_order,
    family_merkle_root,
    slot_order_sha256,
)
from plugin.rhino_listener.c5_slot_protocol import validate_protocol, decide
from training.c5_slot_runner import raw_slot_proof
from plugin.rhino_listener.c5_slot_tail_policy import enabled as tail_repair_enabled


def audit_prework(state, spec, freeze, campaign, terminal, guard):
    from training.c5_formal_reuse_failure_audit import audit_preexposure_failure

    guard()
    proof = audit_preexposure_failure(
        state,
        spec,
        freeze,
        campaign,
        terminal,
        package_recovery=True,
        slot_prework=True,
    )
    guard()
    return proof


class RecordedHealth:
    def __init__(self, state, freeze):
        self.state, self.freeze = state, freeze

    def shared_health(self, slot_id):
        found = []
        for path in self.state.glob("hub-request-*.json"):
            sent = read_json(self.state, path.name)
            body = sent["payload"]
            if body["action"] == "health" and body["slot_id"] == slot_id:
                response = read_json(
                    self.state, path.name.replace("request", "response")
                )
                bootstrap = read_json(self.state, "hub-bootstrap.json")
                require(
                    response
                    == {
                        "status": "slot_shared_health_verified",
                        "slot_id": slot_id,
                        "request_sha256": digest(sent),
                        "active_serial": bootstrap["active_serial"],
                        "active_sha256": bootstrap["active_sha256"],
                        "source_sha256": self.freeze["source_inventory_sha256"],
                        "previous_fixture_closed": True,
                        "previous_bridge_stopped": True,
                    },
                    "slot_final_recorded_health_binding",
                )
                found.append(response)
        require(len(found) == 1, "slot_final_unique_fresh_health")
        return found[0]


def _audit_phase(state, spec, freeze, guard, terminal):
    from training.c5_execution import load_config, load_pinned_tokenizer
    from training.c5_lifecycle_joint_audit import audit_native_timing
    from training.c5_lifecycle_timing_audit import audit_phase as check_time

    root = Path(__file__).resolve().parents[1]
    tokenizer = load_pinned_tokenizer(
        Path(freeze["tokenizer_dir"]),
        config=load_config(root / "eval/c5/c5-engineering-config.json"),
    )
    guard()
    p = validate_protocol(spec["run_package"]["slot_protocol"])
    cases = validate_families(read_json(state, "private-cases.json"))
    order = slot_order(cases, seed=spec["slot_seed"])
    require(
        family_merkle_root(cases) == spec["family_merkle_root_sha256"]
        and slot_order_sha256(order) == spec["slot_order_sha256"],
        "slot_final_original_commitment",
    )
    result = read_json(state, "slot-phase-result.json")
    indices = result["attempted_indices"]
    permit = read_json(state, "load-permit.json")
    remaining = permit["rows"][-1]["payload"]["remaining_indices"]
    require(
        indices == remaining[: len(indices)]
        and result["fixed_denominator"] == 40
        and result["kind"] == p["kind"]
        and result["first_result_overwritten"]
        is result["uninterrupted_initial_full40_claimed"]
        is result["new_blind_holdout_claimed"]
        is result["c5_no_go_changed"]
        is False,
        "slot_final_immutable_kind_prefix",
    )
    labels = [order[i]["slot_id"] for i in indices]
    engine_labels = [
        s for s in labels if (state / (s + ".engine-started.claim.json")).exists()
    ]
    require(engine_labels in (labels, labels[:-1]), "slot_final_engine_prefix")
    if engine_labels != labels:
        last = read_json(state, labels[-1] + ".result.json")
        require(
            last["initial_native"] is None
            and not last["steps"]
            and last["close"] is last["stop"] is None,
            "slot_final_preopen_failure_must_have_no_native_or_model_work",
        )
    require(
        {f.name for f in state.glob("F*.result.json")}
        == {s + ".result.json" for s in labels}
        and {f.name for f in state.glob("F*.engine-started.claim.json")}
        == {s + ".engine-started.claim.json" for s in engine_labels},
        "slot_final_exact_attempted_population",
    )
    host = audit_host_continuity(
        state,
        spec["study_id"],
        digest(freeze),
        freeze["source_inventory_sha256"],
        terminal["seal_sha256"],
        normal_limit=2048,
        cleanup_limit=256,
        journal_limit=4096,
    )
    bindings = audit_request_checkpoint_bindings(
        state, engine_labels, digest(freeze), journal_limit=4096
    )
    signatures = partial_signatures(state, freeze, order, cases, set(engine_labels))
    remote = audit_partial_remote(state, spec, freeze)
    supervisor = audit_supervisor(state, spec, freeze)
    residency = audit_residency_join(state, spec, freeze)
    by_id = {c["family_id"]: c for c in cases}
    keys = []
    outcomes = []
    failed_tail_proofs = {}
    claim_names = set()
    step_names = set()
    timings = [audit_native_timing(state, digest(freeze), hub=True)]
    for i, label in zip(indices, labels):
        slot = order[i]
        raw = read_json(state, label + ".result.json")
        scope = {
            "stage": "formal",
            "task_sha256": hashlib.sha256(
                by_id[slot["family_id"]]["task_text"].encode()
            ).hexdigest(),
            "route": slot["route"],
            "owner_freeze_sha256": digest(freeze),
        }
        name = digest(scope) + ".claim.json"
        claim_names.add(name)
        require(
            read_json(state, name)
            == {
                "version": 1,
                "slot_sha256": digest(scope),
                "scope": scope,
                "replay_allowed": False,
            },
            "slot_final_permanent_slot_claim",
        )
        if label in engine_labels:
            require(
                read_json(state, label + ".engine-started.claim.json")
                == {
                    "study_id": spec["study_id"],
                    "slot_id": label,
                    "runtime_freeze_sha256": digest(freeze),
                    "replay_allowed": False,
                },
                "slot_final_permanent_engine_claim",
            )
        outcome = read_json(state, "slot-outcome-%02d.json" % i)
        require(
            outcome["index"] == i
            and outcome["kind"] == p["kind"]
            and outcome["result_sha256"] == digest(raw),
            "slot_final_outcome_result_join",
        )
        proof = None
        score = None
        if outcome["proof"] is not None:
            proof, score = raw_slot_proof(
                state,
                by_id[slot["family_id"]],
                slot,
                raw,
                freeze,
                tokenizer,
                guard,
                RecordedHealth(state, freeze),
            )
            require(
                proof == outcome["proof"] and score == outcome["score"],
                "slot_final_independent_slot_recomputation",
            )
        if outcome["proof"] is None and tail_repair_enabled(spec):
            from training.c5_slot_tail_audit import audit_failed_native_ttl
            failed_tail_proofs[str(i)] = audit_failed_native_ttl(state, slot, by_id[slot["family_id"]], raw, freeze, tokenizer)
        require(
            decide(outcome["fault"], proof) == outcome["decision"],
            "slot_final_classification_recomputed",
        )
        if outcome["decision"] != "CONTINUE_FIXED_ORDER":
            require(i == indices[-1], "slot_final_no_continue_after_unknown_or_global")
        for step_index, step in enumerate(raw["steps"]):
            prefix = label + "-step-%d" % step_index
            step_names.add(prefix)
            require(
                read_json(state, prefix + ".claim.json")
                == {
                    "slot_id": label,
                    "step_index": step_index,
                    "scene_sha256": digest(step["before"]["native"]),
                    "runtime_freeze_sha256": digest(freeze),
                    "replay_allowed": False,
                },
                "slot_final_step_consumption",
            )
            require(
                read_json(state, prefix + ".record.json") == step,
                "slot_final_step_raw_binding",
            )
            key = digest({"slot": label, "step": step_index, "freeze": digest(freeze)})
            keys.append(key)
            check_time(
                read_json(state, key + "-model-time.json"),
                role="model",
                sequence=len(keys),
                freeze_sha=digest(freeze),
                request=read_json(state, key + "-model-request.json"),
                response=read_json(state, key + "-model-response.json"),
                cap=360,
            )
        if label in engine_labels:
            timings.append(audit_native_timing(state / label, digest(freeze)))
        outcomes.append(outcome)
    require(
        {p.name for p in state.glob("*.claim.json") if len(p.name) == 75} == claim_names
        and {p.name for p in state.glob("F*-step-*.claim.json")}
        == {n + ".claim.json" for n in step_names}
        and {p.name for p in state.glob("F*-step-*.record.json")}
        == {n + ".record.json" for n in step_names},
        "slot_final_exact_claim_population",
    )
    require(
        keys == remote["keys"] and digest(outcomes) == result["outcomes_sha256"],
        "slot_final_remote_and_outcome_population",
    )
    ready = read_json(state, "worker-startup-ready.json")
    check_time(
        read_json(state, "startup-time.json"),
        role="startup",
        sequence=0,
        freeze_sha=digest(freeze),
        request=None,
        response=ready,
        cap=600,
    )
    for seq in range(1, len(keys) + 3):
        prefix = "control-%04d-" % seq
        sent = read_json(state, prefix + "request.json")
        response = read_json(state, prefix + "response.json")
        expected = (
            read_json(state, "worker-bootstrap-request.json")
            if seq == 1
            else (
                {
                    "kind": "formal_stop",
                    "study_id": spec["study_id"],
                    "runtime_freeze_sha256": digest(freeze),
                }
                if seq == len(keys) + 2
                else {
                    "kind": "formal_export_step",
                    "study_id": spec["study_id"],
                    "runtime_freeze_sha256": digest(freeze),
                    "key": keys[seq - 2],
                }
            )
        )
        require(sent == expected, "slot_final_control_population")
        check_time(
            read_json(state, prefix + "time.json"),
            role="formal-control",
            sequence=seq,
            freeze_sha=digest(freeze),
            request=sent,
            response=response,
            cap=360,
        )
    stop = read_json(state, "hub-stop.json")
    require(
        stop["opened_slots"] == engine_labels
        and stop["had_failure"] is False
        and stop["hook_removed_in_same_callback"] is True
        and set(stop["unused_keys_removed"])
        == {s["slot_id"] for s in order if s["slot_id"] not in engine_labels},
        "slot_final_hub_cleanup_population",
    )
    require(
        read_json(state, "worker-bootstrap-request.json")["slot_order"] == order,
        "slot_final_worker_schedule_bound",
    )
    guard()
    return {
        "schema_version": 1,
        "kind": p["kind"],
        "status": "slot_phase_raw_joint_components_verified",
        "attempted_indices": indices,
        "recorded_results": len(indices),
        "scored_task_successes": sum(
            bool(o["score"] and o["score"].get("outcome_correct")) for o in outcomes
        ),
        "task_failures": sum(
            bool(o["score"] is not None and not o["score"].get("outcome_correct"))
            for o in outcomes
        ),
        "full40_first_result_unchanged": True,
        "fixed_denominator": 40,
        "quality_result_is_engineering_only": True,
        "raw_requests": len(keys),
        "generation_stages": remote["generation_stages"],
        "host": host,
        "host_bindings": bindings,
        "signatures": signatures,
        "qualified_gpu": supervisor,
        "residency": residency,
        "raw_native_timing": timings,
        "prospective_failed_tail_proofs": failed_tail_proofs,
        "owner_pause": bool(
            result.get("global_fault")
            and result["global_fault"].get("scope") == "owner_pause"
        ),
        "owner_pause_resume_safe": result["status"] == "SLOT_PAUSED_RECONCILIATION"
        and not result["cleanup_errors"]
        and bool(
            result.get("global_fault")
            and result["global_fault"].get("scope") == "owner_pause"
        )
        and all(o["proof"] is not None for o in outcomes),
        "resume_unattempted_safe": result["status"] == "SLOT_PAUSED_RECONCILIATION"
        and not result["cleanup_errors"]
        and not (
            result.get("global_fault")
            and result["global_fault"].get("scope") == "owner_pause"
        )
        and all(o["proof"] is not None or str(o["index"]) in failed_tail_proofs
            and o["fault"]=={"scope":"unknown","code":"unclassified_exception"}
            for o in outcomes),
        "paired_summary": None,
        "new_blind_holdout_claimed": False,
        "original_c5_no_go_changed": False,
        "private_content_included": False,
        "research_restarted_by_audit": False,
    }


def audit_phase(state, spec, freeze, guard, terminal, *, campaign):
    # Same original-preservation wrapper as the completed attempt3 read-only audit.
    from tools.c5_formal_reuse_partial_owner_audit import (
        copy_evidence,
        evidence_inventory,
    )

    from plugin.rhino_listener.c5_slot_tail_policy import enabled
    if enabled(spec):
        from training.c5_slot_tail_storage import copy_evidence, evidence_inventory
    with tempfile.TemporaryDirectory(prefix="phase-audit-") as name:
        copied = Path(name).resolve() / state.name
        before = copy_evidence(state, copied)
        result = _audit_phase(copied, spec, freeze, guard, terminal)
        require(
            evidence_inventory(state) == before, "slot_final_original_evidence_changed"
        )
    audit_campaign_join(state, spec, freeze, campaign, result)
    return result


def audit_campaign_join(state, spec, freeze, campaign, result):
    value = campaign.observation()
    rows = campaign.log.rows()
    permit = read_json(state, "load-permit.json")
    require(
        rows[: len(permit["rows"])] == permit["rows"]
        and value["scope"] == permit["scope"]
        and value["formal_consumed"]
        and value["first_load_epoch"] == permit["first_load_epoch"],
        "slot_final_original_campaign_and_first_clock",
    )
    require(
        sum(r["kind"] == "private_exposure_intent" for r in rows) == 1,
        "slot_final_no_second_private_exposure",
    )
    tail = rows[len(permit["rows"]) :]
    events = [r["payload"] for r in tail if r["kind"] == "slot_attempt_recorded"]
    require(
        [p["index"] for p in events] == result["attempted_indices"],
        "slot_final_same_phase_global_consumption",
    )
    for event in events:
        outcome = read_json(state, "slot-outcome-%02d.json" % event["index"])
        proof = outcome["proof"]
        expected = (
            proof["proof_sha256"]
            if proof
            else digest({"unverified": True, "result_sha256": outcome["result_sha256"]})
        )
        require(
            event
            == {
                "index": outcome["index"],
                "result_sha256": outcome["result_sha256"],
                "decision": outcome["decision"],
                "proof_sha256": expected,
            },
            "slot_final_consumption_result_proof_join",
        )
    return {
        "global_consumption_prefix_verified": True,
        "initial_private_exposures": 1,
        "historical_first_clock_preserved": True,
    }
