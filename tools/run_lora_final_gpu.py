#!/usr/bin/env python3
"""Final GPU entry; private model views open only after separate final approval."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.append('/data/conda-envs/rhinocoder/lib/python3.11/site-packages')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true')
    group.add_argument('--serve',action='store_true')
    group.add_argument('--worker',type=int,choices=(0,))
    group.add_argument('--export',action='store_true')
    args=parser.parse_args()
    from training.lora_final_preparation import report, runtime_ready
    if args.check:
        print(json.dumps(report(ROOT,json.loads((ROOT/'lora-final-spec.json').read_text()),'gpu'),sort_keys=True)); return
    from plugin.rhino_listener.lora_final_admission import admit
    package,state,_=admit(ROOT,'gpu',cleanup=args.export)
    if Path(sys.executable).resolve() != Path(package['endpoints']['gpu']['python']): raise RuntimeError('fixed GPU Python required')
    if args.export:
        from training.lora_development_export import export_gpu
        export_gpu(state,package,sys.stdout.buffer); return
    ready=runtime_ready(ROOT,package,'gpu')
    if args.serve: ready['supervise'](ROOT,package,state)
    else: ready['worker'](ROOT,package,state,args.worker)


if __name__=='__main__': main()
