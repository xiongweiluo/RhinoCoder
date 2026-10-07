"""Synthetic-only formal v2 controls. No private/live entry invocation."""
import copy
import json
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_formal20_policy_v2 import (
    validate_acceptance,formal_host_policy,validate_formal_binding,STUDY_ID,LIFECYCLE,APPROVAL_BASIS)
from plugin.rhino_listener.c5_formal20_host_session_v2 import FormalHostSession
from training.c5_host_assurance_audit import audit_host_continuity
from training.c5_formal20_budget_v2 import FormalBudgetV2
from eval.test_c5_host_assurance_session import Backend

ROOT=Path(__file__).resolve().parents[1]


def records():
    def public(name):return json.loads((ROOT/'eval/c5'/name).read_bytes())
    proposal=public('formal20-observation-capacity-proposal-20261007.json')
    accepted=public('formal20-capacity-owner-acceptance-20261007.json')
    transition=public('host-assurance-transition-spec-v2-20261006.json')
    consent=public('host-assurance-transition-owner-approval-v2-20261006.json')
    spec={'study_id':STUDY_ID,'field_protocol_version':2,'execution_ready':True,
        'automatic_retry_allowed':False,'default_route_change_allowed':False,
        'zero_consumption_readiness_before_private_loader':True,'lifecycle_protocol':copy.deepcopy(LIFECYCLE),
        'host_assurance':formal_host_policy(transition,consent,proposal,accepted)}
    freeze={'study_id':STUDY_ID,'field_protocol_version':2,'execution_ready':True,'spec_sha256':digest(spec),
        'host_assurance':copy.deepcopy(spec['host_assurance']),'lifecycle_protocol':copy.deepcopy(LIFECYCLE),
        'capacity_proposal':proposal,'capacity_acceptance':accepted,'host_transition_spec':transition,
        'host_transition_consent':consent}
    grant={'study_id':STUDY_ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
        'runtime_freeze_sha256':digest(freeze),'approval_basis':APPROVAL_BASIS}
    return spec,freeze,grant


def test_scope_acceptance_does_not_execute_without_separate_complete_exact_grant():
    spec,freeze,grant=records()
    assert validate_formal_binding(spec,freeze,grant)['formal_capacity_verified']
    with pytest.raises(NativeError):validate_formal_binding(spec,freeze,freeze['capacity_acceptance'])
    grant['approved']=1
    with pytest.raises(NativeError):validate_formal_binding(spec,freeze,grant)
    accepted=copy.deepcopy(freeze['capacity_acceptance']);accepted['accepted']=1
    with pytest.raises(NativeError):validate_acceptance(freeze['capacity_proposal'],accepted)


@pytest.mark.parametrize('change',['legacy','version_float','quota_boolean','extra_subscription',
    'changed_deadline','changed_budget','skip_source','tolerate_drift','retry','readiness_false','old_grant'])
def test_formal_v2_rejects_changed_or_retired_scope(change):
    spec,freeze,grant=records()
    if change=='legacy':spec['field_protocol_version']=1
    elif change=='version_float':spec['field_protocol_version']=2.0
    elif change=='quota_boolean':spec['host_assurance']['normal_checkpoint_limit']=True
    elif change=='extra_subscription':spec['host_assurance']['max_subscriptions']=2
    elif change=='changed_deadline':freeze['capacity_proposal']['generation_cutoff_epoch']+=1
    elif change=='changed_budget':freeze['capacity_proposal']['proposed_formal_gpu_seconds_max']+=1
    elif change=='skip_source':spec['lifecycle_protocol']['source_checks_retained_without_cache']=False
    elif change=='tolerate_drift':spec['host_assurance']['event_policy']='ignore_known_names'
    elif change=='retry':spec['automatic_retry_allowed']=True
    elif change=='readiness_false':spec['zero_consumption_readiness_before_private_loader']=False
    else:grant['study_id']='C5DEV-HOSTASSURANCE-20261007-D'
    freeze['spec_sha256']=digest(spec);grant['spec_sha256']=digest(spec);grant['runtime_freeze_sha256']=digest(freeze)
    with pytest.raises(NativeError):validate_formal_binding(spec,freeze,grant)


def test_more_than_512_actual_cpu_checkpoints_are_independently_replayed(tmp_path):
    spec,freeze,grant=records();binding=validate_formal_binding(spec,freeze,grant)
    state=tmp_path/'s';state.mkdir(mode=0o700)
    session=FormalHostSession(state,binding,Backend(),lambda:'a'*64,'a'*64)
    session.seal_baseline()
    for n in range(600):session.checkpoint('synthetic-%04d'%n)
    session.cleanup_checkpoint('known-close');receipt=session.finish()
    audit=audit_host_continuity(state,STUDY_ID,digest(freeze),'a'*64,receipt['seal_sha256'],
        normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    assert audit['limited_visible_continuity_verified'] and audit['normal_checkpoint_count']==601
    with pytest.raises(NativeError):audit_host_continuity(state,STUDY_ID,digest(freeze),'a'*64,receipt['seal_sha256'])


def test_formal_scope_keeps_every_opaque_host_drift_fatal(tmp_path):
    spec,freeze,grant=records();binding=validate_formal_binding(spec,freeze,grant)
    state=tmp_path/'s';state.mkdir(mode=0o700);backend=Backend()
    session=FormalHostSession(state,binding,backend,lambda:'a'*64,'a'*64);session.seal_baseline()
    backend.value['native_images'].append({'origin_sha256':'d'*64,'file_sha256':None,'state':'unverified'})
    with pytest.raises(RuntimeError):session.checkpoint('changed')
    assert session.blocked


def test_new_budget_keeps_original_16_hours_and_requires_full_window():
    boundary=json.loads((ROOT/'eval/c5/rhino-resource-boundary-v7-formal20-20261007.json').read_bytes())['formal_resource_boundary']
    start=boundary['generation_cutoff_epoch']-20000
    budget=FormalBudgetV2(boundary,wall=lambda:start,mono=lambda:10)
    assert budget.cap==18000
    with pytest.raises(NativeError):FormalBudgetV2(boundary,wall=lambda:boundary['generation_cutoff_epoch']-17999,mono=lambda:10)
    for key,value in [('formal_max_seconds',18001),('research_cumulative_max_seconds',21601),
                      ('original_cumulative_max_seconds',57601),('export_reserve_seconds',True)]:
        bad={**boundary,key:value}
        with pytest.raises(NativeError):FormalBudgetV2(bad,wall=lambda:start,mono=lambda:10)


def test_imports_never_run_live_owner_or_field_entry(monkeypatch):
    import subprocess
    def no_call(*a,**k):raise AssertionError('no process/network/host call on import')
    monkeypatch.setattr(subprocess,'Popen',no_call)
    import importlib
    for name in ('tools.c5_formal20_owner_run_v2','tools.c5_rhino_formal20_arm_v2','tools.run_c5_formal20_worker_v2'):
        importlib.import_module(name)
