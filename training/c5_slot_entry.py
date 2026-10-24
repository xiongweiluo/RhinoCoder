"""Private owner execution only after separate exact execution approval.

Preparation never calls activate(), run_slot_package(), or a field actor.
"""

import json, time
from pathlib import Path
from plugin.rhino_listener.c5_research_native import require, digest
from plugin.rhino_listener.c5_research_channel import read_json, publish_json
from plugin.rhino_listener.c5_slot_protocol import (
    POLICY,
    validate_protocol,
    prework_decision,
)


def require_slot_startable(campaign, attempt):
    value = campaign.observation()
    require(
        value.get("slot_protocol")
        and value["slot_owner_consent"]
        and not value["active"]
        and value["formal_consumed"]
        and value["status"]
        in ("SLOT_PREPARED", "SLOT_RETRYABLE_PREWORK", "SLOT_RESUMABLE")
        and value["attempts"] in value["settled_attempts"]
        and attempt == value["attempts"] + 1 <= POLICY["global_loads_max"]
        and value["attempts"] - value["slot_package_start_attempt"]
        < POLICY["package_loads_max"],
        "slot_real_entry_startable",
    )
    require_remaining_window(value["package"], value)
    return value


def require_remaining_window(package, value, *, now=None):
    from training.c5_formal_run_budget import require_recovery_window

    p = validate_protocol(package["slot_protocol"])
    n = len(p["selected_indices"]) - len(value["slot_attempted_indices"])
    require(n > 0, "slot_no_unattempted_work")
    window = require_recovery_window(
        package,
        value,
        now=now,
        remaining_work_seconds=n * POLICY["slot_work_upper_seconds"],
    )
    require(
        POLICY["research_reservation_seconds_max"]
        - 66773.24127721786
        - value["charged_gpu_seconds"]
        >= window["required_seconds"],
        "slot_known_research_reservation_insufficient",
    )
    return window


def activate(spec, freeze, grant):
    from plugin.rhino_listener.c5_formal_reuse_scope import authority
    from training.c5_formal_reuse_revision import initial_scope, verify_endpoint
    from training.c5_formal_reuse_admission import (
        ROOTS,
        NAMESPACE,
        campaign_scope,
        formal_replay,
        FormalCampaign,
    )
    from training.c5_recovery_storage import EvidenceLog
    from training.c5_recovery_policy import POLICY as LEGACY
    from training.c5_reuse_evidence import sha

    authority(spec, freeze, grant)
    p = validate_protocol(spec["run_package"]["slot_protocol"])
    from plugin.rhino_listener.c5_slot_tail_policy import enabled as tail_enabled
    reference=spec['run_package'].get('tail_repair',{}).get('prior_review')
    prior_audit = (read_json(Path(reference['review_root']),reference['summary_name'])
        if tail_enabled(spec) else read_json(
            Path(spec["run_package"]["original_audit_root"]),
            "owner-public-partial-audit-summary.json"))
    prior_settlement = read_json(
        Path(spec["run_package"]["original_settlement_root"]),
        spec["run_package"]["original_settlement_name"],
    )
    if tail_enabled(spec):
        from training.c5_slot_tail_prior import check_review
        check_review(prior_audit,prior_settlement,reference)
        require(digest(prior_audit)==p['prior_audit_sha256']
            and digest(prior_settlement)==p['prior_settlement_sha256'],
            'slot_tail_plan_prior_review_binding')
    else:
        require(
            digest(prior_audit) == p["prior_audit_sha256"]
            and digest(prior_settlement) == p["prior_settlement_sha256"]
            and prior_audit["original_source_or_evidence_modified"] is False
            and prior_audit["qualified_gpu_audit"]["qualified_child_exited_reaped"]
            and prior_settlement["public_status"]["current_load_unsettled"] is False,
            "slot_original_audit_and_settlement_required",
        )
    log = EvidenceLog(
        ROOTS["mac"] / NAMESPACE / "ledger",
        initial_scope(spec, freeze),
        verify_endpoint("mac", freeze),
    )
    try:
        rows = log.rows()
        value = formal_replay(log.binding, rows)
        scope = campaign_scope(spec, freeze)
        if value["scope"] == scope:
            return {
                "status": "slot_rules_already_registered",
                "research_restarted": False,
            }
        require(
            rows == spec["run_package"]["prior_campaign_events"]
            and rows[-1]["record_sha256"] == p["prior_ledger_head_sha256"],
            "slot_activate_exact_original_prefix",
        )
        campaign = FormalCampaign(value["scope"], log)
        evidence = {
            "actor": "repository_owner",
            "approved": True,
            "protocol": LEGACY["protocol"],
            "scope_sha256": sha(scope),
            "spec_sha256": scope["spec_sha256"],
            "runtime_sha256": scope["runtime_sha256"],
            "policy_sha256": sha(LEGACY),
            "previous_campaign_head_sha256": rows[-1]["record_sha256"],
        }
        campaign._event(
            "slot_protocol_revision_accepted",
            {
                "scope": scope,
                "grant": evidence,
                "previous_head_sha256": rows[-1]["record_sha256"],
                "package": spec["run_package"],
                "original_audit_sha256": digest(prior_audit),
                "original_settlement_sha256": digest(prior_settlement),
            },
        )
        return {
            "status": "slot_rules_registered_no_execution_started",
            "research_restarted": False,
        }
    finally:
        log.close()


