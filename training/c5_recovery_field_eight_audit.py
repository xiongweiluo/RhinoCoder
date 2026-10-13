"""Independent public-eight field join under the explicitly limited guarantee.

The external custodian record is an owner statement. Byte binding never
proves cryptographic human origin, hidden generation absence or memory erasure.
No original/formal private cases or producer summaries are used as scores.
"""
import math
from training.c5_reuse_evidence import require,sha,exact
from training.c5_reuse_field_scope import common_scope
from training.c5_recovery_field_gpu_audit import audit_gpu_entry
from training.c5_reuse_field_transport_audit import audit_join
from training.c5_reuse_native_audit import audit_native_eight
from training.c5_reuse_control_journal import replay_control
from training.c5_reuse_evidence import canonical,raw_sha


def audit_release(observation,binding,plan,qualification,budget):
    exact(observation,('epoch','boot_id','qualified_target','target_proc_present','compute_returncode','compute_stdout',
        'compute_stderr','gpu_returncode','gpu_stdout','gpu_stderr','model_or_cuda_calls','private_formal_reads',
        'physical_release_origin_independently_authenticated'))
    require(observation['qualified_target']==qualification['target']
        and observation['boot_id']==plan['gpu_process']['boot_id']==qualification['target']['boot_id']
        and observation['target_proc_present'] is False
        and type(observation['compute_returncode']) is int and observation['compute_returncode']==0
        and observation['compute_stdout'].strip()=='' and observation['compute_stderr']==''
        and type(observation['gpu_returncode']) is int and observation['gpu_returncode']==0
        and observation['gpu_stderr']=='' and observation['model_or_cuda_calls']==observation['private_formal_reads']==0
        and observation['physical_release_origin_independently_authenticated'] is False,'reuse_field_release_raw')
    fields=[x.strip() for x in observation['gpu_stdout'].strip().split(',')]
    require(len(fields)==2 and fields[0]==plan['gpu_process']['gpu_uuid'] and fields[1].isdigit()
            and int(fields[1])<=32,'reuse_field_same_gpu_idle_observation')
    epoch=observation['epoch'];require(type(epoch) in (int,float) and math.isfinite(epoch)
        and budget['start_epoch']<=epoch<=budget['start_epoch']+budget['reserved_wall_seconds'],
        'reuse_field_release_within_reserved_wall')
    return {'qualified_process_absence_and_idle_gpu_observed':True,
            'conservative_elapsed_to_release_observation_seconds':epoch-budget['start_epoch'],
            'physical_origin_cryptographically_proven':False}


