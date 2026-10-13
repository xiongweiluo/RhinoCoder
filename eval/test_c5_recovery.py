"""Synthetic CPU recovery paths; no field roots, model, Rhino or live signals."""
import copy
import hashlib
import json
import multiprocessing
from pathlib import Path
import threading
import time
import pytest
from training.c5_reuse_evidence import canonical,sha
from training.c5_recovery_policy import POLICY,RETIRED,affected_checks,require_grant,retry_decision
from training.c5_recovery_confirmation import confirm_preload,snapshot,validate_receipt
from training.c5_recovery_storage import EvidenceLog,pinned_history,write_once
from training.c5_recovery_controller import Campaign,EngineeringFault,AttemptFailure,RecoveryController
from training.c5_recovery_stop import CoordinatedStop

def scope(phase='public_engineering'):
    return {'campaign_id':'cpu-test-recovery','phase':phase,'spec_sha256':'1'*64,'runtime_sha256':'2'*64,
            'policy_sha256':sha(POLICY),'history_sha256':'3'*64,'public_plan_sha256':'4'*64,
            'contract_sha256':'5'*64,'development_seconds_max':1000,'generation_cutoff_epoch':10000}
def grant(s):return {'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],
                    'scope_sha256':sha(s),'spec_sha256':s['spec_sha256'],
                    'runtime_sha256':s['runtime_sha256'],'policy_sha256':sha(POLICY)}
def proof(**changes):
    return dict({'raw_anchor_sha256':'a'*64,'capture_complete':True,'qualified_target_absent':True,
                 'known_native_cleanup_complete':True,'private_exposure_absent':True},**changes)
def receipt(s,snap):
    return {'actor':'repository_owner',**snap,'before_model_loading':True,
            'public_attempts_authorized':3 if s['phase']=='public_engineering' else 0,
            'human_origin_cryptographically_proven':False}
def campaign(tmp_path,phase='public_engineering'):
    s=scope(phase);clock=[100.]
    log=EvidenceLog(tmp_path/'campaign',s,lambda:None,create=True)
    return Campaign(s,log,wall=lambda:clock[0]),clock
def confirmed(c):
    snap=snapshot(c.scope,'b'*64,'c'*64);c.confirm(snap,receipt(c.scope,snap));return snap

@pytest.mark.parametrize('raw',['确认并保管',' 确认并保管 ','确认并保管\u00a0'])
def test_owner_confirmation_is_before_load_and_accepts_normal_whitespace(raw):
    s=scope();snap=snapshot(s,'b'*64,'c'*64)
    r=confirm_preload(s,snap,lambda:None,input_fn=lambda _:raw,output=lambda _:None,isatty=lambda:True)
    assert r['before_model_loading'] and r['public_attempts_authorized']==3
    validate_receipt(s,snap,r)

def test_actual_d_style_hidden_input_rejection_can_be_corrected_without_exception_or_authority():
    s=scope();snap=snapshot(s,'b'*64,'c'*64);lines=iter(['确认并保管\u200b','wrong secret text','确认并保管'])
    messages=[]
    r=confirm_preload(s,snap,lambda:None,input_fn=lambda _:next(lines),output=messages.append,isatty=lambda:True)
    assert r and any('U+200B' in line for line in messages)
    assert all('wrong secret text' not in line for line in messages)

@pytest.mark.parametrize('error',[EOFError,KeyboardInterrupt])
def test_owner_cancel_eof_or_keyboard_does_not_consume_a_campaign_attempt(tmp_path,error):
    c,_=campaign(tmp_path)
    def input_fn(_):raise error()
    assert confirm_preload(c.scope,snapshot(c.scope,'b'*64,'c'*64),lambda:None,
                          input_fn=input_fn,output=lambda _:None,isatty=lambda:True) is None
    assert c.observation()['attempts']==0

