"""Independent raw signature, qualified exit, budget and admission checks.

No model, native calls, state mutation or producer-summary PASS shortcuts.
Only the owner invokes these checks on private formal artifacts.
"""
import hashlib
import hmac
import math
import os
from pathlib import Path
from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_gate import signature
from training.c5_reuse_evidence import sha,ZERO

def audit_resource(value,boundary,*,status,first_epoch,package=None,permit=None):
    from plugin.rhino_listener.c5_formal_reuse_resource_policy import validate_boundary
    validate_boundary(boundary)
    require(value['status']==status and value['resource_boundary_sha256']==digest(boundary)
        and value['replay_allowed'] is False,'formal_reuse_resource_receipt_binding')
    for key in ('elapsed_seconds_including_load_and_idle','cap_seconds','start_epoch','stop_epoch'):
        require(type(value[key]) in (int,float) and math.isfinite(value[key]),'formal_reuse_finite_resource_observation')
    if package is not None:
        from plugin.rhino_listener.c5_run_package_policy import validate_policy
        policy=validate_policy(package['policy']);basis=permit['budget_basis']
        require(value.get('accounting')=='gpu_residency_v1' and value['run_package_sha256']==digest(package)
            and value['cap_seconds']==policy['gpu_residency_seconds_max']
            and value['legacy_first_load_epoch']==first_epoch==basis['legacy_first_load_epoch']
            and value['start_epoch']==basis['load_intent_epoch']
            and value['charged_before_seconds']==basis['charged_before_seconds']
            and 0<=value['stop_epoch']-value['start_epoch']<=value['elapsed_seconds_including_load_and_idle']
            and value['charged_before_seconds']+value['elapsed_seconds_including_load_and_idle']<=value['cap_seconds']
            and value['stop_epoch']<=package['lease_expiry_epoch'], 'run_package_raw_resource_overrun')
        return value['elapsed_seconds_including_load_and_idle']
    require(value['cap_seconds']==64800 and value['start_epoch']==first_epoch
        and 0<=value['elapsed_seconds_including_load_and_idle']<=64800
        and boundary['development_elapsed_to_release_seconds']+value['elapsed_seconds_including_load_and_idle']
            <=boundary['research_cumulative_max_seconds']
        and value['start_epoch']<=value['stop_epoch']<=min(value['start_epoch']+64800,boundary['generation_cutoff_epoch']),
        'formal_reuse_observed_resource_overrun')
    return value['elapsed_seconds_including_load_and_idle']

def audit_signatures(state,freeze,order,cases):
    labels=['hub']+[row['slot_id'] for row in order]
    custody=state/'audit-key-custody'
    require({p.name for p in custody.iterdir()}=={n+'.json' for n in labels},'formal_reuse_exact_audit_key_population')
    by_id={c['family_id']:c for c in cases};seen=set();count=0
    for label in labels:
        key=read_json(custody,label+'.json')
        require(set(key)=={'key_hex','runtime_sha256'} and key['runtime_sha256']==digest(freeze)
            and type(key['key_hex']) is str and len(key['key_hex'])==64,'formal_reuse_original_key_scope')
        secret=bytes.fromhex(key['key_hex']);root=state if label=='hub' else state/label
        pattern='hub-request-*.json' if label=='hub' else 'request-*.json'
        paths=sorted(root.glob(pattern));require(paths,'formal_reuse_signature_coverage_missing')
        for p in paths:
            message=read_json(root,p.name);envelope=message if label=='hub' else message['envelope'];body=envelope['payload']
            require(body['owner_freeze_sha256']==digest(freeze) and body['request_id'] not in seen
                and hmac.compare_digest(envelope['signature'],signature(secret,body)),'formal_reuse_raw_hmac_or_replay')
            if label!='hub':
                slot=next(s for s in order if s['slot_id']==label)
                require(body['task_sha256']==hashlib.sha256(by_id[slot['family_id']]['task_text'].encode()).hexdigest(),
                    'formal_reuse_signed_task_binding')
            seen.add(body['request_id']);count+=1
        require(not os.path.lexists(root/('hub.key' if label=='hub' else 'handoff.key')),
            'formal_reuse_dispatch_key_not_removed')
    return {'signed_requests_recomputed':count,'private_audit_keys_retained':41,
        'dispatch_keys_absent':True,'memory_erasure_proven':False}

