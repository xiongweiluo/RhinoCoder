#!/usr/bin/env python3
"""Register the already received direct owner two-hash grant, not obtain it.

Call ONLY after the human has approved the actual full hashes. Hash arguments
are byte bindings, never independent proof of human authorization. Preparation
and CI never invoke this writer. No campaign, roles, keys or model are made.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_formal_reuse_scope import (SPEC_FILE,FREEZE_FILE,MAC_SOURCE,MAC_STATE,
    REMOTE_SOURCE,REMOTE_STATE,expected_grant,validate_materials)
from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from training.c5_formal_reuse_deployment import verify

def register(endpoint,spec_sha,runtime_sha):
    require(endpoint in ('mac','gpu') and ROOT==(MAC_SOURCE if endpoint=='mac' else REMOTE_SOURCE),
        'formal_reuse_approved_fixed_deployment')
    s=json.loads((ROOT/SPEC_FILE).read_bytes());r=json.loads((ROOT/FREEZE_FILE).read_bytes())
    require(spec_sha==digest(s) and runtime_sha==digest(r),'formal_reuse_actual_approved_full_hashes')
    validate_materials(s,r);verify(ROOT,s,r)
    state=MAC_STATE if endpoint=='mac' else REMOTE_STATE
    record=expected_grant(s,r)
    if state.exists():
        require({p.name for p in state.iterdir()}=={'owner-approval.json'}
            and read_json(state,'owner-approval.json')==record,'formal_reuse_existing_consumption_or_other_grant')
    else:state.mkdir(mode=0o700);publish_json(state,'owner-approval.json',record)
    return {'registered_exact_spec_sha256':spec_sha,'registered_exact_runtime_sha256':runtime_sha,
        'endpoint':endpoint,'human_origin_cryptographically_proven':False,'model_or_rhino_calls':0,
        'private_formal_reads':0,'campaign_or_role_created':False}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('endpoint',choices=('mac','gpu'))
    p.add_argument('--approved-spec-sha256',required=True);p.add_argument('--approved-runtime-sha256',required=True)
    a=p.parse_args();print(json.dumps(register(a.endpoint,a.approved_spec_sha256,a.approved_runtime_sha256),sort_keys=True))
