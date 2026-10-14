#!/usr/bin/env python3
"""Inert freeze assembly. Missing actual endpoint/lease facts stays NOT READY.

Writes no grants, campaign/role state, authentication, model or native actor.
Historical GPU material is a reuse baseline; it cannot attest today's assets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import math
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from training.c5_reuse_evidence import canonical,require,sha
from training.c5_recovery_policy import POLICY,affected_checks
from plugin.rhino_listener.c5_recovery_profile import SPEC,RUNTIME,PLAN,HISTORY,STUDY,INSTANCE,ENTRY
from plugin.rhino_listener.c5_reuse_field_scope import PROTOCOL,COMPARISON,LIMITS

def read(n):return json.loads((ROOT/n).read_bytes())
def raw_sha(raw):return hashlib.sha256(raw).hexdigest()
ACTORS={
    'mac':'tools/run_c5_recovery_mac_entry.py','owner':'tools/run_c5_recovery_owner_custody.py',
    'rhino_wrapper':'tools/run_c5_recovery_rhino_wrapper.py','rhino_entry':'tools/run_c5_recovery_rhino_entry.py',
    'gpu':'tools/run_c5_recovery_gpu_entry.py','independent_joint_audit':'tools/audit_c5_recovery_field_eight.py',
    'gpu_supervisor':'training/c5_recovery_field_gpu.py','ssh':'training/c5_recovery_field_ssh.py',
    'native_controller':'training/c5_recovery_field_mac.py','original_model_loader':'training/c5_followup_gpu_loader.py',
    'shared_stop':'training/c5_recovery_stop.py','history':'training/c5_recovery_history.py',
    'ready_and_failure_audit':'training/c5_recovery_field_audit.py',
    'native_failure_audit':'training/c5_recovery_field_native_failure_audit.py',
    'gpu_audit':'training/c5_recovery_field_gpu_audit.py','field_audit':'training/c5_recovery_field_eight_audit.py',
}

def assemble():
    old_spec=read('eval/c5/reuse-followup-development-spec-20261012-d.json')
    old_runtime=read('eval/c5/reuse-followup-development-runtime-freeze-20261012-d.json')
    old_plan=read('eval/c5/reuse-followup-field-environment-plan-20261012-d.json')
    history=read('eval/c5/engineering-recovery-preparation-review-20261013.json')['history']
    mac=read('eval/c5/recovery-field-actual-mac-review-20261013.json')
    facts=read('eval/c5/recovery-field-facts-20261013.json')
    lease=facts['actual_lease_report'];gpu=facts['gpu_current_review'];current=False
    if gpu is not None:
        require(gpu['endpoint']=='gpu' and gpu['model_or_cuda_calls']==gpu['private_formal_reads']==0
            and gpu['source_bytes_verified'] is gpu['original_model_assets_full_bytes_verified'] is True
            and gpu['same_global_history_verified'] is gpu['compatible_environment_full_bytes_verified'] is True
            and gpu['environment_sha256']==sha(old_plan['environment']['gpu'])
            and gpu['model_assets_sha256']==sha(old_plan['model_assets'])
            and gpu['history_sha256']==sha(history),'recovery_actual_gpu_review_incomplete_or_changed')
        current=True
    if lease is not None:
        require(lease['actor']=='repository_owner' and lease['not_execution_approval'] is True
            and lease['timezone']=='Europe/Zurich' and type(lease['expiry_epoch']) in (int,float)
            and math.isfinite(lease['expiry_epoch']) and lease['expiry_epoch']>0
            and type(lease['owner_statement']) is str and bool(lease['owner_statement']),
            'recovery_actual_owner_lease_fact_required')
    acceptance=dict(old_plan['host_acceptance'],instance_id=INSTANCE)
    recovery={'policy':POLICY,'history_sha256':sha(history),'public_attempts_max':3,
        'minimum_attempt_window_seconds':17784,'all_attempts_disclosed':True,
        'owner_confirmation_before_loading':True,'new_blind_holdout_claimed':False,
        'previous_campaign_head_sha256':facts['previous_campaign_head_sha256']}
    resources={'lease_expiry_epoch':1791914400,'generation_cutoff_epoch':1791913500,'export_reserve_seconds':900,
        'development_seconds_max':86400,'formal_seconds_max':64800,'research_seconds_max':151200,
        'historical_cumulative_upper_bound_seconds':None,'original_16_hour_compliance_claimed':False,
        'old_budget_recredited':False,'unused_development_transferred_to_formal':False,
        'actual_lease_basis':'last_reported_2026_10_13_20_00_Europe_Zurich_no_renewed_expiry_attested'}
    if lease is not None:
        resources.update(lease_expiry_epoch=lease['expiry_epoch'],generation_cutoff_epoch=lease['expiry_epoch']-900,
            actual_lease_basis=lease['owner_statement'])
    ready=current and lease is not None and time.time()+17784<=resources['generation_cutoff_epoch']
    spec={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'phase':'development',
        'comparison':COMPARISON,'limits':dict(LIMITS,model_seconds=360),'resources':resources,
        'host_policy':dict(old_spec['host_policy'],instance_id=INSTANCE,acceptance_record_sha256=sha(acceptance)),
        'development_plan_sha256':old_spec['development_plan_sha256'],'recovery':recovery,
        'execution_ready':ready,'private_formal_data_allowed':False,'default_route_change_allowed':False}
    from training.c5_recovery_field_ssh import POLICY as TRANSPORT
    plan={k:old_plan[k] for k in ('environment','model_assets','host_readable_files','loader_policy')}
    plan.update(protocol=PROTOCOL,study_id=STUDY,instance_id=INSTANCE,
        gpu_process=dict(old_plan['gpu_process'],entry=ENTRY,stop_policy=POLICY),
        transport=dict(old_plan['transport'],policy=TRANSPORT),host_acceptance=acceptance,recovery=recovery,
        minimum_attempt_window_seconds=17784,
        resource_basis={'platform_hour_quota':None,'historical_cumulative_upper_bound_seconds':None,
            'accepted_development_seconds_max':86400,'accepted_conditional_formal_seconds_max':64800,
            'owner_statement':'确认预算是足够的，你不需要太纠结预算问题，我会及时续租',
            'reservation_interpretation':'agent_sized_finite_24_hours_preparation_within_owner_resource_authorization_exact_execution_grant_pending',
            'timing_estimate':{'prior_minimum_attempt_window_seconds':16344,'extra_eight_rpc_wait_seconds':1440,
                'revised_minimum_attempt_window_seconds':17784,'one_remaining_window_seconds':17784,
                'shared_cap_seconds':86400,'elapsed_preparation_wait_stop_allowance_seconds':68616,
                'first_load_epoch_preserved':1791916117.781239,'attempts_already_consumed':2},
            'actual_renewed_lease_expiry_verified':lease is not None,'gpu_current_assets_verified':current})
    if current:
        plan['gpu_process'].update(boot_id=gpu['gpu_boot_id'],uid=gpu['uid'],gpu_uuid=gpu['gpu_uuid'])
    from plugin.rhino_listener.c5_recovery_plan import validate
    documents={SPEC:spec,PLAN:plan,HISTORY:history}
    allowed_legacy_changes={'plugin/rhino_listener/c5_reuse_field_scope.py',
        'training/c5_reuse_admission.py','training/c5_reuse_worker_loop.py',
        'training/c5_reuse_field_transport.py','training/c5_reuse_generation.py','training/c5_reuse_gpu_supervisor.py',
        'training/c5_followup_compatible_runtime.py'}
    require(all(n in allowed_legacy_changes or raw_sha((ROOT/n).read_bytes())==h
        for n,h in old_runtime['source_files'].items()),'recovery_unaffected_original_contract_bytes_changed')
    files=set(old_runtime['source_files'])
    files.add('eval/c5/reuse-followup-development-runtime-freeze-20261012-d.json')
    for folder,pattern in (('training','c5_recovery*.py'),('plugin/rhino_listener','c5_recovery*.py'),
                           ('tools','run_c5_recovery*.py'),('tools','audit_c5_recovery*.py')):
        files.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob(pattern))
    files.update(('tools/prepare_c5_recovery_field_freeze.py','tools/stage_c5_recovery_source.py',
        'tools/check_c5_recovery_field_candidate.py','eval/c5/recovery-field-facts-20261013.json',SPEC,PLAN,HISTORY))
    require(all(n in files for n in ACTORS.values()),'recovery_complete_registered_actor_closure')
    source={n:raw_sha(canonical(documents[n])+b'\n') if n in documents else raw_sha((ROOT/n).read_bytes()) for n in sorted(files)}
    runtime={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'spec_sha256':sha(spec),'source_files':source,
        'environment_sha256':sha(plan['environment']),'model_assets_sha256':sha(plan['model_assets']),
        'host_readable_files_sha256':sha(plan['host_readable_files']),'resources':resources,'recovery':recovery,
        'execution_ready':ready}
    validate(spec,runtime,plan,history)
    review={'status':('COMPLETE_CANDIDATE_AWAITING_EXACT_HEAD_CHECKS_AND_OWNER_APPROVAL' if ready else
                  'FIELD_INCREMENTAL_ADAPTATION_READY_FOR_ENVIRONMENT_RECONCILIATION_NOT_EXECUTION'),
        'execution_ready':ready,'new_execution_approval_received':False,'actors':ACTORS,
        'field_actor_sources_registered':True,'candidate_spec_sha256':sha(spec),'candidate_runtime_sha256':sha(runtime),
        'source_files':len(source),'source_inventory_sha256':sha(source),'history_sha256':sha(history),
        'candidate_two_hashes_are_not_execution_approval_objects':not ready,
        'changed_groups':['retry_policy','confirmation','stop','native_tools','runtime_environment'],
        'affected_checks':affected_checks(['retry_policy','confirmation','stop','native_tools','runtime_environment']),
        'reused_model_contract_sha256':sha(COMPARISON),'reused_original_d_runtime_sha256':sha(old_runtime),
        'current_mac_review':mac,'gpu_environment_and_model_assets_currently_verified':current,
        'renewed_actual_lease_expiry_currently_verified':lease is not None,
        'blockers':([] if ready else [k for k,present in (
            ('existing_GPU_authentication_master_missing',facts['gpu_authentication_master_present']),
            ('actual_renewed_lease_expiry_not_provided',lease is not None),
            ('GPU_current_asset_history_and_deployment_review_requires_restored_access',current),
            ('full_development_window_unavailable',time.time()+17784<=resources['generation_cutoff_epoch'])) if not present]),
        'model_or_rhino_calls':0,'private_formal_reads':0,'old_global_registry_writes':0,
        'new_campaign_or_role_state_created':False,'formal_or_product_route_authorized':False}
    documents[RUNTIME]=runtime;documents['eval/c5/recovery-field-incremental-review-20261013.json']=review
    return documents

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');a=p.parse_args()
    result=assemble()
    for name,value in result.items():
        raw=canonical(value)+b'\n'
        if a.check:require((ROOT/name).read_bytes()==raw,'recovery_saved_candidate_drift:'+name)
        else:(ROOT/name).write_bytes(raw)
    review=result['eval/c5/recovery-field-incremental-review-20261013.json']
    print(json.dumps({k:review[k] for k in ('status','execution_ready','source_files','source_inventory_sha256','blockers')},sort_keys=True))
if __name__=='__main__':main()
