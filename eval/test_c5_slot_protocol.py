"""CPU-only new-rule regressions; never opens field/private study artifacts."""
import copy,json,hashlib
from pathlib import Path
import pytest
from plugin.rhino_listener.c5_research_native import digest
from plugin.rhino_listener.c5_slot_protocol import POLICY,validate_protocol,decide,impact_indices,select_schedule
from training.c5_slot_worker import validate_scheduled_request

def plan(kind='interrupted_continuation',indices=None):
 return {'version':1,'kind':kind,'selected_indices':list(range(7,40)) if indices is None else indices,'prior_attempted_indices':list(range(7)) if kind=='interrupted_continuation' else list(range(40)),'prior_audit_sha256':'a'*64,'prior_settlement_sha256':'b'*64,'prior_ledger_head_sha256':'c'*64,'code_change_scope':'none' if kind=='interrupted_continuation' else 'slot_local','regression_wave':0 if kind=='interrupted_continuation' else 1,'original_result_immutable':True}
def proof():return {'raw_slot_audit_verified':True,'cleanup_verified':True,'fresh_shared_health_verified':True,'source_unchanged':True,'evidence_chain_verified':True,'proof_sha256':'d'*64}

@pytest.mark.parametrize('code',['model_task_failure','invalid_model_output','fixture_readback_rejected','local_scene_anomaly'])
def test_only_proven_local_failure_continues(code):
 assert decide({'scope':'local','code':code},proof())=='CONTINUE_FIXED_ORDER'
 for key in proof():
  changed=proof();changed[key]=False
  assert decide({'scope':'local','code':code},changed)=='PAUSED_RECONCILIATION'
@pytest.mark.parametrize('code',['permission_or_safety','source_drift','evidence_chain_damage','shared_environment_pollution','resource_window_insufficient'])
def test_global_fault_stops_even_with_good_cleanup(code):assert decide({'scope':'global','code':code},proof())=='STOP_GLOBAL'
def test_unknown_scope_pauses_without_retirement():assert decide({'scope':'unknown','code':'new_exception'},proof())=='PAUSED_RECONCILIATION'
@pytest.mark.parametrize('change',['replace','rerun','shrink','reverse','reset'])
def test_continuation_keeps_original_prefix_and_exact_suffix(change):
 p=plan()
 if change=='replace':p['selected_indices'][0]=6
 if change=='rerun':p['selected_indices']=list(range(40))
 if change=='shrink':p['selected_indices']=p['selected_indices'][:-1]
 if change=='reverse':p['selected_indices'].reverse()
 if change=='reset':p['prior_attempted_indices']=[]
 with pytest.raises((ValueError,RuntimeError)):validate_protocol(p)
def test_regression_affected_five_and_pairs_deterministic_not_all40():
 indices=impact_indices([2,4,10,12,16],'fixture');assert indices==[2,3,4,5,10,11,12,13,16,17]
 p=plan('engineering_regression',indices);validate_protocol(p)
 assert len(p['selected_indices'])==10
 for scope in ('shared_logic','model','prompt','scoring'):assert impact_indices([2],scope)==list(range(40))
 with pytest.raises((ValueError,RuntimeError)):validate_protocol({**p,'code_change_scope':'scoring'})
 with pytest.raises((ValueError,RuntimeError)):validate_protocol({**p,'regression_wave':2})
def test_worker_rejects_outside_plan_backward_and_repeated_slot():
 order=[{'slot_id':'s%d'%i} for i in range(40)];plans={s['slot_id']:{} for s in order};seen=[]
 validate_scheduled_request({'slot_id':'s7'},plans,order,list(range(7,40)),seen)
 validate_scheduled_request({'slot_id':'s7'},plans,order,list(range(7,40)),seen)
 validate_scheduled_request({'slot_id':'s9'},plans,order,list(range(7,40)),seen)
 for slot in ('s7','s6'):
  with pytest.raises((ValueError,RuntimeError)):validate_scheduled_request({'slot_id':slot},plans,order,list(range(7,40)),seen)
def test_resume_schedule_never_replays_attempted():
 p=plan();order=[{'slot_id':'s%d'%i} for i in range(40)]
 assert select_schedule(order,p,[7,8])[0][0]==9
 with pytest.raises((ValueError,RuntimeError)):select_schedule(order,p,[8])

