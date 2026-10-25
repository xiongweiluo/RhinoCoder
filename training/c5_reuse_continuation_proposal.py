"""Disabled continuation proposal reducer. No admission migration or effects.

This validates a reviewable protocol draft against public retired-C anchors.
It cannot choose a decision, mint an identity/grant, or admit a live role.
"""
import copy,re
from training.c5_reuse_evidence import canonical,sha,require,exact
PROPOSAL='C5-REUSE-C-STARTUP-CONTINUATION-20261012'
GLOBAL_ROOTS={'mac':'/Users/xiongweiluo/RhinoCoder/data/training/c5/c5-reuse-global-admission-v1','gpu':'/data/c5-reuse-global-admission-v1'}
AUTH=('execution_ready','model_or_rhino_calls_authorized','claim_or_migration_authorized','private_formal_access_authorized','rental_or_payment_authorized','automatic_retry_allowed','default_route_change_authorized','pr_merge_authorized')

def same_json(value,expected):
    # JSON bool/int equality must not turn 1 into a true protocol boundary.
    return canonical(value)==canonical(expected)

def validate_proposal(value,legacy_snapshot):
    exact(value,('proposal_id','status','owner_authorized_scope','decisions','selected_decision','retired_c','legacy','continuation','startup','resources','authority'))
    require(value['proposal_id']==PROPOSAL and value['status']=='DRAFT_NOT_ACCEPTED_NOT_FROZEN'
        and value['owner_authorized_scope']=='readonly_startup_diagnosis_cpu_controls_and_protocol_proposal_only'
        and value['decisions']==['end_additional_research','prepare_one_disclosed_followup'] and value['selected_decision'] is None,'continuation_draft_decision')
    require(same_json(value['retired_c'],{'study_id':'C5DEV-REUSE-20261012-C','runtime_sha256':'160e74bb15497960d51d499f51bac6a8be67b38c0124af385296c1119ecedc24','retirement_raw_sha256':'310797d0dfbe9e787424f62140f8dae460fcd443b7b23043ca5e6dc1e8befb80','grant_restore_allowed':False,'serve_stop_or_slot_replay_allowed':False,'historical_unique_root_cause_proven':False}),'continuation_retired_c')
    exact(legacy_snapshot,('mac','gpu'))
    mac,gpu=legacy_snapshot['mac'],legacy_snapshot['gpu']
    for endpoint,snapshot in legacy_snapshot.items():
        exact(snapshot,('exists','rows','file_sha256','root_name','writes'))
        require(type(snapshot['exists']) is bool and snapshot['root_name']=='c5-reuse-global-admission-v1'
            and type(snapshot['writes']) is int and snapshot['writes']==0 and type(snapshot['rows']) is list
            and type(snapshot['file_sha256']) is dict,'continuation_legacy_schema')
        for row in snapshot['rows']:
            require(type(row) is list and len(row)==4 and all(type(v) is str for v in row)
                and all(re.fullmatch('[0-9a-f]{64}',v) for v in row[2:]),'continuation_legacy_row')
        require(all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in snapshot['file_sha256'].values()),'continuation_legacy_file_hash')
    require(mac['exists'] is True and gpu['exists'] is False and gpu['rows']==[] and gpu['file_sha256']=={}
        and len(mac['rows'])==2 and [r[1] for r in mac['rows']]==['controller','host']
        and all(r[0]=='C5DEV-REUSE-20261012-C' for r in mac['rows'])
        and set(mac['file_sha256'])=={'admission.lock','admission.sqlite','controller.consumed.json','host.consumed.json'},'continuation_legacy_population')
    require(same_json(value['legacy'],{'global_roots':GLOBAL_ROOTS,'observed_snapshot_sha256':sha(legacy_snapshot),
        'existing_files_byte_preservation_required':True,'known_consumed_rows_carried_forward':copy.deepcopy(mac['rows']),
        'clear_reset_rewrite_or_namespace_bypass_allowed':False,'unknown_or_partial_legacy_blocks_all_new_effects':True}),'continuation_legacy_carryforward')
    require(same_json(value['continuation'],{'implementation_status':'NOT_IMPLEMENTED_NO_MIGRATION',
        'draft_architecture':'additive_manifest_in_same_global_root_with_nonempty_genesis_bound_to_immutable_v1_files',
        'new_study_id':None,'new_instance_id':None,'maximum_additional_development_attempts':1,'development_slots':8,
        'maximum_conditional_formal_attempts':1,'formal_slots':40,'formal_requires_development_whole_raw_audit_pass':True,
        'same_public_eight_overlap_disclosed':True,'same_sealed_twenty_reuse_disclosed':True,'new_blind_holdout_claimed':False,
        'slot_replacement_or_retry_allowed':False,'original_no_go_or_results_rewrite_allowed':False,
        'protocol_preparation_acceptance_required':True,'fresh_full_spec_runtime_dual_ci_and_exact_approval_required':True,
        'owner_private_ready_final_and_raw_audit_required':True}),'continuation_limits_or_authority')
    require(same_json(value['startup'],{'native_pidfd_open_and_send_required':True,'numeric_pid_or_name_kill_fallback_allowed':False,
        'fully_frozen_compatible_runtime_required':True,'observed_system_python_is_automatically_approved':False,
        'diagnostic_must_cover_actual_new_entry_preamble_without_fork_or_model':True,
        'first_gpu_registry_initialization_requires_accepted_bound_nonempty_history':True,
        'stdout_stderr_separate_bounded_raw_capture_before_launch':True,'stderr_cap_bytes':262144,
        'truncated_or_unobserved_exit_retires_without_retry':True,'qualified_gpu_stop_error_must_not_skip_first_known_native_cleanup':True,
        'original_c_stderr_reconstructed':False}),'continuation_startup_boundary')
    require(same_json(value['resources'],{'status':'NEW_EXECUTION_BOUNDARY_PENDING_NOT_CURRENT_AUTHORITY',
        'lease_expiry_epoch':None,'generation_cutoff_epoch':None,'additional_development_seconds':None,
        'formal_seconds':None,'research_seconds':None,'historical_cumulative_upper_bound_seconds':None,
        'original_16_hour_compliance_claimed':False,'unused_c_budget_automatically_recredited':False,
        'export_reserve_seconds_min':900}),'continuation_resource_authority')
    exact(value['authority'],AUTH);require(all(v is False for v in value['authority'].values()),'continuation_disabled')
    return {'proposal_id':PROPOSAL,'proposal_sha256_not_runtime_freeze':sha(value),
        'legacy_snapshot_sha256':sha(legacy_snapshot),'carryforward_rows':2,'status':'disabled_proposal_consistent',
        'execution_authority':False,'migration_or_new_study_created':False}
