"""Synthetic CPU controls only. Never open the real sealed family package."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import pytest

from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID,COMMITMENT,validate_materials,authority
from plugin.rhino_listener.c5_formal_reuse_resource_policy import validate_boundary
from training.c5_formal_reuse_budget import FormalBudgetV2
from training.c5_formal_reuse_evidence_audit import audit_resource
from training.c5_formal_reuse_supervisor import FormalWatchdog,PACKET,validate_load_permit
from training.c5_formal_reuse_admission import FormalCampaign,campaign_scope,require_startable
from training.c5_recovery_storage import EvidenceLog
from training.c5_recovery_confirmation import snapshot,validate_receipt
from training.c5_recovery_policy import POLICY
from training.c5_reuse_evidence import sha

ROOT=Path(__file__).resolve().parents[1]

def boundary():
    return {'owner_confirmed':True,'provider_expiry_epoch':2000100900,'generation_cutoff_epoch':2000100000,
        'export_reserve_seconds':900,'formal_max_seconds':64800,'historical_cumulative_upper_bound_seconds':None,
        'original_16_hour_compliance_claimed':False,'old_budget_recredited':False,
        'unused_development_transferred_to_formal':False,'development_first_load_epoch':1791916117.781239,
        'development_attempts_consumed':3,'development_campaign_head_sha256':
        'ebb572fbbe53ea2ec5c5a191f56ea1ee7767eef7525eca69d4a8a56a90f1975a',
        'development_seconds_max':86400,'research_cumulative_max_seconds':151200,
        'development_elapsed_to_release_seconds':66773.24127721786}

@pytest.mark.parametrize('key,value',[
    ('formal_max_seconds',64801),('formal_max_seconds',True),('research_cumulative_max_seconds',151201),
    ('development_seconds_max',0),('development_elapsed_to_release_seconds',0),
    ('historical_cumulative_upper_bound_seconds',0),('old_budget_recredited',True),
    ('original_16_hour_compliance_claimed',True),('unused_development_transferred_to_formal',True),
    ('development_first_load_epoch',0),('development_attempts_consumed',0),('export_reserve_seconds',899),
    ('provider_expiry_epoch',float('inf')),('generation_cutoff_epoch',float('nan'))])
def test_finite_budget_and_old_history_cannot_be_replaced(key,value):
    b=boundary();b[key]=value
    with pytest.raises((ValueError,NativeError)):validate_boundary(b)

def test_formal_shared_clock_is_not_restarted_on_reattachment():
    clock=[2000000000.,1000.];b=boundary()
    first=FormalBudgetV2(b,wall=lambda:clock[0],mono=lambda:clock[1])
    clock[0]+=500;clock[1]+=500
    reopened=FormalBudgetV2(b,wall=lambda:clock[0],mono=lambda:clock[1],start={'wall':first.start_wall,'mono':first.start_mono})
    assert reopened.check()==first.check()==64240
    assert reopened.start_wall==2000000000

@pytest.mark.parametrize('kind',['wall','mono','nan','stop','short_window'])
def test_budget_rejects_clock_regression_exhaustion_and_insufficient_full_window(kind):
    c=[2000000000.,1000.];b=boundary()
    if kind=='short_window':
        c[0]=b['generation_cutoff_epoch']-64799
        with pytest.raises((ValueError,NativeError)):FormalBudgetV2(b,wall=lambda:c[0],mono=lambda:c[1])
        return
    v=FormalBudgetV2(b,wall=lambda:c[0],mono=lambda:c[1])
    if kind=='wall':c[0]-=1
    elif kind=='mono':c[1]-=1
    elif kind=='nan':c[0]=float('nan')
    else:c[0]+=64740;c[1]+=64740
    with pytest.raises((ValueError,NativeError)):v.check()

def resource():
    from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID
    return {'study_id':STUDY_ID,'status':'formal_worker_stopped_no_replay','resource_boundary_sha256':digest(boundary()),
        'replay_allowed':False,'elapsed_seconds_including_load_and_idle':100,'cap_seconds':64800,
        'start_epoch':2000000000,'stop_epoch':2000000100}

def test_raw_resource_checks_actual_aggregate_usage_and_original_start():
    assert audit_resource(resource(),boundary(),status='formal_worker_stopped_no_replay',first_epoch=2000000000)==100

@pytest.mark.parametrize('key,value', [('elapsed_seconds_including_load_and_idle',64801),('start_epoch',2000000001),
    ('stop_epoch',2000100001),('cap_seconds',999999),('replay_allowed',True),('stop_epoch',float('nan'))])
def test_raw_resource_overrun_or_reset_is_rejected(key,value):
    r=resource();r[key]=value
    with pytest.raises((ValueError,NativeError)):audit_resource(r,boundary(),status='formal_worker_stopped_no_replay',first_epoch=2000000000)

def test_disabled_real_candidate_cannot_become_execution_authority(monkeypatch):
    from tools.prepare_c5_formal_reuse_freeze import assemble
    from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE
    import tools.prepare_c5_formal_reuse_freeze as builder
    original=builder.read
    def missing_current_gpu(name):
        value=original(name)
        if name==builder.FACTS_FILE:value={**value,'gpu_current_review':None}
        return value
    monkeypatch.setattr(builder,'read',missing_current_gpu)
    docs=assemble(now=2000000000);s,r=docs[SPEC_FILE],docs[FREEZE_FILE]
    assert s['execution_ready'] is r['execution_ready'] is False
    assert docs['eval/c5/formal-reuse-preparation-review-20261022.json']['hashes_are_execution_approval_objects'] is False
    with pytest.raises((ValueError,NativeError)):validate_materials(s,r,clock=lambda:2000000000)
    with pytest.raises((ValueError,NativeError)):authority(s,r,{'approved':True})
    assert s['comparison']['parse_repair_allowed'] is False and s['comparison']['training_allowed'] is False
    assert all(s[k]==v for k,v in COMMITMENT.items())

def make_campaign(tmp_path):
    scope={'campaign_id':STUDY_ID,'phase':'formal','spec_sha256':'1'*64,'runtime_sha256':'2'*64,
        'policy_sha256':sha(POLICY),'history_sha256':'3'*64,'public_plan_sha256':'4'*64,'contract_sha256':'5'*64,
        'development_seconds_max':64800,'generation_cutoff_epoch':2000100000}
    clock=[2000000000.];log=EvidenceLog(tmp_path/'ledger',scope,lambda:None,create=True)
    return FormalCampaign(scope,log,wall=lambda:clock[0]),clock

def confirm(campaign,nonce='a'):
    snap=snapshot(campaign.scope,'b'*64,nonce*64)
    receipt={'actor':'repository_owner',**snap,'before_model_loading':True,
        'public_attempts_authorized':0,'human_origin_cryptographically_proven':False}
    validate_receipt(campaign.scope,snap,receipt);campaign.confirm(snap,receipt)

def proof():return {'raw_anchor_sha256':'c'*64,'capture_complete':True,'qualified_target_absent':True,
    'known_native_cleanup_complete':True,'private_exposure_absent':True}

def test_owner_wait_creates_no_load_intent_and_no_private_consumption(tmp_path):
    c,_=make_campaign(tmp_path)
    try:
        assert c.observation()['attempts']==0 and not c.observation()['formal_consumed']
        confirm(c);assert c.observation()['attempts']==0 and c.observation()['first_load_epoch'] is None
    finally:c.log.close()

def test_three_preexposure_failures_keep_all_receipts_and_first_clock(tmp_path):
    c,clock=make_campaign(tmp_path)
    try:
        for i in range(1,4):
            require_startable(c,i);confirm(c,chr(96+i));c.start()
            assert c.observation()['first_load_epoch']==2000000000
            decision=c.failed('startup',proof());clock[0]+=100
            assert decision==('ATTEMPT_LIMIT_REACHED' if i==3 else 'RETRYABLE_ENGINEERING')
        rows=c.log.rows();assert sum(r['kind']=='owner_preload_confirmed' for r in rows)==3
        assert sum(r['kind']=='attempt_load_intent' for r in rows)==3
        with pytest.raises((ValueError,NativeError)):require_startable(c,4)
    finally:c.log.close()

def test_unknown_cleanup_blocks_reconfirmation_and_retry(tmp_path):
    c,_=make_campaign(tmp_path)
    try:
        confirm(c);c.start();p=proof();p['qualified_target_absent']=False
        assert c.failed('startup',p)=='PAUSED_RECONCILIATION'
        with pytest.raises((ValueError,NativeError)):require_startable(c,2)
        with pytest.raises((ValueError,NativeError)):confirm(c,'d')
    finally:c.log.close()

def test_private_exposure_is_durable_and_permanently_disables_retry(tmp_path):
    c,_=make_campaign(tmp_path)
    try:
        confirm(c);c.start();c.ready('e'*64);c.expose_private('f'*64)
        assert c.observation()['formal_consumed'] is True
        assert c.log.rows()[-1]['kind']=='private_exposure_intent'
        assert c.failed('transport',proof())=='FORMAL_CONSUMED_NO_RETRY'
        with pytest.raises((ValueError,NativeError)):confirm(c,'d')
        with pytest.raises((ValueError,NativeError)):require_startable(c,2)
    finally:c.log.close()

def test_formal_watchdog_allows_56_bounded_requests_and_no_120_second_owner_window():
    c=[1.];limits={'model_seconds':360,'startup_seconds':600,'first_request_idle_seconds':600,'between_requests_idle_seconds':3600}
    v=FormalWatchdog(1,64740,clock=lambda:c[0],limits=limits)
    v.feed(PACKET.pack(b'L',c[0]));c[0]+=1000;assert v.check()>60000
    v.feed(PACKET.pack(b'B',c[0]))
    for _ in range(56):
        c[0]+=1;v.feed(PACKET.pack(b'R',c[0]));v.feed(PACKET.pack(b'S',c[0]));v.feed(PACKET.pack(b'E',c[0]));v.feed(PACKET.pack(b'D',c[0]))
    with pytest.raises((ValueError,NativeError)):v.feed(PACKET.pack(b'R',c[0]))

def test_non_owner_entry_refuses_before_scope_or_any_private_access(monkeypatch):
    import tools.c5_formal_reuse_owner as owner
    monkeypatch.setattr(sys.stdin,'isatty',lambda:False)
    monkeypatch.setattr(owner,'scope',lambda **kw:pytest.fail('scope accessed before private TTY gate'))
    with pytest.raises((ValueError,NativeError)):owner.run_interactive(1)

def test_scoped_actor_modules_are_rhino39_syntax_and_original_actor_files_unchanged():
    import ast
    original=json.loads((ROOT/'eval/c5/formal-reuse-scoped-source-baseline-20261022.json').read_bytes())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in original['source_files'].items())
    for p in (ROOT/'plugin/rhino_listener').glob('*formal_reuse*.py'):ast.parse(p.read_text(),feature_version=(3,9))
