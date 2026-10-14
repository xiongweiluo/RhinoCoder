"""Supplemental READ-ONLY verifier for completed retained-clock campaigns.

The original frozen verifier is preserved and its rejection is reported.
Only _budget differs: observed elapsed time must satisfy BOTH accepted upper
bounds. A maximum shared cap is not a new full reservation from first load.
No model, Rhino, grants, consumption or producer record is changed here.
"""
import math
from plugin.rhino_listener.c5_recovery_profile import PLAN,PYTHON,GPU_FLAGS,ENTRY,RECOVERY_POLICY
import hashlib
from training.c5_reuse_evidence import exact,require,sha,is_sha,raw_sha,strict
from training.c5_reuse_control_journal import replay_control
from training.c5_reuse_field_scope import common_scope,PROTOCOL
from training.c5_reuse_generation_audit import audit_generation
from training.c5_reuse_stop import target

ORDER=('write-base','write-lora','read-lora','read-base','clarify-base','clarify-lora','unsupported-lora','unsupported-base')
STOP_POLICY=RECOVERY_POLICY


def _one(rows,kind):
    values=[r for r in rows if r['kind']==kind]
    require(len(values)==1,'entry_audit_missing_or_duplicate_'+kind)
    return values[0]


def _budget(value,resources):
    exact(value,('elapsed_wall_seconds','start_epoch','operational_cap_seconds','reserved_wall_seconds',
                 'stop_reserve_seconds','within_reserved_wall_seconds','prior_cumulative_upper_bound_seconds',
                 'physical_gpu_release_independently_verified'))
    require(all(type(value[k]) in (int,float) and math.isfinite(value[k]) and value[k]>=0 for k in
                ('elapsed_wall_seconds','start_epoch','operational_cap_seconds','reserved_wall_seconds','stop_reserve_seconds'))
        and value['start_epoch']>0 and value['stop_reserve_seconds']==60
        and value['reserved_wall_seconds']==resources['development_seconds_max']
        and value['operational_cap_seconds']==resources['development_seconds_max']-60
        and value['start_epoch']+value['elapsed_wall_seconds']<=min(
            value['start_epoch']+resources['development_seconds_max'],resources['generation_cutoff_epoch'])
        and value['prior_cumulative_upper_bound_seconds'] is None
        and type(value['within_reserved_wall_seconds']) is bool
        and value['within_reserved_wall_seconds']==(value['elapsed_wall_seconds']<=resources['development_seconds_max'])
        and value['physical_gpu_release_independently_verified'] is None,'recovery_audit_shared_wall_budget')