def test_bad_input_pauses_and_later_confirmation_succeeds(tmp_path):
    c,_=campaign(tmp_path);snap=snapshot(c.scope,'b'*64,'c'*64)
    assert confirm_preload(c.scope,snap,lambda:None,input_fn=lambda _:'bad',output=lambda _:None,isatty=lambda:True) is None
    assert c.observation()['attempts']==0
    r=confirm_preload(c.scope,snap,lambda:None,input_fn=lambda _:'确认并保管',output=lambda _:None,isatty=lambda:True)
    c.confirm(snap,r);assert c.start()==1

def test_agent_non_tty_cannot_sign_even_if_it_supplies_the_correct_phrase():
    with pytest.raises(ValueError,match='interactive'):
        confirm_preload(scope(),snapshot(scope(),'b'*64,'c'*64),lambda:None,
                        input_fn=lambda _:'确认并保管',isatty=lambda:False)

@pytest.mark.parametrize('retired',RETIRED)
def test_new_policy_does_not_reopen_any_retired_identity(retired):
    s=scope();s['campaign_id']=retired
    with pytest.raises(ValueError,match='new_campaign'):require_grant(s,grant(s))

def test_partial_old_approval_and_wrong_new_scope_cannot_authorize_callbacks(tmp_path):
    c,_=campaign(tmp_path);calls=[]
    controller=controller_for(c,calls,owner=None)
    controller.grant={'approved':True,'spec_sha256':c.scope['spec_sha256'],'runtime_sha256':c.scope['runtime_sha256']}
    with pytest.raises(ValueError,match='new_exact'):controller.run_once()
    assert calls==[] and c.observation()['attempts']==0

def test_three_engineering_failures_disclosed_and_fourth_blocked_after_reopen(tmp_path):
    c,clock=campaign(tmp_path);confirmed(c)
    for i in range(1,4):
        assert c.start()==i
        clock[0]+=20
        decision=c.failed('startup',proof())
        assert decision==('RETRYABLE_ENGINEERING' if i<3 else 'ATTEMPT_LIMIT_REACHED')
    c.log.close()
    with EvidenceLog(tmp_path/'campaign',scope(),lambda:None) as log:
        reopened=Campaign(scope(),log,wall=lambda:clock[0])
        with pytest.raises(ValueError):reopened.start()
        assert reopened.observation()['attempts']==3
        assert len([r for r in log.rows() if r['kind']=='attempt_failed'])==3

def test_budget_across_retries_waits_and_reopen_cannot_reset(tmp_path):
    c,clock=campaign(tmp_path);confirmed(c);c.start();clock[0]=800;c.failed('transport',proof())
    c.log.close()
    with EvidenceLog(tmp_path/'campaign',scope(),lambda:None) as log:
        reopened=Campaign(scope(),log,wall=lambda:clock[0])
        assert reopened.budget()==240
        assert reopened.start()==2
        clock[0]=1041
        with pytest.raises(ValueError,match='budget'):reopened.budget()
        assert reopened.observation()['first_load_epoch']==100

def test_clock_regression_after_checkpoint_is_rejected(tmp_path):
    c,clock=campaign(tmp_path);confirmed(c);c.start();clock[0]=300;c.budget();clock[0]=200
    with pytest.raises(ValueError,match='clock_regression'):c.budget()

@pytest.mark.parametrize('marker',['expose','begin'])
def test_formal_consumption_marker_precedes_callback_and_never_reopens(tmp_path,marker):
    c,_=campaign(tmp_path,'formal');confirmed(c);c.start()
    if marker=='expose':c.expose_private('d'*64)
    else:c.ready('e'*64);c.begin('d'*64)
    assert c.failed('transport',proof())=='FORMAL_CONSUMED_NO_RETRY'
    with pytest.raises(ValueError):c.start()
    revised=dict(c.scope,runtime_sha256='7'*64);g=grant(revised)
    g['previous_campaign_head_sha256']=c.log.rows()[-1]['record_sha256']
    with pytest.raises(ValueError):c.accept_revision(revised,g)

def test_formal_loading_failure_without_exposure_can_retry_preparation(tmp_path):
    c,_=campaign(tmp_path,'formal');confirmed(c);c.start()
    assert c.failed('startup',proof())=='RETRYABLE_ENGINEERING'
    assert c.start()==2 and not c.observation()['formal_consumed']

