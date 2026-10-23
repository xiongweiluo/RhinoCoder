"""Public CPU fixtures. No actual field grants, holdout, model or Rhino calls."""
import copy
import json
import time
from pathlib import Path
import pytest
from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_run_package_policy import POLICY,validate_migration,remaining_window,retry_authorized
from training.c5_formal_run_budget import ResidencyBudget,require_recovery_window
from training.c5_formal_reuse_admission import FormalCampaign,campaign_scope,require_startable
from training.c5_formal_reuse_supervisor import validate_load_permit
from training.c5_recovery_confirmation import snapshot
from training.c5_reuse_evidence import sha
from eval.test_c5_formal_reuse_incremental_revision import frozen_log,revision_grant
from eval.test_c5_formal_reuse_preparation import proof

FIRST=1792692329.837715


def layout():
    name='reuse-formal-20261023-r2'
    return {'schema_version':1,'package_id':name,'study_id':POLICY['study_id'],
        'mac_source_root':'/Users/xiongweiluo/RhinoCoder/data/training/c5/'+name+'-source',
        'gpu_source_root':'/data/'+name+'-source',
        'mac_state_root':'/Users/xiongweiluo/RhinoCoder/data/training/c5/'+name+'-state',
        'gpu_state_root':'/data/'+name+'-state','spec_file':'eval/c5/'+name+'-spec.json',
        'runtime_file':'eval/c5/'+name+'-runtime.json','policy_sha256':digest(POLICY)}


def confirm(c):
    snap=snapshot(c.scope,'a'*64,'b'*64)
    c.confirm(snap,{'actor':'repository_owner',**snap,'before_model_loading':True,
        'public_attempts_authorized':0,'human_origin_cryptographically_proven':False})


def package_campaign(tmp_path,*,owner_confirmed=True):
    spec,freeze,_,log=frozen_log(tmp_path)
    now=[FIRST+1000]
    c=FormalCampaign(freeze['incremental_revision']['initial_campaign_scope'],log,wall=lambda:now[0])
    r1=campaign_scope(spec,freeze);c.accept_revision(r1,revision_grant(r1,log.rows()[-1]['record_sha256']))
    confirm(c);c.start();c.failed('startup',proof());now[0]=FIRST+12000
    migration={'schema_version':1,'legacy_first_load_epoch':FIRST,'cutover_epoch':now[0],
        'legacy_generation_stop_epoch':FIRST+64740,'legacy_accounting_end_epoch':now[0],
        'legacy_elapsed_debit_seconds':12000.,'gpu_residency_upper_seconds':11000.,
        'prior_campaign_head_sha256':log.rows()[-1]['record_sha256'],'prior_attempts_consumed':2,
        'legacy_policy_rejudged':False,'historical_first_load_rewritten':False}
    package={'policy':copy.deepcopy(POLICY),'layout':layout(),'timing_migration':migration,
        'prior_campaign_events':copy.deepcopy(log.rows()),'lease_expiry_epoch':FIRST+300000}
    spec=copy.deepcopy(spec);freeze=copy.deepcopy(freeze)
    spec['run_package']=freeze['run_package']=package
    revised=campaign_scope(spec,freeze);head=log.rows()[-1]['record_sha256']
    c._event('run_package_revision_accepted',{'scope':revised,'grant':revision_grant(revised,head),
        'previous_head_sha256':head,'package':package,'accounting_cutover':migration})
    if owner_confirmed:
        confirm(c)
        c._event('package_owner_custody_consent',{'scope_sha256':sha(c.scope),'automatic_receipt_capture':True,
            'manual_per_receipt_attestation':False})
    return spec,freeze,c,now