def audit_supervisor(state,spec,freeze,*,completed=True,prior_release_observation=None):
    value=read_json(state,'export-supervisor-original.json');q=value['qualification'];parent=value['parent']
    require(q['model_loading_started'] is False and q['parent_pid']==parent['pid']
        and q['target']['pid']!=parent['pid'] and all(q['target'][k]==parent[k] for k in
            ('uid','boot_id','argv_sha256','executable_sha256','cwd')),'formal_reuse_raw_preload_qualification')
    from training.c5_reuse_stop import target
    target(q['target']);target(parent)
    from plugin.rhino_listener.c5_formal_reuse_scope import REMOTE_ENV,REMOTE_SOURCE
    from plugin.rhino_listener.c5_followup_profile import GPU_FLAGS
    attempt=int(state.name.split('-')[-1])
    argv=[str(REMOTE_ENV/'bin/python3.11'),*GPU_FLAGS,
        str(REMOTE_SOURCE/'tools/run_c5_formal_reuse_worker.py'),'serve','--attempt',str(attempt)]
    require(parent['argv_sha256']==hashlib.sha256(b'\0'.join(p.encode() for p in argv)+b'\0').hexdigest()
        and parent['cwd']==str(REMOTE_SOURCE)
        and parent['executable_sha256']==freeze['environment']['executable_sha256'],
        'formal_reuse_independent_exact_process_entry')
    expected=freeze['field_plan']['gpu_process']
    require(q['target']['uid']==expected['uid'] and q['target']['boot_id']==value['boot_id']==expected['boot_id']
        and value['target_proc_present'] is False and value['compute_stdout'].strip()==''
        and value['model_or_cuda_calls']==value['private_formal_reads']==0,'formal_reuse_raw_release_incomplete')
    fields=[p.strip() for p in value['gpu_stdout'].strip().split(',')]
    require(len(fields)==2 and fields[0]==expected['gpu_uuid'] and fields[1].isdigit() and int(fields[1])<=32,
        'formal_reuse_same_gpu_idle_required')
    rows=value['stop_rows'];binding={'qualification_sha256':sha(q)};require(value['stop_binding']==binding
        and len(rows)==2,'formal_reuse_shared_stop_population')
    head=ZERO
    for i,row in enumerate(rows):
        require(set(row)=={'seq','previous_sha256','binding_sha256','kind','payload','record_sha256'}
            and row['seq']==i and type(row['seq']) is int and row['previous_sha256']==head
            and row['binding_sha256']==sha(binding) and row['record_sha256']==sha({k:v for k,v in row.items()
                if k!='record_sha256'}),'formal_reuse_shared_stop_original_chain')
        head=row['record_sha256']
    result=rows[1]['payload']
    require(rows[0]['kind']=='stop_claim' and rows[0]['payload']=={'qualification_sha256':sha(q),'signals_max':1}
        and rows[1]['kind']=='stop_result' and set(result)=={'status','signal_attempts','exit_observed','error_type'}
        and result['exit_observed'] is True and result['error_type'] is None
        and type(result['signal_attempts']) is int
        and (result['status'],result['signal_attempts']) in (('already_exited',0),('exit_observed',1)),
        'formal_reuse_shared_stop_known_exit_required')
    final=value['final']
    recovered=False
    if prior_release_observation is not None:
        recovered=verify_prior_absence(value,prior_release_observation,completed=completed)
    require(recovered or (type(final['child_wait_status']) is int and final['child_exit_reaped'] is True
        and final['stop_result']=={**result,'retry_signal_allowed':False} and final['cleanup_errors']==[]
        and type(final['epoch']) in (int,float) and math.isfinite(final['epoch'])
        and type(value['epoch']) in (int,float) and math.isfinite(value['epoch'])
        and 0<final['epoch']<=value['epoch']), 'formal_reuse_original_child_reap_join')
    if completed:
        require(final['child_wait_status']==0 and final['primary_error_type'] is None
            and result['status']=='already_exited' and result['signal_attempts']==0,
            'formal_reuse_natural_exit_shared_stop_required')
    permit=read_json(state,'load-permit.json');require(value['permit']==permit,'formal_reuse_cross_endpoint_load_permit')
    from training.c5_formal_reuse_supervisor import validate_load_permit
    validate_load_permit(permit,spec,freeze,int(state.name.removeprefix('preload-')))
    require(permit['first_load_epoch']<=final['epoch']<=value['epoch']
        and final['epoch']<=freeze['resource_boundary']['provider_expiry_epoch']
        and ('run_package' in freeze or value['epoch']<=freeze['resource_boundary']['provider_expiry_epoch']),
        'formal_reuse_original_release_within_actual_lease')
    raw=read_json(state,'raw-streams-final.json')
    require(raw['complete_raw_capture'] is True and raw['protocol_delivery_overflow'] is False
        and type(raw['unconsumed_protocol_tail_bytes']) is int and raw['unconsumed_protocol_tail_bytes']>=0
        and (not completed or raw['unconsumed_protocol_tail_bytes']==0),'formal_reuse_original_streams_incomplete')
    for stream in ('stdout','stderr'):
        record=raw[stream];require(record['name']=='serve-'+stream+'.raw','formal_reuse_raw_stream_path')
        p=state/record['name']
        require(record['complete_raw_capture'] is True and record['eof_observed'] is True
            and type(record['exit_status']) is int and (not completed or record['exit_status']==0)
            and record['truncated'] is False
            and record['error_type'] is None and p.stat().st_size==record['observed_bytes']==record['retained_bytes']
            and hashlib.sha256(p.read_bytes()).hexdigest()==record['observed_bytes_sha256']==record['retained_bytes_sha256'],
            'formal_reuse_original_stream_raw_hash')
    return {'qualified_child_exited_reaped':not recovered,'same_gpu_idle_observed':True,
        'shared_stop_signals':result['signal_attempts'],'complete_original_stream_capture':True,
        'physical_origin_cryptographically_proven':False,'permit_first_load_epoch':permit['first_load_epoch']}

