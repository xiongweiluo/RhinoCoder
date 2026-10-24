"""Actual synthetic consent/HMAC/SQLite/native callbacks; no field/private reads."""
import copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from eval.test_c5_research_permission import setup, observation
from plugin.rhino_listener.c5_research_gate import ResearchGate
from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener.c5_research_channel import read_json
from training.c5_research_audit import audit_permission_execution
from training.c5_research_permission import ResearchSigner
from training.c5_slot_tail_repair import CleanupEvidenceError, stop_known_child


@pytest.mark.parametrize('read', [False, True])
def test_slow_actual_readbacks_finish_before_ttl_and_original_ledger_audits(tmp_path, read):
    backend, atomic, store, signer, gate = setup(tmp_path)
    observed = observation(atomic, 'get_scene_summary', {}) if read else observation(atomic)
    now = [100.0]
    original = signer.scene.snapshot
    def slow(): now[0] += 70; return original()
    signer.scene.snapshot = slow
    signer.late_ttl = True
    signer.clock = store.clock = gate.clock = atomic.clock = lambda: now[0]
    signed = signer.issue(observed, schemas=backend.schemas)
    assert signed['payload']['expires_at'] - now[0] == 120
    assert signer.last_issue_timing['live_captures_completed_before_ttl']
    receipt = gate.execute(signed)
    proof = audit_permission_execution(store.path, atomic.path, [receipt],
        task_sha256=signed['payload']['task_sha256'], owner_freeze_sha256='a'*64)
    assert proof['consumed_permissions'] == (0 if read else 1)
    with pytest.raises(NativeError): signer.issue(observed, schemas=backend.schemas)
    with pytest.raises(NativeError): gate.execute(signed)
    assert len(backend.calls) == 1


def test_drift_during_last_live_capture_denied_before_permission(tmp_path):
    backend, atomic, store, signer, gate = setup(tmp_path)
    observed = observation(atomic); signer.late_ttl = True
    original = signer.scene.snapshot; count=[0]
    def drift():
        count[0] += 1
        result=original()
        if count[0] == 2: backend.scene['objects'].append({'alias':'A'})
        return result
    signer.scene.snapshot=drift
    with pytest.raises((ValueError, RuntimeError)): signer.issue(observed, schemas=backend.schemas)
    with store._tx() as db: assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0] == 0
    assert not backend.calls


def test_scene_drift_after_signing_still_refused_by_original_native_gate(tmp_path):
    backend, atomic, store, signer, gate=setup(tmp_path); signer.late_ttl=True
    signed=signer.issue(observation(atomic),schemas=backend.schemas)
    backend.scene['objects'].append({'alias':'A'})
    with pytest.raises(NativeError): gate.execute(signed)
    assert not backend.calls


def test_native_ttl_predicate_uses_one_clock_sample_and_keeps_ceiling(tmp_path):
    from eval.test_c5_research_gate import fixture, envelope
    backend,atomic,gate=fixture(tmp_path);calls=[]
    def clock():calls.append(100);return 100
    gate.clock=clock
    gate._payload(envelope(atomic,expires_at=400));assert len(calls)==1
    for expiry in (100,401,True):
        with pytest.raises(NativeError):gate._payload(envelope(atomic,expires_at=expiry))
    assert not backend.calls


@pytest.mark.parametrize('backup_fails',[False,True])
def test_acknowledged_failed_stop_clears_current_before_fallible_backup(tmp_path,backup_fails):
    receipt={'status':'stopped','had_failure':True,'hook_removed_in_same_callback':True}
    channel=SimpleNamespace(control=lambda action:receipt)
    adapter=SimpleNamespace(current='F01-base',_tail_closed={'F01-base':True},
        _tail_stopped={},channels={'F01-base':channel},state=tmp_path)
    def backup(*a):
        if backup_fails:raise OSError('private arbitrary disk text')
        return 'f'*64
    if backup_fails:
        with pytest.raises(CleanupEvidenceError) as error:stop_known_child(adapter,'F01-base',backup,lambda *a:None)
        assert error.value.cleanup_receipt==receipt
    else:assert stop_known_child(adapter,'F01-base',backup,lambda *a:None)==receipt
    assert adapter.current is None and adapter._tail_stopped['F01-base']==receipt