def audit_field_eight(*,mac,gpu,spec,runtime,plan,plan_raw,controller,controller_head,export,
                     native,native_head,public,schemas,slot_inputs,hub_secret,tokenizer,
                     external,write_assertions,actual_deployment_receipts,mac_lifecycle,mac_lifecycle_head,gpu_export_raw,campaign_initial_scope,campaign_rows,load_permit,grant,ready_proof):
    from training.c5_recovery_field_permit import validate as validate_permit
    from training.c5_recovery_field_audit import audit_ready
    from training.c5_recovery_controller import replay
    from training.c5_reuse_evidence import ZERO
    require(type(campaign_rows) is list and 1<=len(campaign_rows)<=512,'recovery_joint_campaign_population')
    previous=ZERO
    for i,row in enumerate(campaign_rows):
        exact(row,('seq','previous_sha256','binding_sha256','kind','payload','record_sha256'))
        require(type(row['seq']) is int and row['seq']==i and row['previous_sha256']==previous
            and row['binding_sha256']==sha(campaign_initial_scope)
            and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),'recovery_joint_campaign_raw_chain')
        previous=row['record_sha256']
    state=replay(campaign_initial_scope,campaign_rows)
    require(state['scope']==mac['recovery']['scope'] and state['attempts']==mac['recovery']['attempt']
        and state['status']=='AWAITING_INDEPENDENT_AUDIT' and state['formal_consumed'] is False,
        'recovery_joint_completed_campaign_consumption')
    validate_permit(load_permit,gpu,grant)
    require(load_permit['rows']==campaign_rows[:len(load_permit['rows'])]
        and load_permit['preload_confirmation']==state['receipt'],'recovery_joint_original_preload_permit_prefix')
    wire_ready=next(row['payload']['ready'] for row in export['lifecycle'] if row['kind']=='worker_ready_published')
    ready_anchor=audit_ready(ready_proof,gpu,wire_ready,load_permit,grant)
    active_ready=[row for row in campaign_rows if row['kind']=='worker_ready'
                  and row['payload']['attempt']==state['attempts']]
    require(len(active_ready)==1 and active_ready[0]['payload']['raw_anchor_sha256']==ready_anchor
        and ready_proof['supervisor']==export['supervisor'][:3]
        and ready_proof['lifecycle']==export['lifecycle'][:4]
        and ready_proof['worker']==export['worker'][:1],'recovery_joint_pre_generation_ready_proof')
    require(common_scope(mac)==common_scope(gpu) and export['binding']==gpu,'reuse_field_master_scope')
    exact(external,('actor','study_id','instance_id','spec_sha256','runtime_sha256','controller_head_sha256',
        'native_head_sha256','gpu_export_sha256','host_seal_sha256','preload_snapshot','preload_receipt',
        'captured_outside_producer','private_custody_confirmed','mac_lifecycle_head_sha256'))
    require(external['actor']=='repository_owner' and all(external[k]==mac[k] for k in
        ('study_id','instance_id','spec_sha256','runtime_sha256')) and external['captured_outside_producer'] is True
        and external['private_custody_confirmed'] is True and external['controller_head_sha256']==controller_head
        and external['native_head_sha256']==native_head and external['gpu_export_sha256']==sha(export),
        'reuse_field_external_owner_custody_binding')
    require(external['mac_lifecycle_head_sha256']==mac_lifecycle_head
            and gpu_export_raw==canonical(export)+b'\n','reuse_field_external_export_serialization')
    replay_control(mac_lifecycle,mac,'controller-lifecycle',head=mac_lifecycle_head)
    pattern=['control_open','remote_launch_intent','raw_streams_created_before_launch','preload_permit_sent',
        'remote_ready_received','ready-proof_raw_streams_final_observed','external_begin_send_intent','external_begin_sent',
        'worker_close_send_intent','worker_close_received','remote_supervisor_exit_observed','raw_streams_final_observed',
        'export_raw_streams_final_observed','gpu_export_observed']
    require([r['kind'] for r in mac_lifecycle]==pattern,'reuse_field_mac_launch_and_cleanup_population')
    def mp(kind):return next(r['payload'] for r in mac_lifecycle if r['kind']==kind)
    def gp(kind):return next(r['payload'] for r in export['lifecycle'] if r['kind']==kind)
    require(mp('preload_permit_sent')=={'permit_sha256':sha(load_permit)}
        and mp('remote_ready_received')['ready']==gp('worker_ready_published')['ready']
        and mp('external_begin_send_intent')['begin']==gp('worker_begin_record_received')['begin']
        and mp('external_begin_sent')['begin_sha256']==sha(mp('external_begin_send_intent')['begin'])
        and mp('worker_close_received')['receipt']==gp('worker_close_recorded')['receipt']
        and mp('remote_supervisor_exit_observed')=={'ssh_exit_status':0,'physical_gpu_release_verified':None}
        and mp('gpu_export_observed')=={'raw_sha256':raw_sha(gpu_export_raw),'bytes':len(gpu_export_raw),
                'human_or_physical_origin_proven_by_export_hash':False}
        and native[-1]['payload']['worker_close']==mp('worker_close_received')['receipt']
        and native[-1]['payload']['gpu_export_raw_sha256']==raw_sha(gpu_export_raw),
        'reuse_field_mac_gpu_native_close_and_ready_join')
    require(actual_deployment_receipts.keys()=={'mac','gpu'} and all(
        r['spec_sha256']==mac['spec_sha256'] and r['runtime_sha256']==mac['runtime_sha256']
        and r['source_inventory_sha256']==sha(runtime['source_files'])
        and r['actual_source_bytes_verified'] is r['actual_installed_asset_bytes_verified'] is True
        for r in actual_deployment_receipts.values()),'reuse_field_actual_byte_receipts_required')
    entry=audit_gpu_entry(export['supervisor'],export['lifecycle'],export['worker'],gpu,plan,spec['resources'],
        spec=spec,runtime=runtime,plan_raw=plan_raw,supervisor_head=export['supervisor_head'],
        lifecycle_head=export['lifecycle_head'],worker_head=export['worker_head'],plans=public['task_plans'],tokenizer=tokenizer)
    require(entry['complete_eight_slot_entry_records'],'reuse_field_incomplete_gpu')
    wire=audit_join(controller,export['worker'],mac,gpu,controller_head,export['worker_head'],public['task_plans'],tokenizer)
    require(wire['complete_raw_join'] and wire['model_acknowledgements']==8,'reuse_field_incomplete_wire')
    qualification=next(r['payload'] for r in export['supervisor'] if r['kind']=='owned_child_qualified')
    budget=next(r['payload']['budget'] for r in export['supervisor'] if r['kind']=='supervisor_final_observation')
    release=audit_release(export['release_observation'],gpu,plan,qualification,budget)
    begin=next(r['payload']['begin'] for r in export['lifecycle'] if r['kind']=='worker_begin_record_received')
    require(begin['preload_snapshot']==external['preload_snapshot']
        and begin['preload_receipt']==external['preload_receipt'],'recovery_field_external_preload_join')
    from training.c5_recovery_field_shared_stop_audit import audit_shared_stop
    audit_shared_stop(export['shared_stop_rows'],export['shared_stop_binding'],qualification,gpu,
                      expected_result=next(r['payload']['result'] for r in export['supervisor'] if r['kind']=='coordinated_stop_observed'))
    native_result=audit_native_eight(native,mac,native_head,controller,controller_head,public,schemas,slot_inputs,hub_secret,
        source_files=runtime['source_files'],external_host_seal_sha256=external['host_seal_sha256'],write_assertions=write_assertions)
    require(begin['host_baseline_head_sha256']==native[1]['payload']['ready']['host_baseline_head_sha256'],
            'reuse_field_baseline_ready_join')
    # Retain the historical engineering criterion. Semantic outcomes are
    # separately disclosed; they do not replace the later formal 14/20 gate.
    engineering=native_result['independently_counted_native_writes']>=1 and native_result['independently_counted_native_reads']>=1
    return {'status':'PASS' if engineering else 'INCOMPLETE_ENGINEERING_COVERAGE_NO_RETRY',
        'complete_original_raw_joint_audit':True,'engineering_gate_passed':engineering,
        'development_all_eight_semantic_outcomes_passed':native_result['all_eight_quality_passed'],
        'native_writes':native_result['independently_counted_native_writes'],
        'native_reads':native_result['independently_counted_native_reads'],
        'recorded_generation_attempts':entry['generation']['recorded_generation_attempts'],
        'actual_physical_generation_total_independently_proven':None,'quality_by_slot':native_result['quality_by_slot'],
        'release':release,'owner_custody_statement_bound':True,'cryptographic_human_origin_proven':False,
        'full_host_byte_closure_or_hidden_handler_absence_proven':False,'memory_erasure_proven':False,
        'original_c5_no_go_changed':False,'formal_execution_authorized':False,'retry_allowed':False}