def test_unknown_cleanup_pauses_then_independent_reconciliation_preserves_history(tmp_path):
    c,_=campaign(tmp_path);confirmed(c);c.start()
    assert c.failed('transport',proof(qualified_target_absent=False))=='PAUSED_RECONCILIATION'
    head=c.log.rows()[-1]['record_sha256']
    with pytest.raises(ValueError):c.start()
    assert c.reconcile('transport',proof())=='RETRYABLE_ENGINEERING'
    assert c.log.rows()[-1]['previous_sha256']==head and c.start()==2

def test_quality_failure_is_kept_and_does_not_automatically_choose_a_better_result():
    assert retry_decision(scope(),1,False,'quality',proof())=='FAILED_NO_AUTOMATIC_RETRY'

def test_runtime_revision_preserves_attempts_budget_and_old_bytes_and_needs_new_confirmation(tmp_path):
    c,clock=campaign(tmp_path);confirmed(c);c.start();c.failed('startup',proof())
    old={p.name:p.read_bytes() for p in c.log.root.iterdir()}
    revised=dict(c.scope,runtime_sha256='7'*64);g=grant(revised)
    g['previous_campaign_head_sha256']=c.log.rows()[-1]['record_sha256']
    c.accept_revision(revised,g)
    assert all((c.log.root/n).read_bytes()==raw for n,raw in old.items())
    assert c.scope==revised and c.observation()['attempts']==1 and c.observation()['first_load_epoch']==100
    with pytest.raises(ValueError):c.start()
    confirmed(c);assert c.start()==2

@pytest.mark.parametrize('change',['budget','contract','plan','history','head'])
def test_revision_cannot_bypass_caps_contract_history_or_raw_anchor(tmp_path,change):
    c,_=campaign(tmp_path);confirmed(c);c.start();c.failed('startup',proof())
    revised=dict(c.scope,runtime_sha256='7'*64)
    key={'budget':'development_seconds_max','contract':'contract_sha256','plan':'public_plan_sha256','history':'history_sha256'}.get(change)
    if key:revised[key]=900 if change=='budget' else '9'*64
    g=grant(revised);g['previous_campaign_head_sha256']='0'*64 if change=='head' else c.log.rows()[-1]['record_sha256']
    before=c.log.rows()
    with pytest.raises(ValueError):c.accept_revision(revised,g)
    assert c.log.rows()==before

def test_pinned_old_history_never_written_and_drift_blocks_next_effect(tmp_path):
    old=tmp_path/'old.json';old.write_bytes(b'old C/D consumed evidence');old.chmod(0o600)
    guard=pinned_history({str(old):hashlib.sha256(old.read_bytes()).hexdigest()})
    with EvidenceLog(tmp_path/'new',scope(),guard,create=True) as log:
        c=Campaign(scope(),log);confirmed(c);assert old.read_bytes()==b'old C/D consumed evidence'
        old.write_bytes(b'changed')
        with pytest.raises(ValueError,match='legacy'):c.observation()

def test_partial_and_rehashed_semantic_corruption_block_without_automatic_repair(tmp_path):
    c,_=campaign(tmp_path);confirmed(c);c.start()
    p=c.log.root/'event-0001.json';row=json.loads(p.read_bytes());row['payload']['attempt']=99
    row['record_sha256']=sha({k:v for k,v in row.items() if k!='record_sha256'})
    p.write_bytes(canonical(row)+b'\n')
    with pytest.raises(ValueError,match='attempt_order'):c.observation()
    p.write_bytes(b'{')
    with pytest.raises((ValueError,json.JSONDecodeError)):c.observation()
    assert p.read_bytes()==b'{'

def qualification():
    t={'pid':200,'uid':1000,'boot_id':'a'*36,'start_ticks':22,'executable_sha256':'b'*64,
       'argv_sha256':'c'*64,'cwd':'/data/cpu-test-only'}
    return {'target':t,'parent_pid':199,'model_loading_started':False}
