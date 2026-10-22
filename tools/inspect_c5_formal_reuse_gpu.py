#!/usr/bin/env python3
"""Read-only current public assets/environment/admission inventory. No CUDA load.

Fixed model/code/history paths only. No sealed tasks, key, formal state, grant
creation or role initialization. Missing original history is a blocker.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_formal_reuse_scope import REMOTE_SOURCE
from training.c5_followup_compatible_runtime import runtime_preflight,file_sha
from training.c5_followup_gpu_loader import MANIFEST,MANIFEST_SHA,SNAPSHOT,ADAPTER,ADAPTER_FILES,ENV
from training.c5_execution import verify_snapshot
from training.c5_recovery_history import RETIRED

def inspect():
    require(ROOT==REMOTE_SOURCE and sys.platform=='linux','formal_reuse_fixed_gpu_inspection_root')
    require(file_sha(MANIFEST)==MANIFEST_SHA,'formal_reuse_original_model_manifest')
    snapshot=verify_snapshot(SNAPSHOT,MANIFEST)
    adapter={n:file_sha(ADAPTER/n) for n in ADAPTER_FILES}
    require(adapter==ADAPTER_FILES,'formal_reuse_checkpoint_bytes_changed')
    runtime,inventory=runtime_preflight(ENV)
    root=Path('/data/c5-reuse-global-admission-v1')
    require(root.is_dir() and (root/'engineering-recovery-v3').is_dir(),
        'formal_reuse_original_nonempty_gpu_history_missing')
    pins={p.relative_to(root).as_posix():file_sha(p) for p in sorted(root.rglob('*'))
        if 'formal-reuse-v1' not in p.relative_to(root).parts and p.is_file()}
    require(all(not p.is_symlink() for p in root.rglob('*')),'formal_reuse_history_alias')
    retired={}
    for name in RETIRED:
        state=root.parent/(name+'-state')
        require(not (state/'owner-approval.json').exists(),'formal_reuse_retired_grant_restored')
        for n in ('entry-retired-no-retry.json','owner-approval.retired-no-retry.json'):
            p=state/n;retired[p.relative_to(root.parent).as_posix()]=file_sha(p)
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.total,memory.used','--format=csv,noheader,nounits'],text=True,timeout=15)
    compute=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True,timeout=15)
    source=json.loads((ROOT/'eval/c5/formal-reuse-runtime-freeze-20261022.json').read_bytes())['source_files']
    require(all(file_sha(ROOT/n)==h for n,h in source.items()),'formal_reuse_gpu_deployed_source_bytes')
    return {'epoch':time.time(),'endpoint':'gpu','full_bytes_verified':True,'environment':runtime['environment'],
        'environment_inventory_sha256':digest(inventory),'snapshot':snapshot,'adapter_files':adapter,
        'deployed_source_inventory_sha256':digest(source),'gpu_boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'uid':os.getuid(),'observation':{'gpu_stdout':gpu,'compute_stdout':compute},
        'admission_review':{'global_files':pins,'retired_files':retired,
            'global_top_level':sorted(p.name for p in root.iterdir() if p.name!='formal-reuse-v1')},
        'model_or_cuda_calls':0,'private_formal_reads':0,'new_admission_created':False}
if __name__=='__main__':print(json.dumps(inspect(),sort_keys=True))