@pytest.mark.parametrize('stage',['native_ttl','model','backup'])
def test_real_runner_failure_claim_record_and_primary_cleanup_separation(tmp_path,monkeypatch,stage):
    from eval.test_c5_formal_reuse_full_field import complete_scoped_field
    from eval.test_c5_slot_protocol import plan
    state,cases,spec,freeze,terminal,result,campaign=complete_scoped_field(
        tmp_path,monkeypatch,slot_plan=plan(),tail_repair=True,
        native_ttl_failure=stage=='native_ttl',model_infer_failure=stage=='model',backup_failure=stage=='backup')
    assert result['status']=='SLOT_PAUSED_RECONCILIATION'
    assert result['attempted_indices']==list(range(7,7+len(result['attempted_indices'])))
    assert campaign.indices==result['attempted_indices']
    if stage != 'native_ttl': assert len(campaign.indices)==1
    claims=list(state.glob('F*-step-*.claim.json'));records=list(state.glob('F*-step-*.record.json'))
    assert len(claims)==len(records)
    assert all(p.with_name(p.name.replace('.claim.', '.record.')).exists() for p in claims)
    label=read_json(state,'native-plans.json')['slot_order'][campaign.indices[-1]]['slot_id']
    value=read_json(state,label+'.result.json')
    if stage in ('native_ttl','model'):
        assert value['steps'][-1]['failure']['replay_allowed'] is False
        assert value['steps'][-1]['failure']['stage']==('native_execute' if stage=='native_ttl' else 'model_request')
    if stage=='native_ttl':assert value['stop']=='stopped' and value['stop_had_failure'] is True
    if stage=='backup':assert value['cleanup_errors'] and value['stop']=='stopped'
    assert (state/'hub-stop.json').exists() and terminal['record_count']>0
    assert not list(state.rglob('*.key'))


def test_original_slow_capture_path_reproduces_expired_handoff_without_dispatch(tmp_path):
    backend, atomic, store, signer, gate=setup(tmp_path)
    now=[100.];observed=observation(atomic);original=signer.scene.snapshot
    def slow():now[0]+=70;return original()
    signer.scene.snapshot=slow
    signer.clock=store.clock=gate.clock=atomic.clock=lambda:now[0]
    signed=signer.issue(observed,schemas=backend.schemas)
    with pytest.raises(NativeError,match='expired/oversized'):gate.execute(signed)
    assert not backend.calls and signer.late_ttl is False


def test_actual_failed_ttl_has_complete_phase_audit_and_never_retries_consumed_slot(tmp_path,monkeypatch):
    from eval.test_c5_formal_reuse_full_field import complete_scoped_field
    from eval.test_c5_slot_protocol import plan
    from eval.test_c5_model_transport import Tokenizer
    from training.c5_slot_audit import _audit_phase
    from training import c5_execution
    state,cases,spec,freeze,terminal,result,campaign=complete_scoped_field(
        tmp_path,monkeypatch,slot_plan=plan(),tail_repair=True,native_ttl_failure=True)
    monkeypatch.setattr(c5_execution,'load_pinned_tokenizer',lambda *a,**k:Tokenizer())
    from training import c5_slot_audit as audit
    monkeypatch.setattr(audit,'audit_supervisor',lambda *a,**k:{'physical_boundary':'CPU_fixture'})
    monkeypatch.setattr(audit,'audit_residency_join',lambda *a,**k:{'physical_boundary':'CPU_fixture'})
    proof=_audit_phase(state,spec,freeze,lambda:None,terminal)
    assert proof['resume_unattempted_safe'] is True
    assert proof['recorded_results']==len(result['attempted_indices'])
    assert len(proof['prospective_failed_tail_proofs'])==1
    tail=next(iter(proof['prospective_failed_tail_proofs'].values()))
    assert tail['failed_request_native_dispatches']==0
    assert tail['original_strict_permission_auditor_passed'] is False
    assert tail['original_permission_refusal'] in {'unaccounted reservation/permission','unaccounted model handoff'}
    assert tail['quality_retry_authorized'] is False
    # Removing consumed terminal evidence must not recreate a permissive proof.
    label=read_json(state,'native-plans.json')['slot_order'][campaign.indices[-1]]['slot_id']
    (state/(label+'-step-0.record.json')).unlink()
    with pytest.raises((ValueError,RuntimeError,FileNotFoundError)):_audit_phase(state,spec,freeze,lambda:None,terminal)


