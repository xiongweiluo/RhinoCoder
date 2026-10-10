"""Independent manual-safety receipt replay; no producer or live import.

The complete old host journal must also be independently replayed against
the separately captured actual UI host receipt. This audit is not C PASS.
"""
import hashlib
import json

ID = 'C5SAFE-HOSTASSURANCE-C-20261007-B'
ACTIVE = 'de8fa7924ad4cf7fbeffdbe982f0b559a77eca7a8cf1f24175df642404ec6cfa'
ORIGINAL_RESULT = '6093aa3ae6e25f31ecaaad551c368a919d499ff2e6c8aa57d674910295b3c3a9'
SCOPE = 'retired C only; V2 exact empty fixture safety Dispose, seven specified keys and exact three delegates; preserve atomic drift and all ledger rows, no replay'


def digest(v):
    return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def require(ok, message):
    if not ok: raise ValueError(message)


def audit_manual_safety(spec, freeze, approval, admission, effects, result, external_result_sha, host_receipt):
    require(spec['study_id'] == freeze['study_id'] == ID and freeze['spec_sha256'] == digest(spec), 'new B complete freeze differs')
    require(digest(approval) == digest({'study_id':ID,'actor':'repository_owner','approved':True,
            'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),'scope':SCOPE}), 'new direct B execution grant differs')
    claim = {'study_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False}
    require(digest(admission) == digest(claim) and digest(effects) == digest(claim), 'one-use B admission/effects differ')
    require(digest(result) == external_result_sha and result['study_id'] == ID and result['runtime_freeze_sha256'] == digest(freeze)
            and result['status'] == 'retired_C_manual_safety_closed_not_experiment_PASS'
            and result['field_remains_failure'] is True and result['execution_authority'] is False
            and result['complete_handler_absence_proven'] is False and result['whole_host_zero_effects_proven'] is False
            and result['memory_or_external_key_copy_erasure_proven'] is False, 'actual result/limited assurance differs')
    require(all(type(result[k]) is int and result[k] == 0 for k in ('model_calls','gpu_calls','holdout_calls',
            'tool_dispatches','new_subscriptions','atomic_snapshot_calls','ledger_updates')), 'forbidden side effects reported')
    require(result['child_idle_exact_remove_call_completed'] is True and result['hub_idle_exact_remove_call_completed'] is True
            and result['fixture_close_attempted'] is True and result['fixture_registry_absent'] is True, 'exact close/Idle proof incomplete')
    close = result['close_capture']
    require(close['fixture_serial'] == 268435475 and close['fixture_registry_absent'] is True
            and close['before_close_active_serial'] == close['after_close_active_serial'] == 268435457
            and close['initial_active_sha256'] == close['before_close_active_sha256'] == close['after_close_active_sha256'] == ACTIVE
            and close['fixture_before_close_native'] == {'groups':{},'objects':[],'unit':'Millimeters'}, 'raw exact empty close capture differs')
    expected_keys = {'hub.key'} | {s+'/handoff.key' for s in ('read-lora','read-base','clarify-base','clarify-lora','unsupported-lora','unsupported-base')}
    require(set(result['key_absence']) == expected_keys and all(digest(v) == digest({'key_removed':True,'actual_absence_checked':True})
            for v in result['key_absence'].values()), 'seven exact key absences incomplete')
    require(result['ledger_logical_rows_preserved'] is True
            and digest(result['ledger_before']) == digest(result['ledger_after']) == freeze['ledger_logical_rows_sha256']
            and result['original_result_sha256'] == ORIGINAL_RESULT and result['historical_HMAC_verified_without_replay'] is True,
            'original failure/logical ledger/historical signature not preserved')
    observed = result['current_empty_fixture_safety_observation']
    require(all(observed[k] is True for k in ('ui_thread','backend_thread','active_serial','active_content',
            'fixture_registry','fixture_serial','headless_unsaved','owner_document'))
            and observed['backend_closed'] is False and observed['native'] == {'groups':{},'objects':[],'unit':'Millimeters'},
            'raw safety predicate differs')
    require(digest(result['host_receipt']) == digest(host_receipt) and host_receipt['record_count'] >= 55
            and host_receipt['execution_authority'] is False, 'separately observed old host receipt differs')
    return {'study_id':ID,'status':'limited_manual_safety_result_verified_requires_raw_host_audit_and_key_absence_check',
            'original_C_remains_failure':True,'whole_host_or_handler_absence_proven':False,
            'model_formal20_D_authorized':False,'external_result_sha256':external_result_sha}
