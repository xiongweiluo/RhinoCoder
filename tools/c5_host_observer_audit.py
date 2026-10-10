#!/usr/bin/env python3
"""Audit fixed observer raw metadata with externally captured seal SHA."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_host_observer_scope import STATE,FREEZE,public
from plugin.rhino_listener.c5_research_native import digest
from training.c5_host_observer_audit import audit_observer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external-seal-sha256',required=True)
    args=parser.parse_args()
    try:value=audit_observer(STATE,digest(public(FREEZE)),args.external_seal_sha256)
    except Exception as exc:
        print(json.dumps({'status':'observer_audit_failed_no_replay','error_type':type(exc).__name__}));return 1
    print(json.dumps(value,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