def test_bounded_evidence_inventory_copy_and_finite_metadata_rejection(tmp_path,monkeypatch):
    from training import c5_slot_tail_storage as storage
    source=tmp_path/'original';source.mkdir(mode=0o700)
    p=source/'fixed-public-synthetic.json';p.write_text('{}');p.chmod(0o600)
    before=storage.copy_evidence(source,tmp_path/'copy')
    assert storage.evidence_inventory(source)==before
    assert (tmp_path/'copy'/p.name).read_bytes()==b'{}'
    monkeypatch.setitem(storage.POLICY,'evidence_total_bytes_max',1)
    with pytest.raises(NativeError,match='population_cap'):storage.evidence_inventory(source)


@pytest.mark.parametrize('kind',['symlink','hardlink'])
def test_private_inventory_rejects_links_before_copy(tmp_path,kind):
    from training.c5_slot_tail_storage import evidence_inventory
    source=tmp_path/'original';source.mkdir(mode=0o700)
    p=source/'public-synthetic.json';p.write_text('{}');p.chmod(0o600)
    if kind=='symlink':(source/'link.json').symlink_to(p)
    else:__import__('os').link(p,source/'link.json')
    with pytest.raises(NativeError):evidence_inventory(source)


@pytest.mark.parametrize('change',[None,'pass','first','charge','cleanup','extra_refusal'])
def test_prior_actual_redacted_review_preserves_refusal_and_resource_anchors(change):
    import json
    from training.c5_slot_tail_prior import check_review
    root=Path(__file__).resolve().parents[1]
    summary=json.loads((root/'eval/c5/slot-attempt4-owner-raw-review-result-20261024.json').read_bytes())
    settlement=json.loads((root/'eval/c5/slot-attempt4-original-gpu-settlement-20261024.json').read_bytes())
    reference={'summary_sha256':digest(summary),'settlement_sha256':digest(settlement),
        'campaign_head_sha256':summary['campaign_head_sha256']}
    if change=='pass':summary['full_original_raw_joint_gate_passed']=True
    if change=='first':summary['first_load_epoch']=0
    if change=='charge':settlement['gpu_charged_seconds_after']=0
    if change=='cleanup':summary['cleanup']['native_cleanup_verified']=False
    if change=='extra_refusal':summary['components'][0]['status']='refused_or_unproven'
    # Rebinding a changed hash still cannot turn changed facts into acceptable evidence.
    reference['summary_sha256']=digest(summary);reference['settlement_sha256']=digest(settlement)
    if change is None:assert check_review(summary,settlement,reference)
    else:
        with pytest.raises(NativeError):check_review(summary,settlement,reference)


@pytest.mark.parametrize('tamper',[None,'change_original','delete_original','extra_file','retain_key'])
def test_prior_cleanup_delta_never_discards_nonkey_evidence(tamper):
    from training.c5_slot_tail_prior import preservation_delta
    before={'original.json':{'sha256':'a'*64},'hub.key':{'sha256':'b'*64}}
    before.update({'F%02d-base/handoff.key'%n:{'sha256':'c'*64} for n in range(1,30)})
    after={'original.json':copy.deepcopy(before['original.json'])}
    names={'hub-'+k+'-0022.json' for k in ('request','response','client-time','service-time','host-check')}
    names|={'hub-stop.json','host-continuity-terminal-receipt.json','host-continuity-seal.json'}
    names|={'host-continuity-%04d.json'%n for n in range(250,255)}
    after.update({n:{'sha256':'d'*64} for n in names})
    if tamper=='change_original':after['original.json']['sha256']='f'*64
    if tamper=='delete_original':del after['original.json']
    if tamper=='extra_file':after['unexpected.json']={}
    if tamper=='retain_key':after['hub.key']=before['hub.key']
    summary={'cleanup':{'preservation':{'added_cleanup_evidence_files':13}}}
    if tamper is None:preservation_delta(before,after,summary)
    else:
        with pytest.raises(NativeError):preservation_delta(before,after,summary)


def test_inert_new_package_keeps_18_consumed_and_22_fixed_unattempted(monkeypatch):
    from tools import prepare_c5_slot_tail_package as prep
    original=prep.read
    def read(name):
        value=original(name)
        if name==prep.FACTS:value['both_public_deployments']=False
        return value
    monkeypatch.setattr(prep,'read',read)
    docs=prep.assemble();s=docs[prep.SPEC];f=docs[prep.RUNTIME]
    assert s['run_package']['slot_protocol']['selected_indices']==list(range(18,40))
    assert s['run_package']['slot_protocol']['prior_attempted_indices']==list(range(18))
    assert len(s['run_package']['prior_campaign_events'])==36
    assert s['run_package']['timing_migration']['prior_attempts_consumed']==4
    assert s['run_package']['timing_migration']['legacy_first_load_epoch']==1792692329.837715
    assert s['run_package']['timing_migration']['gpu_residency_upper_seconds']==70340.89651274681
    assert s['execution_ready'] is f['execution_ready'] is False
    assert docs[prep.REVIEW]['actual_execution_authorized'] is False