def _summary(spec, freeze, campaign, state, proof, status, *, error=None):
    value = campaign.observation()
    plan = spec["run_package"]["slot_protocol"]
    if proof is None and state.is_dir():
        from training.c5_slot_report import read_review

        snapshot = read_review(state, None, prefix="slot-audit")
        if snapshot is not None:
            from training.c5_reuse_evidence import sha

            require(
                snapshot["scope_sha256"] == sha(campaign.scope)
                and snapshot["attempt"] == value["attempts"],
                "slot_audit_snapshot_current_phase",
            )
            proof = snapshot["proof"]
    code = str(error) if error is not None else None
    if code is not None and not (
        code.startswith(("slot_", "formal_", "partial_", "run_package_"))
        and code.replace("_", "").isascii()
        and code.replace("_", "").isalnum()
    ):
        code = type(error).__name__
    result = {
        "schema_version": 1,
        "study_id": spec["study_id"],
        "package_id": spec["instance_id"],
        "kind": plan["kind"],
        "status": status,
        "spec_sha256": digest(spec),
        "runtime_sha256": digest(freeze),
        "attempts_consumed": value["attempts"],
        "first_load_epoch": value["first_load_epoch"],
        "gpu_charged_seconds": value["charged_gpu_seconds"],
        "fixed_denominator": 40,
        "first_evaluation": {
            "attempted": 7,
            "unattempted": 33,
            "complete": False,
            "original_result_unchanged": True,
            "original_audit_sha256": spec["run_package"].get("tail_repair",{}).get("prior_review",{}).get("first_audit_sha256",plan["prior_audit_sha256"]),
        },
        "continuation": {
            "attempted": (
                len(value["slot_attempted_indices"])
                if plan["kind"] == "interrupted_continuation"
                else 0
            ),
            "selected": (
                len(plan["selected_indices"])
                if plan["kind"] == "interrupted_continuation"
                else 0
            ),
            "uninterrupted_initial_run": False,
        },
        "engineering_regression": {
            "waves": plan["regression_wave"],
            "attempted": (
                len(value["slot_attempted_indices"])
                if plan["kind"] == "engineering_regression"
                else 0
            ),
            "changes_original_result": False,
        },
        "raw_audit_sha256": digest(proof) if proof else None,
        "full40_first_quality_result": None,
        "new_independent_blind_test": False,
        "c5_no_go_changed": False,
        "private_content_included": False,
        "execution_authority": False,
    }
    if spec['run_package'].get('tail_repair'):
        result['evidence_reuse_prior_tail']={
            'original_full_phase_gate_passed':False,
            'original_refusal_retained':'slot_final_exact_claim_population',
            'verified_raw_components_reused':32,
            'owner_review_sha256':spec['run_package']['tail_repair']['prior_review']['summary_sha256'],
            'historical_last_failed_slot_rewritten':False,
        }
    result["prior_phase_records"] = [
        {
            "kind": p["plan"]["kind"],
            "spec_sha256": p["scope"]["spec_sha256"],
            "runtime_sha256": p["scope"]["runtime_sha256"],
            "attempted_indices": p["attempted_indices"],
            "status": p["status"],
        }
        for p in value.get("slot_phase_history", [])
    ]
    result["global_ever_attempted_slot_count"] = len(
        value.get("slot_global_attempted_indices", range(7))
    )
    result.update(
        audit_status="verified_raw_components" if proof else "incomplete_unknown",
        audit_error_code=code,
        phase_statistics={
            "task_successes": proof.get("scored_task_successes") if proof else None,
            "task_failures": proof.get("task_failures") if proof else None,
            "recorded_results": proof.get("recorded_results") if proof else None,
        },
        evidence_reuse={
            "original_exit_and_partial_raw_audit": True,
            "original_first_result_unchanged": True,
        },
        unknowns=[
            "historical_total_gpu_usage_unknown",
            "original_full40_quality_unavailable",
            "physical_origin_not_cryptographically_proven",
        ]
        + ([] if proof else ["current_phase_raw_audit_incomplete"]),
    )
    if status == "SLOT_PAUSED_RECONCILIATION":
        result["unknowns"].append("failure_scope_or_resume_conditions_unconfirmed")
    result["campaign_head_sha256"] = campaign.log.rows()[-1]["record_sha256"]
    summary_root = (
        state
        if state.is_dir()
        else Path(spec["run_package"]["layout"]["mac_state_root"])
    )
    from training.c5_slot_report import publish_review

    publish_review(summary_root, result)
    return result