def audit_completed_admission(state,spec,freeze):
    from training.c5_formal_reuse_admission import open_formal_campaign
    from plugin.rhino_listener.c5_formal_reuse_scope import MAC_STATE
    grant=read_json(MAC_STATE,'owner-approval.json')
    campaign=open_formal_campaign(spec,freeze,grant,freeze['history'])
    try:
        value=campaign.observation();attempt=int(state.name.removeprefix('preload-'))
        require(value['attempts']==attempt and value['formal_consumed'] is True and not value['active']
            and value['status']=='AWAITING_INDEPENDENT_AUDIT','formal_reuse_completed_global_consumption')
        prefix=read_json(state,'load-permit.json')['rows'];rows=campaign.log.rows()
        require(rows[:len(prefix)]==prefix and sum(r['kind']=='private_exposure_intent' for r in rows)==1
            and sum(r['kind']=='generation_begin_intent' for r in rows)==1,'formal_reuse_single_private_exposure')
        return {'attempts_consumed':attempt,'formal_exposures':1,'first_load_epoch':value['first_load_epoch'],
            'original_development_first_load_epoch':freeze['history']['development_first_load_epoch'],
            'original_development_attempts':3,'no_history_or_budget_reset':True}
    finally:campaign.log.close()


def audit_residency_join(state,spec,freeze):
    """Cross-endpoint raw join; do not accept a producer's usage summary."""
    package=freeze['run_package'];policy=package['policy']
    permit=read_json(state,'load-permit.json');exported=read_json(state,'export-supervisor-original.json')
    local=read_json(state,'resource-settlement.json')
    remote=read_json(state,'worker-stop-response.json')['raw_records']['resource-settlement.json']
    final=exported['final'];start=permit['budget_basis']['load_intent_epoch'];end=final['epoch']
    require(exported['worker_resource']==remote and final['child_exit_reaped'] is True
        and type(final['child_wait_status']) is int and start<=end<=package['lease_expiry_epoch']
        and local.get('settlement_basis')=='original_qualified_gpu_exit'
        and remote.get('settlement_basis')=='worker_before_exit'
        and local['stop_epoch']==end and remote['stop_epoch']<=end
        and type(local['observation_epoch']) in (int,float) and math.isfinite(local['observation_epoch'])
        and local['observation_epoch']>=end,'run_package_independent_residency_exit_join')
    upper=max(end-start,remote['elapsed_seconds_including_load_and_idle'])
    require(local['elapsed_seconds_including_load_and_idle']==upper
        and local['charged_before_seconds']==remote['charged_before_seconds']==permit['budget_basis']['charged_before_seconds']
        and local['charged_before_seconds']+upper<=policy['gpu_residency_seconds_max'],
        'run_package_independent_residency_amount_join')
    return {'gpu_residency_seconds_upper':upper,'charged_before_seconds':local['charged_before_seconds'],
        'legacy_first_load_epoch':permit['first_load_epoch'],
        'after_gpu_exit_wait_seconds_not_charged':local['observation_epoch']-end,
        'actual_qualified_gpu_exit_epoch':end,'producer_summary_accepted_as_proof':False}


def verify_prior_absence(value,observation,*,completed):
    """Prospective prior-failure audit; never manufactures waitpid or exit time."""
    require(not completed and type(observation) is dict and set(observation)=={
        'schema_version','qualification_sha256','parent_sha256','boot_id','epoch',
        'target_proc_absent','parent_proc_absent','original_final_sha256','producer_waitpid_proof_missing'},
        'run_package_prior_absence_schema')
    final=value['final'];result=value['stop_rows'][1]['payload']
    require(observation['schema_version']==1 and observation['qualification_sha256']==digest(value['qualification'])
        and observation['parent_sha256']==digest(value['parent']) and observation['boot_id']==value['boot_id']
        and observation['original_final_sha256']==digest(final)
        and observation['target_proc_absent'] is observation['parent_proc_absent'] is True
        and observation['producer_waitpid_proof_missing'] is True
        and type(observation['epoch']) in (int,float) and math.isfinite(observation['epoch'])
        and final['epoch']<=observation['epoch']<=value['epoch']
        and final['child_exit_reaped'] is False and final['child_wait_status'] is None
        and final['stop_result'] is None and final['primary_error_type']=='BrokenPipeError'
        and final['cleanup_errors']==[] and result=={'status':'already_exited','signal_attempts':0,
            'exit_observed':True,'error_type':None}, 'run_package_prior_absence_original_evidence')
    return True
