"""CPU-only failures and readonly invariants; never inspect live endpoints."""
import copy,hashlib,itertools,json,os,sqlite3,subprocess,sys
from pathlib import Path
import pytest
from tools import inspect_c5_reuse_retired_startup as diag
from training.c5_reuse_diagnostic_capture import BoundedCapture,FailureCleanupOnce
from training.c5_reuse_continuation_proposal import validate_proposal
ROOT=Path(__file__).resolve().parents[1]

def registry(tmp_path):
    root=tmp_path/'c5-reuse-global-admission-v1';root.mkdir(mode=0o700);(root/'admission.lock').touch(mode=0o600)
    db=sqlite3.connect(root/'admission.sqlite');db.execute(diag.TABLE);rows=[]
    for role in ('controller','host'):
        value={'study_id':'C5DEV-REUSE-20261012-C','role':role,'scope_sha256':'a'*64,'replay_allowed':False}
        row=(value['study_id'],role,value['scope_sha256'],diag.sha(value));rows.append(row)
        (root/(role+'.consumed.json')).write_bytes(diag.canon(value)+b'\n');(root/(role+'.consumed.json')).chmod(0o600)
        db.execute('INSERT INTO admission VALUES (?,?,?,?)',row)
    db.commit();db.close();(root/'admission.sqlite').chmod(0o600);return root

@pytest.mark.parametrize('flags',list(itertools.product((False,True),repeat=3)))
def test_first_frozen_guard_capability_matrix_without_system_calls(flags):
    v=dict(zip(('fork','pidfd_open','pidfd_send_signal'),flags));v['platform']='linux'
    assert diag.primitive_guard(v)==all(flags)
    v['platform']='darwin';assert diag.primitive_guard(v) is False

@pytest.mark.parametrize('value',[1,None,'yes'])
def test_capabilities_cannot_be_claimed_by_truthy_nonbool(value):
    v={'platform':'linux','fork':True,'pidfd_open':value,'pidfd_send_signal':True}
    with pytest.raises(ValueError,match='primitive_schema'):diag.primitive_guard(v)

def test_frozen_source_first_guard_and_registry_construction_are_inspected_not_run():
    v=diag.static_boundaries((ROOT/'training/c5_reuse_gpu_supervisor.py').read_text())
    assert v['supervisor_registry_uses_default_create_false'] and not v['original_remote_failure_proven_by_static_check']

@pytest.mark.parametrize('mutation',['body','guard'])
def test_unknown_changed_guard_or_registry_call_refused(mutation):
    source=(ROOT/'training/c5_reuse_gpu_supervisor.py').read_text()
    if mutation=='guard':source=source.replace("sys.platform=='linux'","True",1)
    else:source=source.replace('registry=AdmissionRegistry(binding)','registry=object()',1)
    with pytest.raises(ValueError):diag.static_boundaries(source)

def test_capture_stream_overflow_drained_hash_retained_prefix_not_complete():
    c=BoundedCapture(17);raw=b'a'*65536+b'b'*100
    c.feed(raw[:65536]);c.feed(raw[65536:]);v=c.finish(eof=True,exit_status=1)
    assert bytes(c.data)==raw[:17] and v['observed_bytes_sha256']==hashlib.sha256(raw).hexdigest()
    assert v['truncated'] and not v['complete_raw_capture'] and not v['retry_allowed']

@pytest.mark.parametrize('eof,status',[(False,0),(True,None),(False,None)])
def test_missing_eof_or_exit_never_complete_capture(eof,status):
    c=BoundedCapture();c.feed(b'traceback\n');v=c.finish(eof=eof,exit_status=status)
    assert not v['complete_raw_capture'] and not v['execution_success_proven']

