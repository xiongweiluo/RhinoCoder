"""Synthetic CPU only: actual raw HMAC/SQLite/model/timing verifiers; no holdout."""
import ast,copy,inspect,json,shutil,gc
from pathlib import Path
import pytest
from eval.test_c5_formal_reuse_full_field import complete_scoped_field
from eval.test_c5_model_transport import Tokenizer
from plugin.rhino_listener.c5_research_native import digest
from plugin.rhino_listener.c5_research_channel import read_json,publish_json
from training import c5_formal_reuse_partial_audit as partial
from training.c5_formal_reuse_joint_audit_base import audit_remote


def fixture(tmp_path,monkeypatch):
    state,cases,spec,freeze,receipt,_,_=complete_scoped_field(tmp_path,monkeypatch,fail_before_model_at=7)
    publish_json(state,'owner-automatic-receipt-custody.json',{'receipt':receipt,'custody':'owner_authorized_automatic_capture',
        'manual_external_receipt_attestation':False,'runtime_sha256':digest(freeze)})
    first=read_json(state,'load-permit.json')['first_load_epoch']
    monkeypatch.setattr(partial,'failed_admission',lambda *a:{'first_load_epoch':first,'attempts_consumed':3,
        'formal_exposures':1,'original_history_preserved':True,'ledger_usage_unsettled':True})
    return state,cases,spec,freeze


def test_partial_remote_diff_is_exactly_minimum_count_and_function_name():
    a=inspect.getsource(audit_remote)
    b=inspect.getsource(partial.audit_partial_remote)
    assert b.replace('def audit_partial_remote(','def audit_remote(',1).replace('0 <= len(keys)','40 <= len(keys)',1)==a


def test_readonly_partial_real_raw_chains_not_full40_or_unsupported_root_cause(tmp_path,monkeypatch):
    state,cases,spec,freeze=fixture(tmp_path,monkeypatch)
    gc.collect()  # Synthetic producer has exited; close unreachable SQLite connections.
    before={p.relative_to(state).as_posix():p.read_bytes() for p in state.rglob('*') if p.is_file()}
    copied=tmp_path/'audit-copy'/'preload-3';copied.parent.mkdir();shutil.copytree(state,copied)
    result=partial.audit_partial(copied,cases,spec,freeze,Tokenizer(),source_guard=lambda:None)
    assert result['recorded_slots_attempted']==7 and result['completed_slot_raw_chains_verified']==6
    assert result['failed_pre_model_slot']['diagnosis']=='unattributed_pre_model_FormalPlanError'
    assert result['failed_pre_model_slot']['initial_fixture_validation_rejection_reproduced'] is False
    assert result['full40_quality_result'] is result['paired_summary'] is None
    assert not result['original_complete_40_gate_passed'] and not result['c5_6_gate_claim']
    assert not result['research_restarted'] and result['model_or_rhino_calls']==0
    text=json.dumps(result)
    for case in cases:assert case['task_text'] not in text and case['family_id'] not in text
    after={p.relative_to(state).as_posix():p.read_bytes() for p in state.rglob('*') if p.is_file()}
    assert before==after


@pytest.mark.parametrize('mutation',['hmac','model','control_time','case_commitment','unused_key','extra_slot','resource'])
def test_partial_rejects_altered_raw_evidence(tmp_path,monkeypatch,mutation):
    state,cases,spec,freeze=fixture(tmp_path,monkeypatch)
    if mutation=='case_commitment':
        cases=copy.deepcopy(cases);cases[0]['task_text']+=' changed'
    elif mutation=='unused_key':
        unused=next(p for p in state.glob('F*') if p.is_dir() and not (p/'bootstrap.json').exists())
        (unused/'handoff.key').write_text('{}')
    elif mutation=='extra_slot':
        (state/'F20-lora.result.json').write_text('{}')
    else:
        if mutation=='hmac':
            p=next(state.glob('F*/request-*.json'));v=json.loads(p.read_bytes());v['envelope']['signature']='0'*64
        elif mutation=='model':
            p=next(state.glob('*-model-response.json'));v=json.loads(p.read_bytes());v['model_identity_sha256']='f'*64
        elif mutation=='control_time':
            p=state/'control-0001-time.json';v=json.loads(p.read_bytes());v['completed_in_budget']=False
        else:
            p=state/'resource-settlement.json';v=json.loads(p.read_bytes());v['cap_seconds']=9999999
        p.write_text(json.dumps(v))
    with pytest.raises((ValueError,RuntimeError,KeyError,AssertionError)):
        partial.audit_partial(state,cases,spec,freeze,Tokenizer(),source_guard=lambda:None)