class Ops:
    def __init__(self):self.signals=0;self.closed=0;self.exit=False;self.drift=False
    def guard(self):pass
    def pin(self,pid):assert pid==200;return 123
    def identity(self,pid):return dict(qualification()['target'],start_ticks=999) if self.drift else qualification()['target']
    def parent(self,pid):return 199
    def exited(self,fd):return self.exit
    def send(self,fd):self.signals+=1;self.exit=True
    def wait(self,fd,seconds):return self.exit
    def close(self,fd):self.closed+=1
def stop_log(tmp_path):
    q=qualification();b={'qualification_sha256':sha(q)}
    return EvidenceLog(tmp_path/'stop',b,lambda:None,create=True),q

def test_d_double_stop_race_reads_shared_result_without_second_claim_or_signal(tmp_path):
    log,q=stop_log(tmp_path);ops=Ops();a=CoordinatedStop(log,q)
    with EvidenceLog(log.root,log.binding,lambda:None) as other:
        b=CoordinatedStop(other,q)
        first=a.stop(ops);second=b.stop(ops)
    assert first==second and first['exit_observed'] and ops.signals==1 and ops.closed==1
    assert [r['kind'] for r in log.rows()]==['stop_claim','stop_result']

def test_same_object_concurrent_threads_send_once(tmp_path):
    log,q=stop_log(tmp_path);ops=Ops();stop=CoordinatedStop(log,q);out=[]
    threads=[threading.Thread(target=lambda:out.append(stop.stop(ops))) for _ in range(8)]
    for t in threads:t.start()
    for t in threads:t.join(timeout=5)
    assert len(out)==8 and ops.signals==1

def _process_stop(root,binding,output):
    with EvidenceLog(Path(root),binding,lambda:None) as log:
        ops=Ops();CoordinatedStop(log,qualification()).stop(ops);output.put(ops.signals)
def test_two_processes_coordinate_one_signal(tmp_path):
    log,q=stop_log(tmp_path);ctx=multiprocessing.get_context('spawn');queue=ctx.Queue()
    processes=[ctx.Process(target=_process_stop,args=(str(log.root),log.binding,queue)) for _ in range(2)]
    for p in processes:p.start()
    for p in processes:p.join(10);assert p.exitcode==0
    assert sorted(queue.get(timeout=3) for _ in processes)==[0,1]

def test_crash_after_stop_claim_never_resends_and_retains_unknown(tmp_path):
    log,q=stop_log(tmp_path);log.append('stop_claim',{'qualification_sha256':sha(q),'signals_max':1})
    ops=Ops();result=CoordinatedStop(log,q).stop(ops)
    assert result['status']=='unknown_after_claim' and not result['retry_signal_allowed'] and ops.signals==0

def test_stop_wrong_identity_never_claims_or_signals(tmp_path):
    log,q=stop_log(tmp_path);ops=Ops();ops.drift=True
    with pytest.raises(ValueError,match='identity'):CoordinatedStop(log,q).stop(ops)
    assert not log.rows() and ops.signals==0

def controller_for(c,calls,owner='valid',load_error=None,run_error=None,stop_error=False):
    snap=snapshot(c.scope,'b'*64,'c'*64)
    def load(attempt):
        calls.append('load')
        if load_error:raise load_error
        return {'cpu_synthetic':True}
    def stop(worker):
        calls.append('stop')
        if stop_error:raise RuntimeError('synthetic stop unknown')
        return {'exit_observed':True}
    def run(worker,attempt):
        calls.append('run')
        if run_error:raise run_error
        return 'f'*64
    return RecoveryController(c,grant(c.scope),guard=lambda:None,preflight=lambda:snap,
        owner_confirm=lambda pre:calls.append('owner') or (receipt(c.scope,pre) if owner else None),
        load_worker=load,verify_ready=lambda w,p:'e'*64,run_public=run,stop_worker=stop,
        cleanup_native=lambda:calls.append('native') or True,
        finalize_capture=lambda:calls.append('capture') or True,
        verify_cleanup=lambda w,s,n,cap:proof(qualified_target_absent=s is not None))

