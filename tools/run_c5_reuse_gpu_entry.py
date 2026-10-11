#!/usr/bin/env python3
"""New fixed development entry; rejects missing full freeze/owner approval.

Never invokes historical entries or searches for a worker. --stop is limited
to the one durably qualified child of this new --serve supervisor. Neither
mode is presently approved/deployed merely by committing this source.
"""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--serve',action='store_true')
    modes.add_argument('--stop',action='store_true')
    args=parser.parse_args()
    from plugin.rhino_listener.c5_reuse_runtime_scope import approved_entry
    # Pure fixed-root/complete-record checks happen before state mutation,
    # process inspection, launch, model imports, stdin or signal attempts.
    spec,runtime,binding,plan,guard=approved_entry(ROOT,'gpu',cleanup_only=args.stop,
                                              private_prefixes=('main','rhino_client','__main__'))
    os.umask(0o077)
    os.chdir(ROOT)
    from training.c5_reuse_gpu_supervisor import supervise,independent_stop
    if args.serve:
        result=supervise(spec,runtime,binding,plan,guard)
        if not result['child_exit_success']:raise RuntimeError('reuse_child_failed_no_retry')
    else:independent_stop(spec,runtime,binding,plan,guard)


if __name__=='__main__':main()
