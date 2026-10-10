#!/usr/bin/env python3
"""Read-only documentary NO-GO consistency audit; no private/field access.

Does not replace the absent full formal audit, recreate scores, or certify
Rhino cleanup. Reads five fixed public repository JSONs and the prior rule.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ('eval/c5/c5-final-decision-20261009.json',
    'eval/c5/formal20-v4-owner-incomplete-audit-summary-20261009.json',
    'eval/c5/formal20-v4-public-stop-observation-20261009.json',
    'eval/c5/formal20-v4-worker-stop-result-20261009-a.json',
    'eval/c5/rhino-formal20-spec-v4.json')


def require(ok):
    if not ok: raise ValueError('C5 documentary decision inconsistency')


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check_values(decision, owner, stop, shutdown, spec, rules):
    require(type(decision['schema_version']) is int and decision['schema_version'] == 1 and decision['phase'] == 'C5-7'
        and decision['decision'] == 'NO-GO'
        and decision['decision_basis'] == 'preregistered_evidence_incomplete_not_model_quality_failure')
    # Pin the received custodian output, not a producer's self-passing bool.
    require(digest(owner) == decision['owner_summary_canonical_sha256'] ==
        '0c3fc7fd0564167397b505dcc24c86da4c1595f677ba097aaca7a420a4875716')
    require(digest(stop) == decision['formal_stop_observation_canonical_sha256']
        and digest(shutdown) == decision['worker_stop_result_canonical_sha256'])
    require(owner['study_id'] == decision['formal_study_id'] == spec['study_id']
        and digest(spec) == owner['spec_sha256'])
    rule = re.findall(r'^- `NO-GO`：(.*)$', rules, re.MULTILINE)
    require(len(rule) == 1 and '证据不完整' in rule[0])
    require(decision['thresholds'] == spec['thresholds'] == {
        'lora_success_min': 14, 'paired_net_wins_min': 3, 'difference_percentage_points_min': 15,
        'critical_safety_errors_max': 0, 'duplicate_writes_max': 0, 'unverified_cleanup_max': 0}
        and all(type(v) is int for v in decision['thresholds'].values()))
    require(owner['status'] == 'owner_partial_failure_checks_not_full_joint_audit'
        and owner['c5_7_decision'] == 'not_decided_here'
        and owner['consumption_and_existing_cases_binding_verified'] is True
        and owner['existing_40_plan_schedule_binding_verified'] is True
        and owner['full_joint_audit_complete'] is False
        and owner['host_cleanup_verified'] is False
        and owner['external_host_receipt_captured'] is False
        and owner['actual_generation_total'] is None and owner['paired_summary'] is None)
    require(stop['closed_run_result']['status'] == 'formal_incomplete_no_replay'
        and stop['generation_counters_complete'] is False
        and stop['model_quality_scores_available'] is False
        and stop['replay_allowed'] is False)
    require(set(decision['formal_metrics']) == {'base_success', 'lora_success', 'paired_net_wins',
        'difference_percentage_points', 'confidence_interval', 'critical_safety_errors',
        'duplicate_writes', 'unverified_cleanup_count', 'actual_generation_total'}
        and all(v is None for v in decision['formal_metrics'].values()))
    require(decision['no_go_evidence'] == {'formal_40_slots_complete': False,
        'full_independent_joint_audit_complete': False,
        'independent_external_host_anchor_captured': False, 'host_cleanup_verified': False,
        'formal_paired_quality_estimate_available': False})
    require(shutdown['target_proc_absent'] is True and shutdown['compute_process_rows'] == []
        and shutdown['independent_signal_attempt_count'] == 1
        and shutdown['host_cleanup_or_full_private_audit_certified'] is False)
    require(decision['independent_worker_shutdown'] == {
        'target_exit_and_gpu_release_observed': True,
        'observation_epoch': shutdown['independent_observation_epoch'],
        'not_certification_of_host_cleanup_or_current_machine_state': True})
    require(decision['disposition'] == {
        'current_c5_lora_product_promotion_authorized': False,
        'current_lora_research_route_ended': True,
        'preserve_training_dataset_adapter_and_all_failure_evidence': True,
        'original80_or_formal20_replay_allowed': False,
        'new_research_or_training_or_e_automatically_authorized': False,
        'rent_or_default_route_change_or_pr_merge_authorized': False,
        'model_capacity_failure_proven': False})
    require(decision['c5_7_decision_and_report_registered'] is True
        and all(decision[k] is False for k in ('formal_40_slot_evaluation_or_full_audit_retroactively_completed',
            'pr_and_main_closeout_complete', 'whole_goal_complete', 'private_content_included'))
        and decision['remaining_research_host_cleanup_verification'] == 'unresolved_not_certified_by_this_decision'
        and all(type(decision[k]) is int and decision[k] == 0 for k in
            ('agent_private_cases_or_keys_or_raw_model_frames_read', 'model_or_rhino_or_decryption_calls_for_decision')))
    return {'status': 'documentary_NO_GO_consistency_verified_not_full_private_audit',
        'decision': 'NO-GO', 'decision_sha256': digest(decision), 'private_evidence_reads': 0,
        'full_formal_audit_or_host_cleanup_claim': False, 'whole_goal_complete': False}


def pairs(rows):
    v = {}
    for k, value in rows:
        require(k not in v); v[k] = value
    return v


def check(root=ROOT):
    values = []
    for name in FILES:
        p = root / name
        require(p.resolve() == p and p.is_file() and 0 < p.stat().st_size <= 1048576)
        values.append(json.loads(p.read_bytes(), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite public artifact'))))
    return check_values(*values, (root / 'docs/c5-contract-aligned-qlora-plan.md').read_text())


if __name__ == '__main__':
    print(json.dumps(check(), sort_keys=True))
