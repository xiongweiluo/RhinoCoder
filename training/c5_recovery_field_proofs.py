"""Read-only raw qualification/release export. No torch/CUDA/model imports."""
import os
from pathlib import Path
import subprocess
import time
from plugin.rhino_listener.c5_followup_runtime_scope import read_bytes
from training.c5_reuse_evidence import strict,require,sha
from training.c5_reuse_control_journal import read_control
from training.c5_reuse_field_journal import read_record,read_journal
from training.c5_reuse_process_identity import LinuxIdentity
from training.c5_recovery_history import open_qualified_stop,history_guard

def ready_proof(binding,guard):
    guard();state=Path(binding['paths']['state_root'])
    supervisor=read_control(state/'supervisor',binding,'supervisor')
    deadline=time.monotonic()+30
    while True:
        lifecycle=read_control(state/'worker-lifecycle',binding,'worker-lifecycle')
        if any(row['kind']=='worker_ready_published' for row in lifecycle):break
        require(time.monotonic()<deadline,'recovery_ready_publication_deadline');guard();time.sleep(0.05)
    root=state/'worker';names=set(os.listdir(root));require(len(names)==1,'recovery_ready_before_generation')
    last,_=read_record(root,'raw-0000.json');worker=read_journal(root,binding,'worker',last['record_sha256'])
    q=[r['payload'] for r in supervisor if r['kind']=='owned_child_qualified'];require(len(q)==1,'recovery_ready_qualification')
    value={'binding':binding,'supervisor':supervisor,'lifecycle':lifecycle,'worker':worker,
        'supervisor_head':supervisor[-1]['record_sha256'],'lifecycle_head':lifecycle[-1]['record_sha256'],
        'worker_head':last['record_sha256'],'qualified_identity':LinuxIdentity()(q[0]['target']['pid']),
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'model_or_cuda_calls':0,'private_formal_reads':0}
    guard();return value

def failure_proof(binding,history,guard):
    guard(cleanup_only=True);state=Path(binding['paths']['state_root'])
    require(os.path.lexists(state/'cancelled.json'),'recovery_launch_revocation_required')
    rows=read_control(state/'supervisor',binding,'supervisor') if (state/'supervisor').exists() else []
    qualified=[r['payload'] for r in rows if r['kind']=='owned_child_qualified'];require(len(qualified)<=1,'recovery_failure_qualification')
    q=qualified[0] if qualified else None;stop=None
    if q:
        coordinator=open_qualified_stop(Path(binding['paths']['admission_root'])/'engineering-recovery-v3',
            binding['recovery']['scope'],q,history_guard(binding['paths']['admission_root'],'gpu',history))
        try:stop=coordinator.observe()
        finally:coordinator.log.close()
    commands=(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits'],
              ['nvidia-smi','--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'])
    compute,gpu=[subprocess.run(c,capture_output=True,text=True,timeout=15) for c in commands]
    value={'binding':binding,'cancelled_before_future_launch':True,'cancellation_record':strict(read_bytes(state/'cancelled.json',private=True)),'supervisor':rows,
        'supervisor_head':rows[-1]['record_sha256'] if rows else None,'qualification':q,'shared_stop':stop,
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'target_proc_present':os.path.exists('/proc/'+str(q['target']['pid'])) if q else False,
        'compute_returncode':compute.returncode,'compute_stdout':compute.stdout,'compute_stderr':compute.stderr,
        'gpu_returncode':gpu.returncode,'gpu_stdout':gpu.stdout,'gpu_stderr':gpu.stderr,
        'model_or_cuda_calls':0,'private_formal_reads':0}
    guard(cleanup_only=True);return value