def test_integration_pause_then_success_without_model_load_on_owner_wait(tmp_path):
    c,_=campaign(tmp_path);calls=[]
    assert controller_for(c,calls,owner=None).run_once()['status']=='WAITING_OWNER'
    assert calls==['owner'] and c.observation()['attempts']==0
    calls.clear();result=controller_for(c,calls).run_once()
    assert calls==['owner','load','run','stop','native','capture']
    assert result['status']=='AWAITING_INDEPENDENT_AUDIT' and not result['whole_field_pass']

def test_integration_known_startup_retry_reuses_confirmation_and_all_failed_attempts(tmp_path):
    c,_=campaign(tmp_path);calls=[];control=controller_for(c,calls,load_error=RuntimeError('CPU startup'))
    with pytest.raises(AttemptFailure) as error:control.run_once()
    assert error.value.decision=='RETRYABLE_ENGINEERING' and calls==['owner','load','stop','native','capture']
    calls.clear();assert controller_for(c,calls).run_once()['attempt']==2
    assert 'owner' not in calls and c.observation()['attempts']==2

def test_failure_after_success_path_cleanup_does_not_repeat_stop_or_skip_native(tmp_path):
    c,_=campaign(tmp_path);calls=[];control=controller_for(c,calls,stop_error=True)
    with pytest.raises(AttemptFailure) as error:control.run_once()
    assert calls.count('stop')==calls.count('native')==calls.count('capture')==1
    assert error.value.decision=='PAUSED_RECONCILIATION'

def test_model_quality_error_does_not_automatically_retry(tmp_path):
    c,_=campaign(tmp_path);calls=[]
    with pytest.raises(AttemptFailure) as error:
        controller_for(c,calls,run_error=EngineeringFault('quality','quality not an operational retry')).run()
    assert error.value.decision=='FAILED_NO_AUTOMATIC_RETRY' and calls.count('load')==1

def test_only_affected_groups_selected_and_unknown_dependencies_are_not_silently_skipped():
    checks=affected_checks(['retry_policy','confirmation','stop'])
    assert {'formal_consumption','owner_custody','concurrent_stop','shared_budget'}<=set(checks)
    assert not {'model_assets','model_contract','tokenizer','runtime_environment'}&set(checks)
    with pytest.raises(ValueError):affected_checks(['new_unregistered_dependency'])


def test_missing_public_diagnostics_is_disclosed_without_retiring_known_clean_engineering(tmp_path):
    c,_=campaign(tmp_path);confirmed(c);c.start()
    assert c.failed('capture',proof(capture_complete=False))=='RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE'
    assert c.start()==2

def test_formal_missing_diagnostics_remains_paused(tmp_path):
    c,_=campaign(tmp_path,'formal');confirmed(c);c.start()
    assert c.failed('capture',proof(capture_complete=False))=='PAUSED_RECONCILIATION'

def test_user_keyboard_cancel_cleans_up_once_and_does_not_auto_restart(tmp_path):
    c,_=campaign(tmp_path);calls=[]
    with pytest.raises(AttemptFailure) as error:
        controller_for(c,calls,load_error=KeyboardInterrupt()).run()
    assert error.value.decision=='PAUSED_OWNER' and isinstance(error.value.original,KeyboardInterrupt)
    assert calls.count('load')==calls.count('stop')==calls.count('native')==calls.count('capture')==1
    c.resume_after_owner_pause();assert c.start()==2

def test_boolean_alias_cannot_become_owner_receipt_or_retry_counter():
    s=scope();snap=snapshot(s,'b'*64,'c'*64);r=receipt(s,snap);r['before_model_loading']=1
    with pytest.raises(ValueError):validate_receipt(s,snap,r)
    with pytest.raises(ValueError):retry_decision(s,True,False,'startup',proof())

def test_stop_rehashed_contradictory_result_rejected(tmp_path):
    log,q=stop_log(tmp_path)
    log.append('stop_claim',{'qualification_sha256':sha(q),'signals_max':1})
    log.append('stop_result',{'status':'exit_observed','signal_attempts':0,'exit_observed':True,'error_type':None})
    with pytest.raises(ValueError,match='semantics'):CoordinatedStop(log,q).stop(Ops())

