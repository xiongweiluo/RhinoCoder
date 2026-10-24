"""Prospective slot rules. Pure, Rhino 3.9 compatible; no field effects."""

import math
from .c5_research_native import digest, require

VERSION = 1
POLICY = {
    "version": 2,
    "study_id": "c5-rhino-paired-20-reuse-v1",
    "global_preexposure_loads_max": 5,
    "package_preexposure_loads_max": 3,
    "global_loads_max": 6,
    "package_loads_max": 3,
    "pause_resumes_max": 2,
    "regression_waves_max": 1,
    "regression_slots_max": 40,
    "private_exposures_max": 1,
    "gpu_residency_seconds_max": 129600,
    "research_reservation_seconds_max": 216000,
    "historical_cumulative_upper_bound_seconds": None,
    "original_16_hour_compliance_claimed": False,
    "export_reserve_seconds": 900,
    "startup_seconds": 600,
    "remaining_chain_upper_seconds": 52200,
    "slot_work_upper_seconds": 1500,
    "retry_requires_complete_raw_and_known_cleanup": True,
    "code_change_requires_new_exact_pair": True,
    "owner_private_entry_per_package": 1,
    "owner_confirmation_precedes_native_preparation": True,
    "manual_per_attempt_host_attestation": False,
    "actual_execution_separate_approval_required": True,
    "receipt_custody": "owner_authorized_automatic_capture_not_manual_per_receipt",
    "historical_clock_rewritten": False,
    "new_campaign_allowed": False,
    "unplanned_post_exposure_retry_allowed": False,
    "predeclared_engineering_regression_allowed": True,
    "continuation_of_unattempted_allowed": True,
    "quality_retry_allowed": False,
    "reviewer_2_required": False,
    "local_failure_continue_requires_raw_audit_and_fresh_shared_health": True,
    "interrupted_continuation_requires_explicit_frozen_plan": True,
    "regression_is_engineering_only": True,
    "first_results_immutable": True,
}
GLOBAL_CODES = {
    "permission_or_safety",
    "source_drift",
    "evidence_chain_damage",
    "shared_environment_pollution",
    "resource_window_insufficient",
}
LOCAL_CODES = {
    "model_task_failure",
    "invalid_model_output",
    "fixture_readback_rejected",
    "local_scene_anomaly",
}


def validate_protocol(p):
    require(
        type(p) is dict
        and set(p)
        == {
            "version",
            "kind",
            "selected_indices",
            "prior_attempted_indices",
            "prior_audit_sha256",
            "prior_settlement_sha256",
            "prior_ledger_head_sha256",
            "code_change_scope",
            "regression_wave",
            "original_result_immutable",
        }
        and p["version"] == VERSION,
        "slot_protocol_shape",
    )
    require(
        p["kind"] in ("initial", "interrupted_continuation", "engineering_regression")
        and p["original_result_immutable"] is True,
        "slot_protocol_result_kind",
    )
    for key in ("selected_indices", "prior_attempted_indices"):
        v = p[key]
        require(
            type(v) is list
            and v == sorted(set(v))
            and all(type(i) is int and 0 <= i < 40 for i in v),
            "slot_protocol_order_indices",
        )
    require(bool(p["selected_indices"]), "slot_protocol_empty_work")
    for key in (
        "prior_audit_sha256",
        "prior_settlement_sha256",
        "prior_ledger_head_sha256",
    ):
        require(
            type(p[key]) is str
            and len(p[key]) == 64
            and all(c in "0123456789abcdef" for c in p[key]),
            "slot_protocol_history_anchor",
        )
    require(
        p["code_change_scope"]
        in (
            "none",
            "slot_local",
            "shared_logic",
            "model",
            "prompt",
            "scoring",
            "fixture",
        )
        and type(p["regression_wave"]) is int,
        "slot_protocol_impact",
    )
    if p["kind"] == "initial":
        require(
            p["selected_indices"] == list(range(40))
            and not p["prior_attempted_indices"]
            and p["regression_wave"] == 0,
            "slot_protocol_initial_full_denominator",
        )
    elif p["kind"] == "interrupted_continuation":
        prior = p["prior_attempted_indices"]
        require(
            prior == list(range(len(prior)))
            and p["selected_indices"] == list(range(len(prior), 40))
            and p["regression_wave"] == 0,
            "slot_protocol_continuation_exact_suffix",
        )
    else:
        require(
            p["regression_wave"] == 1
            and len(p["selected_indices"]) <= POLICY["regression_slots_max"],
            "slot_protocol_finite_regression",
        )
        require(
            all((i ^ 1) in p["selected_indices"] for i in p["selected_indices"]),
            "slot_protocol_necessary_pair",
        )
        if p["code_change_scope"] in ("shared_logic", "model", "prompt", "scoring"):
            require(
                p["selected_indices"] == list(range(40)),
                "slot_protocol_shared_impact_full",
            )
    return p


