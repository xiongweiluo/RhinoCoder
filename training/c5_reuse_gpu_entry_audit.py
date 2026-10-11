"""Independent raw entry audit; never imports launcher, loader or generators.

Integrity with supplied anchors is not human-origin, physical-GPU, Rhino,
native permission/geometry, cleanup, or complete field PASS evidence.
"""
import math
import hashlib
from training.c5_reuse_evidence import exact,require,sha,is_sha,raw_sha,strict
from training.c5_reuse_control_journal import replay_control
from training.c5_reuse_field_scope import common_scope,PROTOCOL
from training.c5_reuse_generation_audit import audit_generation
from training.c5_reuse_stop import target

ORDER=('write-base','write-lora','read-lora','read-base','clarify-base','clarify-lora','unsupported-lora','unsupported-base')
STOP_POLICY={'kind':'one_new_owned_child_pidfd_only','qualify_before_model_loading':True,
             'signal':'SIGTERM','signals_max':1,'exit_wait_seconds':30,'name_kill_allowed':False,
             'reconnect_or_retry_allowed':False,'signal_escalation_allowed':False}


def _one(rows,kind):
    values=[r for r in rows if r['kind']==kind]
    require(len(values)==1,'entry_audit_missing_or_duplicate_'+kind)
    return values[0]


def _budget(value,resources):
    revised=resources.get('resource_policy')=='incremental_reuse_unknown_history_v1'
    exact(value,('elapsed_wall_seconds','start_epoch','operational_cap_seconds','reserved_wall_seconds',
                 'stop_reserve_seconds','within_reserved_wall_seconds','prior_cumulative_upper_bound_seconds',
                 'physical_gpu_release_independently_verified'))
    require(all(type(value[k]) in (int,float) and math.isfinite(value[k]) and value[k]>=0 for k in
                ('elapsed_wall_seconds','start_epoch','operational_cap_seconds','reserved_wall_seconds','stop_reserve_seconds'))
            and value['start_epoch']>0 and value['stop_reserve_seconds']==60 and value['operational_cap_seconds']>0
            and value['operational_cap_seconds']==value['reserved_wall_seconds']-60
            and (not revised or (resources['prior_cumulative_upper_bound_seconds'] is None
                  and resources['original_cumulative_compliance_claimed'] is False
                  and value['start_epoch']+18000<=resources['generation_cutoff_epoch']))
            and value['reserved_wall_seconds']==(18000 if revised else min(resources['development_seconds_max'],resources['remaining_gpu_seconds'],
                  resources['original_cumulative_seconds_max']-resources['prior_cumulative_upper_bound_seconds'],
                  resources['generation_cutoff_epoch']-value['start_epoch']))
            and type(value['within_reserved_wall_seconds']) is bool
            and value['within_reserved_wall_seconds']==(value['elapsed_wall_seconds']<=value['reserved_wall_seconds'])
            and value['prior_cumulative_upper_bound_seconds']==resources['prior_cumulative_upper_bound_seconds']
            and value['physical_gpu_release_independently_verified'] is None,'entry_audit_wall_reservation')