def test_actual_cpu_subprocess_error_retained_but_not_promoted_to_execution_success():
    p=subprocess.Popen([sys.executable,'-I','-B','-c','import sys;sys.stderr.write("cpu synthetic startup error\\n");sys.exit(7)'],stderr=subprocess.PIPE,stdout=subprocess.DEVNULL)
    c=BoundedCapture()
    while True:
        raw=p.stderr.read(4096)
        if not raw:break
        c.feed(raw)
    p.stderr.close();code=p.wait(timeout=10);v=c.finish(eof=True,exit_status=code)
    assert code==7 and bytes(c.data)==b'cpu synthetic startup error\n' and v['complete_raw_capture']
    assert not v['execution_success_proven'] and not v['execution_authority']

@pytest.mark.parametrize('cap',[0,262145,True])
def test_invalid_capture_cap(cap):
    with pytest.raises(ValueError):BoundedCapture(cap)

def test_capture_no_append_or_refinish_after_seal():
    c=BoundedCapture();c.finish(eof=True,exit_status=0)
    with pytest.raises(ValueError):c.feed(b'x')
    with pytest.raises(ValueError):c.finish(eof=True,exit_status=0)

@pytest.mark.parametrize('gpu_error,native_error',[(False,False),(True,False),(False,True),(True,True)])
def test_gpu_stop_failure_cannot_skip_first_known_cleanup_or_enable_retry(gpu_error,native_error):
    calls=[]
    def gpu():
        calls.append('gpu')
        if gpu_error:raise ValueError('synthetic unknown stop')
        return {'observed':True}
    def native():
        calls.append('native')
        if native_error:raise RuntimeError('synthetic unknown cleanup')
        return {'observed':True}
    runner=FailureCleanupOnce();v=runner.run(gpu,native)
    assert calls==['gpu','native'] and not v['whole_field_pass'] and not v['full_cleanup_proven']
    with pytest.raises(ValueError,match='no_retry'):runner.run(gpu,native)
    assert calls==['gpu','native']

def test_empty_lock_allowed_only_with_explicit_read_policy(tmp_path):
    p=tmp_path/'lock';p.touch(mode=0o600)
    with pytest.raises(ValueError):diag.read(p,private=True)
    assert diag.read(p,private=True,allow_empty=True)==b''

@pytest.mark.parametrize('change',['alias','hardlink','mode','fifo'])
def test_secure_read_denies_untrusted_file_metadata_before_effects(tmp_path,change):
    p=tmp_path/'v';p.write_bytes(b'{}');p.chmod(0o600)
    if change=='alias':q=tmp_path/'q';q.symlink_to(p);p=q
    elif change=='hardlink':os.link(p,tmp_path/'q')
    elif change=='mode':p.chmod(0o660)
    else:p.unlink();os.mkfifo(p,0o600)
    with pytest.raises((ValueError,OSError)):diag.read(p,private=True)

def test_legacy_two_rows_and_every_original_byte_preserved_under_readonly_snapshot(tmp_path):
    root=registry(tmp_path);before={p.name:p.read_bytes() for p in root.iterdir()}
    value=diag.registry_snapshot(tmp_path,'mac')
    assert len(value['rows'])==2 and value['writes']==0 and before=={p.name:p.read_bytes() for p in root.iterdir()}

def test_missing_gpu_registry_is_observation_not_initialization(tmp_path):
    assert diag.registry_snapshot(tmp_path,'gpu')['exists'] is False and list(tmp_path.iterdir())==[]
    with pytest.raises(ValueError):diag.registry_snapshot(tmp_path,'mac')

@pytest.mark.parametrize('change',['row','tombstone','extra','missing'])
def test_partial_unknown_or_corrupted_consumption_refused(tmp_path,change):
    root=registry(tmp_path)
    if change=='row':
        db=sqlite3.connect(root/'admission.sqlite');db.execute("DELETE FROM admission WHERE role='host'");db.commit();db.close()
    elif change=='tombstone':(root/'host.consumed.json').write_bytes(b'{}')
    elif change=='extra':(root/'new-namespace.json').write_bytes(b'{}')
    else:(root/'host.consumed.json').unlink()
    with pytest.raises((ValueError,OSError)):diag.registry_snapshot(tmp_path,'mac')