@pytest.mark.parametrize('exception',[KeyboardInterrupt,PermissionError])
def test_backup_interrupt_or_permission_error_retains_actual_stop_and_original_error(tmp_path,exception):
    value={'status':'stopped','had_failure':True,'hook_removed_in_same_callback':True}
    adapter=SimpleNamespace(current='F01-base',_tail_closed={'F01-base':True},_tail_stopped={},
        channels={'F01-base':SimpleNamespace(control=lambda action:value)},state=tmp_path)
    def fail(*a):raise exception('synthetic')
    with pytest.raises(exception) as caught:stop_known_child(adapter,'F01-base',fail,lambda *a:None)
    assert adapter.current is None and caught.value.cleanup_receipt==value


def test_interruption_after_durable_claim_still_writes_terminal_record_without_generation(tmp_path,monkeypatch):
    from eval.test_c5_formal_reuse_full_field import complete_scoped_field
    from eval.test_c5_slot_protocol import plan
    from training import c5_formal_reuse_runner as runner
    publish=runner.publish_json;fired=[False]
    def interrupt(directory,name,value):
        publish(directory,name,value)
        if name.endswith('-step-0.claim.json') and not fired[0]:
            fired[0]=True;raise KeyboardInterrupt('synthetic after durable claim')
    monkeypatch.setattr(runner,'publish_json',interrupt)
    state,cases,spec,freeze,terminal,result,campaign=complete_scoped_field(
        tmp_path,monkeypatch,slot_plan=plan(),tail_repair=True)
    assert result['status']=='SLOT_PAUSED_RECONCILIATION' and result['generation_stages']==0
    assert result['global_fault']=={'scope':'owner_pause','code':'owner_cancelled'}
    claims=list(state.glob('F*-step-*.claim.json'));assert len(claims)==1
    record=read_json(state,claims[0].name.replace('.claim.','.record.'))
    assert record['response'] is None and record['failure']['stage']=='step_claim'
    assert (state/'hub-stop.json').exists()


@pytest.mark.parametrize('indices',[list(range(18,40)),list(range(40))])
def test_new_tail_policy_healthy_22_suffix_and_shared_logic_40_cpu_regression(tmp_path,monkeypatch,indices):
    from eval.test_c5_formal_reuse_full_field import complete_scoped_field
    from eval.test_c5_slot_protocol import plan
    from eval.test_c5_model_transport import Tokenizer
    from training import c5_execution,c5_slot_audit as audit
    p=plan() if indices[0] else plan('engineering_regression',indices)
    if indices[0]:p.update(selected_indices=indices,prior_attempted_indices=list(range(18)))
    state,cases,spec,freeze,terminal,result,campaign=complete_scoped_field(
        tmp_path,monkeypatch,slot_plan=p,tail_repair=True)
    assert result['status']=='SLOT_PHASE_COMPLETE' and result['attempted_indices']==indices
    monkeypatch.setattr(c5_execution,'load_pinned_tokenizer',lambda *a,**k:Tokenizer())
    monkeypatch.setattr(audit,'audit_supervisor',lambda *a,**k:{'physical_boundary':'CPU_fixture'})
    monkeypatch.setattr(audit,'audit_residency_join',lambda *a,**k:{'physical_boundary':'CPU_fixture'})
    proof=audit._audit_phase(state,spec,freeze,lambda:None,terminal)
    assert proof['recorded_results']==len(indices) and proof['prospective_failed_tail_proofs']=={}
    assert proof['full40_first_result_unchanged'] is True and proof['new_blind_holdout_claimed'] is False
    assert not list(state.rglob('*.key'))


def test_primary_native_failure_is_not_replaced_by_backup_failure(tmp_path,monkeypatch):
    from eval.test_c5_formal_reuse_full_field import complete_scoped_field
    from eval.test_c5_slot_protocol import plan
    p=plan();p.update(selected_indices=list(range(18,40)),prior_attempted_indices=list(range(18)))
    state,cases,spec,freeze,terminal,result,campaign=complete_scoped_field(
        tmp_path,monkeypatch,slot_plan=p,tail_repair=True,native_ttl_failure=True,backup_failure=True)
    label=read_json(state,'native-plans.json')['slot_order'][18]['slot_id']
    value=read_json(state,label+'.result.json')
    assert value['error_type']=='NativeError' and value['stop']=='stopped'
    assert value['cleanup_errors'][0]['error_type']=='CleanupEvidenceError'
    assert result['status']=='SLOT_PAUSED_RECONCILIATION' and campaign.indices==[18]
    assert (state/'hub-stop.json').exists()


