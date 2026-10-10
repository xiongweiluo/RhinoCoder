#!/usr/bin/env python3
"""Fixed public preparation JSONs only. Never a runner, freezer or grant maker."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'eval/c5/formal20-reuse-preparation-draft-20261011.json',
    'eval/c5/rhino-formal20-public-commitment-v1.json',
    'eval/c5/rhino-formal20-spec-v4.json',
    'eval/c5/formal20-v4-owner-incomplete-audit-summary-20261009.json',
    'eval/c5/c5-final-decision-20261009.json',
)


def require(ok):
    if not ok:
        raise ValueError('public reuse preparation draft inconsistent')


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected.split()))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def parse_public(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: require(False))


def load_public(path):
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= 1048576)
    return parse_public(path.read_bytes())


def check_values(d, commitment, spec, owner, decision):
    keys(d, 'schema_version status proposal_id candidate_study_id parent_study_id '
        'source_baseline_commit owner_data_reuse_decision dataset comparison thresholds history resources freeze authority')
    require(type(d['schema_version']) is int and d['schema_version'] == 1
        and d['status'] == 'DRAFT_PREPARATION_ONLY_NOT_EXECUTION_FREEZE'
        and d['proposal_id'] == 'C5FORMAL20-REUSE-AMENDMENT-20261011-DRAFT1'
        and d['candidate_study_id'] == 'c5-rhino-paired-20-reuse-v1'
        and d['parent_study_id'] == commitment['study_id'] == spec['study_id'] == owner['study_id']
        == decision['formal_study_id'] == 'c5-rhino-paired-20-v1'
        and d['source_baseline_commit'] == '9d20bd70fb0367da9346f11e83bd78d347f443b8')
    a = d['owner_data_reuse_decision']
    keys(a, 'actor received basis statements prior_actual_generation_total development_exposure_independently_verified')
    require(a['actor'] == 'repository_owner' and a['received'] is True
        and a['basis'] == 'direct_human_statement_not_independent_private_log_audit'
        and a['statements'] == ['可明确确定可复用原20题', '可复用']
        and a['prior_actual_generation_total'] is None
        and a['development_exposure_independently_verified'] is None)
    data = d['dataset']
    keys(data, 'public_commitment_sha256 family_merkle_root_sha256 family_count route_slots slot_seed '
        'slot_order_sha256 original80_reuse_allowed task_replacement_allowed new_independent_holdout_claimed label')
    require(digest(commitment) == data['public_commitment_sha256'] == spec['public_commitment_sha256']
        == '41c92c723df663782000a4e34934a371a2a552e5ef27d6052b7c6d07656ebaf4')
    for key, value in (('family_count', 20), ('route_slots', 40), ('slot_seed', 20261003)):
        require(type(data[key]) is int and data[key] == commitment[key] == spec[key] == value)
    for key in ('family_merkle_root_sha256', 'slot_order_sha256'):
        require(data[key] == commitment[key] == spec[key])
    require(data['label'] == 'disclosed_same_sealed_set_reuse'
        and all(data[k] is False for k in
            ('original80_reuse_allowed', 'task_replacement_allowed', 'new_independent_holdout_claimed')))
    c = d['comparison']
    keys(c, 'base_revision adapter_sha256 checkpoint contract_id training_allowed parse_repair_allowed')
    require(c['base_revision'] == spec['base_revision']
        and c['adapter_sha256'] == spec['adapter_sha256']
        and c['contract_id'] == spec['contract_id']
        and c['checkpoint'] == spec['selected_checkpoint'] == 'checkpoint-132'
        and c['training_allowed'] is False and c['parse_repair_allowed'] is False)
    require(d['thresholds'] == spec['thresholds'] == decision['thresholds']
        and all(type(v) is int for v in d['thresholds'].values()))
    h = d['history']
    keys(h, 'parent_spec_sha256 parent_runtime_sha256 parent_owner_summary_sha256 '
        'parent_decision_sha256 parent_decision parent_claim_reset_allowed parent_entry_replay_allowed parent_result_rewrite_allowed')
    require(h['parent_spec_sha256'] == digest(spec) == owner['spec_sha256']
        == '1ce7dba2a75a853a6a2b8d81027235c442586f30718f05dc177f64a04b002fa7'
        and h['parent_runtime_sha256'] == owner['runtime_freeze_sha256']
        == '9f72a0491b49bbb5f21dd83e6c87bb16530218a375593e0308e69caee134f1a3'
        and h['parent_owner_summary_sha256'] == digest(owner)
        == '0c3fc7fd0564167397b505dcc24c86da4c1595f677ba097aaca7a420a4875716'
        and h['parent_decision_sha256'] == digest(decision)
        == '09392d883ca147c547e292384837cefe2dc84b10b1fcd9c9423da84e2725ec19'
        and h['parent_decision'] == decision['decision'] == 'NO-GO'
        and all(h[k] is False for k in
            ('parent_claim_reset_allowed', 'parent_entry_replay_allowed', 'parent_result_rewrite_allowed')))
    r = d['resources']
    keys(r, 'status lease_expiry_epoch generation_cutoff_epoch prior_cumulative_upper_bound_seconds '
        'approved_remaining_gpu_seconds export_reserve_seconds_min proposed_limits_seconds '
        'old_lease_or_prior_ledger_reused_as_current_authority rental_or_payment_authorized')
    require(r['status'] == 'UNSET_PROPOSAL_NOT_AUTHORITY'
        and all(r[k] is None for k in ('lease_expiry_epoch', 'generation_cutoff_epoch',
            'prior_cumulative_upper_bound_seconds', 'approved_remaining_gpu_seconds'))
        and type(r['export_reserve_seconds_min']) is int and r['export_reserve_seconds_min'] == 900
        and r['old_lease_or_prior_ledger_reused_as_current_authority'] is False
        and r['rental_or_payment_authorized'] is False
        and r['proposed_limits_seconds'] == {'development': 3600, 'formal': 18000,
            'new_research_total': 21600, 'original_cumulative': 57600}
        and all(type(v) is int for v in r['proposed_limits_seconds'].values()))
    f = d['freeze']
    keys(f, 'status spec_sha256 runtime_sha256 new_host_preparation_accepted resource_boundary_accepted '
        'live_development_exact_approval_received live_development_raw_audit_passed formal_exact_approval_received')
    require(f['status'] == 'NOT_FROZEN' and f['spec_sha256'] is None and f['runtime_sha256'] is None
        and all(f[k] is False for k in ('new_host_preparation_accepted', 'resource_boundary_accepted',
            'live_development_exact_approval_received', 'live_development_raw_audit_passed', 'formal_exact_approval_received')))
    auth = d['authority']
    keys(auth, 'execution_ready model_or_rhino_calls_authorized private_data_or_decryption_access_authorized '
        'new_run_or_claim_creation_authorized default_route_change_authorized pr_merge_authorized automatic_retry_allowed')
    require(all(v is False for v in auth.values()))
    return {'status': 'draft_boundaries_consistent_not_execution_authority',
        'proposal_id': d['proposal_id'], 'draft_content_sha256_not_runtime_freeze': digest(d),
        'execution_ready': False, 'private_evidence_reads': 0, 'model_or_rhino_calls': 0,
        'formal_spec_sha256': None, 'formal_runtime_sha256': None}


def check():
    return check_values(*(load_public(ROOT / name) for name in FILES))


class PublicArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'public draft checker accepts no input paths\n')


if __name__ == '__main__':
    PublicArgumentParser(description=__doc__).parse_args()
    try:
        result = check()
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status': 'invalid_public_reuse_preparation_draft'}))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True))