def test_package_revision_preserves_history_attempts_and_first_clock(tmp_path):
    s,f,c,now=package_campaign(tmp_path)
    try:
        v=c.observation()
        assert v['first_load_epoch']==FIRST and v['attempts']==2 and v['charged_gpu_seconds']==12000
        assert v['attempts_max']==5 and not v['formal_consumed']
        assert c.log.rows()[:len(s['run_package']['prior_campaign_events'])]==s['run_package']['prior_campaign_events']
        require_startable(c,3);assert observed_start(c)==3
        value=c.observation()
        permit={'scope':c.scope,'rows':c.log.rows(),'attempt':3,'first_load_epoch':FIRST,
            'budget_basis':{'charged_before_seconds':12000.,'load_intent_epoch':now[0],
                            'legacy_first_load_epoch':FIRST}}
        assert validate_load_permit(permit,s,f,3)['attempts']==3
        for key in permit['budget_basis']:
            bad=copy.deepcopy(permit);bad['budget_basis'][key]+=1
            with pytest.raises((ValueError,NativeError)):validate_load_permit(bad,s,f,3)
    finally:c.log.close()


def test_same_package_has_finite_global_and_package_limits(tmp_path):
    _,_,c,now=package_campaign(tmp_path)
    try:
        for attempt in (3,4,5):
            require_startable(c,attempt);observed_start(c)
            decision=c.failed('startup',proof())
            now[0]+=10
            c._event('gpu_residency_settled',{'attempt':attempt,'start_epoch':now[0]-10,
                'stop_epoch':now[0],'charged_seconds':10.,'proof_sha256':'a'*64})
            assert decision==('ATTEMPT_LIMIT_REACHED' if attempt==5 else 'RETRYABLE_ENGINEERING')
        with pytest.raises((ValueError,NativeError)):require_startable(c,6)
        assert c.observation()['attempts']==5 and c.observation()['first_load_epoch']==FIRST
    finally:c.log.close()


def test_unsettled_previous_load_cannot_undercount_and_retry(tmp_path):
    _,_,c,_=package_campaign(tmp_path)
    try:
        observed_start(c);assert c.failed('startup',proof())=='RETRYABLE_ENGINEERING'
        with pytest.raises((ValueError,NativeError),match='usage_unsettled'):require_startable(c,4)
    finally:c.log.close()


@pytest.mark.parametrize('bad',['private','unknown','changed_pair','global_limit','package_limit'])
def test_automatic_retry_does_not_mean_unlimited_or_post_exposure(bad):
    values=dict(package_start_attempt=2,attempts=3,exposed=False,complete_proof=True,same_pair=True)
    if bad=='private':values['exposed']=True
    if bad=='unknown':values['complete_proof']=False
    if bad=='changed_pair':values['same_pair']=False
    if bad=='global_limit':values['attempts']=5
    if bad=='package_limit':values.update(package_start_attempt=0,attempts=3)
    assert not retry_authorized(POLICY,**values)


def test_budget_separates_timeline_residency_and_provider_clock(tmp_path):
    _,f,c,now=package_campaign(tmp_path)
    try:
        package=f['run_package'];clock=[FIRST+100000,1000.]
        # Old 18h wall stop is in the past. This is a separately granted
        # prospective residency contract, never a rewrite of that old result.
        basis={'charged_before_seconds':12000.,'load_intent_epoch':clock[0],'legacy_first_load_epoch':FIRST}
        b=ResidencyBudget(package,basis,wall=lambda:clock[0],mono=lambda:clock[1])
        assert b.check()==86400-12000-900
        clock[0]+=500;clock[1]+=500
        assert b.check()==86400-12500-900
        assert basis['legacy_first_load_epoch']==FIRST
        require_recovery_window(package,c.observation(),now=clock[0],remaining_work_seconds=1000)
        package['lease_expiry_epoch']=clock[0]+2499
        with pytest.raises((ValueError,NativeError)):require_recovery_window(package,c.observation(),now=clock[0],remaining_work_seconds=1000)
    finally:c.log.close()


