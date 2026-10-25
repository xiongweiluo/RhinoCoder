"""Pure binding of an unexposed revision to the original finite campaign."""
from .c5_research_native import require

PRIOR_SPEC='4b4b22d221a70700770c802654dbc503ff5a31c9f5dc7b834abbf1276a8cb3c8'
PRIOR_RUNTIME='1eee8af1dc25092708297f0c8f5e29b6322ebe7527d670475195d2f364a2f262'
FIRST=1792692329.837715
HEAD='dd26bc138be965f7cd9ef6283a3b9c63aa0424ad3f049c0e00113e6d4813f2c0'
LINEAGE_FILE='eval/c5/formal-reuse-incremental-lineage-20261022-r1.json'

def validate_lineage(value):
    require(type(value) is dict and value.get('schema_version')==1
        and value.get('prior_spec_sha256')==PRIOR_SPEC and value.get('prior_runtime_sha256')==PRIOR_RUNTIME
        and value.get('formal_first_load_epoch')==FIRST and type(value.get('attempts_consumed')) is int
        and value['attempts_consumed']==1 and value.get('preexposure_attempts_max')==3
        and value.get('formal_exposures')==0 and value.get('prior_status')=='RETRYABLE_ENGINEERING'
        and value.get('prior_campaign_head_sha256')==HEAD and value.get('prior_campaign_rows')==4
        and all(value.get(k) is False for k in ('history_or_consumption_reset','prior_sources_modified','new_execution_approved')),
        'formal_reuse_exact_unexposed_revision_lineage_required')
    initial=value.get('initial_campaign_scope');prior=value.get('prior_scope')
    require(type(initial) is dict and initial==prior and initial.get('spec_sha256')==PRIOR_SPEC
        and initial.get('runtime_sha256')==PRIOR_RUNTIME and initial.get('development_seconds_max')==64800,
        'formal_reuse_original_campaign_scope_required')
    proof=value.get('prior_failure_proof',{})
    require(proof.get('raw_anchor_sha256')=='5e3959f1dcd11fb5212055eea8743c814c206265149753946835d6b2bc329518'
        and all(proof.get(k) is True for k in ('capture_complete','qualified_target_absent','known_native_cleanup_complete','private_exposure_absent')),
        'formal_reuse_original_independent_failure_audit_required')
    require(len(value.get('prior_public_source_files',{}))==429
        and set(value.get('gpu_campaign_prefix_files',{}))=={'campaign.json','worker-role-1.json'}
        and set(value.get('mac_campaign_prefix_files',{}))=={'campaign.json','ledger/manifest.json'}|{
            'ledger/event-%04d.json'%n for n in range(4)},'formal_reuse_original_closed_prefix_required')
    return initial
