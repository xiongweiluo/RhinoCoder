"""Lazy original pinned inference loader for the new development entry.

No package import, CUDA initialization, data split read or model loading on
module import. Admission/owned-child qualification precede calling load().
"""
import contextlib
import os
from pathlib import Path
import sys
import re

from training.c5_reuse_evidence import exact,is_sha,require,sha
from training.c5_reuse_field_scope import COMPARISON,STUDY,PROTOCOL
from training.c5_reuse_owned_child import POLICY
from training.c5_reuse_process_identity import stable_file_sha
from plugin.rhino_listener.c5_reuse_runtime_scope import read_bytes

ENV=Path('/data/conda-envs/rhinocoder')
PYTHON=ENV/'bin/python3.11'
MANIFEST=Path('/data/RhinoCoder-c5/base-snapshot-manifest.json')
MANIFEST_SHA='5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd'
SNAPSHOT=Path('/data/hf-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots')/COMPARISON['base_revision']
ADAPTER=Path('/data/c5-runs-20261001/formal/checkpoint-132')
ADAPTER_FILES={'adapter_config.json':'8a776a47b085b787b7c7f3c9b068aed8c0f018278de2b94bf66130f5542d6d4f',
               'adapter_model.safetensors':'da8acdcde2671aa397534b35369fe4a84b9d150f80f7b7026a4366a770be2883'}
ENTRY='tools/run_c5_reuse_gpu_entry.py'
LOADER_POLICY={'seed':20260928,'tf32':True,'quantization':'nf4_double_quant_bfloat16',
               'prepare_base':'prepare_model_for_kbit_training_no_checkpoint_hooks',
               'base_route':'same_PEFT_model_disable_adapter','lora_trainable':False,
               'local_files_only':True,'trust_remote_code':False,'device':0,
               'parse_repair':False,'training':False}


def validate_plan(spec,runtime,plan):
    revised=spec['resources'].get('resource_policy')=='incremental_reuse_unknown_history_v1'
    exact(plan,('protocol','study_id','instance_id','environment','model_assets','host_readable_files',
                'gpu_process','loader_policy','transport','host_acceptance','resource_basis')+
          (('predecessor',) if spec['instance_id']=='reuse-dev-20261012-b' else ()))
    if spec['instance_id']=='reuse-dev-20261012-b':
        from plugin.rhino_listener.c5_reuse_predecessor import POLICY as PREDECESSOR
        require(plan['predecessor']==PREDECESSOR,'reuse_plan_retired_predecessor')
    require(plan['protocol']==PROTOCOL and plan['study_id']==STUDY
            and plan['instance_id']==spec['instance_id'],'reuse_plan_identity')
    exact(plan['environment'],('mac','gpu'))
    require(sha(plan['environment'])==runtime['environment_sha256']
            and sha(plan['model_assets'])==runtime['model_assets_sha256']
            and sha(plan['host_readable_files'])==runtime['host_readable_files_sha256'], 'reuse_plan_asset_closure')
    exact(plan['model_assets'],('manifest_raw_sha256','snapshot_dir','base_files','adapter_root','adapter_files')+
          (('audit_tokenizer_dir','audit_tokenizer_files') if revised else ()))
    assets=plan['model_assets']
    require(assets['manifest_raw_sha256']==MANIFEST_SHA and assets['snapshot_dir']==str(SNAPSHOT)
            and assets['adapter_root']==str(ADAPTER) and assets['adapter_files']==ADAPTER_FILES
            and sha(assets['adapter_files'])==COMPARISON['adapter_sha256']
            and type(assets['base_files']) is dict and len(assets['base_files'])==14
            and all(type(n) is str and Path(n).name==n and is_sha(s) for n,s in assets['base_files'].items()),
            'reuse_plan_original_assets')
    if revised:
        names={'config.json','generation_config.json','merges.txt','tokenizer.json','tokenizer_config.json','vocab.json'}
        require(assets['audit_tokenizer_dir']=='/Users/xiongweiluo/RhinoCoder/data/training/c5/modelbridge-tokenizer/'+COMPARISON['base_revision']
            and set(assets['audit_tokenizer_files'])==names
            and assets['audit_tokenizer_files']=={n:assets['base_files'][n] for n in names},
            'reuse_original_audit_tokenizer_assets')
    process=plan['gpu_process']
    exact(process,('python','entry','boot_id','uid','gpu_uuid','stop_policy'))
    require(process['python']==str(PYTHON) and process['entry']==ENTRY and process['stop_policy']==POLICY
            and type(process['uid']) is int and process['uid']>=0
            and type(process['boot_id']) is str and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',process['boot_id'])
            and type(process['gpu_uuid']) is str and re.fullmatch(r'GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',process['gpu_uuid'])
            and plan['loader_policy']==LOADER_POLICY,'reuse_plan_owned_loader_policy')
    require(sha(plan['host_acceptance'])==spec['host_policy']['acceptance_record_sha256']
            and plan['host_acceptance']['instance_id']==spec['instance_id'],'reuse_plan_current_host')
    basis=plan['resource_basis']
    from training.c5_reuse_ssh import validate_transport
    validate_transport(plan['transport'])
    exact(basis,('platform_hour_quota','remaining_gpu_seconds_meaning','prior_cumulative_upper_bound_basis')+
          (('resource_revision_acceptance',) if revised else ()))
    if revised:
        from training.c5_reuse_field_scope import RESOURCE_ACCEPTANCE
        require(basis['platform_hour_quota'] is None
            and basis['remaining_gpu_seconds_meaning']=='incremental_research_reservation_not_platform_balance'
            and basis['prior_cumulative_upper_bound_basis']=='owner_reported_unknown_not_original_16_hour_compliance'
            and basis['resource_revision_acceptance']==RESOURCE_ACCEPTANCE
            and sha(basis['resource_revision_acceptance'])==spec['resources']['resource_revision_acceptance_sha256'],
            'reuse_incremental_resource_reservation_basis')
    else:require(spec['instance_id'] not in ('reuse-dev-20261011-a','reuse-dev-20261012-b') and basis['platform_hour_quota'] is None
            and basis['remaining_gpu_seconds_meaning']=='research_reservation_within_original_cap_not_platform_balance'
            and type(basis['prior_cumulative_upper_bound_basis']) is str
            and 0<len(basis['prior_cumulative_upper_bound_basis'])<=2048,'reuse_resource_reservation_basis')