def _reconcile_slot_attempt(
    campaign, state, spec, freeze, guard, *, owner_resume_invocation, output
):
    from training.c5_formal_run_package import capture_owner_receipt, settle_known_load
    from training.c5_slot_audit import audit_phase, audit_prework
    from training.c5_slot_report import publish_review
    from training.c5_reuse_evidence import sha

    observed = campaign.observation()
    terminal = capture_owner_receipt(state, spec, freeze, output=output)
    if not (state / "formal20.started.json").exists():
        proof = audit_prework(state, spec, freeze, campaign, terminal, guard)
        failure = read_json(state, "formal-preexposure-failure.json")
        status = prework_decision(failure, proof, owner_resume=owner_resume_invocation)
        global_code = failure.get("global_fault", {}).get(
            "code", "permission_or_safety"
        )
    else:
        proof = audit_phase(state, spec, freeze, guard, terminal, campaign=campaign)
        result = read_json(state, "slot-phase-result.json")
        status = result["status"]
        global_code = (result.get("global_fault") or {}).get("code")
    publish_review(
        state,
        {
            "study_id": spec["study_id"],
            "campaign_head_sha256": campaign.log.rows()[-1]["record_sha256"],
            "scope_sha256": sha(campaign.scope),
            "attempt": observed["attempts"],
            "proof": proof,
            "owner_resume_invocation": owner_resume_invocation,
            "private_content_included": False,
        },
        prefix="slot-audit",
    )
    if observed["active"]:
        campaign._event(
            "slot_phase_finished",
            {
                "attempt": observed["attempts"],
                "status": status,
                "raw_anchor_sha256": digest(proof),
                "cleanup_proof_sha256": digest(proof),
            },
        )
    settle_known_load(campaign, state, digest(proof))
    observed = campaign.observation()
    if observed["status"] == "SLOT_PAUSED_RECONCILIATION":
        if status == "SLOT_STOPPED_GLOBAL":
            campaign._event(
                "slot_global_failure_reconciled",
                {
                    "raw_anchor_sha256": digest(proof),
                    "global_fault_code": global_code,
                },
            )
        elif (
            status == "SLOT_RETRYABLE_PREWORK"
            or proof.get("resume_unattempted_safe") is True
            or owner_resume_invocation
            and proof.get("owner_pause_resume_safe") is True
        ):
            campaign._event(
                "slot_cleanup_reconciled",
                {
                    "raw_anchor_sha256": digest(proof),
                    "cleanup_verified": True,
                    "evidence_chain_verified": True,
                    "shared_health_verified": True,
                    "permission_safe": True,
                    "source_unchanged": True,
                },
            )
    return proof


