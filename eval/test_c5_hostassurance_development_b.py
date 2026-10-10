"""B exact scope and deferred release: synthetic only, never live entry."""
import copy
import io
import tarfile
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_hostassurance_development_scope_b import ID,SPEC,public,authority,TRANSITION,CONSENT
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
            'export_reserve_seconds':900,'development_max_seconds':3222,'prior_cumulative_seconds':7577.8156609169965,
            'original_cumulative_max_seconds':57600}}
    a={'study_id':ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(s),
        'runtime_freeze_sha256':digest(f),'approval_basis':STUDIES[ID]}
    return s,f,a,public(ROOT,TRANSITION),public(ROOT,CONSENT)


def test_b_has_distinct_scope_same_strict_visible_comparison_and_smaller_budget():
    value=authority(*records(),check_time=False)
    assert value['study_id']=='C5DEV-HOSTASSURANCE-20261007-B'
    assert value['whole_field_authority_verified'] is False


@pytest.mark.parametrize('change',['a_grant','a_policy','a_state','old_budget','main_ignore','premature_release','dispatch_on_seal'])
def test_no_a_replay_or_name_exception_even_with_synthetic_rehashed_grant(change):
    s,f,a,t,c=records()
    if change=='a_grant':a['study_id']='C5DEV-HOSTASSURANCE-20261007-A'
    elif change=='a_policy':s['host_assurance']['baseline_sealing']=f['host_assurance']['baseline_sealing']='after_declared_import_type_controller_warmup_before_any_model_generation'
    elif change=='a_state':s['mac_state_root']=s['mac_state_root'].replace('20261007-B','20261007-A')
    elif change=='old_budget':f['resource_boundary']['development_max_seconds']=3259
    elif change=='main_ignore':s['host_assurance']['ignored_module']='__main__'
    elif change=='premature_release':s['entry_return_protocol']['release_called_after_run_path_returns']=False
    elif change=='dispatch_on_seal':s['entry_return_protocol']['seal_callback_dispatches_no_task']=False
    f['spec_sha256']=a['spec_sha256']=digest(s);a['runtime_freeze_sha256']=digest(f)
    with pytest.raises(NativeError):authority(s,f,a,t,c,check_time=False)


def test_b_entry_import_does_not_arm_or_execute():
    import tools.c5_rhino_hostassurance_dev_b as entry
    assert callable(entry.start) and not hasattr(entry,'ENTRY_RETURN_BARRIER')


@pytest.mark.parametrize('variant',['gzip','plain','extra','duplicate','missing','symlink','hardlink','appledouble'])
def test_transport_exact_regular_population(variant):
    from tools.prepare_c5_hostassurance_development_freeze_b import verify_archive_population
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
