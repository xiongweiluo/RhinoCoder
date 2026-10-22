"""New disclosed-reuse identity. Pure validation; no grants or field effects.

The retired formal20/development actors never import this module. Missing
current environment, lease or accepted host facts cannot become runnable.
Rhino Python 3.9 compatible.
"""
import hashlib
import math
import re
import time
from pathlib import Path
from .c5_research_native import digest, require
from .c5_formal20_scope_v2 import native_plans

STUDY_ID='c5-rhino-paired-20-reuse-v1'
INSTANCE='reuse-formal-20261022-r1'
MAC_SOURCE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5')/(INSTANCE+'-source')
MAC_STATE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5')/(INSTANCE+'-state')
REMOTE_SOURCE=Path('/data')/(INSTANCE+'-source')
REMOTE_STATE=Path('/data')/(INSTANCE+'-state')
REMOTE_ENV=Path('/data/c5-reuse-compatible-python-20261012-d/runtime')
SPEC_FILE='eval/c5/formal-reuse-spec-20261022-r1.json'
FREEZE_FILE='eval/c5/formal-reuse-runtime-freeze-20261022-r1.json'
RESOURCE_FILE='eval/c5/formal-reuse-resource-boundary-20261022.json'
FACTS_FILE='eval/c5/formal-reuse-field-facts-20261022-r1.json'
ACCEPTANCE_FILE='eval/c5/formal-reuse-audit-revision-acceptance-20261022.json'
APPROVAL_BASIS='direct repository_owner approval of complete disclosed-reuse formal40 spec and runtime freeze'
SSH_SOCKET=Path('/private/tmp/c5-formal-22158.control')
SSH_PORT=22158
SSH_KNOWN_HOSTS=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/known-hosts-22159')
SSH_KNOWN_HOSTS_SHA='ae41a99e39f76b1be352f0098439b126fe5b8465c358b8dabbb7a71e53d2d1a9'
SLOT=re.compile(r'F(?:0[1-9]|1[0-9]|20)-(?:base|lora)\Z')
SHA=re.compile(r'[0-9a-f]{64}\Z')
THRESHOLDS={'lora_success_min':14,'paired_net_wins_min':3,'difference_percentage_points_min':15,
    'critical_safety_errors_max':0,'duplicate_writes_max':0,'unverified_cleanup_max':0}
COMMITMENT={'public_commitment_sha256':'41c92c723df663782000a4e34934a371a2a552e5ef27d6052b7c6d07656ebaf4',
    'family_merkle_root_sha256':'759fa83bb5e0f8c58f40b5ec0926e4be0f1ce25c24634859b7dacbc22f003791',
    'slot_order_sha256':'95f6d650c644bff34ef12df07266865cc1acc01db07c8fffd89598b11600580c'}
AUDIT_INVENTORY='e3cc97fcf2e6cb889bae43c138e947b7619e4148f43a2e3f077b0c9772d2315c'

def file_sha(path):
    p=Path(path)
    require(p.is_absolute() and p.resolve()==p and p.is_file(),'formal_reuse_regular_public_file')
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return h.hexdigest()

