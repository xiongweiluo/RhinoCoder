"""Independent reduction of supplied public observations; not origin proof.

No model/Rhino/process APIs, imports or writes. Epochs are observation times,
not lease or resource authority. Historical cache exclusions remain explicit.
"""
import hashlib
import json
from pathlib import Path
import re

ENV = Path('/data/conda-envs/rhinocoder')


def require(ok, code):
    if not ok:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def loadable(name):
    return '__pycache__' not in Path(name).parts and Path(name).suffix not in ('.pyc','.pyo')


def reduce_assets(historical, gpu, mac):
    require(gpu['model_loaded'] is gpu['cuda_initialized_by_this_checker'] is False, 'model effects')
    require(gpu['remote_files_written']==gpu['private_evidence_reads']==0, 'remote effects')
    require(mac['rhino_instance_prepared_or_subscribed'] is mac['old_instance_guarantee_transferred'] is False, 'host effects')
    require(mac['model_or_rhino_calls']==mac['private_evidence_reads']==0, 'mac effects')
    env=historical['environment']
    result={}
    for kind in ('distribution','stdlib'):
        supplied=gpu[kind+'_file_sha256']
        require(digest(supplied)==gpu[kind+'_inventory_sha256'], 'raw inventory digest drift')
        normalized={str(Path(name).relative_to(ENV)):value for name,value in supplied.items() if loadable(name)}
        expected=env['inventory_sha256' if kind=='distribution' else 'stdlib_inventory_sha256']
        require(digest(normalized)==expected and len(normalized)==env[kind+'_file_count'], 'loadable inventory drift')
        result[kind]={'historical_loadable_file_count':len(normalized),'inventory_sha256':expected,
                      'additional_cache_bytecode_files':len(supplied)-len(normalized)}
    missing=sorted(name for name in gpu['missing_metadata_files'] if loadable(name))
    require(missing==env['missing_metadata_files'], 'non-cache missing metadata drift')
    require(gpu['interpreter_sha256']==env['executable_sha256'], 'interpreter drift')
    require({str(Path(k).relative_to(ENV)):v for k,v in gpu['libpython_file_sha256'].items()}==env['libpython_files'], 'libpython drift')
    packages={}
    for name,version in gpu['packages'].items():
        normalized=re.sub(r'[-_.]+','-',name).lower()
        require(normalized not in packages, 'duplicate normalized package')
        packages[normalized]=version
    require(all(packages.get(name)==value['version'] for name,value in env['packages'].items()), 'package drift')
    require(gpu['adapter_files']==historical['model_assets']['adapter_files'], 'adapter drift')
    require(gpu['base_files_match_pinned_manifest'] is True, 'base observation incomplete')
    require(gpu['base_manifest_sha256']==historical['model_assets']['base_manifest_sha256'], 'base manifest drift')
    manifest_raw=bytes.fromhex(gpu['base_manifest_raw_hex'])
    require(hashlib.sha256(manifest_raw).hexdigest()==gpu['base_manifest_sha256'], 'base manifest bytes drift')
    manifest=json.loads(manifest_raw)
    require(manifest['file_sha256']==gpu['base_files'], 'base all file bytes drift')
    require(len(gpu['base_files'])==historical['model_assets']['base_file_identities']['files'], 'base population drift')
    require(all(gpu['base_files'].get(k)==v for k,v in historical['tokenizer_file_sha256'].items()), 'tokenizer drift')
    for key,expected in [('host',historical['rhino_environment_files']),('mac_python',historical['mac_environment']['file_sha256'])]:
        observation=mac[key]
        require(observation['file_sha256']==expected and observation['missing']==observation['changed']==[], 'mac files drift')
        require(observation['files']==len(expected) and observation['inventory_sha256']==digest(expected), 'mac inventory drift')
        result[key]={'files':len(expected),'inventory_sha256':digest(expected),'missing':0,'changed':0}
    return {'status':'supplied_current_readable_asset_maps_match_historical_population',
            'gpu_asset_observation_epoch':[gpu['start_epoch'],gpu['finish_epoch']],
            'mac_asset_observation_epoch':mac['epoch'],'gpu_boot_id':gpu['boot_id'],
            'gpu_rows':gpu['gpu_rows'],'gpu_python_executable_sha256':gpu['interpreter_sha256'],
            'inventories':result,'missing_metadata_files':missing,'base_files':len(gpu['base_files']),
            'adapter_files':len(gpu['adapter_files']),'rhino_bundle_version':mac['rhino_bundle_version'],
            'model_or_rhino_calls':0,'private_evidence_reads':0,'new_host_acceptance_proven':False,
            'observation_origin_independently_authenticated':False,'complete_current_runtime_freeze':False,
            'full_code_byte_closure_proven':False,'execution_ready':False}
