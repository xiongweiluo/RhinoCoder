"""New fixed study CPU/synthetic admission and signed cleanup controls only."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_hostassurance_development_scope import (
    ID,SPEC,TRANSITION,CONSENT,public,authority,MAC_SOURCE,REMOTE_SOURCE,STATE,REMOTE_STATE,
)
from plugin.rhino_listener.c5_host_assurance_session import STUDIES
from plugin.rhino_listener.c5_hostassurance_development_hub import CleanupAwareBridge
from plugin.rhino_listener.c5_research_native import NativeError,digest
from plugin.rhino_listener.c5_research_gate import signature
import plugin.rhino_listener.c5_research_session as bridge_module

ROOT=Path(__file__).resolve().parents[1]


def records():
    spec=copy.deepcopy(public(ROOT,SPEC));spec['execution_ready']=True
    freeze={'study_id':ID,'probe_id':ID,'execution_ready':True,'spec_sha256':digest(spec),
        'host_assurance':copy.deepcopy(spec['host_assurance']),
        'model_identities':{'base':'63f7de2f37a997c829ec98eaf617cdc78808586bc9df1139a90c030c4d76ebae',
            'lora':spec['adapter_sha256']},'legacy_byte_closure_verified':False,'formal_execution_ready':False,
        'missing_metadata_files':['pip:../../../bin/pip3.13'],
        'resource_boundary':{'owner_confirmed':True,'hard_stop_epoch':1791392400,'provider_expiry_epoch':1791392400,
            'export_reserve_seconds':900,'development_max_seconds':3259,'prior_cumulative_seconds':7540.027163848994,
            'original_cumulative_max_seconds':57600}}
    approval={'study_id':ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
        'runtime_freeze_sha256':digest(freeze),'approval_basis':STUDIES[ID]}
    return spec,freeze,approval,public(ROOT,TRANSITION),public(ROOT,CONSENT)


def test_new_fixed_profile_never_reuses_retired_roots():
    assert len({MAC_SOURCE,REMOTE_SOURCE,STATE,REMOTE_STATE})==4
    assert authority(*records(),check_time=False)['whole_field_authority_verified'] is False


@pytest.mark.parametrize('change',['draft','old_grant','root','port','model','pip','budget','extra_slot',
    'expanded_write','strong_byte_claim','default_route','retry'])
def test_no_scope_expansion_with_synthetic_rehashed_grant(change):
    spec,freeze,approval,transition,consent=records()
    if change=='draft':spec['execution_ready']=False
    elif change=='old_grant':approval['approval_basis']='old native12 or B'
    elif change=='root':spec['mac_state_root']='/tmp/fresh'
    elif change=='port':spec['ssh_port']=24206
    elif change=='model':spec['adapter_sha256']='a'*64
    elif change=='pip':freeze['missing_metadata_files']=[]
    elif change=='budget':freeze['resource_boundary']['development_max_seconds']=3600
    elif change=='extra_slot':spec['slot_order'].append('extra-lora')
    elif change=='expanded_write':spec['slot_policies']['read-base']['max_writes']=1
    elif change=='strong_byte_claim':freeze['legacy_byte_closure_verified']=True
    elif change=='default_route':spec['default_route_change_allowed']=True
    elif change=='retry':spec['automatic_retry_allowed']=True
    freeze['spec_sha256']=approval['spec_sha256']=digest(spec);approval['runtime_freeze_sha256']=digest(freeze)
    with pytest.raises(NativeError):authority(spec,freeze,approval,transition,consent,check_time=False)


def fake_bridge():
    b=object.__new__(CleanupAwareBridge)
    calls=[]
    def normal():calls.append('dispatch_guard');raise NativeError('host drift')
    def cleanup():calls.append('cleanup_guard');return 'a'*64
    b.guard_source,b.cleanup_source,b.source_sha=normal,cleanup,'a'*64
    b.current_request=None;b._attest=lambda request:None
    b._active=lambda:'active'
    b.attached=True;b.stopped=False;b.blocked=True;b.close_attempted=False;b.pending=None
    b.clock=lambda:100;b.control_ids=set();b.key_name='handoff.key';b.directory=Path('/synthetic-only')
    def close():calls.append('close');return {'fixture_registry_absent':True}
    b.gate=SimpleNamespace(secret=b'x'*32,owner_freeze='b'*64,task_sha='c'*64,backend=SimpleNamespace(close=close))
    return b,calls


def message(b,kind='control',action='close'):
    p={'version':1,'request_id':'synthetic_close_only_id_0123456789','task_sha256':b.gate.task_sha,
        'owner_freeze_sha256':b.gate.owner_freeze,'action':action,'expires_at':200}
    return {'kind':kind,'envelope':{'payload':p,'signature':signature(b.gate.secret,p)}}


def test_signed_close_can_reconcile_owned_fixture_without_admitting_dispatch(monkeypatch):
    b,calls=fake_bridge()
    monkeypatch.setattr(bridge_module,'remove_private_key',lambda *args:{'key_removed':True,'actual_absence_checked':True})
    result=b.handle(message(b))
    assert result['status']=='closed' and calls==['cleanup_guard','close']
    with pytest.raises(NativeError):b.handle(message(b,kind='execute'))
    assert calls[-1]=='dispatch_guard'


def test_bad_signature_gets_no_cleanup_effect_even_if_host_blocked():
    b,calls=fake_bridge();sent=message(b);sent['envelope']['signature']='0'*64
    with pytest.raises(NativeError,match='signature'):b.handle(sent)
    assert calls==['cleanup_guard'] and not b.close_attempted


def test_capture_cannot_borrow_cleanup_mode():
    b,calls=fake_bridge()
    with pytest.raises(NativeError):b.handle(message(b,action='capture'))
    assert calls==['dispatch_guard']


def test_all_new_entries_import_without_live_rhino_or_model():
    import tools.c5_rhino_hostassurance_dev
    import tools.run_c5_hostassurance_dev_worker
    assert callable(tools.c5_rhino_hostassurance_dev.start)
