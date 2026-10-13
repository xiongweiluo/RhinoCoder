#!/usr/bin/env python3
"""Read-only actual candidate preflight. NEVER initializes approval/actors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--endpoint',choices=('mac','gpu'),required=True);a=p.parse_args()
    from plugin.rhino_listener.c5_recovery_profile import SPEC,RUNTIME,PLAN,HISTORY,INSTANCE,PYTHON
    from plugin.rhino_listener.c5_recovery_scope import paths
    from plugin.rhino_listener.c5_recovery_runtime_scope import SourceGuard,read_bytes
    from plugin.rhino_listener.c5_recovery_plan import validate
    from training.c5_reuse_evidence import require,strict,sha
    require(ROOT==Path(paths(a.endpoint,1)['source_root']) and ROOT.resolve()==ROOT,'recovery_readonly_fixed_source_root')
    s,r,plan,h=[strict(read_bytes(ROOT/n,limit=16*1024*1024),limit=16*1024*1024) for n in (SPEC,RUNTIME,PLAN,HISTORY)]
    validate(s,r,plan,h)
    source=SourceGuard(ROOT,r['source_files'],private_prefixes=('__main__',));source()
    from training.c5_recovery_history import history_guard
    hg=history_guard(paths(a.endpoint,1)['admission_root'],a.endpoint,h);hg()
    from training.c5_reuse_evidence import canonical
    result={'endpoint':a.endpoint,'epoch':time.time(),'source_bytes_verified':True,
        'source_inventory_sha256':sha(r['source_files']),'candidate_spec_sha256':sha(s),
        'candidate_runtime_sha256':sha(r),'history_sha256':sha(h),'same_global_history_verified':True,
        'model_or_cuda_calls':0,'private_formal_reads':0,'new_grants_or_campaign_state_created':False,
        'candidate_phase':s['phase'],'actual_lease_report_is_separate_input':True}
    if a.endpoint=='gpu':
        require(sys.platform=='linux' and Path(sys.executable).resolve()==Path(PYTHON)
            and hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal'),'recovery_readonly_compatible_pidfd')
        fd=os.pidfd_open(os.getpid(),0);os.close(fd) # pin only; NEVER sends any signal.
        from training.c5_followup_gpu_loader import preflight
        inventory=preflight(r,plan,source)
        require('torch' not in sys.modules and 'peft' not in sys.modules,'recovery_readonly_no_model_import')
        uuid=subprocess.check_output(['nvidia-smi','--query-gpu=uuid','--format=csv,noheader'],text=True,timeout=15).strip()
        result.update(environment_sha256=sha(plan['environment']['gpu']),model_assets_sha256=sha(plan['model_assets']),
            original_model_assets_full_bytes_verified=True,compatible_environment_full_bytes_verified=True,
            distribution_files_reverified=len(inventory),gpu_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            uid=os.getuid(),gpu_uuid=uuid,actual_pidfd_available=True)
    else:
        from plugin.rhino_listener.c5_followup_mac_scope import readable_scope,verify_audit_tokenizer
        guard=readable_scope(ROOT,s,r,plan,source);guard();verify_audit_tokenizer(plan['model_assets'])
        result.update(readable_host_bytes_verified=True,mac_environment_full_bytes_verified=True,
            mac_environment_files_reverified=len(plan['environment']['mac']['file_sha256']),
            readable_host_files_reverified=len(plan['host_readable_files']),audit_tokenizer_files_reverified=6)
    source();hg();print(canonical(result).decode())
if __name__=='__main__':main()
