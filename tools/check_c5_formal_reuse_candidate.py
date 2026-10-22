#!/usr/bin/env python3
"""Public-only complete byte/semantic checks; never constructs an owner grant."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.prepare_c5_formal_reuse_freeze import assemble,encoded
from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE,validate_materials
from plugin.rhino_listener.c5_research_native import digest,require

def check():
    documents=assemble()
    for n,v in documents.items():require((ROOT/n).read_bytes()==encoded(v),'formal_reuse_saved_candidate_drift:'+n)
    spec,runtime=documents[SPEC_FILE],documents[FREEZE_FILE]
    require(all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in runtime['source_files'].items()),
        'formal_reuse_current_source_byte_inventory')
    require(runtime['spec_file_sha256']==hashlib.sha256((ROOT/SPEC_FILE).read_bytes()).hexdigest(),
        'formal_reuse_spec_raw_bytes')
    if runtime['execution_ready']:validate_materials(spec,runtime)
    return {'status':'COMPLETE_CURRENT_PUBLIC_MATERIALS_NO_EXECUTION_AUTHORITY' if runtime['execution_ready'] else
        'DISABLED_OFFLINE_MATERIALS_VERIFIED_CURRENT_FACTS_PENDING',
        'source_files_verified':len(runtime['source_files']),'source_inventory_sha256':digest(runtime['source_files']),
        'spec_sha256':digest(spec),'runtime_sha256':digest(runtime),
        'hashes_are_execution_approval_objects':runtime['execution_ready'],'owner_grant_used':False,
        'model_or_rhino_calls':0,'private_formal_reads':0,'state_or_consumption_created':False}
if __name__=='__main__':print(json.dumps(check(),sort_keys=True))