def test_owner_entry_checks_private_tty_before_any_original_or_evidence_read(tmp_path,monkeypatch):
    import importlib.util,sys
    path=Path(__file__).resolve().parents[1]/'tools/c5_formal_reuse_partial_owner_audit.py'
    spec=importlib.util.spec_from_file_location('partial_owner_cpu',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(sys,'argv',[str(path),'audit','--review-sha256','0'*64])
    monkeypatch.setattr(sys.stdin,'isatty',lambda:False)
    monkeypatch.setattr(module,'public_original',lambda:pytest.fail('private gate must come first'))
    assert module.main()==1

def owner_module():
    import importlib.util
    path=Path(__file__).resolve().parents[1]/'tools/c5_formal_reuse_partial_owner_audit.py'
    spec=importlib.util.spec_from_file_location('partial_copy_cpu',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_private_copy_keeps_original_bytes_and_inventory_when_sqlite_adds_sidecars(tmp_path):
    owner=owner_module();original=tmp_path/'original';original.mkdir(mode=0o700)
    p=original/'fixture-audit.sqlite3';p.write_bytes(b'original bounded snapshot');p.chmod(0o600)
    copied=tmp_path/'copy';before=owner.copy_evidence(original,copied)
    (copied/'fixture-audit.sqlite3-wal').write_bytes(b'new disposable SQLite sidecar')
    (copied/'fixture-audit.sqlite3').write_bytes(b'audit copy can be modified by SQLite')
    assert owner.evidence_inventory(original)==before
    assert p.read_bytes()==b'original bounded snapshot'


@pytest.mark.parametrize('bad',['symlink','hardlink','nonempty_wal','writable'])
def test_copy_refuses_unbound_input_or_nonempty_snapshot_wal(tmp_path,bad):
    owner=owner_module();original=tmp_path/'original';original.mkdir(mode=0o700)
    p=original/'fixture-audit.sqlite3';p.write_bytes(b'snapshot');p.chmod(0o600)
    if bad=='symlink':(original/'other').symlink_to(p)
    elif bad=='hardlink':__import__('os').link(p,original/'other')
    elif bad=='nonempty_wal':
        extra=original/'fixture-audit.sqlite3-wal';extra.write_bytes(b'not covered by original snapshot hash');extra.chmod(0o600)
    else:p.chmod(0o622)
    with pytest.raises(ValueError):owner.copy_evidence(original,tmp_path/'copy')

def test_closed_environment_allows_late_registered_import_but_refuses_unknown_or_identity_change():
    owner=owner_module()
    expected={'python':'fixed','executable':'fixed','sys_path':['fixed'],
        'kernel_and_unlisted_opaque_runtime_trusted_not_byte_proven':True,
        'readable_loaded_external_files':{'early':'a','late':'b'}}
    current=copy.deepcopy(expected);current['readable_loaded_external_files']={'late':'b'}
    owner.verify_environment(current,expected)
    current['readable_loaded_external_files']['unknown']='c'
    with pytest.raises(ValueError):owner.verify_environment(current,expected)
    current=copy.deepcopy(expected);current['python']='changed'
    with pytest.raises(ValueError):owner.verify_environment(current,expected)


@pytest.mark.parametrize('concurrent_change',[False,True])
def test_private_owner_entry_copies_audits_and_publishes_only_after_original_unchanged(tmp_path,monkeypatch,concurrent_change):
    import sys
    state,cases,spec,freeze=fixture(tmp_path,monkeypatch);gc.collect()
    publish_json(state,'private-cases.json',cases)
    owner=owner_module();source=tmp_path/'audit-source';source.mkdir(mode=0o700)
    for name in owner.FILES:
        p=source/name;p.write_text('public synthetic CPU source');p.chmod(0o600)
    environment={'python':'cpu','executable':'cpu','sys_path':['cpu'],
        'kernel_and_unlisted_opaque_runtime_trusted_not_byte_proven':True,'readable_loaded_external_files':{}}
    review={'original_spec_sha256':owner.SPEC,'original_runtime_sha256':owner.RUNTIME,
        'source_files':{name:owner.file_sha(source/name) for name in owner.FILES},'environment':environment}
    p=source/'review-runtime.json';p.write_text(json.dumps(review));p.chmod(0o600)
    output=tmp_path/'audit-output'
    monkeypatch.setattr(owner,'SOURCE',source);monkeypatch.setattr(owner,'EVIDENCE',state);monkeypatch.setattr(owner,'OUTPUT',output)
    monkeypatch.setattr(owner,'public_original',lambda:(spec,freeze,lambda:None))
    monkeypatch.setattr(owner,'environment',lambda:copy.deepcopy(environment))
    def audit(*a,**k):
        value=partial.audit_partial(*a,**k)
        if concurrent_change:
            path=state/'resource-settlement.json';path.write_bytes(path.read_bytes()+b' ')
        return value
    monkeypatch.setattr(owner,'load_core',lambda _: (audit,Tokenizer()))
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True);monkeypatch.setattr(sys.stderr,'isatty',lambda:True)
    monkeypatch.setattr(sys,'argv',['owner.py','audit','--review-sha256',owner.digest(review)])
    assert owner.main()==(1 if concurrent_change else 0)
    summary=output/'owner-public-partial-audit-summary.json'
    assert summary.exists() is (not concurrent_change)
    assert not list(output.glob('readonly-evidence-*'))
    if concurrent_change:
        paths=list(output.glob('owner-public-partial-audit-refusal-*.json'))
        assert len(paths)==1
        assert json.loads(paths[0].read_bytes())['error_code']=='partial_audit_original_changed_after_audit'
    if not concurrent_change:
        value=json.loads(summary.read_bytes())
        assert value['evidence_copy_bytes_verified'] and not value['original_source_or_evidence_modified']
        assert value['sqlite_reader_sidecars_confined_to_disposable_private_copy']
        assert not value['original_complete_40_gate_passed'] and value['full40_quality_result'] is None

@pytest.mark.parametrize('kind',['ops','classes'])
def test_owner_environment_uses_exact_typed_frozen_virtual_origin(tmp_path,monkeypatch,kind):
    import types,sys
    owner=owner_module();path=tmp_path/'defining.py';path.write_text('public CPU defining source')
    cls_name='_Ops' if kind=='ops' else '_Classes'
    cls=type(cls_name,(types.ModuleType,),{})
    virtual=cls('torch.'+kind);virtual.__file__='_'+kind+'.py'
    defining=types.ModuleType('torch._'+kind);defining.__file__=str(path);setattr(defining,cls_name,cls)
    torch=types.ModuleType('torch');setattr(torch,kind,virtual)
    modules={'torch':torch,'torch._'+kind:defining,'torch.'+kind:virtual}
    monkeypatch.setattr(owner,'sys',types.SimpleNamespace(modules=modules,executable=sys.executable,version=sys.version,path=sys.path))
    result=owner.environment()
    assert result['readable_loaded_external_files'][str(path)]==owner.file_sha(path)
    spoof=types.ModuleType('torch.'+kind);spoof.__file__='_'+kind+'.py';modules['torch.'+kind]=spoof;setattr(torch,kind,spoof)
    with pytest.raises(ValueError,match='virtual_namespace_identity'):owner.environment()


def test_public_contract_probe_seals_schema_loader_path_before_private_audit():
    import sys
    owner=owner_module();a=owner.prepare_public_contract(Tokenizer());paths=list(sys.path)
    b=owner.prepare_public_contract(Tokenizer())
    assert a==b and a['public_tools']==23 and a['private_evidence_reads']==0 and a['model_or_rhino_calls']==0
    assert list(sys.path)==paths