def test_prospective_policy_rejects_boolean_numeric_alias_and_private_error_text():
    from plugin.rhino_listener.c5_slot_tail_policy import enabled,POLICY
    from training.c5_slot_tail_repair import error_record
    value={'run_package':{'tail_repair':{'version':1,'policy':copy.deepcopy(POLICY)}}}
    assert enabled(value)
    value['run_package']['tail_repair']['policy']['version']=True
    with pytest.raises(NativeError):enabled(value)
    error=ValueError('private arbitrary prompt');error.tail_code='private arbitrary prompt'
    assert 'private arbitrary prompt' not in str(error_record(error,'native_execute'))


def test_actual_signing_scene_drift_remains_typed_global_before_permission():
    from training.c5_formal_reuse_adapters_base import ActualScene
    from training.c5_slot_tail_repair import SigningSceneDrift
    expected={'state':{'revision':0},'native':{'objects':[]}}
    channel=SimpleNamespace(control=lambda action:{'status':'captured','state':{'revision':1},'native':{'objects':[]}})
    proxy=ActualScene(channel,expected,{'signing_captures':[]},tail_repair=True)
    with pytest.raises(SigningSceneDrift) as caught:proxy.snapshot()
    assert caught.value.slot_scope=='global' and caught.value.code=='shared_environment_pollution'


def test_late_consent_keeps_global_permission_fault_through_preflight_wrapper(tmp_path):
    from training.consent_candidate import DELEGATED_HEADLESS_SCOPE
    backend,atomic,store,signer,gate=setup(tmp_path)
    class Scene:
        def snapshot(self):raise PermissionError('synthetic private filesystem message')
    with pytest.raises(PermissionError):store._prepare_consumed_delegated_c5(
        'public synthetic task','create_box',{'width':2,'depth':3,'height':4},
        scene=Scene(),delegated_scope=DELEGATED_HEADLESS_SCOPE)
    with store._tx() as db:assert db.execute('SELECT count(*) FROM consent_requests').fetchone()[0]==0


def test_public_history_permit_over_generic_record_bound_retains_all_bytes(tmp_path):
    import io, os
    from training.c5_slot_load_permit import encode, decode, receive, saved
    from training.c5_reuse_evidence import strict
    value={'scope': 'public synthetic history', 'rows': ['a'*300000]}
    raw=encode(value)
    with pytest.raises(ValueError,match='json_size'):strict(raw)
    stream=io.BytesIO(raw+b'next-frame\n')
    assert receive(stream)==value and stream.read()==b'next-frame\n'
    p=tmp_path/'load-permit.json';p.write_bytes(raw);p.chmod(0o600)
    assert saved(p)==decode(raw)==value


@pytest.mark.parametrize('raw', [b'',b'{}',b'{'+b'a'*1048576+b'}\n',
    b'{"a":1,"a":2}\n',b'{"a":NaN}\n'], ids=['empty','truncated','oversized','duplicate','nonfinite'])
def test_public_permit_frames_refuse_size_truncation_duplicates_nonfinite(raw):
    import io
    from training.c5_slot_load_permit import receive
    with pytest.raises(ValueError):receive(io.BytesIO(raw))


def test_oversized_permit_rejected_before_any_scope_or_launch():
    from training.c5_formal_reuse_supervisor import validate_load_permit
    with pytest.raises(ValueError,match='formal_reuse_load_permit_size'):
        validate_load_permit({'oversized':'a'*1048576},{},{},5)


def test_public_permit_exact_bound_roundtrip_and_export_headroom(tmp_path):
    import io
    from training.c5_slot_load_permit import encode, receive, saved, MAX_BYTES
    assert MAX_BYTES==786432 and 1048576-MAX_BYTES==262144
    value={'a':'x'*(MAX_BYTES-len(encode({'a':''})))}
    raw=encode(value);assert len(raw)==MAX_BYTES
    assert receive(io.BytesIO(raw))==value
    p=tmp_path/'load-permit.json';p.write_bytes(raw);p.chmod(0o600)
    assert saved(p)==value
    value['a']+='x'
    with pytest.raises(ValueError,match='formal_reuse_load_permit_size'):encode(value)
