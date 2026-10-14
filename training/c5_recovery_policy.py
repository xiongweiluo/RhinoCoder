"""Versioned recovery rules. No field entry, grant writer or model imports."""
import math
from training.c5_reuse_evidence import canonical, exact, is_sha, require, sha

POLICY = {
    'protocol': 'c5-engineering-recovery-v3',
    'public_attempts_max': 3,
    'confirmation_inputs_per_invocation': 3,
    'owner_confirmation_before_loading': True,
    'owner_wait_consumes_attempt': False,
    'budget_reset_on_retry': False,
    'formal_attempts_after_exposure_or_generation_intent': 1,
    'unknown_cleanup': 'pause_for_reconciliation',
    'signals_per_qualified_target': 1,
    'quality_failure_automatic_retry': False,
    'all_attempts_disclosed': True,
    'retired_a_to_d_reopening_allowed': False,
}
RETIRED = ('reuse-dev-20261011-a', 'reuse-dev-20261012-b',
           'reuse-dev-20261012-c', 'reuse-dev-20261012-d')
SCOPE_KEYS = ('campaign_id','phase','spec_sha256','runtime_sha256','policy_sha256',
              'history_sha256','public_plan_sha256','contract_sha256','development_seconds_max',
              'generation_cutoff_epoch')
RETRY_ERRORS = {'startup','transport','owner_wait','native_operational','capture'}

def validate_scope(scope):
    exact(scope,SCOPE_KEYS)
    require(type(scope['campaign_id']) is str and 1<=len(scope['campaign_id'])<=80
            and all(c.isascii() and (c.isalnum() or c in '-_') for c in scope['campaign_id'])
            and scope['campaign_id'].lower() not in RETIRED
            and scope['campaign_id'].upper() not in ('C5DEV-REUSE-20261011-A','C5DEV-REUSE-20261012-B',
                                             'C5DEV-REUSE-20261012-C','C5DEV-REUSE-20261012-D'),
            'recovery_new_campaign_required')
    require(scope['phase'] in ('public_engineering','formal')
            and all(is_sha(scope[k]) for k in ('spec_sha256','runtime_sha256','policy_sha256',
                                              'history_sha256','public_plan_sha256','contract_sha256'))
            and scope['policy_sha256']==sha(POLICY),'recovery_scope_policy')
    require(type(scope['development_seconds_max']) is int and 60<scope['development_seconds_max']<=86400
            and type(scope['generation_cutoff_epoch']) in (int,float)
            and math.isfinite(scope['generation_cutoff_epoch']) and scope['generation_cutoff_epoch']>0,
            'recovery_finite_shared_budget')
    return scope

def require_grant(scope,grant):
    validate_scope(scope)
    expected={'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],
              'scope_sha256':sha(scope),'spec_sha256':scope['spec_sha256'],
              'runtime_sha256':scope['runtime_sha256'],'policy_sha256':sha(POLICY)}
    require(canonical(grant)==canonical(expected),'recovery_new_exact_execution_grant_required')
    # This checks byte binding, never cryptographic human provenance.

def retry_decision(scope,attempts,formal_consumed,error,proof):
    validate_scope(scope)
    require(type(attempts) is int and 0<=attempts<=POLICY['public_attempts_max']
            and type(formal_consumed) is bool and type(error) is str,'recovery_retry_types')
    exact(proof,('raw_anchor_sha256','capture_complete','qualified_target_absent',
                 'known_native_cleanup_complete','private_exposure_absent'))
    require(is_sha(proof['raw_anchor_sha256'])
            and all(type(proof[k]) is bool for k in proof if k!='raw_anchor_sha256'),
            'recovery_independent_cleanup_proof')
    if formal_consumed or (scope['phase']=='formal' and not proof['private_exposure_absent']):
        return 'FORMAL_CONSUMED_NO_RETRY'
    # Missing diagnostics are disclosed for PUBLIC engineering; known target/native
    # cleanup and absence of private exposure still must be independently checked.
    required=('qualified_target_absent','known_native_cleanup_complete','private_exposure_absent')
    if not all(proof[k] for k in required) or (scope['phase']=='formal' and not proof['capture_complete']):
        return 'PAUSED_RECONCILIATION'
    # Operational preparation has the same finite limit before private exposure.
    limit=POLICY['public_attempts_max']
    if error=='cancelled':return 'PAUSED_OWNER'
    if error not in RETRY_ERRORS:return 'FAILED_NO_AUTOMATIC_RETRY'
    if attempts>=limit:return 'ATTEMPT_LIMIT_REACHED'
    return 'RETRYABLE_ENGINEERING' if proof['capture_complete'] else 'RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE'

# These are validation dependencies, not a cache that asserts fresh host bytes.
DEPENDENCIES={
    'retry_policy': ('recovery_controller','formal_consumption','shared_budget'),
    'confirmation': ('recovery_controller','owner_custody'),
    'stop': ('recovery_controller','pidfd_identity','concurrent_stop','cleanup'),
    'model_assets': ('model_contract','tokenizer'),
    'runtime_environment': ('startup','pidfd_identity','model_contract'),
    'native_tools': ('native_contract','cleanup','recovery_controller'),
}
def affected_checks(changed):
    require(type(changed) in (set,list,tuple) and all(x in DEPENDENCIES for x in changed),
            'recovery_unknown_dependency')
    return sorted(set(changed)|{dep for name in changed for dep in DEPENDENCIES[name]})