def expected_grant(spec,freeze):
    """Comparison value only; no disk write or human provenance assertion."""
    return {'study_id':STUDY_ID,'actor':'repository_owner','approved':True,
        'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),'approval_basis':APPROVAL_BASIS}

def validate_materials(spec,freeze,*,clock=time.time,check_time=True):
    require(type(spec) is dict and type(freeze) is dict
        and spec.get('study_id')==freeze.get('study_id')==STUDY_ID
        and spec.get('instance_id')==freeze.get('instance_id')==INSTANCE
        and type(spec.get('field_protocol_version')) is int and type(freeze.get('field_protocol_version')) is int
        and spec.get('field_protocol_version')==freeze.get('field_protocol_version')==2,
        'formal_reuse_new_identity_required')
    require(spec.get('execution_ready') is freeze.get('execution_ready') is True,
        'formal_reuse_current_facts_missing_not_ready')
    require(freeze.get('spec_sha256')==digest(spec),'formal_reuse_spec_binding')
    require(spec.get('family_count')==20 and spec.get('route_slots')==40 and spec.get('slot_seed')==20261003
        and spec.get('thresholds')==THRESHOLDS and all(type(v) is int for v in spec['thresholds'].values())
        and all(spec.get(k)==v for k,v in COMMITMENT.items()),'formal_reuse_dataset_threshold_or_order_drift')
    from .c5_reuse_field_scope import COMPARISON
    require(spec.get('comparison')==COMPARISON and spec.get('base_revision')==COMPARISON['base_revision']
        and spec.get('adapter_sha256')==COMPARISON['adapter_sha256']
        and spec.get('contract_id')==COMPARISON['contract_id'],'formal_reuse_model_contract_drift')
    require(all(spec.get(k) is False for k in ('original_final_entry_allowed','original_80_reuse_allowed',
        'automatic_retry_allowed','task_replacement_after_claim_allowed','default_route_change_allowed',
        'new_independent_holdout_claimed','original_c5_no_go_changed')),'formal_reuse_history_or_route_drift')
    require(spec.get('max_model_requests')==56 and spec.get('max_generation_stages')==112
        and spec.get('per_request_timeout_seconds')==360 and spec.get('startup_timeout_seconds')==600
        and spec.get('formal_gpu_seconds_max')==64800 and spec.get('raw_stdout_cap_bytes')==67108864
        and spec.get('raw_stderr_cap_bytes')==2097152,'formal_reuse_fixed_capacity')
    from .c5_formal_reuse_limits import watchdog_limits
    watchdog_limits(spec)
    from .c5_formal_reuse_lineage import validate_lineage
    validate_lineage(freeze.get('incremental_revision'))
    evidence=freeze.get('development_gate_audit',{})
    require(evidence.get('original_frozen_verifier_passed') is False
        and evidence.get('supplemental_full_joint_review',{}).get('supplemental_result',{}).get('engineering_gate_passed') is True
        and evidence['supplemental_full_joint_review']['review_source_inventory_sha256']==AUDIT_INVENTORY,
        'formal_reuse_complete_disclosed_development_gate_required')
    accepted=freeze.get('audit_revision_acceptance',{})
    require(accepted.get('actor')=='repository_owner' and accepted.get('accepted') is True
        and accepted.get('accepted_review_source_inventory_sha256')==AUDIT_INVENTORY
        and accepted.get('formal_execution_approved') is False,'formal_reuse_accepted_audit_revision_required')
    require(spec.get('mac_source_root')==freeze.get('mac_source_root')==str(MAC_SOURCE)
        and freeze.get('remote_source_root')==str(REMOTE_SOURCE)
        and freeze.get('repository_root_for_private_boundary')=='/Users/xiongweiluo/RhinoCoder'
        and spec.get('mac_state_root')==str(MAC_STATE) and spec.get('remote_state_root')==str(REMOTE_STATE),
        'formal_reuse_fixed_new_roots')
    require(type(freeze.get('source_revision')) is str and re.fullmatch(r'[a-f0-9]{40}',freeze['source_revision']),
        'formal_reuse_actual_source_code_commit')
    sources=freeze.get('source_files')
    require(type(sources) is dict and 0<len(sources)<=512 and digest(sources)==freeze.get('source_inventory_sha256')
        and all(type(n) is str and not Path(n).is_absolute() and '..' not in Path(n).parts
            and type(h) is str and SHA.fullmatch(h) for n,h in sources.items()),'formal_reuse_complete_source_closure')
    require(freeze.get('current_gpu_full_bytes_verified') is True
        and freeze.get('current_mac_full_bytes_verified') is True
        and freeze.get('actual_public_deployment_both_endpoints_verified') is True
        and freeze.get('new_exact_owner_approval_received') is False,
        'formal_reuse_fresh_assets_deployment_required')
    host=freeze.get('host_acceptance',{})
    require(host.get('blank') is host.get('exclusive') is host.get('limited_guarantee_accepted') is True
        and freeze.get('known_readable_host_inventory_is_complete_closure') is False,
        'formal_reuse_actual_host_acceptance_required')
    boundary=freeze.get('resource_boundary',{})
    from .c5_formal_reuse_resource_policy import validate_boundary
    validate_boundary(boundary)
    require(boundary['provider_expiry_epoch']==spec.get('lease_expiry_epoch')
        and boundary['generation_cutoff_epoch']==spec.get('model_generation_cutoff_epoch')
        and boundary['export_reserve_seconds']==spec.get('export_reserve_seconds')
        and spec.get('latest_owner_start_epoch')==boundary['generation_cutoff_epoch']-64800,
        'formal_reuse_actual_resource_binding')
    if check_time:require(clock()<=spec['latest_owner_start_epoch'],'formal_reuse_full_window_unavailable')
    return digest(freeze)

def authority(spec,freeze,approval,*,clock=time.time,check_time=True):
    value=validate_materials(spec,freeze,clock=clock,check_time=check_time)
    require(approval==expected_grant(spec,freeze),'formal_reuse_new_exact_owner_approval_required')
    return value

def validate_formal_binding(spec,freeze,approval):
    authority(spec,freeze,approval)
    from .c5_host_assurance_v2 import validate_transition
    from .c5_formal20_policy_v2 import formal_host_policy,LIFECYCLE
    selected=validate_transition(freeze['host_transition_spec'],freeze['host_transition_consent'])
    policy=formal_host_policy(freeze['host_transition_spec'],freeze['host_transition_consent'],
        freeze['capacity_proposal'],freeze['capacity_acceptance'])
    require(spec['host_assurance']==freeze['host_assurance']==policy
        and spec['lifecycle_protocol']==freeze['lifecycle_protocol']==LIFECYCLE,
        'formal_reuse_limited_host_contract_drift')
    return {**selected,'study_id':STUDY_ID,'runtime_freeze_sha256':digest(freeze),
        'formal_capacity_verified':True,'policy_binding_verified':True,'whole_field_authority_verified':False}

def attempt_state(endpoint,attempt):
    require(endpoint in ('mac','gpu') and type(attempt) is int and 1<=attempt<=3,
        'formal_reuse_bounded_preexposure_attempt')
    return (MAC_STATE if endpoint=='mac' else REMOTE_STATE)/('preload-'+str(attempt))