def verify_entry_process(binding,plan,reader):
    require(sys.platform=='linux' and Path(sys.executable).resolve()==PYTHON
            and Path.cwd()==Path(binding['paths']['source_root']) and os.getuid()==plan['gpu_process']['uid'],
            'reuse_fixed_gpu_interpreter_process')
    observed=reader(os.getpid())
    expected_argv=[str(PYTHON),'-I','-B',str(Path(binding['paths']['source_root'])/ENTRY),'--serve']
    import hashlib
    require(observed['argv_sha256']==hashlib.sha256(b'\0'.join(s.encode() for s in expected_argv)+b'\0').hexdigest()
            and observed['boot_id']==plan['gpu_process']['boot_id'],'reuse_fixed_gpu_argv_boot')
    return observed


def preflight(runtime,plan,guard):
    """Read frozen public model/environment bytes; no torch import."""
    from training.c5_modelbridge_runtime import runtime_preflight
    from training.c5_execution import verify_snapshot
    from training.c5_reuse_evidence import strict,raw_sha
    guard()
    raw=read_bytes(MANIFEST)
    require(raw_sha(raw)==MANIFEST_SHA,'reuse_manifest_bytes')
    manifest=strict(raw)
    require(manifest['snapshot_dir']==str(SNAPSHOT) and manifest['file_sha256']==plan['model_assets']['base_files'],
            'reuse_manifest_population')
    verify_snapshot(SNAPSHOT,MANIFEST)
    require(all(stable_file_sha(ADAPTER/n)==s for n,s in ADAPTER_FILES.items()),'reuse_adapter_bytes')
    observed,inventory=runtime_preflight(ENV)
    require(observed['environment']==plan['environment']['gpu'],'reuse_current_gpu_environment')
    import subprocess
    rows=subprocess.check_output(['nvidia-smi','--query-gpu=uuid','--format=csv,noheader'],text=True,timeout=15).strip()
    require(rows==plan['gpu_process']['gpu_uuid'],'reuse_gpu_uuid')
    guard()
    return inventory


def load(root,inventory,guard,budget,*,runtime,plan):
    """Only qualified child calls this; original inference settings unchanged."""
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    guard();budget()
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        from peft import PeftModel,prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM,BitsAndBytesConfig
        from training.c5_execution import generation,load_config,load_pinned_tokenizer
        from training.c5_modelbridge_runtime import verify_loaded_environment
        guard();verify_loaded_environment(ENV,inventory);budget()
        require(torch.cuda.is_available() and torch.cuda.is_bf16_supported()
                and torch.cuda.mem_get_info()[0]>=16*1024**3,'reuse_cuda_bf16_memory')
        tokenizer=load_pinned_tokenizer(SNAPSHOT,config=load_config(Path(root)/'eval/c5/c5-engineering-config.json'))
        guard();budget()
        torch.manual_seed(20260928);torch.cuda.manual_seed_all(20260928)
        torch.backends.cuda.matmul.allow_tf32=True
        quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
                                bnb_4bit_compute_dtype=torch.bfloat16)
        base=AutoModelForCausalLM.from_pretrained(SNAPSHOT,local_files_only=True,trust_remote_code=False,
                quantization_config=quant,dtype=torch.bfloat16,device_map={'':0})
        base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=False)
        base.config.use_cache=False
        guard();budget()
        model=PeftModel.from_pretrained(base,ADAPTER,local_files_only=True,is_trainable=False)
        model.eval();torch.cuda.reset_peak_memory_stats()
        require(preflight(runtime,plan,guard)==inventory,'reuse_model_load_asset_closure')
        guard();verify_loaded_environment(ENV,inventory);budget()
    def check():
        guard();verify_loaded_environment(ENV,inventory);budget()
    def generate(prompt,stage):
        check()
        with contextlib.redirect_stdout(sys.stderr):value=generation(model,tokenizer,prompt,stage)
        check()
        return value
    def route(route):
        require(route in ('base','lora'),'reuse_original_route')
        return model.disable_adapter() if route=='base' else contextlib.nullcontext()
    check()
    return tokenizer,generate,route,check
