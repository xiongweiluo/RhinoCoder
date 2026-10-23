#!/usr/bin/env python3
"""Inert complete public formal package assembler. No grants/run/private I/O.

Unknown current GPU, lease, host acceptance or deployment facts remain unknown.
The resulting disabled hashes are diagnostics, never execution approval objects.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import re
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_formal_reuse_scope import (STUDY_ID,INSTANCE,SPEC_FILE,FREEZE_FILE,
    RESOURCE_FILE,FACTS_FILE,ACCEPTANCE_FILE,MAC_SOURCE,MAC_STATE,REMOTE_SOURCE,REMOTE_STATE,REMOTE_ENV,
    THRESHOLDS,COMMITMENT,AUDIT_INVENTORY)
from plugin.rhino_listener.c5_reuse_field_scope import COMPARISON

HISTORY='eval/c5/formal-reuse-history-20261022.json'
ACTORS={'owner':'tools/c5_formal_reuse_owner.py','rhino':'tools/c5_rhino_formal_reuse_arm.py',
    'worker':'tools/run_c5_formal_reuse_worker.py','runner':'training/c5_formal_reuse_runner.py',
    'gpu_supervisor':'training/c5_formal_reuse_supervisor.py','audit':'training/c5_formal_reuse_joint_audit.py',
    'admission':'training/c5_formal_reuse_admission.py','budget':'training/c5_formal_reuse_budget.py',
    'source_guard':'training/c5_formal_reuse_field_scope.py','transport':'training/c5_formal_reuse_transport.py'}

def read(n):return json.loads((ROOT/n).read_bytes())
def raw_sha(value):return hashlib.sha256(value).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()

def verify_code_commit(revision,pins):
    # Git is preparation-only. Actual runtime relies on exact SHA-256 bytes.
    import subprocess
    if type(revision) is not str or re.fullmatch(r'[0-9a-f]{40}',revision) is None:return False
    for name,h in pins.items():
        if not name.endswith('.py'):continue
        p=subprocess.run(['git','show',revision+':'+name],cwd=ROOT,capture_output=True)
        if p.returncode!=0 or raw_sha(p.stdout)!=h:return False
    return True

def gpu_facts_match(gpu,code,now):
    if gpu is None:return False
    receipt=gpu.get('loader_preflight');environment=gpu.get('environment',{})
    if type(receipt) is not dict or receipt.get('source_code_inventory_sha256')!=digest(code):return False
    require(gpu.get('full_bytes_verified') is True and gpu.get('model_or_cuda_calls')==0
        and gpu.get('private_formal_reads')==0 and gpu.get('new_admission_created') is False,
        'formal_reuse_actual_readonly_gpu_observation')
    require(receipt.get('status')=='formal_readonly_loader_closure_verified_not_execution_authority'
        and receipt.get('environment_sha256')==digest(environment)
        and receipt.get('cuda_initialized') is receipt.get('model_loaded') is False
        and type(receipt.get('generation_calls')) is int and receipt['generation_calls']==0
        and type(receipt.get('holdout_rows_read')) is int and receipt['holdout_rows_read']==0,
        'formal_reuse_current_gpu_loader_code_environment_binding')
    if receipt.get('source_code_inventory_sha256')!=digest(code):return False
    require(all(type(value) in (int,float) and 0<=now-value<=86400
        for value in (gpu.get('epoch'),receipt.get('epoch'))),'formal_reuse_current_gpu_observation_age')
    fields=[p.strip() for p in gpu['observation']['gpu_stdout'].strip().split(',')]
    require(len(fields)==4 and fields[0].startswith('GPU-') and fields[3].isdigit() and int(fields[3])<=32
        and gpu['observation']['compute_stdout'].strip()=='' and type(gpu['uid']) is int
        and type(gpu['gpu_boot_id']) is str,'formal_reuse_current_same_idle_gpu')
    return True

def assemble(*,now=None):
    now=time.time() if now is None else now
    facts=read(FACTS_FILE);accepted=read(ACCEPTANCE_FILE);old=read('eval/c5/rhino-formal20-runtime-freeze-v4.json')
    old_spec=read('eval/c5/rhino-formal20-spec-v4.json');baseline=read('eval/c5/recovery-environment-plan-20261013.json')
    history=read(HISTORY);gate=read('eval/c5/recovery-attempt3-execution-review-20261014.json')
    require(accepted['accepted_review_source_inventory_sha256']==AUDIT_INVENTORY and accepted['accepted'] is True
        and accepted['formal_execution_approved'] is False,'formal_reuse_actual_audit_revision_acceptance')
    require(gate['supplemental_full_joint_review']['supplemental_result']['status']=='PASS'
        and gate['supplemental_engineering_gate_passed'] is True and gate['original_frozen_verifier_passed'] is False,
        'formal_reuse_complete_development_gate')
    lease=facts['actual_lease_report'];gpu=facts['gpu_current_review'];mac=facts['mac_current_review'];host=facts['host_acceptance_current']
    expiry=lease['expiry_epoch'] if lease is not None else None
    if lease is not None:
        require(lease['actor']=='repository_owner' and lease['timezone']=='Europe/Zurich'
            and type(expiry) in (int,float) and expiry>0 and lease['not_execution_approval'] is True,
            'formal_reuse_owner_actual_lease_required')
    cutoff=expiry-900 if expiry is not None else None
    resources={'owner_confirmed':lease is not None,'provider_expiry_epoch':expiry,'generation_cutoff_epoch':cutoff,
        'export_reserve_seconds':900,'formal_max_seconds':64800,'historical_cumulative_upper_bound_seconds':None,
        'original_16_hour_compliance_claimed':False,'old_budget_recredited':False,
        'unused_development_transferred_to_formal':False,'development_first_load_epoch':1791916117.781239,
        'development_attempts_consumed':3,'development_campaign_head_sha256':gate['campaign_head_sha256'],
        'development_seconds_max':86400,'research_cumulative_max_seconds':151200,
        'development_elapsed_to_release_seconds':gate['shared_elapsed_to_release_observation_seconds']}
    current_mac=mac is not None and mac.get('full_bytes_verified') is True
    current_gpu=gpu is not None and gpu.get('full_bytes_verified') is True
    host_ready=host is not None and all(host.get(k) is True for k in ('blank','exclusive','limited_guarantee_accepted'))
    deployed=facts.get('actual_public_deployment_both_endpoints_verified') is True
    window=cutoff is not None and now+64800<=cutoff
    revision_ready=type(facts.get('source_code_revision')) is str and re.fullmatch(r'[0-9a-f]{40}',facts['source_code_revision']) is not None
    ready=current_mac and current_gpu and host_ready and deployed and window and revision_ready
    spec=dict(old_spec)
    spec.update(study_id=STUDY_ID,instance_id=INSTANCE,experiment_id='disclosed-same-sealed-20-reuse',
        state='complete_public_freeze_awaiting_separate_exact_approval' if ready else 'disabled_offline_formal_preparation',
        execution_ready=ready,comparison=COMPARISON,thresholds=THRESHOLDS,**COMMITMENT,
        formal_gpu_seconds_max=64800,model_generation_cutoff_epoch=cutoff,lease_expiry_epoch=expiry,
        latest_owner_start_epoch=cutoff-64800 if cutoff is not None else None,
        export_reserve_seconds=900,per_request_timeout_seconds=360,startup_timeout_seconds=600,
        raw_stdout_cap_bytes=67108864,raw_stderr_cap_bytes=2097152,
        mac_source_root=str(MAC_SOURCE),mac_state_root=str(MAC_STATE),remote_source_root=str(REMOTE_SOURCE),
        remote_state_root=str(REMOTE_STATE),remote_environment_root=str(REMOTE_ENV),
        new_independent_holdout_claimed=False,original_c5_no_go_changed=False,
        owner_approval_received=False,formal_holdout_rows_read=0,formal_route_slots_consumed=0,
        deployment_revision=facts.get('source_code_revision'),
        ssh_host=None,ssh_user=None,ssh_port=None,ssh_socket=None,ssh_known_hosts_file=None,
        ssh_known_hosts_file_sha256=None,entry_return_wrapper=None,
        generation_cutoff_reported_utc=None,lease_expiry_reported_utc=None)
    endpoint=facts['actual_gpu_endpoint']
    if endpoint is not None:
        for k in ('host','user','port','socket','known_hosts_file','known_hosts_file_sha256'):
            spec['ssh_'+k]=endpoint[k]
        spec['ssh_host_key_alias']=endpoint['host_key_alias']
    spec['entry_return_wrapper_template']='#! python 3\nimport runpy\nscope = runpy.run_path("'+str(MAC_SOURCE)+'/tools/c5_rhino_formal_reuse_arm.py", init_globals={"FORMAL_ATTEMPT": {attempt}}, run_name="__main__")\nscope["ENTRY_RETURN_BARRIER"].release_after_entry_return()\n'
    spec['entry_return_wrapper']=spec['entry_return_wrapper_template'].replace('{attempt}','2')
    spec['observer_backend']=dict(old_spec['observer_backend'])
    spec['observer_backend']['code_read_roots']=[str(MAC_SOURCE) if p.startswith('/Users/xiongweiluo/RhinoCoder/data/training/c5/') else p
        for p in old_spec['observer_backend']['code_read_roots']]
    from plugin.rhino_listener.c5_formal_reuse_limits import LIMITS
    from plugin.rhino_listener.c5_formal_reuse_lineage import LINEAGE_FILE,validate_lineage
    lineage=read(LINEAGE_FILE);validate_lineage(lineage)
    spec['runtime_limits']=dict(LIMITS)
    spec['next_preexposure_attempt']=2
    spec['original_first_load_epoch']=lineage['formal_first_load_epoch']
    spec['preexposure_operational_attempts_max']=3
    spec['private_exposure_or_generation_intent_attempts_max']=1
    spec['owner_preload_confirmation_without_artificial_timeout']=True
    spec['preexposure_retry_requires_independent_complete_cleanup']=True
    gpu_environment=baseline['environment']['gpu'] if gpu is None else gpu['environment']
    host_files=baseline['host_readable_files'] if mac is None else mac['host_files']
    mac_environment=baseline['environment']['mac'] if mac is None else mac['environment']
    public_names=set(old['fixed_public_files'])-{'eval/c5/rhino-resource-boundary-v8-formal20-20261008.json',
        'eval/c5/hostassurance-development-independent-audit-20261007-d.json'}
    public_names|={SPEC_FILE,RESOURCE_FILE,HISTORY,ACCEPTANCE_FILE,FACTS_FILE,LINEAGE_FILE,
        'eval/c5/recovery-attempt3-execution-review-20261014.json',
        'eval/c5/recovery-completed-audit-source-review-20261014.json'}
    documents={SPEC_FILE:spec,RESOURCE_FILE:resources}
    source=set(read('eval/c5/recovery-runtime-freeze-20261013.json')['source_files'])
    source|={p.relative_to(ROOT).as_posix() for folder in ('training','plugin/rhino_listener','tools')
        for p in (ROOT/folder).glob('*.py') if any(x in p.name for x in ('formal_reuse','formal_run','run_package'))}
    source|=public_names|{'eval/c5/recovery-runtime-freeze-20261013.json'}
    require(set(ACTORS.values())<=source and len(source)<=512,'formal_reuse_complete_actor_source_population')
    payload={n:encoded(documents[n]) if n in documents else (ROOT/n).read_bytes() for n in sorted(source)}
    pins={n:raw_sha(v) for n,v in payload.items()}
    current_gpu=gpu_facts_match(gpu,{n:h for n,h in pins.items() if n.endswith('.py')},now)
    revision_ready=verify_code_commit(facts.get('source_code_revision'),pins)
    ready=current_mac and current_gpu and host_ready and deployed and window and revision_ready
    spec.update(execution_ready=ready,state='complete_public_freeze_awaiting_separate_exact_approval'
        if ready else 'disabled_offline_formal_preparation')
    payload[SPEC_FILE]=encoded(spec);pins[SPEC_FILE]=raw_sha(payload[SPEC_FILE])
    freeze=dict(old)
    freeze.update(study_id=STUDY_ID,instance_id=INSTANCE,incremental_revision=lineage,execution_ready=ready,spec_sha256=digest(spec),
        spec_file_sha256=pins[SPEC_FILE],source_files=pins,source_inventory_sha256=digest(pins),
        fixed_public_files={n:pins[n] for n in sorted(public_names)},source_revision=spec['deployment_revision'],
        mac_source_root=str(MAC_SOURCE),remote_source_root=str(REMOTE_SOURCE),
        environment=gpu_environment,environment_sha256=digest(gpu_environment),mac_environment=mac_environment,
        rhino_environment_files=host_files,model_assets=baseline['model_assets'],
        development_gate_audit=gate,audit_revision_acceptance=accepted,resource_boundary=resources,
        history_sha256=raw_sha(encoded(history).rstrip(b'\n')),history=history,ssh_executable_sha256=mac.get('ssh_executable_sha256') if mac else None,
        decryption_executable=mac.get('decryption_executable') if mac else old['decryption_executable'],
        decryption_executable_sha256=mac.get('decryption_executable_sha256') if mac else old['decryption_executable_sha256'],
        current_gpu_full_bytes_verified=current_gpu,current_mac_full_bytes_verified=current_mac,
        actual_public_deployment_both_endpoints_verified=deployed,host_acceptance=host,
        field_plan={**{k:baseline[k] for k in ('model_assets','gpu_process','loader_policy')},'environment':{'gpu':gpu_environment},'study_id':STUDY_ID,'instance_id':INSTANCE},
        synthetic_field_probe_independent_audit_passed=True,new_exact_owner_approval_received=False,
        actual_new_formal_host_baseline_observed=False,study_executed=False,formal_holdout_rows_read=0,
        gpu_readonly_observation=None if gpu is None else gpu.get('observation'),
        gpu_loader_import_preflight=None if gpu is None else gpu.get('loader_preflight'),
        execution_ready_meaning='complete_current_materials_not_execution_authority; separate_full_two_hash_approval_required')
    freeze['field_plan']['gpu_process']=dict(freeze['field_plan']['gpu_process'])
    freeze['field_plan']['gpu_process']['entry']='tools/run_c5_formal_reuse_worker.py'
    if gpu is not None:
        process=freeze['field_plan']['gpu_process']
        process.update(uid=gpu['uid'],boot_id=gpu['gpu_boot_id'],
            gpu_uuid=gpu['observation']['gpu_stdout'].split(',')[0].strip())
    # The admission module uses the established ASCII canonical history hash.
    from training.c5_reuse_evidence import sha
    freeze['history_sha256']=sha(history)
    documents[FREEZE_FILE]=freeze
    blockers=[name for name,ok in [('current_gpu_full_bytes',current_gpu),('actual_lease_full_18h_window',window),
        ('current_mac_full_bytes',current_mac),('fresh_blank_exclusive_host_acceptance',host_ready),
        ('both_actual_public_deployments',deployed),('source_code_commit',revision_ready)] if not ok]
    review={'status':'COMPLETE_FORMAL_FREEZE_AWAITING_EXACT_OWNER_APPROVAL' if ready else 'DISABLED_OFFLINE_FORMAL_PREPARATION',
        'blockers':blockers,'candidate_execution_ready':ready,'hashes_are_execution_approval_objects':ready,
        'candidate_spec_sha256':digest(spec),'candidate_runtime_sha256':digest(freeze),'source_files':len(pins),
        'source_inventory_sha256':digest(pins),'actors':ACTORS,'owner_audit_revision_accepted':True,
        'formal_execution_approval_received':False,'model_or_rhino_calls':0,'private_formal_reads':0,
        'new_state_grant_or_consumption_created':False,'old_failure_and_development_history_preserved':True}
    documents['eval/c5/formal-reuse-preparation-review-20261022.json']=review
    return documents

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');a=p.parse_args()
    docs=assemble()
    for n,v in docs.items():
        raw=encoded(v)
        if a.check:require((ROOT/n).read_bytes()==raw,'formal_reuse_saved_material_drift:'+n)
        else:(ROOT/n).write_bytes(raw)
    print(json.dumps(docs['eval/c5/formal-reuse-preparation-review-20261022.json'],sort_keys=True))
if __name__=='__main__':main()