def select_schedule(order, p, already_attempted=()):
    validate_protocol(p)
    require(
        type(order) is list
        and len(order) == 40
        and len({s["slot_id"] for s in order}) == 40,
        "slot_protocol_full_fixed_schedule",
    )
    require(digest(order) is not None, "slot_protocol_schedule")
    attempted = list(already_attempted)
    require(
        attempted == p["selected_indices"][: len(attempted)],
        "slot_protocol_attempted_prefix",
    )
    return [(i, order[i]) for i in p["selected_indices"][len(attempted) :]]


def decide(fault, proof):
    # No exception-message matching or producer cleanup booleans grant continuation.
    if fault and fault.get("scope") == "global" and fault.get("code") in GLOBAL_CODES:
        return "STOP_GLOBAL"
    if fault and (
        fault.get("scope") != "local" or fault.get("code") not in LOCAL_CODES
    ):
        return "PAUSED_RECONCILIATION"
    if (
        type(proof) is not dict
        or set(proof)
        != {
            "raw_slot_audit_verified",
            "cleanup_verified",
            "fresh_shared_health_verified",
            "source_unchanged",
            "evidence_chain_verified",
            "proof_sha256",
        }
        or not all(proof[k] is True for k in proof if k != "proof_sha256")
        or type(proof["proof_sha256"]) is not str
        or len(proof["proof_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in proof["proof_sha256"])
    ):
        return "PAUSED_RECONCILIATION"
    return "CONTINUE_FIXED_ORDER"


def impact_indices(indices, scope):
    require(
        scope
        in ("slot_local", "fixture", "shared_logic", "model", "prompt", "scoring"),
        "slot_protocol_impact_scope",
    )
    require(
        type(indices) is list
        and indices
        and all(type(i) is int and 0 <= i < 40 for i in indices),
        "slot_protocol_affected_indices",
    )
    return (
        list(range(40))
        if scope in ("shared_logic", "model", "prompt", "scoring")
        else sorted(set(indices) | {i ^ 1 for i in indices})
    )


PREWORK_ENGINEERING_CODES = {
    "formal_reuse_complete_frame_timeout",
    "formal_reuse_decoded_frame_timeout",
    "formal_reuse_ready_validation_timeout",
    "field_pipe_deadline",
}


def prework_decision(failure, proof, *, owner_resume=False):
    """Complete cleanup alone does not identify an unknown startup fault."""
    required = {
        "raw_anchor_sha256",
        "capture_complete",
        "qualified_target_absent",
        "known_native_cleanup_complete",
        "new_work_absent",
        "historical_private_exposure_preserved",
    }
    if (
        not isinstance(proof, dict)
        or set(proof) != required
        or not all(proof[k] is True for k in required - {"raw_anchor_sha256"})
    ):
        return "SLOT_PAUSED_RECONCILIATION"
    anchor = proof.get("raw_anchor_sha256")
    if (
        not isinstance(anchor, str)
        or len(anchor) != 64
        or any(c not in "0123456789abcdef" for c in anchor)
    ):
        return "SLOT_PAUSED_RECONCILIATION"
    fault = failure.get("global_fault", {})
    if (
        failure.get("error_type") == "PermissionError"
        or fault.get("scope") == "global"
        and fault.get("code") in GLOBAL_CODES
    ):
        return "SLOT_STOPPED_GLOBAL"
    if failure.get("error_type") == "KeyboardInterrupt":
        return (
            "SLOT_RETRYABLE_PREWORK" if owner_resume else "SLOT_PAUSED_RECONCILIATION"
        )
    if (
        failure.get("error_type")
        in ("TimeoutError", "BrokenPipeError", "ConnectionError", "EOFError")
        or failure.get("error_code") in PREWORK_ENGINEERING_CODES
    ):
        return "SLOT_RETRYABLE_PREWORK"
    return "SLOT_PAUSED_RECONCILIATION"
