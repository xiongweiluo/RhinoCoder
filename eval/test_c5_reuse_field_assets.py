"""Independent observed map/scope negatives, no live environment inspections."""
import copy
import pytest
from tools.check_c5_reuse_field_assets import check_assets,digest


def records():
    distribution={'/data/conda-envs/rhinocoder/lib/python3.11/site-packages/x.py':'a'*64}
    stdlib={'/data/conda-envs/rhinocoder/lib/python3.11/json.py':'b'*64}
    environment={'inventory_sha256':digest({'lib/python3.11/site-packages/x.py':'a'*64}),
        'stdlib_inventory_sha256':digest({'lib/python3.11/json.py':'b'*64}),
        'distribution_file_count':1,'stdlib_file_count':1,'packages':{'x':{'version':'1.0'}},
        'executable_sha256':'c'*64,'libpython_files':{'lib/libpython3.11.so':'d'*64},'python':'CPU fixture','platform':'CPU fixture',
        'gpu_name':'CPU GPU','gpu_total_memory':'24576 MiB','driver_version':'CPU driver','missing_metadata_files':['pip:CPU missing']}
    assets={'base_files':{'tokenizer.json':'a'*64},'adapter_files':{'adapter_model.safetensors':'b'*64},
            'manifest_raw_sha256':'f'*64}
    plan={'model_assets':assets,'environment':{'gpu':environment,'mac':{'file_sha256':{'/opt/anaconda3/lib/a.py':'a'*64}}},
        'host_readable_files':{'/Applications/Rhino 8.app/Contents/a.dll':'b'*64},
        'gpu_process':{'boot_id':'CPU boot','gpu_uuid':'GPU-CPU'}}
    gpu={'model_loaded':False,'cuda_initialized_by_this_checker':False,'remote_files_written':0,'private_evidence_reads':0,
        'base_files':assets['base_files'].copy(),'adapter_files':assets['adapter_files'].copy(),
        'base_manifest_sha256':'f'*64,'base_files_match_pinned_manifest':True,
        'distribution_file_sha256':distribution,'distribution_inventory_sha256':digest(distribution),
        'stdlib_file_sha256':stdlib,'stdlib_inventory_sha256':digest(stdlib),'packages':{'x':'1.0'},
        'interpreter_sha256':'c'*64,'libpython_file_sha256':{'/data/conda-envs/rhinocoder/lib/libpython3.11.so':'d'*64},
        'target_runtime':{'python':'CPU fixture','platform':'CPU fixture'},'boot_id':'CPU boot',
        'gpu_rows':['GPU-CPU, CPU GPU, CPU driver, 11, 24576, 0'],'historical_policy_missing_metadata_files':['pip:CPU missing'],
        'start_epoch':100,'finish_epoch':101}
    mac={'model_or_rhino_calls':0,'private_evidence_reads':0,'rhino_instance_prepared_or_subscribed':False,'epoch':102,
        'host':{'file_sha256':plan['host_readable_files'].copy(),'missing':[],'changed':[]},
        'mac_python':{'file_sha256':plan['environment']['mac']['file_sha256'].copy(),'missing':[],'changed':[]}}
    return plan,gpu,mac


def test_complete_supplied_maps_retain_observation_and_origin_limits():
    result=check_assets(*records())
    assert result['supplied_actual_installed_asset_maps_verified'] and result['gpu_observation_epochs']==[100,101]
    assert not result['human_or_transport_acquisition_origin_proven'] and not result['execution_ready']


@pytest.mark.parametrize('change',['base','adapter','stdlib','distribution','interpreter','package','libpython',
                                  'runtime','boot','gpu','host','mac','private','loaded'])
def test_rehashed_or_missing_current_assets_never_reuse_a_historical_verdict(change):
    p,g,m=copy.deepcopy(records())
    if change=='base':g['base_files']['tokenizer.json']='0'*64
    elif change=='adapter':g['adapter_files']['adapter_model.safetensors']='0'*64
    elif change in ('stdlib','distribution'):
        k=change+'_file_sha256';g[k][next(iter(g[k]))]='0'*64;g[change+'_inventory_sha256']=digest(g[k])
    elif change=='interpreter':g['interpreter_sha256']='0'*64
    elif change=='package':g['packages']['x']='2.0'
    elif change=='libpython':g['libpython_file_sha256'].clear()
    elif change=='runtime':g['target_runtime']['python']='other'
    elif change=='boot':g['boot_id']='other'
    elif change=='gpu':g['gpu_rows']=['GPU-other, RTX']
    elif change=='host':m['host']['changed']=['a.dll']
    elif change=='mac':m['mac_python']['file_sha256'].clear()
    elif change=='private':g['private_evidence_reads']=1
    else:g['model_loaded']=True
    with pytest.raises(ValueError):check_assets(p,g,m)