@pytest.mark.parametrize('kind,indices',[('interrupted_continuation',list(range(7,40))),('engineering_regression',[2,3,4,5])])
def test_real_native_hmac_sqlite_and_worker_wire_selected_scope(tmp_path,monkeypatch,kind,indices):
 from eval.test_c5_formal_reuse_full_field import complete_scoped_field
 from plugin.rhino_listener.c5_research_channel import read_json
 p=plan(kind,indices)
 state,cases,spec,freeze,receipt,result,campaign=complete_scoped_field(tmp_path,monkeypatch,slot_plan=p)
 assert result['status']=='SLOT_PHASE_COMPLETE',result
 assert result['attempted_indices']==indices and campaign.indices==indices
 assert not list(state.rglob('*.key'))
 assert len(list(state.glob('hub-request-*.json')))==len(indices)*2+1
 assert all(read_json(state,'slot-outcome-%02d.json'%i)['proof']['fresh_shared_health_verified'] for i in indices)
 assert not result['uninterrupted_initial_full40_claimed']

@pytest.mark.parametrize('fault,expected',[('cleanup','SLOT_PAUSED_RECONCILIATION'),('global','SLOT_STOPPED_GLOBAL')])
def test_actual_runner_global_stop_and_cleanup_pause_no_next(tmp_path,monkeypatch,fault,expected):
 from eval.test_c5_formal_reuse_full_field import complete_scoped_field
 state,cases,spec,freeze,receipt,result,campaign=complete_scoped_field(tmp_path,monkeypatch,slot_plan=plan(),slot_fault=fault)
 assert result['status']==expected,result
 assert len(result['attempted_indices'])<=1


def test_reproduced_local_fixture_failure_is_recorded_then_next_pair_runs(tmp_path,monkeypatch):
 from eval.test_c5_formal_reuse_full_field import complete_scoped_field
 from plugin.rhino_listener.c5_research_channel import read_json
 p=plan('engineering_regression',[2,3,4,5])
 state,cases,spec,freeze,receipt,result,campaign=complete_scoped_field(tmp_path,monkeypatch,slot_plan=p,fixture_mismatch_index=2)
 assert result['status']=='SLOT_PHASE_COMPLETE',result
 assert result['attempted_indices']==[2,3,4,5]
 first=read_json(state,'slot-outcome-02.json')
 assert first['fault']=={'scope':'local','code':'fixture_readback_rejected'}
 assert first['score']['outcome_correct'] is False and first['decision']=='CONTINUE_FIXED_ORDER'
 assert first['proof']['raw_slot_audit_verified'] is True


def real_campaign_fixture(tmp_path):
 from training.c5_recovery_storage import EvidenceLog
 from training.c5_formal_reuse_admission import FormalCampaign,campaign_scope,formal_replay
 from eval.test_c5_formal_reuse_incremental_revision import revision_grant
 from training.c5_reuse_evidence import sha
 root=Path(__file__).resolve().parents[1]
 prior=json.loads((root/'eval/c5/slot-protocol-original-public-history-20261023.json').read_bytes())
 s=json.loads((root/'eval/c5/reuse-formal-20261023-r3-spec.json').read_bytes())
 f=json.loads((root/'eval/c5/reuse-formal-20261023-r3-runtime.json').read_bytes())
 log=EvidenceLog(tmp_path/'ledger',f['incremental_revision']['initial_campaign_scope'],lambda:None,create=True)
 for row in prior['prior_campaign_events']:assert log.append(row['kind'],row['payload'])==row
 old=formal_replay(log.binding,log.rows());c=FormalCampaign(old['scope'],log)
 scope=campaign_scope(s,f);head=log.rows()[-1]['record_sha256'];p=s['run_package']['slot_protocol']
 c._event('slot_protocol_revision_accepted',{'scope':scope,'grant':revision_grant(scope,head),'previous_head_sha256':head,'package':s['run_package'],'original_audit_sha256':p['prior_audit_sha256'],'original_settlement_sha256':p['prior_settlement_sha256']})
 c._event('slot_owner_session_confirmed',{'scope_sha256':sha(scope),'automatic_receipt_capture':True,'manual_host_ready_attestation':False,'before_model_loading':True})
 return s,f,c,prior

