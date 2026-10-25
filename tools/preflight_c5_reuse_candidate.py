#!/usr/bin/env python3
"""Fixed candidate read-only preflight using the actual endpoint interpreter.

Run with the same host access permissions planned for the eventual entry.
No owner grant (real or synthetic), state/key/claim creation, Rhino call,
subscription, model/CUDA initialization, signal, or execution authority.
"""
import argparse
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def preflight(endpoint):
    from plugin.rhino_listener.c5_reuse_runtime_scope import fixed_paths,SPEC,RUNTIME,PLAN,read_bytes,ReuseSourceGuard
    from plugin.rhino_listener.c5_reuse_field_scope import require,strict,sha,check_candidate_materials
    from plugin.rhino_listener.c5_reuse_predecessor import verify_record,verify_retirement
    from tools.stage_c5_reuse_field_source import preparation_scope
    from tools.check_c5_reuse_field_freeze import check
    from training.c5_reuse_gpu_loader import validate_plan
    from training.c5_reuse_budget import ReuseBudget
    paths=fixed_paths(endpoint)
    require(ROOT==Path(paths['source_root']) and ROOT.resolve()==ROOT,'reuse_candidate_fixed_root')
    raw={name:read_bytes(ROOT/name) for name in (SPEC,RUNTIME,PLAN)}
    spec,runtime,plan=(strict(raw[name]) for name in (SPEC,RUNTIME,PLAN))
    require(runtime['endpoints']=={e:fixed_paths(e) for e in ('mac','gpu')},'reuse_candidate_fixed_endpoints')
    material=check_candidate_materials(spec,runtime,now=time.time(),endpoint=endpoint)
    source_check=check(ROOT,material['spec_sha256'],material['runtime_sha256'])
    validate_plan(spec,runtime,plan);verify_record(ROOT,plan,read_bytes)
    parent=ROOT.parent
    require(not os.path.lexists(parent/(spec['instance_id']+'-external-custody')),'reuse_candidate_no_custody')
    preparation_scope(parent)
    source=ReuseSourceGuard(ROOT,runtime['source_files'],private_prefixes=('__main__',))
    def guard(*,cleanup_only=False):
        require(cleanup_only is False,'reuse_candidate_readonly_not_cleanup_authority')
        require(all(read_bytes(ROOT/name)==value for name,value in raw.items()),'reuse_candidate_records_changed')
        verify_retirement(parent,read_bytes)
        return source()
    if endpoint=='mac':
        # Resolve inert dependencies before the exact same readable_scope used
        # by --prepare/--drive. These imports do not invoke their main/prepare.
        from training import c5_reuse_mac_controller
        from tools import run_c5_reuse_owner_custody
        from plugin.rhino_listener.c5_reuse_mac_scope import readable_scope
        readable=readable_scope(ROOT,spec,runtime,plan,guard)
        from training.c5_reuse_ssh import master_pin
        master_pin(plan['transport']);readable()
        installed='mac_fixed_interpreter_process_host_controller_tokenizer_bytes'
    else:
        from training import c5_reuse_gpu_supervisor
        from training.c5_reuse_gpu_loader import preflight as gpu_preflight,PYTHON
        require(sys.platform=='linux' and Path(sys.executable).resolve()==PYTHON
                and os.getuid()==plan['gpu_process']['uid'],'reuse_candidate_gpu_interpreter_uid')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==plan['gpu_process']['boot_id'],
                'reuse_candidate_gpu_boot')
        gpu_preflight(runtime,plan,guard)
        installed='gpu_fixed_interpreter_boot_uid_uuid_model_environment_bytes'
    budget=ReuseBudget(spec['resources']);budget.check();guard();preparation_scope(parent)
    return {**material,'endpoint':endpoint,'epoch':time.time(),'source_check':source_check,
        'actual_installed_asset_bytes_verified':True,'installed_check':installed,
        'both_retired_predecessors_verified':True,'unchanged_shared_admission_checked':True,
        'full_development_window_verified':True,'budget_check_not_actual_research_start':budget.observation(),
        'state_or_owner_grant_or_key_or_claim_created':False,'research_started':False,
        'model_or_rhino_calls':0,'private_formal_reads':0,'execution_ready':False,
        'human_or_transport_origin_proven':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--endpoint',choices=('mac','gpu'),required=True)
    args=p.parse_args()
    import json
    print(json.dumps(preflight(args.endpoint),sort_keys=True),flush=True)


if __name__=='__main__':main()
