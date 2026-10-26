#!/usr/bin/env python3
"""Unapproved new development entry: full package + separate owner record required."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append('/data/conda-envs/rhinocoder/lib/python3.11/site-packages')  # -S: no .pth or site hooks.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--serve', action='store_true')
    group.add_argument('--worker', type=int, choices=(0, 1))
    group.add_argument('--export', action='store_true')
    args = parser.parse_args()
    from training.lora_development_authority import verify_approval
    from plugin.rhino_listener.c5_research_channel import read_json
    package = json.loads((ROOT / 'lora-development-package.json').read_text())
    state = Path(package['endpoints']['gpu']['state_root'])
    approval = read_json(state, 'owner-approval.json')
    if args.export:
        from training.lora_development_authority import validate_package
        from plugin.rhino_listener.lora_development_admission import admit
        validate_package(package); admit(ROOT, package, 'gpu')
        from training.lora_development_export import export_gpu
        export_gpu(state, package, sys.stdout.buffer)
        return
    verify_approval(package, approval, endpoint='gpu', source_root=ROOT, state_root=state)
    if Path(sys.executable).resolve() != Path(package['endpoints']['gpu']['python']):
        raise RuntimeError('fixed GPU Python required')
    from training.lora_development_gpu_entry import supervise, worker
    if args.serve: supervise(ROOT, package, state)
    else: worker(ROOT, package, state, args.worker)


if __name__ == '__main__': main()
