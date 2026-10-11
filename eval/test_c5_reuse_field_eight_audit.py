"""Raw target release negatives; no actual process or GPU inspection."""
import copy
import pytest
from eval.test_c5_reuse_gpu_entry_audit import bundle
from training.c5_reuse_field_eight_audit import audit_release


def release_arguments(tmp_path):
    b=bundle(tmp_path);q=b['supervisor'][2]['payload'];budget=b['supervisor'][-1]['payload']['budget']
    observation={'epoch':110,'boot_id':q['target']['boot_id'],'qualified_target':q['target'],
        'target_proc_present':False,'compute_returncode':0,'compute_stdout':'','compute_stderr':'',
        'gpu_returncode':0,'gpu_stdout':b['plan']['gpu_process']['gpu_uuid']+', 11\n','gpu_stderr':'',
        'model_or_cuda_calls':0,'private_formal_reads':0,'physical_release_origin_independently_authenticated':False}
    return observation,b['binding'],b['plan'],q,budget


def test_absent_exact_owned_target_idle_gpu_and_full_wall_reservation(tmp_path):
    result=audit_release(*release_arguments(tmp_path))
    assert result['qualified_process_absence_and_idle_gpu_observed']
    assert result['conservative_elapsed_to_release_observation_seconds']==10
    assert not result['physical_origin_cryptographically_proven']


@pytest.mark.parametrize('change',['present','other_pid','boot','compute','compute_error','gpu_error','other_gpu',
                                  'memory','late','nan','pretend_origin','generation'])
def test_residency_or_missing_or_wrong_raw_release_blocks_complete_gate(tmp_path,change):
    o,b,p,q,budget=release_arguments(tmp_path);o=copy.deepcopy(o)
    if change=='present':o['target_proc_present']=True
    elif change=='other_pid':o['qualified_target']['pid']+=1
    elif change=='boot':o['boot_id']='0'*36
    elif change=='compute':o['compute_stdout']='201, python, 19000\n'
    elif change=='compute_error':o['compute_returncode']=1
    elif change=='gpu_error':o['gpu_returncode']=1
    elif change=='other_gpu':o['gpu_stdout']='GPU-other, 11\n'
    elif change=='memory':o['gpu_stdout']=p['gpu_process']['gpu_uuid']+', 19000\n'
    elif change=='late':o['epoch']=3701
    elif change=='nan':o['epoch']=float('nan')
    elif change=='pretend_origin':o['physical_release_origin_independently_authenticated']=True
    else:o['model_or_cuda_calls']=1
    with pytest.raises(ValueError):audit_release(o,b,p,q,budget)
