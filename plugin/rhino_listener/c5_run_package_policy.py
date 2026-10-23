"""Pure run-package contract. No grants, clocks, private input or field effects."""
import math
from pathlib import Path
from .c5_research_native import digest, require

LAYOUT_FILE = 'eval/c5/formal-run-package-layout.json'
POLICY = {
    'version': 1,
    'study_id': 'c5-rhino-paired-20-reuse-v1',
    'global_preexposure_loads_max': 5,
    'package_preexposure_loads_max': 3,
    'private_exposures_max': 1,
    'gpu_residency_seconds_max': 129600,
    'research_reservation_seconds_max': 216000,
    'historical_cumulative_upper_bound_seconds': None,
    'original_16_hour_compliance_claimed': False,
    'export_reserve_seconds': 900,
    'startup_seconds': 600,
    'remaining_chain_upper_seconds': 52200,
    'retry_requires_complete_raw_and_known_cleanup': True,
    'code_change_requires_new_exact_pair': True,
    'owner_private_entry_per_package': 1,
    'owner_confirmation_precedes_native_preparation': True,
    'manual_per_attempt_host_attestation': False,
    'actual_execution_separate_approval_required': True,
    'receipt_custody': 'owner_authorized_automatic_capture_not_manual_per_receipt',
    'historical_clock_rewritten': False,
    'new_campaign_allowed': False,
    'post_exposure_retry_allowed': False,
    'quality_retry_allowed': False,
    'reviewer_2_required': False,
}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_policy(value):
    require(value == POLICY, 'run_package_unapproved_rule_change')
    return value


def validate_layout(value):
    keys = {'schema_version', 'package_id', 'study_id', 'mac_source_root', 'gpu_source_root',
            'mac_state_root', 'gpu_state_root', 'spec_file', 'runtime_file', 'policy_sha256'}
    require(type(value) is dict and set(value) == keys and value['schema_version'] == 1
            and value['study_id'] == POLICY['study_id']
            and value['policy_sha256'] == digest(POLICY), 'run_package_layout_binding')
    name = value['package_id']
    require(type(name) is str and name.startswith('reuse-formal-') and len(name) <= 80
            and all(c.isascii() and (c.isalnum() or c == '-') for c in name), 'run_package_name')
    for endpoint, parent in (('mac', '/Users/xiongweiluo/RhinoCoder/data/training/c5'), ('gpu', '/data')):
        for suffix in ('source', 'state'):
            require(value[endpoint + '_' + suffix + '_root'] == str(Path(parent) / (name + '-' + suffix)),
                    'run_package_fixed_layout')
    require(value['spec_file'] == 'eval/c5/' + name + '-spec.json'
            and value['runtime_file'] == 'eval/c5/' + name + '-runtime.json', 'run_package_material_names')
    return value


def validate_migration(value):
    keys = {'schema_version', 'legacy_first_load_epoch', 'cutover_epoch', 'legacy_generation_stop_epoch',
            'legacy_elapsed_debit_seconds', 'gpu_residency_upper_seconds', 'prior_campaign_head_sha256',
            'prior_attempts_consumed', 'legacy_accounting_end_epoch', 'legacy_policy_rejudged', 'historical_first_load_rewritten'}
    require(type(value) is dict and set(value) == keys and value['schema_version'] == 1
            and all(finite(value[k]) for k in ('legacy_first_load_epoch', 'cutover_epoch',
                'legacy_generation_stop_epoch', 'legacy_accounting_end_epoch', 'legacy_elapsed_debit_seconds', 'gpu_residency_upper_seconds'))
            and value['legacy_first_load_epoch'] == 1792692329.837715
            and value['legacy_generation_stop_epoch'] == value['legacy_first_load_epoch'] + 64740
            and value['cutover_epoch'] >= value['legacy_first_load_epoch']
            and value['cutover_epoch'] >= value['legacy_accounting_end_epoch'] >= value['legacy_first_load_epoch']
            and value['legacy_elapsed_debit_seconds'] >= value['legacy_accounting_end_epoch'] - value['legacy_first_load_epoch']
            and value['legacy_elapsed_debit_seconds'] >= value['gpu_residency_upper_seconds']
            and type(value['prior_attempts_consumed']) is int and 1 <= value['prior_attempts_consumed'] < 5
            and type(value['prior_campaign_head_sha256']) is str and len(value['prior_campaign_head_sha256']) == 64
            and all(c in '0123456789abcdef' for c in value['prior_campaign_head_sha256'])
            and value['legacy_policy_rejudged'] is value['historical_first_load_rewritten'] is False,
            'run_package_no_retrospective_clock_reset')
    return value


def remaining_window(policy, *, charged_seconds, remaining_work_seconds, now, expiry):
    validate_policy(policy)
    require(all(finite(v) for v in (charged_seconds, remaining_work_seconds, now, expiry)),
            'run_package_finite_window')
    required = remaining_work_seconds + policy['startup_seconds'] + policy['export_reserve_seconds']
    budget = policy['gpu_residency_seconds_max'] - charged_seconds
    lease = expiry - now
    return {'required_seconds': required, 'remaining_budget_seconds': budget,
            'remaining_lease_seconds': lease, 'can_load': required <= min(budget, lease)}


def retry_authorized(policy, *, package_start_attempt, attempts, exposed, complete_proof, same_pair):
    validate_policy(policy)
    require(type(attempts) is int and type(package_start_attempt) is int
            and 0 <= package_start_attempt <= attempts <= policy['global_preexposure_loads_max'],
            'run_package_attempt_accounting')
    return (not exposed and same_pair and complete_proof
            and attempts < policy['global_preexposure_loads_max']
            and attempts - package_start_attempt < policy['package_preexposure_loads_max'])