def run_slot_package(spec, freeze, grant, guard, *, output=print, input_fn=input):
    from plugin.rhino_listener.c5_formal_reuse_scope import attempt_state
    from training.c5_formal_reuse_admission import open_formal_campaign
    from tools.c5_formal_reuse_owner import run_interactive
    from training.c5_recovery_confirmation import input_status
    from training.c5_reuse_evidence import sha

    campaign = open_formal_campaign(spec, freeze, grant, freeze["history"])
    try:
        observed = campaign.observation()
        owner_resume_invocation = observed["status"] == "SLOT_PAUSED_RECONCILIATION"
        require(
            observed.get("slot_protocol") == spec["run_package"]["slot_protocol"],
            "slot_package_not_activated",
        )
        if not observed["slot_owner_consent"]:
            output(
                json.dumps(
                    {
                        "package_id": spec["instance_id"],
                        "spec_sha256": digest(spec),
                        "runtime_sha256": digest(freeze),
                        "rules": spec["run_package"]["policy"],
                        "plan": spec["run_package"]["slot_protocol"],
                        "private_input": "复用本人已保管的原封存题；无新解密或私下路径输入",
                        "custody": "一次确认；实际回执自动显示及保管",
                    },
                    ensure_ascii=False,
                )
            )
            confirmed = False
            for _ in range(3):
                try:
                    status, _ = input_status(
                        input_fn("输入“确认并保管”（取消则不加载、不消费）：")
                    )
                except (EOFError, KeyboardInterrupt):
                    return {"status": "SLOT_WAITING_OWNER", "attempt_consumed": False}
                if status == "confirmed":
                    confirmed = True
                    break
                if status == "cancelled":
                    return {"status": "SLOT_WAITING_OWNER", "attempt_consumed": False}
            if not confirmed:
                return {"status": "SLOT_WAITING_OWNER", "attempt_consumed": False}
            guard()
            campaign._event(
                "slot_owner_session_confirmed",
                {
                    "scope_sha256": sha(campaign.scope),
                    "automatic_receipt_capture": True,
                    "manual_host_ready_attestation": False,
                    "before_model_loading": True,
                },
            )
        while True:
            observed = campaign.observation()
            if observed["active"] or observed["status"] == "SLOT_PAUSED_RECONCILIATION":
                state = attempt_state("mac", observed["attempts"])
                proof = None
                try:
                    proof = _reconcile_slot_attempt(
                        campaign,
                        state,
                        spec,
                        freeze,
                        guard,
                        owner_resume_invocation=owner_resume_invocation,
                        output=output,
                    )
                except BaseException as error:
                    if campaign.observation()["active"]:
                        campaign._event(
                            "slot_phase_finished",
                            {
                                "attempt": observed["attempts"],
                                "status": "SLOT_PAUSED_RECONCILIATION",
                                "raw_anchor_sha256": digest(
                                    {"error_type": type(error).__name__}
                                ),
                                "cleanup_proof_sha256": None,
                            },
                        )
                    result = _summary(
                        spec,
                        freeze,
                        campaign,
                        state,
                        proof,
                        "SLOT_PAUSED_RECONCILIATION",
                        error=error,
                    )
                    output(json.dumps(result))
                    return result
            observed = campaign.observation()
            if observed["status"] in (
                "SLOT_PHASE_COMPLETE",
                "SLOT_STOPPED_GLOBAL",
                "SLOT_PAUSED_RECONCILIATION",
            ):
                return _summary(
                    spec,
                    freeze,
                    campaign,
                    attempt_state("mac", observed["attempts"]),
                    None,
                    observed["status"],
                )
            attempt = observed["attempts"] + 1
            try:
                if not observed["active"] and observed["status"] in (
                    "SLOT_PREPARED",
                    "SLOT_RETRYABLE_PREWORK",
                    "SLOT_RESUMABLE",
                ):
                    verify_prior_private_evidence(spec, freeze)
                require_slot_startable(campaign, attempt)
                guard()
            except BaseException as error:
                return _summary(
                    spec,
                    freeze,
                    campaign,
                    attempt_state("mac", max(1, observed["attempts"])),
                    None,
                    "SLOT_STOPPED_PRELOAD_CHECK",
                    error=error,
                )
            campaign.log.close()
            try:
                run_interactive(attempt, package_session={"confirmed": True})
            except BaseException:
                pass
            campaign = open_formal_campaign(spec, freeze, grant, freeze["history"])
            if campaign.observation()["attempts"] < attempt:
                return {
                    "status": "SLOT_PREPARATION_PAUSED",
                    "attempt_consumed": False,
                    "private_content_included": False,
                }
            # A fresh invocation permits an earlier owner pause to resume, but
            # it must never auto-resume a new Ctrl+C during this invocation.
            owner_resume_invocation = False
    finally:
        campaign.log.close()


def verify_prior_private_evidence(spec, freeze):
    # Owner-private actual entry only; public preparation/agent never calls this.
    from tools.c5_formal_reuse_partial_owner_audit import evidence_inventory

    summary = read_json(
        Path(spec["run_package"]["original_audit_root"]),
        "owner-public-partial-audit-summary.json",
    )
    from plugin.rhino_listener.c5_slot_tail_policy import enabled as tail_enabled
    reference=spec['run_package'].get('tail_repair',{}).get('prior_review')
    expected=(reference['first_audit_sha256'] if tail_enabled(spec)
        else spec['run_package']['slot_protocol']['prior_audit_sha256'])
    require(digest(summary)==expected,'slot_original_review_changed')
    prior = Path(spec["run_package"]["original_private_attempt_root"])
    require(
        digest(evidence_inventory(prior))
        == summary["original_evidence_inventory_sha256"],
        "slot_original_private_evidence_changed",
    )
    if tail_enabled(spec):
        from training.c5_slot_tail_prior import verify_prior_private
        latest=read_json(Path(reference['review_root']),reference['summary_name'])
        require(digest(latest)==reference['summary_sha256'],'slot_tail_prior_public_anchor')
        verify_prior_private(reference,latest)
    return True


def public_phase_summary(campaign, state):
    from training.c5_formal_run_package import public_status
    from training.c5_slot_report import read_review

    root = (
        state
        if state.is_dir()
        else Path(campaign.observation()["package"]["layout"]["mac_state_root"])
    )
    value = read_review(root, campaign.log.rows()[-1]["record_sha256"])
    return value if value is not None else public_status(campaign, state)