@pytest.mark.skipif(__import__('sys').platform!='linux',reason='Linux pidfd primitive; CPU-only child, no GPU')
def test_real_owned_cpu_child_single_pidfd_signal_and_second_actor_observation(tmp_path):
    import os,subprocess,sys
    from training.c5_reuse_process_identity import LinuxIdentity,OwnedPidfdOperations
    p=subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(30)'],cwd=tmp_path)
    try:
        reader=LinuxIdentity();q={'target':reader(p.pid),'parent_pid':os.getpid(),'model_loading_started':False}
        binding={'qualification_sha256':sha(q)}
        with EvidenceLog(tmp_path/'real-stop',binding,lambda:None,create=True) as log:
            first=CoordinatedStop(log,q).stop(OwnedPidfdOperations(lambda:None))
            second=CoordinatedStop(log,q).stop(OwnedPidfdOperations(lambda:None))
            assert first==second and first['signal_attempts']==1 and first['exit_observed']
            p.wait(timeout=3);assert p.returncode<0
    finally:
        if p.poll() is None:p.terminate();p.wait(timeout=3)


def history_fixture(tmp_path):
    from training.c5_recovery_history import history_guard
    root=tmp_path/'c5-reuse-global-admission-v1';root.mkdir(mode=0o700)
    names=['admission.lock','admission.sqlite','controller.consumed.json','host.consumed.json',
           'followup-v2-genesis.json','followup-d-controller.consumed.json','followup-d-host.consumed.json']
    pins={}
    for n in names:
        p=root/n;p.write_bytes(b'' if n=='admission.lock' else ('synthetic preserved '+n).encode());p.chmod(0o600)
        pins[n]=hashlib.sha256(p.read_bytes()).hexdigest()
    retired={}
    for instance in RETIRED:
        d=tmp_path/(instance+'-state');d.mkdir(mode=0o700);values={}
        for name,key in [('entry-retired-no-retry.json','retirement_raw_sha256'),
                         ('owner-approval.retired-no-retry.json','retired_grant_raw_sha256')]:
            p=d/name;p.write_bytes(('synthetic preserved '+instance+name).encode());p.chmod(0o600)
            values[key]=hashlib.sha256(p.read_bytes()).hexdigest()
        retired[instance]=values
    document={'protocol':POLICY['protocol'],'retirements':retired,'registry_file_sha256':{
        'mac':pins,'gpu':{n:'a'*64 for n in ['followup-v2-genesis.json','followup-d-worker.consumed.json','followup-d-stop.consumed.json']}},
        'historical_consumption_nonempty':True,'old_no_go_preserved':True,'old_active_grants_must_be_absent':True}
    roots={'mac':str(root),'gpu':'/data/cpu-test-not-called/c5-reuse-global-admission-v1'}
    return root,document,roots

