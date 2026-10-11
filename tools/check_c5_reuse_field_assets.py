#!/usr/bin/env python3
"""Independent map reduction from explicit fresh readonly asset receipts.

No imports of model/entry/host producer. Supplied observations retain their
timestamps and origin limitation; authenticated acquisition is separate.
"""
import hashlib
import json
from pathlib import Path
import re
import argparse


def require(ok,code):
    if not ok:raise ValueError(code)


def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def check_assets(plan,gpu,mac):
    require(gpu['model_loaded'] is gpu['cuda_initialized_by_this_checker'] is False
        and gpu['remote_files_written']==gpu['private_evidence_reads']==0
        and mac['model_or_rhino_calls']==mac['private_evidence_reads']==0
        and mac['rhino_instance_prepared_or_subscribed'] is False,'field_assets_checker_effects')
    assets=plan['model_assets'];environment=plan['environment']['gpu'];prefix=Path('/data/conda-envs/rhinocoder')
    require(gpu['base_files']==assets['base_files'] and gpu['adapter_files']==assets['adapter_files']
        and gpu['base_manifest_sha256']==assets['manifest_raw_sha256'] and gpu['base_files_match_pinned_manifest'] is True,
        'field_assets_original_model_bytes')
    for kind in ('distribution','stdlib'):
        full=gpu[kind+'_file_sha256'];require(digest(full)==gpu[kind+'_inventory_sha256'],'field_assets_raw_map')
        normalized={str(Path(n).relative_to(prefix)):s for n,s in full.items()
                    if '__pycache__' not in Path(n).parts and Path(n).suffix not in ('.pyc','.pyo')}
        key='inventory_sha256' if kind=='distribution' else 'stdlib_inventory_sha256'
        require(digest(normalized)==environment[key] and len(normalized)==environment[kind+'_file_count'],
                'field_assets_installed_environment')
    versions={re.sub(r'[-_.]+','-',k).lower():v for k,v in gpu['packages'].items()}
    require(all(versions.get(k)==v['version'] for k,v in environment['packages'].items())
        and gpu['interpreter_sha256']==environment['executable_sha256']
        and {str(Path(n).relative_to(prefix)):s for n,s in gpu['libpython_file_sha256'].items()}==environment['libpython_files']
        and gpu['target_runtime']=={k:environment[k] for k in ('python','platform')},'field_assets_interpreter_packages')
    require(gpu['boot_id']==plan['gpu_process']['boot_id'] and len(gpu['gpu_rows'])==1
        and gpu['gpu_rows'][0].split(',')[0].strip()==plan['gpu_process']['gpu_uuid'],'field_assets_current_boot_gpu')
    fields=[v.strip() for v in gpu['gpu_rows'][0].split(',')]
    require(len(fields)==6 and fields[1]==environment['gpu_name']
            and fields[2]==environment['driver_version'] and fields[4]+' MiB'==environment['gpu_total_memory'],
            'field_assets_gpu_driver_and_capacity')
    require(gpu['historical_policy_missing_metadata_files']==environment['missing_metadata_files'],
            'field_assets_missing_metadata_preserved')
    require(mac['host']['file_sha256']==plan['host_readable_files']
        and mac['mac_python']['file_sha256']==plan['environment']['mac']['file_sha256']
        and all(mac[k]['missing']==mac[k]['changed']==[] for k in ('host','mac_python')),'field_assets_current_mac_bytes')
    return {'supplied_actual_installed_asset_maps_verified':True,
        'gpu_observation_epochs':[gpu['start_epoch'],gpu['finish_epoch']],'mac_observation_epoch':mac['epoch'],
        'human_or_transport_acquisition_origin_proven':False,'model_calls':0,'rhino_calls':0,'execution_ready':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--gpu-receipt',type=Path,required=True)
    p.add_argument('--mac-receipt',type=Path,required=True);a=p.parse_args()
    values=[]
    for path in (a.plan,a.gpu_receipt,a.mac_receipt):
        require(path.is_absolute() and path.resolve()==path and path.is_file()
                and 0<path.stat().st_size<=8*1024*1024,'field_assets_public_receipt_path')
        values.append(json.loads(path.read_bytes()))
    print(json.dumps(check_assets(*values),sort_keys=True))


if __name__=='__main__':main()
