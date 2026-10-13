"""Independent pre-generation/failure joins. Never imports loader or actors."""
from training.c5_reuse_evidence import exact,is_sha,require,sha
from training.c5_reuse_control_journal import replay_control
from training.c5_reuse_field_journal import replay_records
from training.c5_reuse_field_scope import common_scope
from training.c5_reuse_worker_loop import readiness
from training.c5_reuse_stop import target
from training.c5_recovery_field_permit import validate as validate_permit

def audit_ready(value,binding,wire_ready,load_permit,grant):
    exact(value,('binding','supervisor','lifecycle','worker','supervisor_head','lifecycle_head','worker_head',
                 'qualified_identity','boot_id','model_or_cuda_calls','private_formal_reads'))
    require(value['binding']==binding and all(type(value[k]) is int and value[k]==0 for k in ('model_or_cuda_calls','private_formal_reads')),
            'recovery_ready_proof_scope')
    validate_permit(load_permit,binding,grant)
    replay_control(value['supervisor'],binding,'supervisor',head=value['supervisor_head'])
    replay_control(value['lifecycle'],binding,'worker-lifecycle',head=value['lifecycle_head'])
    replay_records(value['worker'],binding,'worker',value['worker_head'])
    require([r['kind'] for r in value['supervisor']]==['control_open','child_launch_intent','owned_child_qualified']
        and [r['kind'] for r in value['lifecycle']]==['control_open','model_loading_intent','model_loaded','worker_ready_published']
        and [r['kind'] for r in value['worker']]==['open'],'recovery_ready_original_prefix')
    require(all(type(wire_ready[k]) is int and wire_ready[k]==0 for k in
        ('model_requests_before_ready','generation_stages_before_ready')),'recovery_ready_typed_zero_counts')
    q=value['supervisor'][2]['payload'];exact(q,('target','parent_pid','model_loading_started'));target(q['target'])
    require(q['model_loading_started'] is False and q['parent_pid']==value['supervisor'][1]['payload']['parent']['pid']
        and value['qualified_identity']==q['target'] and value['boot_id']==q['target']['boot_id']
        and value['lifecycle'][1]['payload']=={'qualification_sha256':sha(q),'worker_open_head_sha256':value['worker_head']}
        and value['lifecycle'][2]['payload']=={'qualification_sha256':sha(q),'training':False,'parse_repair':False}
        and value['lifecycle'][3]['payload']=={'ready':wire_ready}
        and wire_ready==readiness(binding,sha(q),value['worker_head']), 'recovery_ready_original_qualification_join')
    return sha(value)

def audit_failure(value,binding,*,serve_capture,native_known,expected_gpu_uuid):
    exact(value,('binding','cancelled_before_future_launch','cancellation_record','supervisor','supervisor_head','qualification',
        'shared_stop','boot_id','target_proc_present','compute_returncode','compute_stdout','compute_stderr',
        'gpu_returncode','gpu_stdout','gpu_stderr','model_or_cuda_calls','private_formal_reads'))
    require(value['binding']==binding and value['cancelled_before_future_launch'] is True
        and value['cancellation_record']=={'binding_sha256':sha(binding),'future_launch_allowed':False}
        and all(type(value[k]) is int and value[k]==0 for k in ('model_or_cuda_calls','private_formal_reads')),'recovery_failure_proof_scope')
    rows=value['supervisor'];qualified=value['qualification'];known=False
    if not rows:
        known=qualified is None and value['target_proc_present'] is False and value['shared_stop'] is None
    else:
        replay_control(rows,binding,'supervisor',head=value['supervisor_head'])
        qs=[r for r in rows if r['kind']=='owned_child_qualified'];final=[r for r in rows if r['kind']=='supervisor_final_observation']
        if qualified is None:
            known=not qs and len(final)==1 and final[0]['payload']['child_exit_reaped'] is True
        else:
            require(len(qs)==1 and qs[0]['payload']==qualified,'recovery_failure_qualification_anchor')
            target(qualified['target'])
            known=(value['boot_id']==qualified['target']['boot_id'] and value['target_proc_present'] is False)
    idle=(type(value['compute_returncode']) is int and value['compute_returncode']==0
          and value['compute_stdout'].strip()=='' and value['compute_stderr']==''
          and type(value['gpu_returncode']) is int and value['gpu_returncode']==0 and value['gpu_stderr']=='')
    fields=[s.strip() for s in value['gpu_stdout'].strip().split(',')]
    idle=idle and len(fields)==2 and fields[0]==expected_gpu_uuid and fields[1].isdigit() and int(fields[1])<=32
    return {'raw_anchor_sha256':sha({'gpu':value,'serve_capture':serve_capture,'native_known':native_known}),
        'capture_complete':type(serve_capture) is dict and serve_capture.get('complete_raw_capture') is True,
        'qualified_target_absent':bool(known and idle),'known_native_cleanup_complete':native_known is True,
        'private_exposure_absent':True}