def test_same_root_history_import_after_new_approval_preserves_old_bytes_and_only_one_campaign(tmp_path):
    from training.c5_recovery_history import open_campaign
    root,document,roots=history_fixture(tmp_path);s=dict(scope(),history_sha256=sha(document))
    before={p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with open_campaign(root,'mac',s,document,create=True,grant=grant(s),expected_roots=roots) as log:
        c=Campaign(s,log,wall=lambda:100);confirmed(c);c.start();c.failed('startup',proof())
    assert all((tmp_path/n).read_bytes()==raw for n,raw in before.items())
    with open_campaign(root,'mac',s,document,expected_roots=roots) as log:
        assert Campaign(s,log,wall=lambda:120).start()==2
    with pytest.raises(ValueError):
        open_campaign(root,'mac',dict(s,campaign_id='cpu-replacement'),document,expected_roots=roots)
    with pytest.raises(ValueError):
        open_campaign(root,'mac',s,document,create=True,grant=grant(s),expected_roots=roots)

@pytest.mark.parametrize('change',['missing_history','changed_byte','active_grant','different_root'])
def test_history_cannot_be_zeroed_restored_or_bypassed(tmp_path,change):
    from training.c5_recovery_history import open_campaign
    root,document,roots=history_fixture(tmp_path);s=dict(scope(),history_sha256=sha(document))
    if change=='missing_history':document['registry_file_sha256']['mac'].pop('followup-d-host.consumed.json')
    elif change=='changed_byte':(root/'admission.sqlite').write_bytes(b'reset')
    elif change=='active_grant':(tmp_path/(RETIRED[-1]+'-state')/'owner-approval.json').write_bytes(b'{}')
    else:root=tmp_path/'empty-replacement';root.mkdir(mode=0o700)
    with pytest.raises(ValueError):
        open_campaign(root,'mac',s,document,create=True,grant=grant(s),expected_roots=roots)
    assert not (root/'engineering-recovery-v3').exists()

def test_qualification_input_mutation_does_not_change_stop_target(tmp_path):
    log,q=stop_log(tmp_path);coordinator=CoordinatedStop(log,q);q['target']['pid']=999
    ops=Ops();assert coordinator.stop(ops)['exit_observed'] and ops.signals==1


def test_preparation_review_preserves_legacy_bytes_and_cannot_be_used_as_execution_grant():
    from tools.check_c5_recovery_preparation import review
    packet=review()
    assert packet['legacy_source_files_reverified']==337
    assert len(packet['history']['retirements'])==4
    assert not packet['execution_authority'] and not packet['review_runtime']['execution_ready']
    assert not packet['review_runtime']['field_actors_registered']
    assert packet['review_spec']['new_field_identity'] is None
    root=Path(__file__).resolve().parents[1]
    assert json.loads((root/'eval/c5/engineering-recovery-preparation-review-20261013.json').read_bytes())==packet
    with pytest.raises(ValueError):require_grant(scope(),packet['review_spec'])


def test_success_path_incomplete_diagnostics_is_not_pass_and_clean_public_retry_is_allowed(tmp_path):
    c,_=campaign(tmp_path);calls=[];control=controller_for(c,calls)
    control.verify_cleanup=lambda *args:proof(capture_complete=False)
    with pytest.raises(AttemptFailure) as error:control.run_once()
    assert error.value.decision=='RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE'
    assert calls.count('stop')==calls.count('native')==calls.count('capture')==1

def test_actual_cpu_subprocess_startup_failure_then_success_reuses_owner_confirmation(tmp_path):
    import subprocess,sys
    c,_=campaign(tmp_path);calls=[];control=controller_for(c,calls);outputs=[]
    def load(attempt):
        p=subprocess.run([sys.executable,'-I','-B','-c',
                          'import sys; print("CPU synthetic worker"); sys.exit('+('7' if attempt==1 else '0')+')'],
                         capture_output=True,timeout=5)
        outputs.append({'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        if p.returncode:raise EngineeringFault('startup','retained CPU worker exit 7')
        return p
    control.load_worker=load
    control.verify_ready=lambda worker,pre:hashlib.sha256(worker.stdout+worker.stderr).hexdigest()
    result=control.run()
    assert result['attempt']==2 and c.observation()['first_load_epoch']==100
    assert [o['exit'] for o in outputs]==[7,0] and calls.count('owner')==1
    assert len([r for r in c.log.rows() if r['kind']=='attempt_failed'])==1


def test_stop_factory_derives_one_path_for_both_actors_and_campaign_reopens(tmp_path):
    from training.c5_recovery_history import open_campaign,open_qualified_stop,history_guard
    root,document,roots=history_fixture(tmp_path);s=dict(scope(),history_sha256=sha(document))
    with open_campaign(root,'mac',s,document,create=True,grant=grant(s),expected_roots=roots) as log:
        parent=log.root.parent;guard=history_guard(root,'mac',document,expected_roots=roots)
        a=open_qualified_stop(parent,s,qualification(),guard,create=True,grant=grant(s))
        b=open_qualified_stop(parent,s,qualification(),guard)
        try:
            ops=Ops();assert a.stop(ops)==b.stop(ops) and ops.signals==1
            assert a.log.root==b.log.root
        finally:a.log.close();b.log.close()
    with open_campaign(root,'mac',s,document,expected_roots=roots) as reopened:
        assert reopened.rows()==[]
