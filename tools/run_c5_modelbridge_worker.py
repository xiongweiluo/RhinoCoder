#!/usr/bin/env python3
"""Fixed development worker; no arbitrary corpus/path/route or final entry.

--preflight reads fixed assets/environment without importing torch or writing.
--serve remains disabled until the NEW actual runtime freeze is ready and the
owner has approved its exact hash. Original C5/native12/R grants never apply.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import json
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from plugin.rhino_listener.c5_research_channel import publish_json,read_json,private_directory
from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_research_provenance import SourceGuard
from training.c5_modelbridge_runtime import Budget,file_sha,runtime_preflight,verify_loaded_environment
from training.c5_model_transport import OneShotModelSession,strict_json,frame,LIMIT

ID = 'C5DEV-MODELBRIDGE-20261003-A'
STATE = Path('/data/c5-modelbridge-state-20261003-A')
SOURCE = Path('/data/RhinoCoder-c5-modelbridge-A')
ENV = Path('/data/conda-envs/rhinocoder')
ASSET = Path('/data/RhinoCoder-c5')
ADAPTER = Path('/data/c5-runs-20261001/formal/checkpoint-132')


def public(path):
    require(path.resolve()==path and path.is_file() and path.stat().st_size <= LIMIT,'fixed public path/size differs')
    return strict_json(path.read_bytes())


def preflight():
    require(ROOT==SOURCE and sys.platform=='linux','fixed Linux deployment required')
    from training.c5_execution import verify_snapshot
    registry = public(ROOT/'eval/c5/gpu-formal-registry-20261001.json')
    manifest = ASSET/'base-snapshot-manifest.json'
    require(file_sha(manifest)=='5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd','base manifest drift')
    snapshot = Path(public(manifest)['snapshot_dir'])
    verified = verify_snapshot(snapshot,manifest)
    require(registry['selected_checkpoint']=='checkpoint-132'
            and digest(registry['files'])==registry['adapter_sha256']=='305d72703270d16e93233d1d34ae27cdaddd777e4530afead88c7edb8dc22cae',
            'original selected model registration differs')
    require(all(file_sha(ADAPTER/name)==sha for name,sha in registry['files'].items()),'selected adapter bytes drift')
    environment,inventory = runtime_preflight(ENV)
    return {**environment,'snapshot':verified,'adapter_sha256':registry['adapter_sha256'],
            'adapter_files':registry['files'],'source_files':{
                p.relative_to(ROOT).as_posix():file_sha(p) for folder in ('agent','training','tools','plugin','data_pipeline')
                for p in sorted((ROOT/folder).rglob('*.py'))},
            'status':'modelbridge_readonly_preflight_not_execution_authority'},inventory,snapshot


def approved_scope(*,check_budget=True):
    # No stdin/model is touched before complete source/spec/resource approval.
    require(ROOT==SOURCE and sys.platform=='linux','fixed Linux deployment required')
    spec = public(ROOT/'eval/c5/modelbridge-development-spec-20261003.json')
    freeze = public(ROOT/'eval/c5/modelbridge-runtime-freeze-20261003.json')
    require(spec['execution_ready'] is True and freeze['execution_ready'] is True
            and spec['probe_id']==freeze['probe_id']==ID and freeze['spec_sha256']==digest(spec),
            'complete NEW development freeze missing; draft cannot execute')
    fd = private_directory(STATE); os.close(fd)
    approval = read_json(STATE,'owner-approval.json')
    require(approval=={'probe_id':ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
                      'runtime_freeze_sha256':digest(freeze),
                      'approval_basis':'direct repository_owner approval of new modelbridge development spec and complete runtime freeze'},
            'new exact modelbridge owner approval missing/different')
    guard = SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],
                        project_prefixes=('agent','training','tools','plugin','data_pipeline'))
    guard()
    require(file_sha(ROOT/'eval/c5/modelbridge-development-spec-20261003.json')==freeze['spec_file_sha256'],
            'actual development spec bytes differ')
    assets,inventory,snapshot = preflight()
    require(assets['environment_sha256']==freeze['environment_sha256'] and assets['adapter_sha256']==spec['adapter_sha256'],
            'actual model/environment drift')
    # A precise newly approved resource boundary is mandatory, not old auth.
    budget = Budget(freeze['resource_boundary']) if check_budget else None
    return spec,freeze,guard,assets,inventory,snapshot,budget


def serve():
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'; os.umask(0o077)
    spec,freeze,guard,assets,inventory,snapshot,budget = approved_scope()
    publish_json(STATE,ID+'.worker-started.claim.json',{'probe_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    output = sys.stdout.buffer
    status = 'worker_failed_no_replay'
    def stop(*_): raise TimeoutError('bounded modelbridge worker stop')
    signal.signal(signal.SIGALRM,stop)
    signal.setitimer(signal.ITIMER_REAL,budget.check())
    try:
        # All loaders are lazy; preflight/missing approval never calls these.
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            from peft import PeftModel,prepare_model_for_kbit_training
            from transformers import AutoModelForCausalLM,BitsAndBytesConfig
            from training.c5_execution import generation,load_config,load_pinned_tokenizer
            require(torch.cuda.is_available() and torch.cuda.is_bf16_supported(),'CUDA/BF16 unavailable')
            require(torch.cuda.mem_get_info()[0] >= 16*1024**3,'less than 16GiB GPU free')
            for line in (ROOT/'requirements-training.txt').read_text().splitlines():
                if '==' in line and not line.startswith('#'):
                    name,version = line.split('==')
                    require(importlib.metadata.version(name).split('+')[0]==version,'locked package version differs')
            tokenizer = load_pinned_tokenizer(snapshot,config=load_config())
            torch.manual_seed(20260928); torch.cuda.manual_seed_all(20260928)
            torch.backends.cuda.matmul.allow_tf32=True
            quant = BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
                                      bnb_4bit_compute_dtype=torch.bfloat16)
            base = AutoModelForCausalLM.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False,
                quantization_config=quant,dtype=torch.bfloat16,device_map={'':0})
            base = prepare_model_for_kbit_training(base,use_gradient_checkpointing=False)
            base.config.use_cache=False
            model = PeftModel.from_pretrained(base,ADAPTER,local_files_only=True,is_trainable=False)
            model.eval(); torch.cuda.reset_peak_memory_stats()
        def check_source():
            guard(); verify_loaded_environment(ENV,inventory)
        check_source(); budget.check()
        publish_json(STATE,'loaded-runtime.json',{'environment_sha256':assets['environment_sha256'],
                     'source_inventory_sha256':freeze['source_inventory_sha256'],'adapter_sha256':spec['adapter_sha256'],
                     'torch_cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),
                     'base_dtype_cast':'prepare_model_for_kbit_training_no_checkpoint_hooks',
                     'base_route':'same PEFT-wrapped base with disable_adapter context',
                     'default_route_changed':False,'holdout_calls':0})
        def generate(prompt,stage):
            with contextlib.redirect_stdout(sys.stderr): return generation(model,tokenizer,prompt,stage)
        session = OneShotModelSession(ID,digest(freeze),spec['task_plans'],STATE,tokenizer,generate,
                 lambda route:model.disable_adapter() if route=='base' else contextlib.nullcontext(),
                 {'base':digest(assets['snapshot']),'lora':spec['adapter_sha256']},check_source,budget.check)
        count = 0
        while True:
            budget.check()
            raw = sys.stdin.buffer.readline(LIMIT+1)
            if not raw: break
            require(raw.endswith(b'\n') and len(raw) <= LIMIT,'bounded complete request frame required')
            require(count < spec['generation_requests_max'],'fixed request count exhausted')
            count += 1
            result = session.infer(strict_json(raw))
            output.write(frame(result)); output.flush()
            if session.blocked: break
        status = 'worker_stopped_no_replay'
        publish_json(STATE,'worker-summary.json',{'requests':count,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
                     'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'model_generation_only_not_Rhino_or_C5_GO':True})
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        budget.settle(STATE,status)


def export():
    """Read-only, exact development evidence export; never touches a holdout."""
    spec,freeze,guard,assets,inventory,snapshot,_ = approved_scope(check_budget=False)
    require(read_json(STATE,'worker-summary.json')['requests']==spec['generation_requests_max'],
            'worker incomplete; no complete export')
    settlement=read_json(STATE,'resource-settlement.json')
    require(settlement['status']=='worker_stopped_no_replay','worker not cleanly stopped')
    names=['worker-summary.json','loaded-runtime.json','resource-settlement.json',
           ID+'.worker-started.claim.json']
    for slot in spec['slot_order']:
        key=digest({'slot':slot,'step':0,'freeze':digest(freeze)})
        names.extend(('generation-'+key+'.claim.json',key+'-selector-attempt.json',
                      key+'-selector-raw.json',key+'-response.json'))
        response=read_json(STATE,key+'-response.json')
        if len(response['generation_receipts'])==2:
            names.extend((key+'-invocation-attempt.json',key+'-invocation-raw.json'))
    expected=set(names)
    actual={p.name for p in STATE.glob('generation-*.claim.json')}
    require(actual=={n for n in expected if n.startswith('generation-')},'extra or missing model generation claim')
    bundle={'probe_id':ID,'runtime_freeze_sha256':digest(freeze),
            'records':{name:read_json(STATE,name) for name in names},'holdout_rows_read':0}
    require(len(frame(bundle)) <= LIMIT,'remote development evidence exceeds bounded export')
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('preflight','serve','export'))
    args = parser.parse_args()
    if args.mode=='preflight':
        result,_,_ = preflight(); print(json.dumps(result,sort_keys=True))
    elif args.mode=='export':
        print(frame(export()).decode(),end='')
    else: serve()


if __name__=='__main__': main()
