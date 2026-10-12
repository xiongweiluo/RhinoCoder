#!/usr/bin/env python3
"""Check the disabled public proposal; no endpoint reads or execution."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from training.c5_reuse_continuation_proposal import validate_proposal
from tools.inspect_c5_reuse_retired_startup import decode,need

def check(root=ROOT):
    p=decode((root/'eval/c5/reuse-c-continuation-proposal-20261012.json').read_bytes())
    d=decode((root/'eval/c5/reuse-c-startup-readonly-diagnosis-20261012.json').read_bytes())
    need(d['status']=='completed_readonly_diagnosis_not_field_pass' and all(v==0 for v in d['effects'].values()) and d['limitations']['execution_ready'] is False,'proposal_diagnosis_disabled')
    for e in ('mac','gpu'):
        o=d['observations'][e]
        need(o['registry_before']==o['registry_after']==d['legacy_snapshot'][e] and o['execution_authority'] is False and o['execution_ready'] is False,'proposal_unchanged_legacy')
    need(d['observations']['gpu']['process']['frozen_first_primitive_guard_would_pass'] is False and d['finding']['historical_unique_root_cause_proven'] is False,'proposal_current_guard_not_historical_proof')
    return validate_proposal(p,d['legacy_snapshot'])
if __name__=='__main__':print(json.dumps(check(),sort_keys=True))
