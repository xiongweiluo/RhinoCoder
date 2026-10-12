#!/usr/bin/env python3
"""New fixed Mac prepare/drive modes; exact owner grant is prerequisite."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--prepare',action='store_true');m.add_argument('--drive',action='store_true');args=p.parse_args()
    from plugin.rhino_listener.c5_reuse_mac_scope import mac_scope
    spec,runtime,binding,plan,guard=mac_scope(ROOT,private_prefixes=('__main__',))
    os.umask(0o077);os.chdir(ROOT)
    from training.c5_reuse_mac_controller import prepare,MacController,external_readiness
    if args.prepare:prepare(binding,guard);return
    from training.c5_reuse_budget import ReuseBudget
    from training.c5_reuse_admission import AdmissionRegistry
    from plugin.rhino_listener.c5_reuse_runtime_scope import read_bytes
    from training.c5_reuse_evidence import strict
    schemas=strict(read_bytes(ROOT/'eval/c5/rhino-runtime-schema-v1.json'))['core_parameters']
    # Source inventory is the actual master mapping, not a plan-owned alias.
    controller_plan={**plan,'source_files':runtime['source_files']}
    with AdmissionRegistry(binding) as registry:
        budget=ReuseBudget(spec['resources'])
        runner=MacController(binding,controller_plan,schemas,registry,guard,budget.check)
        result=runner.drive(lambda host,worker:external_readiness(binding,host,worker))
        from training.c5_reuse_evidence import canonical
        print('C5_REUSE_CONTROLLER_EXTERNAL_FINAL_REQUIRED '+canonical(result).decode(),flush=True)


if __name__=='__main__':main()
