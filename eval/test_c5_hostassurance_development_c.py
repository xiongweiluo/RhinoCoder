"""C exact scope, deferred release and startup phase: synthetic only."""
import copy
import io
import tarfile
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_hostassurance_development_scope_c import ID,SPEC,public,authority,TRANSITION,CONSENT
from plugin.rhino_listener.c5_host_assurance_session import STUDIES
from plugin.rhino_listener.c5_research_native import digest,NativeError

ROOT=Path(__file__).resolve().parents[1]


def records():
    s=copy.deepcopy(public(ROOT,SPEC));s['execution_ready']=True
    f={'study_id':ID,'probe_id':ID,'execution_ready':True,'spec_sha256':digest(s),
        'host_assurance':copy.deepcopy(s['host_assurance']),
        'model_identities':{'base':'63f7de2f37a997c829ec98eaf617cdc78808586bc9df1139a90c030c4d76ebae','lora':s['adapter_sha256']},
        'legacy_byte_closure_verified':False,'formal_execution_ready':False,
        'missing_metadata_files':['pip:../../../bin/pip3.13'],
        'resource_boundary':{'owner_confirmed':True,'hard_stop_epoch':1791392400,'provider_expiry_epoch':1791392400,
            'export_reserve_seconds':900,'development_max_seconds':3104,'prior_cumulative_seconds':7695.654411741009,
            'original_cumulative_max_seconds':57600}}
    a={'study_id':ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(s),
        'runtime_freeze_sha256':digest(f),'approval_basis':STUDIES[ID]}
    return s,f,a,public(ROOT,TRANSITION),public(ROOT,CONSENT)


def test_c_has_distinct_scope_same_strict_visible_comparison_and_smaller_budget():
    value=authority(*records(),check_time=False)
    assert value['study_id']=='C5DEV-HOSTASSURANCE-20261007-C'
    assert value['whole_field_authority_verified'] is False


@pytest.mark.parametrize('change',['a_grant','b_grant','a_policy','a_state','old_budget','b_budget',
    'main_ignore','premature_release','dispatch_on_seal','missing_startup','startup_task_first','startup_integer_flag','old_request_window'])
def test_no_a_replay_or_name_exception_even_with_synthetic_rehashed_grant(change):
    s,f,a,t,c=records()
    if change=='a_grant':a['study_id']='C5DEV-HOSTASSURANCE-20261007-A'
    elif change=='b_grant':a['study_id']='C5DEV-HOSTASSURANCE-20261007-B'
    elif change=='a_policy':s['host_assurance']['baseline_sealing']=f['host_assurance']['baseline_sealing']='after_declared_import_type_controller_warmup_before_any_model_generation'
    elif change=='a_state':s['mac_state_root']=s['mac_state_root'].replace('20261007-C','20261007-A')
    elif change=='old_budget':f['resource_boundary']['development_max_seconds']=3259
    elif change=='b_budget':f['resource_boundary']['development_max_seconds']=3222
    elif change=='main_ignore':s['host_assurance']['ignored_module']='__main__'
    elif change=='premature_release':s['entry_return_protocol']['release_called_after_run_path_returns']=False
    elif change=='dispatch_on_seal':s['entry_return_protocol']['seal_callback_dispatches_no_task']=False
    elif change=='missing_startup':del s['startup_protocol']
    elif change=='startup_task_first':s['startup_protocol']['ready_before_any_model_fixture_open']=False
    elif change=='startup_integer_flag':s['startup_protocol']['ready_consumption_counts_zero']=1
    elif change=='old_request_window':s['per_request_timeout_seconds']=120
    f['spec_sha256']=a['spec_sha256']=digest(s);a['runtime_freeze_sha256']=digest(f)
    with pytest.raises(NativeError):authority(s,f,a,t,c,check_time=False)


def test_c_entry_import_does_not_arm_or_execute():
    import tools.c5_rhino_hostassurance_dev_c as entry
    assert callable(entry.start) and not hasattr(entry,'ENTRY_RETURN_BARRIER')


def test_all_independent_c_source_and_state_constants_are_not_retired_b():
    from plugin.rhino_listener import c5_hostassurance_development_scope_c as scope
    from tools import c5_hostassurance_dev_client_c as client,run_c5_hostassurance_dev_worker_c as worker
    s=public(ROOT,SPEC)
    assert str(scope.REMOTE_SOURCE)==client.REMOTE_SOURCE==str(worker.SOURCE)==s['remote_source_root']=='/data/RhinoCoder-c5-hostassurance-dev-C'
    assert str(scope.REMOTE_STATE)==client.REMOTE_STATE==str(worker.STATE)==s['remote_state_root']=='/data/c5-hostassurance-dev-state-20261007-C'
    assert str(scope.MAC_SOURCE)==s['mac_source_root']=='/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-source-20261007-C'


def test_static_driver_orders_ready_before_all_claims_and_fixture_open():
    import inspect
    from tools.c5_hostassurance_dev_client_c import drive
    source=inspect.getsource(drive)
    assert source.index('wire.wait_ready()') < source.index('for slot in spec') < source.index("hub.control('open',slot)")


@pytest.mark.parametrize('variant',['gzip','plain','extra','duplicate','missing','symlink','hardlink','appledouble'])
def test_transport_exact_regular_population(variant):
    from tools.prepare_c5_hostassurance_development_freeze_c import verify_archive_population
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w:gz' if variant=='gzip' else 'w') as stream:
        names=['tools/example.py']
        if variant=='extra':names.append('private.json')
        if variant=='duplicate':names.append(names[0])
        if variant=='missing':names=[]
        if variant=='appledouble':names.append('tools/._example.py')
        for name in names:
            item=tarfile.TarInfo(name)
            if variant in {'symlink','hardlink'}:
                item.type=tarfile.SYMTYPE if variant=='symlink' else tarfile.LNKTYPE
                item.linkname='outside.py';stream.addfile(item)
            else:
                item.size=1;stream.addfile(item,io.BytesIO(b'x'))
    if variant in {'gzip','plain'}:verify_archive_population(raw.getvalue(),['tools/example.py'])
    else:
        with pytest.raises(NativeError):verify_archive_population(raw.getvalue(),['tools/example.py'])
