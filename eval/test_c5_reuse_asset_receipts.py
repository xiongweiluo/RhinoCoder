"""Small synthetic public metadata maps; never hash local/GPU installations."""
import copy
import hashlib
import json
import pytest
from tools.check_c5_reuse_asset_receipts import reduce_assets, digest


def fixture():
    root='/data/conda-envs/rhinocoder/'
    distributions={'lib/python3.11/site-packages/a.py':'a'*64}
    stdlib={'lib/python3.11/x.py':'b'*64}
    mac_files={'/public-code.py':'c'*64}
    base={'config.json':'d'*64}
    manifest_raw=json.dumps({'file_sha256':base}).encode()
    manifest_sha=hashlib.sha256(manifest_raw).hexdigest()
    env={'inventory_sha256':digest(distributions),'distribution_file_count':1,
         'stdlib_inventory_sha256':digest(stdlib),'stdlib_file_count':1,'missing_metadata_files':['pip:../../../bin/pip3.13'],
         'executable_sha256':'e'*64,'libpython_files':{'lib/libpython3.so':'f'*64},'packages':{'x':{'version':'1'}}}
    historical={'environment':env,'model_assets':{'adapter_files':{'adapter.bin':'f'*64},'base_manifest_sha256':manifest_sha,
        'base_file_identities':{'files':1}},'tokenizer_file_sha256':copy.deepcopy(base),
        'rhino_environment_files':mac_files,'mac_environment':{'file_sha256':mac_files}}
    gpu={'model_loaded':False,'cuda_initialized_by_this_checker':False,'remote_files_written':0,'private_evidence_reads':0,
        'distribution_file_sha256':{root+k:v for k,v in distributions.items()},
        'stdlib_file_sha256':{root+k:v for k,v in stdlib.items()},'missing_metadata_files':env['missing_metadata_files']+['x:__pycache__/a.pyc'],
        'interpreter_sha256':'e'*64,'libpython_file_sha256':{root+'lib/libpython3.so':'f'*64},'packages':{'x':'1'},
        'adapter_files':{'adapter.bin':'f'*64},'base_files_match_pinned_manifest':True,'base_manifest_sha256':manifest_sha,
        'base_manifest_raw_hex':manifest_raw.hex(),
        'base_files':base,'start_epoch':1,'finish_epoch':2,'boot_id':'cpu','gpu_rows':[]}
    gpu['distribution_file_sha256'][root+'lib/python3.11/site-packages/__pycache__/a.pyc']='2'*64
    for kind in ('distribution','stdlib'): gpu[kind+'_inventory_sha256']=digest(gpu[kind+'_file_sha256'])
    observation={'file_sha256':mac_files,'missing':[],'changed':[],'files':1,'inventory_sha256':digest(mac_files)}
    mac={'rhino_instance_prepared_or_subscribed':False,'old_instance_guarantee_transferred':False,
         'model_or_rhino_calls':0,'private_evidence_reads':0,'host':copy.deepcopy(observation),'mac_python':copy.deepcopy(observation),
         'epoch':3,'rhino_bundle_version':{'CFBundleVersion':'cpu'}}
    return historical,gpu,mac


def test_cache_policy_and_missing_exception_preserved_without_origin_or_execution_claim():
    h,g,m=fixture(); r=reduce_assets(h,g,m)
    assert r['inventories']['distribution']['additional_cache_bytecode_files']==1
    assert r['missing_metadata_files']==['pip:../../../bin/pip3.13']
    assert not any(r[k] for k in ('execution_ready','full_code_byte_closure_proven','complete_current_runtime_freeze',
                                  'observation_origin_independently_authenticated','new_host_acceptance_proven'))


@pytest.mark.parametrize('kind',['model','cuda','remote_write','private','host_prepare','host_transfer','mac_call',
    'raw_digest','loadable_bytes','extra_loadable','missing','interpreter','libpython','version','adapter','base_count','manifest','tokenizer','host_bytes','mac_count'])
def test_independent_asset_reduction_rejects_drift_even_after_rehash(kind):
    h,g,m=fixture()
    if kind=='model': g['model_loaded']=True
    elif kind=='cuda': g['cuda_initialized_by_this_checker']=True
    elif kind=='remote_write': g['remote_files_written']=1
    elif kind=='private': g['private_evidence_reads']=1
    elif kind=='host_prepare': m['rhino_instance_prepared_or_subscribed']=True
    elif kind=='host_transfer': m['old_instance_guarantee_transferred']=True
    elif kind=='mac_call': m['model_or_rhino_calls']=1
    elif kind=='raw_digest': g['distribution_inventory_sha256']='0'*64
    elif kind in ('loadable_bytes','extra_loadable'):
        k='/data/conda-envs/rhinocoder/lib/python3.11/site-packages/a.py'
        if kind=='extra_loadable': k+='.extra'
        g['distribution_file_sha256'][k]='0'*64
        g['distribution_inventory_sha256']=digest(g['distribution_file_sha256'])
    elif kind=='missing': g['missing_metadata_files'].append('extra:code.py')
    elif kind=='interpreter': g['interpreter_sha256']='0'*64
    elif kind=='libpython': g['libpython_file_sha256'].clear()
    elif kind=='version': g['packages']['x']='2'
    elif kind=='adapter': g['adapter_files']['adapter.bin']='0'*64
    elif kind=='base_count': g['base_files']['extra']='0'*64
    elif kind=='manifest': g['base_manifest_sha256']='0'*64
    elif kind=='tokenizer': g['base_files']['config.json']='0'*64
    elif kind=='host_bytes': m['host']['file_sha256']['/public-code.py']='0'*64
    else: m['mac_python']['files']=0
    with pytest.raises(ValueError): reduce_assets(h,g,m)