@pytest.mark.parametrize('mutation',['legacy_epoch','negative_debit','zero_unknown_as_fact','rewrite'])
def test_migration_refuses_rewriting_or_fabricating_history(tmp_path,mutation):
    _,f,c,_=package_campaign(tmp_path)
    try:
        v=copy.deepcopy(f['run_package']['timing_migration'])
        if mutation=='legacy_epoch':v['legacy_first_load_epoch']+=1
        if mutation=='negative_debit':v['legacy_elapsed_debit_seconds']=-1
        if mutation=='zero_unknown_as_fact':v['gpu_residency_upper_seconds']=None
        if mutation=='rewrite':v['legacy_policy_rejudged']=True
        with pytest.raises((ValueError,NativeError)):validate_migration(v)
    finally:c.log.close()


def test_window_depends_on_remaining_work_not_a_fresh_full_phase():
    assert remaining_window(POLICY,charged_seconds=82000,remaining_work_seconds=1000,now=100,expiry=3000)['can_load']
    assert not remaining_window(POLICY,charged_seconds=82000,remaining_work_seconds=52200,now=100,expiry=100000)['can_load']


def test_stop_and_export_route_never_calls_loader_preflight(monkeypatch):
    import tools.run_c5_formal_reuse_worker as worker
    import training.c5_formal_reuse_control as control
    import training.c5_formal_reuse_supervisor as supervisor
    monkeypatch.setattr(worker,'approved_scope',lambda:pytest.fail('loader must not block cleanup'))
    monkeypatch.setattr(control,'control_scope',lambda root:({}, {}, lambda:None))
    monkeypatch.setattr(supervisor,'independent_stop',lambda *args:{'status':'known_exit'})
    monkeypatch.setattr(supervisor,'export_supervisor',lambda *args:{'status':'original_export'})
    for mode in ('stop','export-supervisor'):
        monkeypatch.setattr('sys.argv',['worker',mode,'--attempt','3'])
        worker.main()


def test_ci_selector_is_conservative_and_does_not_duplicate_c5_checks():
    from tools.select_affected_checks import select
    assert select(['training/c5_formal_run_budget.py'])['python_scope']=='c5'
    assert not select(['training/c5_formal_run_budget.py'])['ui']
    assert select(['docs/review.md'])['python_scope']=='none'
    assert select(['.github/workflows/ci.yml'])['python_scope']=='full'
    assert select(['unknown/new_feature.py'])['python_scope']=='full'


def test_automatic_preload_observation_is_not_a_fabricated_manual_confirmation(tmp_path):
    _,_,c,now=package_campaign(tmp_path)
    try:
        manual_count=sum(row['kind']=='owner_preload_confirmed' for row in c.log.rows())
        observed_start(c);c.failed('startup',proof());now[0]+=10
        c._event('gpu_residency_settled',{'attempt':3,'start_epoch':now[0]-10,
            'stop_epoch':now[0],'charged_seconds':10.,'proof_sha256':'a'*64})
        p={'scope_sha256':sha(c.scope),'attempt':4,'host_ready_sha256':'a'*64,
           'snapshot_sha256':'b'*64,'manual_owner_attestation':False}
        c._event('package_preload_observed',p)
        assert sum(row['kind']=='owner_preload_confirmed' for row in c.log.rows())==manual_count
        with pytest.raises((ValueError,NativeError)):
            c._event('package_preload_observed',{**p,'manual_owner_attestation':True})
    finally:c.log.close()


def test_public_package_status_has_no_private_payload_or_key_fields(tmp_path):
    from training.c5_formal_run_package import public_status
    _,_,c,_=package_campaign(tmp_path)
    try:
        v=public_status(c,tmp_path/'preload-3')
        assert v['attempts_consumed']==2 and v['first_load_epoch']==FIRST
        assert v['private_content_included'] is False and v['legacy_wall_policy_rejudged'] is False
        assert not any(key in json.dumps(v) for key in ('key_hex','task_text','family_id','identity_path'))
    finally:c.log.close()