def audit_gpu_entry(supervisor,lifecycle,worker,binding,plan,resources,*,spec,runtime,plan_raw,
                    supervisor_head,lifecycle_head,worker_head,plans,tokenizer):
    require(binding['endpoint']=='gpu' and all(is_sha(h) for h in (supervisor_head,lifecycle_head,worker_head)),
            'entry_audit_endpoint_external_anchors')
    require(sha(spec)==binding['spec_sha256'] and sha(runtime)==binding['runtime_sha256']
            and resources==spec['resources']==runtime['resources']
            and strict(plan_raw,limit=2*1024*1024)==plan
            and raw_sha(plan_raw)==runtime['source_files'].get(PLAN)
            and sha(plan['environment'])==runtime['environment_sha256']
            and sha(plan['model_assets'])==runtime['model_assets_sha256']
            and sha(plan['host_readable_files'])==runtime['host_readable_files_sha256']
            and plan['gpu_process']['stop_policy']==STOP_POLICY,'entry_audit_frozen_plan_and_policy')
    replay_control(supervisor,binding,'supervisor',head=supervisor_head)
    replay_control(lifecycle,binding,'worker-lifecycle',head=lifecycle_head)
    generation=audit_generation(worker,binding,worker_head,plans=plans,tokenizer=tokenizer)
    require(set(plans)==set(ORDER),'entry_audit_eight_plan_population')
    permitted={'control_open','child_launch_intent','owned_child_qualified','coordinated_stop_observed','supervisor_final_observation'}
    require(all(r['kind'] in permitted for r in supervisor),'entry_audit_unknown_supervisor_event')
    launch=_one(supervisor,'child_launch_intent');qualification=_one(supervisor,'owned_child_qualified')
    stop=_one(supervisor,'coordinated_stop_observed');final=_one(supervisor,'supervisor_final_observation')
    exact(launch['payload'],('parent','worker_open_head_sha256','policy_sha256','budget'))
    q=qualification['payload'];exact(q,('target','parent_pid','model_loading_started'))
    parent=launch['payload']['parent'];child=q['target'];target(parent);target(child)
    require(launch['seq']<qualification['seq']<stop['seq']<final['seq'] and child['pid']!=parent['pid']
            and q['parent_pid']==parent['pid'] and q['model_loading_started'] is False
            and launch['payload']['policy_sha256']==sha(plan['gpu_process']['stop_policy'])
            and all(parent[k]==child[k] for k in ('uid','boot_id','executable_sha256','argv_sha256','cwd'))
            and launch['payload']['worker_open_head_sha256']==worker[0]['record_sha256'],'entry_audit_preload_owned_child')
    argv=[PYTHON,*GPU_FLAGS,binding['paths']['source_root']+'/'+ENTRY,'--serve','--attempt',str(binding['recovery']['attempt'])]
    require(parent['uid']==plan['gpu_process']['uid'] and parent['boot_id']==plan['gpu_process']['boot_id']
            and parent['cwd']==binding['paths']['source_root']
            and parent['executable_sha256']==plan['environment']['gpu']['executable_sha256']
            and parent['argv_sha256']==hashlib.sha256(b'\0'.join(s.encode() for s in argv)+b'\0').hexdigest(),
            'entry_audit_fixed_parent_process')
    exact(stop['payload'],('result','qualification_sha256'))
    require(stop['payload']['qualification_sha256']==sha(q),'recovery_audit_stop_qualification')
    result=stop['payload']['result']
    exact(result,('status','signal_attempts','exit_observed','error_type','retry_signal_allowed'))
    require(result['status']=='already_exited' and result['signal_attempts']==0
        and result['exit_observed'] is True and result['error_type'] is None
        and result['retry_signal_allowed'] is False,'recovery_audit_normal_stop')
    fp=final['payload'];exact(fp,('child_wait_status','child_exit_reaped','budget','physical_gpu_release_verified','whole_field_pass'))
    require(type(fp['child_exit_reaped']) is bool and fp['child_exit_reaped']==(fp['child_wait_status'] is not None)
            and (fp['child_wait_status'] is None or type(fp['child_wait_status']) is int)
            and fp['physical_gpu_release_verified'] is None and fp['whole_field_pass'] is False,'entry_audit_final_observation')
    _budget(launch['payload']['budget'],resources);_budget(fp['budget'],resources)
    require(fp['budget']['start_epoch']==launch['payload']['budget']['start_epoch']
            and fp['budget']['elapsed_wall_seconds']>=launch['payload']['budget']['elapsed_wall_seconds'],'entry_audit_cumulative_elapsed')
    pattern=['control_open','model_loading_intent','model_loaded','worker_ready_published','worker_begin_record_received',
             'worker_close_recorded','worker_budget_observation']
    complete_lifecycle=[r['kind'] for r in lifecycle]==pattern
    if complete_lifecycle:
        loading,l,ready,begin,closing,settlement=[r['payload'] for r in lifecycle[1:]]
        require(loading=={'qualification_sha256':sha(q),'worker_open_head_sha256':worker[0]['record_sha256']}
                and l=={'qualification_sha256':sha(q),'training':False,'parse_repair':False},'entry_audit_loading_binding')
        exact(ready,('ready',));r=ready['ready']
        require(all(type(r[k]) is int for k in ('model_requests_before_ready','generation_stages_before_ready'))
                and r=={'kind':'reuse_worker_loaded_ready','protocol':PROTOCOL,'scope_sha256':sha(common_scope(binding)),
            'qualification_sha256':sha(q),'worker_open_head_sha256':worker[0]['record_sha256'],
            'model_requests_before_ready':0,'generation_stages_before_ready':0},'entry_audit_ready_binding')
        exact(begin,('begin','human_provenance_independently_verified'))
        from plugin.rhino_listener.c5_recovery_scope import validate_preload_begin
        v=begin['begin'];validate_preload_begin(binding,v)
        require(begin['human_provenance_independently_verified'] is False
            and v['worker_readiness_sha256']==sha(r),'recovery_audit_preload_ready_join')
        require(closing=={'receipt':{'kind':'reuse_worker_closed','protocol':PROTOCOL,'scope_sha256':sha(common_scope(binding)),
            'worker_final_head_sha256':worker_head,'requests':generation['requests_complete'],
            'generation_intents':generation['recorded_generation_attempts'],'physical_gpu_release_verified':None,'whole_field_pass':False}},
            'entry_audit_close_raw_generation_join')
        _budget(settlement,resources)
        require(settlement['start_epoch']==fp['budget']['start_epoch']
                and settlement['elapsed_wall_seconds']<=fp['budget']['elapsed_wall_seconds'],'entry_audit_child_wall_join')
    requests=[r['payload']['envelope']['request'] for r in worker if r['kind']=='request_intent']
    exact_order=[(r['slot_id'],r['step_index']) for r in requests]==[(slot,0) for slot in ORDER]
    complete=complete_lifecycle and exact_order and generation['coverage_complete']
    complete=complete and fp['child_exit_reaped'] and fp['child_wait_status']==0 and result['exit_observed']
    complete=complete and result['signal_attempts']==0 and result['status']=='already_exited' and fp['budget']['within_reserved_wall_seconds']
    return {'complete_eight_slot_entry_records':complete,'generation':generation,
            'original_order_recomputed':exact_order,'preload_qualification_record_bound':True,
            'recorded_signal_attempts':result['signal_attempts'],'elapsed_wall_seconds':fp['budget']['elapsed_wall_seconds'],
            'human_readiness_or_approval_origin_independently_verified':False,
            'physical_gpu_release_independently_verified':None,'native_geometry_permission_cleanup_verified':False,
            'whole_field_pass':False,'execution_ready':False}