def test_disabled_site_rejected_before_reading_any_endpoint(monkeypatch):
    class Flags:no_site=True
    monkeypatch.setattr(sys,'flags',Flags())
    monkeypatch.setattr(diag,'retired',lambda p:pytest.fail('retired metadata read'))
    with pytest.raises(ValueError,match='site_required'):diag.diagnose('gpu')

@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"a":NaN}'])
def test_duplicate_or_nonfinite_observation_refused(raw):
    with pytest.raises(ValueError):diag.decode(raw)

def proposal():
    return json.loads((ROOT/'eval/c5/reuse-c-continuation-proposal-20261012.json').read_bytes()),json.loads((ROOT/'eval/c5/reuse-c-startup-readonly-diagnosis-20261012.json').read_bytes())['legacy_snapshot']

def test_disabled_proposal_binds_legacy_bytes_and_never_creates_authority():
    p,s=proposal();before=copy.deepcopy((p,s));v=validate_proposal(p,s)
    assert v['carryforward_rows']==2 and not v['execution_authority'] and not v['migration_or_new_study_created'] and (p,s)==before

@pytest.mark.parametrize('change',['authority','selected','restore','root','carry','snapshot','attempts','identity','blind','fallback','resource','formal'])
def test_proposal_cannot_silently_admit_new_research_or_discard_history(change):
    p,s=proposal()
    if change=='authority':p['authority']['execution_ready']=True
    elif change=='selected':p['selected_decision']='prepare_one_disclosed_followup'
    elif change=='restore':p['retired_c']['grant_restore_allowed']=True
    elif change=='root':p['legacy']['global_roots']['mac']+='/empty'
    elif change=='carry':p['legacy']['known_consumed_rows_carried_forward']=[]
    elif change=='snapshot':s['mac']['file_sha256']['admission.sqlite']='0'*64
    elif change=='attempts':p['continuation']['maximum_additional_development_attempts']=2
    elif change=='identity':p['continuation']['new_study_id']='live-real-id'
    elif change=='blind':p['continuation']['new_blind_holdout_claimed']=True
    elif change=='fallback':p['startup']['numeric_pid_or_name_kill_fallback_allowed']=True
    elif change=='resource':p['resources']['lease_expiry_epoch']=1791914400
    else:p['continuation']['formal_requires_development_whole_raw_audit_pass']=False
    with pytest.raises(ValueError):validate_proposal(p,s)

@pytest.mark.parametrize('container,key,value',[
    ('continuation','maximum_additional_development_attempts',True),
    ('continuation','formal_requires_development_whole_raw_audit_pass',1),
    ('startup','native_pidfd_open_and_send_required',1),
    ('retired_c','grant_restore_allowed',0),
    ('resources','export_reserve_seconds_min',900.0),
])
def test_protocol_json_types_cannot_alias_bool_and_integer(container,key,value):
    p,s=proposal();p[container][key]=value
    with pytest.raises(ValueError):validate_proposal(p,s)

@pytest.mark.parametrize('change',['hash','row','writes','root'])
def test_legacy_snapshot_shape_and_exact_hashes_cannot_be_invented(change):
    p,s=proposal()
    if change=='hash':s['mac']['file_sha256']['admission.sqlite']='unknown'
    elif change=='row':s['mac']['rows'][0]=s['mac']['rows'][0][:2]
    elif change=='writes':s['mac']['writes']=False
    else:s['gpu']['root_name']='empty_namespace'
    with pytest.raises(ValueError):validate_proposal(p,s)

def test_public_proposal_cli_checks_disabled_receipts():
    from tools.check_c5_reuse_continuation_proposal import check
    assert check()['status']=='disabled_proposal_consistent'
