#!/usr/bin/env python3
"""Frozen recovery GPU entry; no effects before NEW full two-hash grant."""
import argparse
import os
from pathlib import Path
import selectors
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def read_permit(guard):
    from training.c5_reuse_evidence import require,strict,canonical
    raw=b'';deadline=time.monotonic()+60
    with selectors.DefaultSelector() as selector:
        selector.register(sys.stdin.fileno(),selectors.EVENT_READ)
        while not raw.endswith(b'\n'):
            guard();require(time.monotonic()<deadline,'recovery_permit_transport_timeout')
            if not selector.select(min(1,max(0,deadline-time.monotonic()))):continue
            chunk=os.read(sys.stdin.fileno(),4096);require(chunk,'recovery_permit_eof');raw+=chunk
            require(len(raw)<=1048576 and raw.count(b'\n')<=1,'recovery_permit_frame_capacity')
    value=strict(raw,limit=1048576);require(raw==canonical(value)+b'\n','recovery_permit_serialization');return value

def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    for mode in ('serve','stop','export','ready-proof','failure-proof'):m.add_argument('--'+mode,action='store_true')
    p.add_argument('--attempt',required=True,type=int,choices=(1,2,3));args=p.parse_args()
    from plugin.rhino_listener.c5_recovery_runtime_scope import approved_entry
    s,r,b,plan,h,g,guard=approved_entry(ROOT,'gpu',args.attempt,
        cleanup_only=args.stop or args.export or getattr(args,'failure_proof'),private_prefixes=('__main__',))
    os.umask(0o077);os.chdir(ROOT)
    from training.c5_recovery_field_gpu import supervise,independent_stop
    from training.c5_reuse_evidence import canonical,require,sha
    if args.stop:
        from training.c5_recovery_storage import write_once,read_private
        from training.c5_reuse_evidence import strict
        state=Path(b['paths']['state_root'])
        if not state.exists():state.mkdir(mode=0o700)
        cancel={'binding_sha256':sha(b),'future_launch_allowed':False}
        if not (state/'cancelled.json').exists():write_once(state,'cancelled.json',cancel)
        else:require(strict(read_private(state/'cancelled.json'))==cancel,'recovery_cancellation_scope')
        if (state/'supervisor').exists():
            from training.c5_reuse_control_journal import read_control
            rows=read_control(state/'supervisor',b,'supervisor')
            qualified=[r for r in rows if r['kind']=='owned_child_qualified']
            result=independent_stop(b,h,g,guard) if qualified else {'status':'unqualified_launch_revoked','exit_observed':False}
        else:result={'status':'launch_revoked_before_supervisor','exit_observed':False}
        print(canonical(result).decode());return
    if getattr(args,'ready_proof'):
        from training.c5_recovery_field_proofs import ready_proof
        print(canonical(ready_proof(b,guard)).decode());return
    if getattr(args,'failure_proof'):
        from training.c5_recovery_field_proofs import failure_proof
        print(canonical(failure_proof(b,h,guard)).decode());return
    if args.export:
        from training.c5_reuse_gpu_export import export_gpu
        value=export_gpu(b,plan,guard)
        from training.c5_recovery_history import open_qualified_stop,history_guard
        q=next(row['payload'] for row in value['supervisor'] if row['kind']=='owned_child_qualified')
        coordinator=open_qualified_stop(Path(b['paths']['admission_root'])/'engineering-recovery-v3',
            b['recovery']['scope'],q,history_guard(b['paths']['admission_root'],'gpu',h))
        try:
            value['shared_stop_rows']=coordinator.log.rows();value['shared_stop_binding']=coordinator.log.binding
        finally:coordinator.log.close()
        print(canonical(value).decode());return
    # No fork/model import/state/campaign effect until permit fully recomputed.
    value=read_permit(guard)
    from training.c5_recovery_field_permit import import_permit
    campaign=import_permit(b['paths']['admission_root'],b,h,g,value)
    try:
        state=Path(b['paths']['state_root']);state.mkdir(mode=0o700)
        result=supervise(b,plan,r,h,g,guard,campaign)
        require(result['child_exit_success'],'recovery_gpu_child_failed')
    finally:campaign.log.close()
if __name__=='__main__':main()
