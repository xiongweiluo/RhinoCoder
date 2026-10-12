#!/usr/bin/env python3
"""Independent D candidate byte/population check; no admission/model actions."""
import argparse,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_followup_profile import SPEC,PLAN,RUNTIME,GENESIS,CONTINUATION
from plugin.rhino_listener.c5_followup_runtime_scope import read_bytes,strict,sha
from plugin.rhino_listener.c5_reuse_field_scope import require,check_candidate_materials
from plugin.rhino_listener.c5_followup_predecessor import verify_record
from training.c5_followup_gpu_loader import validate_plan

def check(root,spec_sha,runtime_sha,*,review=False):
    root=Path(root);require(root.is_absolute() and root.resolve()==root,'followup_review_root')
    s,r,p=(strict(read_bytes(root/n)) for n in (SPEC,RUNTIME,PLAN))
    require(sha(s)==spec_sha and sha(r)==runtime_sha,'followup_independent_exact_hash')
    expected=set(r['source_files'])|{RUNTIME}|({'review-materials.json'} if review else set())
    require({x.relative_to(root).as_posix() for x in root.rglob('*') if x.is_file()}==expected
        and not any(x.is_symlink() for x in root.rglob('*')),'followup_independent_population')
    for n,pin in r['source_files'].items():require(hashlib.sha256(read_bytes(root/n)).hexdigest()==pin,'followup_independent_source_byte')
    require(s['continuation']==r['continuation']==CONTINUATION and p['continuation']=={'binding':CONTINUATION,'genesis':GENESIS},'followup_independent_nonempty_history')
    require(strict(read_bytes(root/'eval/c5/reuse-followup-admission-genesis-20261012-d.json'))==GENESIS,'followup_genesis_public_byte_binding')
    validate_plan(s,r,p);verify_record(root,p,read_bytes)
    for endpoint in ('mac','gpu'):check_candidate_materials(s,r,now=1,endpoint=endpoint)
    return {'spec_sha256':sha(s),'runtime_sha256':sha(r),'source_files':len(r['source_files']),
        'complete_candidate_source_bytes_verified':True,'nonempty_legacy_history_bound':True,
        'original_three_failures_retained':True,'execution_authority':False,'execution_ready':False}
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--spec-sha256',required=True);a.add_argument('--runtime-sha256',required=True);a.add_argument('--review',action='store_true');v=a.parse_args()
    print(json.dumps(check(v.root,v.spec_sha256,v.runtime_sha256,review=v.review),sort_keys=True))
