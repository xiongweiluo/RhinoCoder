"""Complete inert plan validation; unchanged original inference/model contract."""
from pathlib import Path
from .c5_reuse_field_scope import require,sha,exact,COMPARISON,PROTOCOL
from .c5_recovery_profile import STUDY,INSTANCE,ENTRY,PYTHON,RECOVERY_POLICY

def validate(spec,runtime,plan,history):
    exact(plan,('protocol','study_id','instance_id','environment','model_assets','host_readable_files','gpu_process',
        'loader_policy','transport','host_acceptance','resource_basis','recovery','minimum_attempt_window_seconds'))
    require(plan['protocol']==PROTOCOL and plan['study_id']==STUDY and plan['instance_id']==INSTANCE
        and plan['recovery']==spec['recovery']==runtime['recovery']
        and plan['minimum_attempt_window_seconds']==spec['recovery']['minimum_attempt_window_seconds']
        and spec['recovery']['history_sha256']==sha(history),'recovery_plan_identity_policy')
    process=plan['gpu_process'];exact(process,('python','entry','boot_id','uid','gpu_uuid','stop_policy'))
    import re
    require(process['python']==PYTHON and process['entry']==ENTRY and process['stop_policy']==RECOVERY_POLICY
        and type(process['uid']) is int and process['uid']>=0
        and type(process['boot_id']) is str and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',process['boot_id'])
        and type(process['gpu_uuid']) is str and re.fullmatch(r'GPU-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',process['gpu_uuid']),
        'recovery_plan_owned_gpu')
    expected={'seed':20260928,'tf32':True,'quantization':'nf4_double_quant_bfloat16',
        'prepare_base':'prepare_model_for_kbit_training_no_checkpoint_hooks','base_route':'same_PEFT_model_disable_adapter',
        'lora_trainable':False,'local_files_only':True,'trust_remote_code':False,'device':0,'parse_repair':False,'training':False}
    require(plan['loader_policy']==expected,'recovery_original_inference_policy')
    assets=plan['model_assets']
    require(assets['manifest_raw_sha256']=='5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd'
        and assets['snapshot_dir']=='/data/hf-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/'+COMPARISON['base_revision']
        and assets['adapter_root']=='/data/c5-runs-20261001/formal/checkpoint-132'
        and assets['adapter_files']=={'adapter_config.json':'8a776a47b085b787b7c7f3c9b068aed8c0f018278de2b94bf66130f5542d6d4f',
            'adapter_model.safetensors':'da8acdcde2671aa397534b35369fe4a84b9d150f80f7b7026a4366a770be2883'}
        and sha(assets['adapter_files'])==COMPARISON['adapter_sha256'],'recovery_original_model_contract')
    acceptance=plan['host_acceptance']
    require(acceptance['instance_id']==INSTANCE and sha(acceptance)==spec['host_policy']['acceptance_record_sha256']
        and all(acceptance[k] is True for k in ('owner_confirms_blank_active_document',
            'owner_confirms_exclusive_use_and_no_other_operations_during_research',
            'owner_accepts_readable_files_frozen_opaque_host_trusted_visible_checkpoints_only')), 'recovery_current_host_acceptance')
    require(plan['resource_basis']['platform_hour_quota'] is None
        and plan['resource_basis']['historical_cumulative_upper_bound_seconds'] is None
        and plan['resource_basis']['accepted_development_seconds_max']==18000
        and plan['resource_basis']['accepted_conditional_formal_seconds_max']==64800,
        'recovery_resource_fact_not_platform_balance')
