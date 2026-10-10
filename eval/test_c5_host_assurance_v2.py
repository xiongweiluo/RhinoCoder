"""Proposal only: no default guard or actual host execution."""
import copy

import pytest

from plugin.rhino_listener.c5_host_assurance_v2 import POLICY,ASSUMPTIONS,validate_transition,compare_visible_continuity
from plugin.rhino_listener.c5_research_native import digest,NativeError


def data():
    row={'instance_id':'opaque-1','name':'synthetic-not-an-allowlist','dynamic':True,'file':None,
        'visible_types':[],'visible_type_count':0}
    row['surface_sha256']=digest(row)
    baseline={'process_identity':'a'*64,'active_sha256':'b'*64,'active_serial':1,'active_object_count':0,
        'python_origins':[{'module':name,'origin':'unknown','object_identity':'same'} for name in ('CLR','clr')],
        'assemblies':[row],'native_images':[{'origin_sha256':'c'*64,'file_sha256':None,'state':'unverified'}],
        'inspection_limits':['opaque code is a host trust assumption']}
    return baseline,copy.deepcopy(baseline),{'events':[],'dropped':0,'errors':[]}


def test_positive_is_explicitly_not_execution_or_byte_proof():
    baseline,now,events=data();result=compare_visible_continuity(baseline,now,events)
    assert result['visible_checkpoint_continuity_verified']
    for key in ('execution_authority','causal_origin_or_emitted_bytes_proven','legacy_byte_closure_verified',
        'continuous_between_checkpoint_integrity_proven'):assert result[key] is False


@pytest.mark.parametrize('change',['same_name_new_instance','same_instance_changed_surface','new_assembly',
    'new_native_image','rebound_CLR','new_python_module','process','document','missing_limits',
    'new_event','dropped_event','event_error','missing_CLR'])
def test_no_baseline_or_name_exception_for_changes(change):
    baseline,now,events=data()
    if change=='same_name_new_instance':now['assemblies'][0]['instance_id']='another'
    elif change=='same_instance_changed_surface':now['assemblies'][0]['visible_type_count']=1
    elif change=='new_assembly':now['assemblies'].append(copy.deepcopy(now['assemblies'][0]));now['assemblies'][1]['instance_id']='new'
    elif change=='new_native_image':now['native_images'].append({'unverified':'new'})
    elif change=='rebound_CLR':now['python_origins'][0]['object_identity']='different'
    elif change=='new_python_module':now['python_origins'].append({'module':'new'})
    elif change=='process':now['process_identity']='d'*64
    elif change=='document':now['active_sha256']='d'*64
    elif change=='missing_limits':now['inspection_limits']=[]
    elif change=='new_event':events['events']=[{'same_name':'still refused'}]
    elif change=='dropped_event':events['dropped']=1
    elif change=='event_error':events['errors']=['error']
    elif change=='missing_CLR':baseline['python_origins']=now['python_origins']=[]
    for row in now['assemblies']:
        row['surface_sha256']=digest({k:v for k,v in row.items() if k!='surface_sha256'})
    with pytest.raises(NativeError):compare_visible_continuity(baseline,now,events)


def test_old_or_broad_approval_is_not_transition_consent():
    spec={'policy_id':POLICY,'purpose':'guarantee_transition_preparation_only_no_execution',
        'assumptions':copy.deepcopy(ASSUMPTIONS),'default_admission_enabled':False,'model_or_fixture_or_holdout_authorized':False}
    approval={'actor':'repository_owner','approved':True,'policy_id':POLICY,'transition_spec_sha256':digest(spec),
        'approval_basis':'direct owner acceptance of weaker host assurance and research-exclusive preparation; no study execution'}
    assert validate_transition(spec,approval)['model_or_fixture_or_holdout_authorized'] is False
    with pytest.raises(NativeError):validate_transition(spec,{'actor':'repository_owner','approved':True})
    spec['assumptions']['reflection_does_not_prove_emitted_bytes_or_causal_origin']=False
    approval['transition_spec_sha256']=digest(spec)
    with pytest.raises(NativeError):validate_transition(spec,approval)