def audit_gpu_entry(supervisor,lifecycle,worker,binding,plan,resources,*,spec,runtime,plan_raw,
                    supervisor_head,lifecycle_head,worker_head,plans,tokenizer):
    require(binding['endpoint']=='gpu' and all(is_sha(h) for h in (supervisor_head,lifecycle_head,worker_head)),
            'entry_audit_endpoint_external_anchors')
    require(sha(spec)==binding['spec_sha256'] and sha(runtime)==binding['runtime_sha256']
            and resources==spec['resources']==runtime['resources']
            and strict(plan_raw,limit=2*1024*1024)==plan
            and raw_sha(plan_raw)==runtime['source_files']['eval/c5/reuse-field-environment-plan-20261011-a.json']
            and sha(plan['environment'])==runtime['environment_sha256']
            and sha(plan['model_assets'])==runtime['model_assets_sha256']
            and sha(plan['host_readable_files'])==runtime['host_readable_files_sha256']
            and plan['gpu_process']['stop_policy']==STOP_POLICY,'entry_audit_frozen_plan_and_policy')
    replay_control(supervisor,binding,'supervisor',head=supervisor_head)
    replay_control(lifecycle,binding,'worker-lifecycle',head=lifecycle_head)
    generation=audit_generation(worker,binding,worker_head,plans=plans,tokenizer=tokenizer)
    require(set(plans)==set(ORDER),'entry_audit_eight_plan_population')
    permitted={'control_open','child_launch_intent','owned_child_qualified','owned_signal_intent',
               'owned_stop_result','supervisor_final_observation'}
    require(all(r['kind'] in permitted for r in supervisor),'entry_audit_unknown_supervisor_event')
    launch=_one(supervisor,'child_launch_intent');qualification=_one(supervisor,'owned_child_qualified')
    stop=_one(supervisor,'owned_stop_result');final=_one(supervisor,'supervisor_final_observation')
    exact(launch['payload'],('parent','worker_open_head_sha256','policy_sha256','budget'))
    q=qualification['payload'];exact(q,('target','parent_pid','policy_sha256','model_loading_started'))
    parent=launch['payload']['parent'];child=q['target'];target(parent);target(child)
    require(launch['seq']<qualification['seq']<stop['seq']<final['seq'] and child['pid']!=parent['pid']
            and q['parent_pid']==parent['pid'] and q['model_loading_started'] is False
            and q['policy_sha256']==launch['payload']['policy_sha256']==sha(plan['gpu_process']['stop_policy'])
            and all(parent[k]==child[k] for k in ('uid','boot_id','executable_sha256','argv_sha256','cwd'))
            and launch['payload']['worker_open_head_sha256']==worker[0]['record_sha256'],'entry_audit_preload_owned_child')
    argv=['/data/conda-envs/rhinocoder/bin/python3.11','-I','-B',
          binding['paths']['source_root']+'/tools/run_c5_reuse_gpu_entry.py','--serve']
    require(parent['uid']==plan['gpu_process']['uid'] and parent['boot_id']==plan['gpu_process']['boot_id']
            and parent['cwd']==binding['paths']['source_root']
            and parent['executable_sha256']==plan['environment']['gpu']['executable_sha256']
            and parent['argv_sha256']==hashlib.sha256(b'\0'.join(s.encode() for s in argv)+b'\0').hexdigest(),
            'entry_audit_fixed_parent_process')
    signals=[r for r in supervisor if r['kind']=='owned_signal_intent']
    require(len(signals)<=1,'entry_audit_more_than_one_signal')
    result=stop['payload'];exact(result,('signal_attempts','exit_observed','gpu_release_verified','status'))
    require(type(result['signal_attempts']) is int and result['signal_attempts'] in (0,1)
            and type(result['exit_observed']) is bool and result['gpu_release_verified'] is None
            and result['status'] in ('unknown_no_retry','already_exited_no_signal','exit_observed_pending_gpu'),
            'entry_audit_stop_result')
    if signals:
        intent=signals[0]
        require(qualification['seq']<intent['seq']<stop['seq']
                and intent['payload']=={'target_sha256':sha(child),'signal':'SIGTERM','attempts_max':1},'entry_audit_signal_scope')
    require(result['signal_attempts']<=len(signals)
            and (result['signal_attempts']!=0 or result['status']!='exit_observed_pending_gpu'), 'entry_audit_signal_attempt_order')
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
        exact(begin['begin'],('kind','protocol','scope_sha256','owner_readiness'))
        v=begin['begin'];owner=v['owner_readiness']
        exact(owner,('study_id','instance_id','spec_sha256','runtime_sha256','host_baseline_head_sha256',
                     'worker_readiness_sha256','actor','captured_after_host_baseline','approved_generation_start'))
        require(begin['human_provenance_independently_verified'] is False
                and v['kind']=='reuse_begin_after_external_readiness' and v['protocol']==PROTOCOL
                and v['scope_sha256']==sha(common_scope(binding))
                and all(owner[k]==binding[k] for k in ('study_id','instance_id','spec_sha256','runtime_sha256'))
                and owner['worker_readiness_sha256']==sha(r) and is_sha(owner['host_baseline_head_sha256'])
                and owner['actor']=='repository_owner' and owner['captured_after_host_baseline'] is True
                and owner['approved_generation_start'] is True,'entry_audit_external_ready_matching_not_origin')
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
    complete=complete and result['signal_attempts']==0 and result['status']=='already_exited_no_signal' and fp['budget']['within_reserved_wall_seconds']
    return {'complete_eight_slot_entry_records':complete,'generation':generation,
            'original_order_recomputed':exact_order,'preload_qualification_record_bound':True,
            'recorded_signal_attempts':result['signal_attempts'],'elapsed_wall_seconds':fp['budget']['elapsed_wall_seconds'],
            'human_readiness_or_approval_origin_independently_verified':False,
            'physical_gpu_release_independently_verified':None,'native_geometry_permission_cleanup_verified':False,
            'whole_field_pass':False,'execution_ready':False}
