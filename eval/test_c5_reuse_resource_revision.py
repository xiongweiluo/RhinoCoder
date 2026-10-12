"""Accepted finite resource revision; inert CPU records, no field admission."""
import copy
import pytest
from eval.test_c5_reuse_field_preparation import records
from training.c5_reuse_freeze_materials import build
from plugin.rhino_listener.c5_reuse_field_scope import bind,RESOURCE_ACCEPTANCE,RESOURCE_POLICY,sha
from training.c5_reuse_budget import ReuseBudget
from training.c5_reuse_gpu_entry_audit import _budget
from training.c5_reuse_gpu_supervisor import Watchdog
from plugin.rhino_listener.c5_reuse_field_scope import LIMITS
from pathlib import Path


def revised(tmp_path):
    s,r,a,_=records(tmp_path)
    s['resources']={'lease_expiry_epoch':1791914400,'generation_cutoff_epoch':1791913500,'export_reserve_seconds':900,
        'prior_cumulative_upper_bound_seconds':None,'remaining_gpu_seconds':82800,'development_seconds_max':18000,
        'formal_seconds_max':64800,'research_seconds_max':82800,'original_cumulative_seconds_max':57600,
        'resource_policy':RESOURCE_POLICY,'resource_revision_acceptance_sha256':sha(RESOURCE_ACCEPTANCE),
        'original_cumulative_compliance_claimed':False}
    return s,r,a


def rebound(s,r,a):
    r['resources']=copy.deepcopy(s['resources']);r['spec_sha256']=a['spec_sha256']=sha(s);a['runtime_sha256']=sha(r)


@pytest.mark.parametrize('change',['valid','zero_history','old_count','original_compliance','more_development',
    'more_formal','transfer','wrong_acceptance','lease','cutoff','no_reserve','fake_quota'])
def test_unknown_history_is_disclosed_and_new_budget_cannot_be_rewritten(tmp_path,change):
    s,r,a=revised(tmp_path);q=s['resources']
    if change=='zero_history':q['prior_cumulative_upper_bound_seconds']=0
    elif change=='old_count':q['prior_cumulative_upper_bound_seconds']=9607
    elif change=='original_compliance':q['original_cumulative_compliance_claimed']=True
    elif change=='more_development':q['development_seconds_max']=18001
    elif change=='more_formal':q['formal_seconds_max']=64801
    elif change=='transfer':q['development_seconds_max']=17999;q['formal_seconds_max']=64801
    elif change=='wrong_acceptance':q['resource_revision_acceptance_sha256']='0'*64
    elif change=='lease':q['lease_expiry_epoch']+=86400
    elif change=='cutoff':q['generation_cutoff_epoch']+=1
    elif change=='no_reserve':q['export_reserve_seconds']=0
    elif change=='fake_quota':q['remaining_gpu_seconds']=999999
    rebound(s,r,a)
    if change=='valid':assert bind(s,r,a,now=100,endpoint='gpu')['record_binding_verified']
    else:
        with pytest.raises(ValueError):bind(s,r,a,now=100,endpoint='gpu')


def test_full_phase_is_not_silently_truncated_and_raw_auditor_preserves_unknown(tmp_path):
    s,_,_=revised(tmp_path);q=s['resources'];clock=[q['generation_cutoff_epoch']-18000,100.]
    b=ReuseBudget(q,wall=lambda:clock[0],mono=lambda:clock[1])
    assert b.reservation==18000 and b.cap==17940
    _budget(b.observation(),q)
    bad=b.observation();bad['reserved_wall_seconds']=17999
    with pytest.raises(ValueError):_budget(bad,q)
    clock[0]+=1
    with pytest.raises(ValueError,match='full_phase_reservation_unavailable'):
        ReuseBudget(q,wall=lambda:clock[0],mono=lambda:clock[1])
    w=Watchdog(100,17940,clock=lambda:100,limits=LIMITS)
    assert w.hard==18040
    with pytest.raises(ValueError):Watchdog(100,18001,limits=LIMITS)


def test_actual_namespace_rejects_legacy_cumulative_authority(tmp_path):
    s,r,a,_=records(tmp_path);s['instance_id']='reuse-dev-20261012-c';r['instance_id']=s['instance_id']
    rebound(s,r,a)
    with pytest.raises(ValueError,match='actual_resource_revision_required'):bind(s,r,a,now=100,endpoint='gpu')


def test_material_requires_explicit_resource_record_not_execution_authority():
    root=Path(__file__).resolve().parents[1]
    args=dict(environment={},model_assets={},host_files={},host_acceptance={},gpu_process={},transport={},
              current_gpu_independently_rechecked=True)
    s,r,p,_,review=build(root,**args)
    assert not s['execution_ready'] and 'explicit_resource_revision_acceptance' in review['pending_facts']
    s,r,p,_,review=build(root,resource_acceptance=RESOURCE_ACCEPTANCE,**args)
    assert s['execution_ready'] and r['execution_ready'] and not review['execution_ready']
    assert s['resources']['prior_cumulative_upper_bound_seconds'] is None
    assert p['resource_basis']['resource_revision_acceptance']['exact_two_hash_execution_approval_received'] is False
    invalid=copy.deepcopy(RESOURCE_ACCEPTANCE);invalid['formal_seconds_max']+=1
    with pytest.raises(ValueError):build(root,resource_acceptance=invalid,**args)
