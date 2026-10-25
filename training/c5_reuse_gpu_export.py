"""After-stop read-only export of this new public-eight state only."""
import os
from pathlib import Path
import subprocess
import time
from plugin.rhino_listener.c5_research_channel import private_directory
from training.c5_reuse_evidence import require,canonical
from training.c5_reuse_control_journal import read_control
from training.c5_reuse_field_journal import read_record,read_journal


def export_gpu(binding,plan,guard):
    require(binding['endpoint']=='gpu','reuse_export_gpu');guard(cleanup_only=True)
    state=Path(binding['paths']['state_root'])
    supervisor=read_control(state/'supervisor',binding,'supervisor')
    lifecycle=read_control(state/'worker-lifecycle',binding,'worker-lifecycle')
    q=[r['payload'] for r in supervisor if r['kind']=='owned_child_qualified']
    final=[r['payload'] for r in supervisor if r['kind']=='supervisor_final_observation']
    require(len(q)==len(final)==1 and final[0]['child_exit_reaped'] is True
            and final[0]['child_wait_status']==0,'reuse_export_complete_known_exit')
    root=state/'worker';fd=private_directory(root)
    try:names=set(os.listdir(fd))
    finally:os.close(fd)
    require(0<len(names)<=4096 and names=={'raw-%04d.json'%i for i in range(len(names))},'reuse_export_worker_population')
    last,_=read_record(root,'raw-%04d.json'%(len(names)-1))
    worker=read_journal(root,binding,'worker',last['record_sha256'])
    target=q[0]['target'];boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(boot==target['boot_id']==plan['gpu_process']['boot_id'],'reuse_export_same_boot')
    present=Path('/proc/%d'%target['pid']).exists()
    compute=subprocess.run(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory',
        '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15)
    gpu=subprocess.run(['nvidia-smi','--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'],
        capture_output=True,text=True,timeout=15)
    observation={'epoch':time.time(),'boot_id':boot,'qualified_target':target,'target_proc_present':present,
        'compute_returncode':compute.returncode,'compute_stdout':compute.stdout,'compute_stderr':compute.stderr,
        'gpu_returncode':gpu.returncode,'gpu_stdout':gpu.stdout,'gpu_stderr':gpu.stderr,
        'model_or_cuda_calls':0,'private_formal_reads':0,'physical_release_origin_independently_authenticated':False}
    guard(cleanup_only=True)
    value={'binding':binding,'supervisor':supervisor,'lifecycle':lifecycle,'worker':worker,
        'supervisor_head':supervisor[-1]['record_sha256'],'lifecycle_head':lifecycle[-1]['record_sha256'],
        'worker_head':last['record_sha256'],'release_observation':observation,'whole_field_pass':False}
    require(len(canonical(value))<=64*1024*1024,'reuse_export_capacity')
    return value