def test_original_real_18_events_and_consumption_preserved_during_append(tmp_path):
 from training.c5_slot_entry import require_slot_startable
 from training.c5_formal_reuse_supervisor import validate_load_permit
 s,f,c,prior=real_campaign_fixture(tmp_path)
 try:
  v=c.observation();assert v['attempts']==3 and v['formal_consumed'] and v['first_load_epoch']==prior['first_load_epoch'] and v['charged_gpu_seconds']==prior['gpu_charged_seconds']
  assert c.log.rows()[:18]==prior['prior_campaign_events']
  require_slot_startable(c,4)
  c._event('slot_load_intent',{'attempt':4,'epoch':1792779000.,'remaining_indices':list(range(7,40))})
  permit={'scope':c.scope,'rows':c.log.rows(),'attempt':4,'first_load_epoch':v['first_load_epoch'],'budget_basis':{'charged_before_seconds':v['charged_gpu_seconds'],'load_intent_epoch':1792779000.,'legacy_first_load_epoch':v['first_load_epoch']}}
  assert validate_load_permit(permit,s,f,4)['formal_consumed'] is True
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_load_intent',{'attempt':5,'epoch':1792779001.,'remaining_indices':list(range(7,40))})
  c._event('slot_worker_ready',{'attempt':4,'raw_anchor_sha256':'a'*64});c._event('slot_work_begin',{'attempt':4,'raw_anchor_sha256':'b'*64})
  payload={'index':7,'result_sha256':'c'*64,'decision':'CONTINUE_FIXED_ORDER','proof_sha256':'d'*64};c._event('slot_attempt_recorded',payload)
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_attempt_recorded',payload)
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_attempt_recorded',{**payload,'index':9})
  assert sum(r['kind']=='private_exposure_intent' for r in c.log.rows())==1
 finally:c.log.close()

def test_prework_retries_have_finite_loads_and_never_reset_usage(tmp_path):
 s,f,c,prior=real_campaign_fixture(tmp_path)
 try:
  for attempt in (4,5,6):
   c._event('slot_load_intent',{'attempt':attempt,'epoch':1792779000.+attempt*10,'remaining_indices':list(range(7,40))})
   c._event('slot_phase_finished',{'attempt':attempt,'status':'SLOT_RETRYABLE_PREWORK','raw_anchor_sha256':'a'*64,'cleanup_proof_sha256':'b'*64})
   c._event('gpu_residency_settled',{'attempt':attempt,'start_epoch':1792779000.+attempt*10,'stop_epoch':1792779001.+attempt*10,'charged_seconds':1.,'proof_sha256':'c'*64})
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_load_intent',{'attempt':7,'epoch':1792779100.,'remaining_indices':list(range(7,40))})
  v=c.observation();assert v['attempts']==6 and v['charged_gpu_seconds']==prior['gpu_charged_seconds']+3 and v['first_load_epoch']==prior['first_load_epoch']
 finally:c.log.close()

def test_pause_resume_requires_raw_cleanup_and_remaining_slot_prefix(tmp_path):
 s,f,c,prior=real_campaign_fixture(tmp_path)
 try:
  c._event('slot_load_intent',{'attempt':4,'epoch':1792779000.,'remaining_indices':list(range(7,40))})
  c._event('slot_worker_ready',{'attempt':4,'raw_anchor_sha256':'a'*64});c._event('slot_work_begin',{'attempt':4,'raw_anchor_sha256':'b'*64})
  c._event('slot_attempt_recorded',{'index':7,'result_sha256':'c'*64,'decision':'PAUSED_RECONCILIATION','proof_sha256':'d'*64})
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_attempt_recorded',{'index':8,'result_sha256':'c'*64,'decision':'CONTINUE_FIXED_ORDER','proof_sha256':'d'*64})
  c._event('slot_phase_finished',{'attempt':4,'status':'SLOT_PAUSED_RECONCILIATION','raw_anchor_sha256':'a'*64,'cleanup_proof_sha256':None})
  payload={'raw_anchor_sha256':'a'*64,'cleanup_verified':True,'evidence_chain_verified':True,'shared_health_verified':True,'permission_safe':True,'source_unchanged':True}
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_cleanup_reconciled',payload)
  c._event('gpu_residency_settled',{'attempt':4,'start_epoch':1792779000.,'stop_epoch':1792779001.,'charged_seconds':1.,'proof_sha256':'b'*64})
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_cleanup_reconciled',{**payload,'cleanup_verified':False})
  c._event('slot_cleanup_reconciled',payload)
  with pytest.raises((ValueError,RuntimeError)):c._event('slot_load_intent',{'attempt':5,'epoch':1792779010.,'remaining_indices':list(range(7,40))})
  c._event('slot_load_intent',{'attempt':5,'epoch':1792779010.,'remaining_indices':list(range(8,40))})
  assert c.observation()['slot_attempted_indices']==[7]
 finally:c.log.close()
