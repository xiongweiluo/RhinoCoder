#!/usr/bin/env python3
"""Final comparison entry: --check is public CPU only; live mode needs exact grant."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--ssh-control',type=Path)
    args=parser.parse_args()
    from training.lora_development_local_tokenizer import SITE
    if SITE not in sys.path: sys.path.append(SITE)
    from training.lora_final_preparation import report, runtime_ready
    if args.check:
        print(json.dumps(report(ROOT,json.loads((ROOT/'lora-final-spec.json').read_text()),'mac'),sort_keys=True)); return
    if args.ssh_control is None: parser.error('--ssh-control required')
    from plugin.rhino_listener.lora_final_admission import admit
    package, _, _ = admit(ROOT,'mac')
    ready=runtime_ready(ROOT,package,'mac')
    from tools.run_lora_development_mac import run
    run(ROOT,package,ready,args.ssh_control)


if __name__=='__main__': main()
