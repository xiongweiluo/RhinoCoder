#!/usr/bin/env python3
"""Build one new C5 development freeze from actual read-only preflights.

This command never creates owner approval, a run claim, a model process,
Rhino fixture, or a holdout read. Its output is non-overwriting and remains
non-executable until the owner directly approves BOTH printed hashes.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from plugin.rhino_listener.c5_research_native import digest,require
from tools.c5_modelbridge_client import preflight,ssh_args
from tools.c5_modelbridge_common import ROOT,public
from training.c5_model_transport import strict_json,LIMIT
from training.c5_modelbridge_runtime import file_sha

TARGET=ROOT/'eval/c5/modelbridge-runtime-freeze-20261003-b.json'
SPEC=ROOT/'eval/c5/modelbridge-development-spec-20261003-b.json'
BOUNDARY=ROOT/'eval/c5/rhino-resource-boundary-v3-20261003.json'


def source_files():
    result={p.relative_to(ROOT).as_posix():file_sha(p) for folder in (
        'agent','training','tools','plugin','data_pipeline')
        for p in sorted((ROOT/folder).rglob('*.py'))}
    result['eval/c5/rhino-runtime-schema-v1.json']=file_sha(ROOT/'eval/c5/rhino-runtime-schema-v1.json')
    require(len(result)<=512,'source inventory exceeds guard budget')
    return result


def build():
    require(not TARGET.exists(),'one freeze path already exists; no rewrite')
    spec=public(SPEC)
    require(spec['execution_ready'] is True and spec['state']=='FROZEN_AWAITING_EXACT_OWNER_APPROVAL',
            'completed and reviewable development spec required')
    resource=public(BOUNDARY)
    require(resource['owner_reported_expiry_utc']=='2026-10-04T18:00:00Z'
            and resource['latest_generation_cutoff_utc']=='2026-10-04T17:45:00Z'
            and resource['new_b_execution_authorized'] is False
            and resource['retired_a_actual_elapsed_seconds_including_load_and_idle']<18
            and resource['new_b_max_seconds']==3500
            and resource['combined_a_plus_b_ceiling_seconds']<3600,
            'new B residual development boundary differs')
    local=preflight(include_manifest=True)
    command=('cd /data/RhinoCoder-c5-modelbridge-B && '
             '/data/conda-envs/rhinocoder/bin/python -B -m tools.run_c5_modelbridge_worker preflight')
    remote=strict_json(subprocess.check_output(ssh_args()+[command],timeout=240))
    import_command=('cd /data/RhinoCoder-c5-modelbridge-B && '
             '/data/conda-envs/rhinocoder/bin/python -B -m tools.run_c5_modelbridge_worker import-preflight')
    imports=strict_json(subprocess.check_output(ssh_args()+[import_command],timeout=240))
    require(remote['status']=='modelbridge_readonly_preflight_not_execution_authority'
            and remote['model_loaded'] is False and remote['holdout_rows_read']==0
            and remote['gpu_generation_calls']==0 and local['gpu_calls']==local['holdout_calls']==0,
            'actual read-only preflights differ')
    sources=source_files()
    fixed={name:file_sha(ROOT/name) for name in (
        'requirements-training.txt','requirements.txt','eval/c5/c5-engineering-config.json',
        'eval/c5/gpu-formal-registry-20261001.json')}
    require(remote['source_files']==sources and remote['fixed_public_files']==fixed,
            'Mac/remote source or public configuration bytes differ')
    require(imports['status']=='read_only_loader_import_closure_verified_not_execution_authority'
            and imports['environment_sha256']==remote['environment_sha256']
            and imports['source_inventory_sha256']==digest(sources)
            and imports['cuda_initialized'] is False and imports['model_loaded'] is False
            and imports['generation_calls']==imports['holdout_rows_read']==0,
            'actual remote loader-import closure differs')
    require(remote['adapter_sha256']==spec['adapter_sha256']
            and remote['environment']['missing_metadata_files']==['pip:../../../bin/pip3.13']
            and remote['environment']['gpu_name']=='NVIDIA GeForce RTX 3090'
            and remote['environment']['gpu_total_memory']=='24576 MiB',
            'actual remote base/adapter/environment differs')
    prior=public(ROOT/'eval/c5/rhino-resource-boundary-20261002.json')
    require(prior['prior_public_active_usage_approx_gpu_hours']<=2,
            'prior public GPU use exceeds conservative 2h reservation')
    native=public(ROOT/'eval/c5/native12-development-audit-20261003.json')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(len(revision)==40,'immutable local source revision required')
    freeze={'schema_version':1,'probe_id':spec['probe_id'],
        'state':'PREEXECUTION_SOURCE_FREEZE_WAIT_NEW_OWNER_APPROVAL',
        'execution_ready':True,'source_revision':revision,'spec_sha256':digest(spec),
        'spec_file_sha256':file_sha(SPEC),'source_files':sources,
        'source_inventory_sha256':digest(sources),'fixed_public_files':fixed,
        'resource_boundary_v3_file_sha256':file_sha(BOUNDARY),
        'resource_boundary':{'owner_confirmed':True,'provider_expiry_epoch':1791136800,
            'hard_stop_epoch':1791136800,'export_reserve_seconds':900,
            'development_max_seconds':3500,'prior_cumulative_seconds':7218,
            'original_cumulative_max_seconds':57600},
        'prior_cumulative_accounting_note':'7218 seconds reserves 7200 prior seconds plus the retired A actual 17.614 seconds, rounded upward; public prior active use approximately 1.72828 GPU-hours, not provider billing',
        'environment_sha256':remote['environment_sha256'],
        'remote_import_preflight':imports,
        'remote_environment_summary':{'python':remote['environment']['python'],
            'distribution_file_count':remote['environment']['distribution_file_count'],
            'missing_metadata_files':remote['environment']['missing_metadata_files'],
            'gpu_name':remote['environment']['gpu_name'],
            'gpu_total_memory':remote['environment']['gpu_total_memory'],
            'driver_version':remote['environment']['driver_version']},
        'mac_environment':local['mac_environment'],
        'tokenizer_files':local['tokenizer_files'],
        'max_input_plus_output_reserve_tokens':local['max_input_plus_output_reserve_tokens'],
        'model_identities':{'base':digest(remote['snapshot']),'lora':spec['adapter_sha256']},
        'rhino_version':native['rhino_version'],
        'original_final_run_access_allowed':False,'new_holdout_access_allowed':False,
        'training_allowed':False,'default_route_change_allowed':False,
        'automatic_retry_allowed':False,'automatic_merge_allowed':False,
        'exact_owner_approval_record_present':False}
    raw=(json.dumps(freeze,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    require(len(raw)<=LIMIT,'complete freeze exceeds fixed public JSON size bound')
    fd=os.open(TARGET,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    try:
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(raw);stream.flush();os.fsync(fd)
    finally:os.close(fd)
    return {'status':'new_development_freeze_written_waiting_exact_owner_approval',
            'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
            'source_revision':revision,'source_files':len(sources),
            'mac_environment_file_count':local['mac_environment_file_count'],
            'remote_environment_sha256':remote['environment_sha256'],
            'model_calls':0,'holdout_calls':0}


if __name__=='__main__':print(json.dumps(build(),sort_keys=True))
