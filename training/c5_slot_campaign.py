"""Append-only prospective phase state in the ORIGINAL formal ledger."""
import math
from training.c5_reuse_evidence import sha,require,exact,is_sha
from training.c5_recovery_policy import validate_scope,require_grant,POLICY as LEGACY_POLICY
from plugin.rhino_listener.c5_slot_protocol import POLICY,validate_protocol
EVENTS={'slot_protocol_revision_accepted','slot_owner_session_confirmed','slot_load_intent','slot_worker_ready','slot_work_begin','slot_attempt_recorded','slot_phase_finished','slot_cleanup_reconciled'}
def replay(state,row):
 kind,p=row['kind'],row['payload']
 if kind=='slot_protocol_revision_accepted':
  exact(p,('scope','grant','previous_head_sha256','package','original_audit_sha256','original_settlement_sha256'))
  new=validate_scope(p['scope']);package=p['package'];plan=validate_protocol(package['slot_protocol'])
  require(package['policy']==POLICY and not state['active'] and state['formal_consumed'] and state['attempts'] in state['settled_attempts'],'slot_revision_requires_closed_settled_original')
  require(state['status'] in ('FORMAL_CONSUMED_NO_RETRY','SLOT_PHASE_COMPLETE','SLOT_STOPPED_GLOBAL','SLOT_PAUSED_RECONCILIATION') and all(new[k]==state['scope'][k] for k in ('campaign_id','phase','policy_sha256','history_sha256','public_plan_sha256','contract_sha256')),'slot_revision_same_study_and_contract')
  require(new['development_seconds_max']==state['scope']['development_seconds_max'] and new['generation_cutoff_epoch']>=state['scope']['generation_cutoff_epoch'],'slot_revision_no_budget_reset')
  grant=dict(p['grant']);require(grant.pop('previous_campaign_head_sha256')==p['previous_head_sha256']==row['previous_sha256'],'slot_revision_exact_original_head');require_grant(new,grant)
  require(plan['prior_ledger_head_sha256']==p['previous_head_sha256'] and plan['prior_audit_sha256']==p['original_audit_sha256'] and plan['prior_settlement_sha256']==p['original_settlement_sha256'],'slot_revision_original_raw_review_binding')
  require(package['prior_campaign_events'][-1]['record_sha256']==row['previous_sha256'],'slot_revision_nonempty_original_prefix')
  require(state['first_load_epoch']==package['timing_migration']['legacy_first_load_epoch'],'slot_revision_first_time_preserved')
  state.update(scope=new,package=package,status='SLOT_WAITING_OWNER',slot_protocol=plan,slot_attempted_indices=[],slot_results=[],slot_owner_consent=False,slot_resumes=0,slot_package_start_attempt=state['attempts'],slot_work_begun=False,slot_current_indices=[],slot_current_initial_exposure=False)
  return
 require(state.get('slot_protocol') is not None,'slot_event_without_new_exact_rules')
 if kind=='slot_owner_session_confirmed':
  exact(p,('scope_sha256','automatic_receipt_capture','manual_host_ready_attestation','before_model_loading'))
  require(p=={'scope_sha256':sha(state['scope']),'automatic_receipt_capture':True,'manual_host_ready_attestation':False,'before_model_loading':True} and not state['active'] and not state['slot_owner_consent'],'slot_owner_consent_once')
  state.update(slot_owner_consent=True,package_owner_consent=True,status='SLOT_PREPARED')
 elif kind=='slot_load_intent':
  exact(p,('attempt','epoch','remaining_indices'))
  plan=state['slot_protocol'];remaining=plan['selected_indices'][len(state['slot_attempted_indices']):]
  require(state['slot_owner_consent'] and not state['active'] and state['status'] in ('SLOT_PREPARED','SLOT_RETRYABLE_PREWORK','SLOT_RESUMABLE') and state['attempts'] in state['settled_attempts'] and p['attempt']==state['attempts']+1<=POLICY['global_loads_max'] and state['attempts']-state['slot_package_start_attempt']<POLICY['package_loads_max'] and p['remaining_indices']==remaining and remaining,'slot_load_finite_remaining_work')
  require(type(p['epoch']) in (int,float) and math.isfinite(p['epoch']) and p['epoch']>=state['last_epoch'],'slot_load_clock')
  state.update(attempts=p['attempt'],active=True,ready=False,begun=False,status='LOADING',last_epoch=p['epoch'],load_intent_epoch=p['epoch'],slot_current_indices=[],slot_work_begun=False)
 elif kind=='slot_worker_ready':
  exact(p,('attempt','raw_anchor_sha256'));require(state['active'] and not state['ready'] and p['attempt']==state['attempts'] and is_sha(p['raw_anchor_sha256']),'slot_ready_order');state.update(ready=True,status='READY')
 elif kind=='slot_work_begin':
  exact(p,('attempt','raw_anchor_sha256'));require(state['active'] and state['ready'] and not state['begun'] and p['attempt']==state['attempts'] and is_sha(p['raw_anchor_sha256']),'slot_begin_order');state.update(begun=True,slot_work_begun=True,status='RUNNING')
 elif kind=='slot_attempt_recorded':
  exact(p,('index','result_sha256','decision','proof_sha256'))
  indices=state['slot_protocol']['selected_indices'];n=len(state['slot_attempted_indices'])
  require(state['active'] and state['status']=='RUNNING' and state['begun'] and n<len(indices) and p['index']==indices[n] and is_sha(p['result_sha256']) and is_sha(p['proof_sha256']) and p['decision'] in ('CONTINUE_FIXED_ORDER','STOP_GLOBAL','PAUSED_RECONCILIATION'),'slot_record_once_fixed_order')
  state['slot_attempted_indices'].append(p['index']);state['slot_current_indices'].append(p['index']);state['slot_results'].append(dict(p))
  if p['decision']!='CONTINUE_FIXED_ORDER':state['status']='SLOT_'+('STOPPED_GLOBAL' if p['decision']=='STOP_GLOBAL' else 'PAUSED_RECONCILIATION')
 elif kind=='slot_phase_finished':
  exact(p,('attempt','status','raw_anchor_sha256','cleanup_proof_sha256'))
  require(state['active'] and p['attempt']==state['attempts'] and is_sha(p['raw_anchor_sha256']) and (p['cleanup_proof_sha256'] is None or is_sha(p['cleanup_proof_sha256'])),'slot_phase_finish_binding')
  require(p['status'] in ('SLOT_PHASE_COMPLETE','SLOT_STOPPED_GLOBAL','SLOT_PAUSED_RECONCILIATION','SLOT_RETRYABLE_PREWORK'),'slot_phase_status')
  if p['status']=='SLOT_PHASE_COMPLETE':require(state['slot_attempted_indices']==state['slot_protocol']['selected_indices'] and state['status']=='RUNNING' and p['cleanup_proof_sha256'] is not None,'slot_phase_complete_all_ordered')
  if p['status']=='SLOT_RETRYABLE_PREWORK':require(not state['slot_current_indices'] and p['cleanup_proof_sha256'] is not None,'slot_prework_retry_known_cleanup')
  state.update(active=False,status=p['status'])
 elif kind=='slot_cleanup_reconciled':
  exact(p,('raw_anchor_sha256','cleanup_verified','evidence_chain_verified','shared_health_verified','permission_safe','source_unchanged'))
  require(not state['active'] and state['status']=='SLOT_PAUSED_RECONCILIATION' and is_sha(p['raw_anchor_sha256']) and all(p[k] is True for k in p if k!='raw_anchor_sha256') and state['attempts'] in state['settled_attempts'] and state['slot_resumes']<POLICY['pause_resumes_max'],'slot_resume_proof_and_bound')
  require(len(state['slot_attempted_indices'])<len(state['slot_protocol']['selected_indices']),'slot_resume_only_remaining')
  state['slot_resumes']+=1;state['status']='SLOT_RESUMABLE'
