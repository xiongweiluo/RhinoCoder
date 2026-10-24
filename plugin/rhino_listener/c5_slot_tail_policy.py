"""Prospective signed tail-repair policy. No approvals or actors."""
from .c5_research_native import require, digest

POLICY = {
    "version": 1,
    "handoff_ttl_seconds": 120,
    "public_load_permit_bytes_max": 786432,
    "evidence_total_bytes_max": 1073741824,
    "evidence_file_bytes_max": 33554432,
    "evidence_files_max": 20000,
    "native_ttl_ceiling_seconds": 300,
    "minimum_signature_remaining_seconds": 30,
    "live_readbacks_before_ttl_creation": True,
    "consumed_permission_renewal_allowed": False,
    "failed_claim_terminal_record_required": True,
    "primary_and_cleanup_errors_separate": True,
    "acknowledged_stop_not_erased_by_business_failure": True,
    "unknown_cleanup_never_clears_current": True,
    "known_ttl_resume_requires_full_raw_phase_and_cleanup": True,
    "resume_only_unattempted_slots": True,
    "historical_results_or_refusals_rewritten": False,
    "model_prompt_scorer_or_data_changed": False,
}


def enabled(spec):
    value=spec.get('run_package',{}).get('tail_repair')
    if value is None:return False
    require(type(value) is dict and type(value.get('version')) is int
        and value['version']==1 and digest(value.get('policy'))==digest(POLICY),
        'slot_tail_repair_policy_binding')
    return True
