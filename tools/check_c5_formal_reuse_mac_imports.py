#!/usr/bin/env python3
"""Actual Mac CPU/tokenizer/import closure. No grant, model or Rhino call."""
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_formal_reuse_scope import FREEZE_FILE,file_sha
from plugin.rhino_listener.c5_formal_reuse_origins import origin_path
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_formal_reuse_source_guard import SourceGuard
from plugin.rhino_listener.c5_followup_profile import MAC_CACHE
from training.c5_execution import load_pinned_tokenizer,load_config

def check():
    freeze=json.loads((ROOT/FREEZE_FILE).read_bytes())
    require(sys.version==freeze['mac_environment']['python'] and sys.flags.isolated==1
        and sys.dont_write_bytecode is True and sys.pycache_prefix==MAC_CACHE
        and not Path(MAC_CACHE).exists(),'formal_reuse_actual_mac_cpu_interpreter')
    source=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],
        project_prefixes=('tools','training','plugin','agent','data_pipeline'))
    source();directory=Path(freeze['tokenizer_dir'])
    require(all(file_sha(directory/n)==h for n,h in freeze['tokenizer_file_sha256'].items()),
        'formal_reuse_actual_public_tokenizer_bytes')
    tokenizer=load_pinned_tokenizer(directory,config=load_config(ROOT/'eval/c5/c5-engineering-config.json'))
    import torch
    require(not torch.cuda.is_initialized(),'formal_reuse_cpu_preflight_no_cuda_initialization')
    source();external=0
    for module in tuple(sys.modules.values()):
        path=origin_path(module,sys.modules,require)
        if path is None:continue
        if path.is_relative_to(ROOT):require(path.relative_to(ROOT).as_posix() in freeze['source_files'],
            'formal_reuse_cpu_unregistered_project_import')
        else:
            require(str(path) in freeze['mac_environment']['file_sha256']
                and file_sha(path)==freeze['mac_environment']['file_sha256'][str(path)],
                'formal_reuse_cpu_unfrozen_external_import');external+=1
    for files in (freeze['mac_environment']['file_sha256'],freeze['rhino_environment_files']):
        require(all(file_sha(n)==h for n,h in files.items()),'formal_reuse_current_mac_file_drift')
    code={n:h for n,h in freeze['source_files'].items() if n.endswith('.py')}
    return {'status':'ACTUAL_MAC_CPU_TOKENIZER_CLOSURE_VERIFIED_NOT_EXECUTION_AUTHORITY','epoch':time.time(),
        'source_code_inventory_sha256':digest(code),'external_loaded_modules_verified':external,
        'public_tokenizer_class':type(tokenizer).__name__,'cuda_initialized':False,'model_loaded':False,
        'model_generation_calls':0,'rhino_calls':0,'private_formal_reads':0,'grant_or_state_created':False}
if __name__=='__main__':print(json.dumps(check(),sort_keys=True))
