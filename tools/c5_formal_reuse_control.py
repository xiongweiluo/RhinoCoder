#!/usr/bin/env python3
"""Minimal qualified stop/export entry: no model/loader/runner imports."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('stop','export-supervisor'));p.add_argument('--attempt',type=int,required=True)
    a=p.parse_args()
    from training.c5_formal_reuse_control import control_scope
    spec,freeze,guard=control_scope(ROOT)
    from plugin.rhino_listener.c5_formal_reuse_scope import attempt_state
    from training.c5_formal_reuse_supervisor import independent_stop,export_supervisor
    state=attempt_state('gpu',a.attempt)
    value=independent_stop(state,guard) if a.mode=='stop' else export_supervisor(state,freeze,guard)
    print(json.dumps(value,sort_keys=True,separators=(',',':')))


if __name__=='__main__':main()