def test_minimal_control_entry_static_closure_excludes_model_loader():
    from training.c5_formal_reuse_control import code_closure,CONTROL_FILES
    root=Path(__file__).resolve().parents[1]
    files={p.relative_to(root).as_posix():'a'*64 for folder in ('training','tools','plugin')
           for p in (root/folder).rglob('*.py')}
    closure=code_closure(root,'tools/c5_formal_reuse_control.py',files)
    assert set(CONTROL_FILES)<=set(closure)
    assert 'training/c5_followup_gpu_loader.py' not in closure
    assert 'tools/run_c5_formal_reuse_worker.py' not in closure


def test_private_request_pointer_is_atomic_bounded_and_contains_no_paths(tmp_path,monkeypatch):
    import training.c5_formal_run_package_entry as entry
    tmp_path.chmod(0o700);monkeypatch.setattr(entry,'MAC_STATE',tmp_path)
    value=entry.request_rhino_attempt({'study_id':POLICY['study_id']},{'fixture':True},3)
    actual=json.loads((tmp_path/'rhino-active-attempt.json').read_bytes())
    assert actual==value and actual['attempt']==3 and len(actual['nonce'])==64
    assert set(actual)=={'attempt','nonce','runtime_sha256','study_id'}
    assert not list(tmp_path.glob('*.tmp'))


def observed_start(c):
    c._event('package_preload_observed',{'scope_sha256':sha(c.scope),'attempt':c.observation()['attempts']+1,
        'host_ready_sha256':'a'*64,'snapshot_sha256':'b'*64,'manual_owner_attestation':False})
    return c.start()


def test_material_review_does_not_create_an_execution_grant_by_default():
    from plugin.rhino_listener.c5_formal_reuse_scope import expected_grant
    spec={'run_package':{'fixture':True}};freeze={'fixture':True}
    template=expected_grant(spec,freeze)
    assert template['approved'] is template['actual_execution_approved'] is False
    actual=expected_grant(spec,freeze,execution_approved=True)
    assert actual['actual_execution_approved'] is actual['within_package_retries_approved'] is True


def test_private_input_errors_happen_before_native_preparation_and_do_not_consume(tmp_path,monkeypatch):
    import training.c5_formal_run_package_entry as entry
    import tools.c5_formal20_owner_run_v2 as metadata
    s,f,c,_=package_campaign(tmp_path,owner_confirmed=False)
    try:
        before=c.log.rows();answers=iter(['/private/tmp/cpu-fixture.age','/private/tmp/cpu-fixture.identity'])
        monkeypatch.setattr(entry.getpass,'getpass',lambda _:next(answers))
        def invalid(*args):raise ValueError('fixture incorrect private path')
        monkeypatch.setattr(metadata,'verify_private_metadata',invalid)
        with pytest.raises(ValueError):entry.prepare_owner_session({},c,s,f,{},lambda:None,
            input_fn=lambda _:pytest.fail('confirmation must follow metadata validity'))
        assert c.log.rows()==before and c.observation()['attempts']==2
        assert not c.observation()['package_owner_consent'] and not (tmp_path/'preload-3').exists()
        answers=iter(['/private/tmp/cpu-fixture.age','/private/tmp/cpu-fixture.identity'])
        monkeypatch.setattr(metadata,'verify_private_metadata',lambda *args:None)
        session={}
        assert entry.prepare_owner_session(session,c,s,f,{},lambda:None,input_fn=lambda _:'确认并保管 ',output=lambda _:None)
        assert session['confirmed'] and c.observation()['package_owner_consent']
        assert c.observation()['receipt'].keys()=={'package_session'}
        # Package consent never substitutes for actual machine ready.
        with pytest.raises((ValueError,NativeError)):c.start()
        assert c.observation()['attempts']==2
        assert observed_start(c)==3
    finally:c.log.close()
