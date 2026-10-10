"""CPU safety admission/independent receipt tests, never real cleanup."""
import ast
import copy
from pathlib import Path
import pytest
from tools import c5_retired_c_cleanup_b as b
from training.c5_cleanup_b_audit import audit_manual_safety


def values():
    p = {'owner_freeze_sha256': b.C_SHA, 'operation': 'get_scene_summary', 'arguments': {},
         'expected': {'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64}, 'request_id':'synthetic-read'}
    rows = {'scene':[{'document_key':'a'*64,'revision':1,'scene_sha256':'c'*64}],
            'read':[{'request_id':p['request_id'],'state':'done','payload_sha256':b.digest(p),'result_sha256':b.digest(b.EMPTY)}], 'write':[]}
    created = {'fixture_serial':268435475,'active_serial':268435457,'runtime_freeze_sha256':b.C_SHA}
    observed = {k:True for k in ('ui_thread','backend_thread','active_serial','active_content','fixture_registry',
                                 'fixture_serial','headless_unsaved','owner_document')}
    observed.update(backend_closed=False,native=copy.deepcopy(b.EMPTY))
    return copy.deepcopy([created,p,rows,observed])


def test_atomic_drift_is_retained_only_for_exact_empty_manual_Dispose():
    c,p,r,o = values(); before = copy.deepcopy(r); result = b.validate_safety_binding(c,p,r,o)
    assert result['historical_atomic_matches_stored'] is False and r == before
    assert result['safety_Dispose_only_not_write_authority'] is True


@pytest.mark.parametrize('bad', ['fixture','active','old_runtime','operation','arguments','document_key','read_pending',
                               'write','wrong_request','wrong_payload','wrong_result','geometry','closed','ui','owner','integer_true'])
def test_unverified_scope_or_read_never_admits_manual_Dispose(bad):
    c,p,r,o = values()
    if bad=='fixture':c['fixture_serial']=1
    elif bad=='active':c['active_serial']=2
    elif bad=='old_runtime':c['runtime_freeze_sha256']='0'*64
    elif bad=='operation':p['operation']='create_box'
    elif bad=='arguments':p['arguments']={'not_readonly':True}
    elif bad=='document_key':r['scene'][0]['document_key']='d'*64
    elif bad=='read_pending':r['read'][0]['state']='reserved'
    elif bad=='write':r['write']=[{'state':'done'}]
    elif bad=='wrong_request':r['read'][0]['request_id']='other'
    elif bad=='wrong_payload':r['read'][0]['payload_sha256']='0'*64
    elif bad=='wrong_result':r['read'][0]['result_sha256']='0'*64
    elif bad=='geometry':o['native']['objects']=['not_empty']
    elif bad=='closed':o['backend_closed']=True
    elif bad=='ui':o['ui_thread']=False
    elif bad=='owner':o['owner_document']=False
    else:o['ui_thread']=1
    with pytest.raises(RuntimeError):b.validate_safety_binding(c,p,r,o)


@pytest.mark.parametrize('bad',[None,'only_prepare','old_A','integer_grant','script','model','snapshot','historical_match','decision'])
def test_V2_prepare_acceptance_cannot_replace_new_B_exact_execution_grant(bad):
    root=Path(__file__).resolve().parents[1]
    s=b.read(root/b.SPEC);d=b.read(root/b.DECISION);accepted=b.read(root/b.ACCEPTANCE)
    f={'study_id':b.ID,'spec_sha256':b.digest(s),'script_sha256':'a'*64,'decision_sha256':b.DECISION_SHA,'acceptance_sha256':b.digest(accepted)}
    a={'study_id':b.ID,'actor':'repository_owner','approved':True,'spec_sha256':b.digest(s),'runtime_freeze_sha256':b.digest(f),'scope':b.SCOPE};sha='a'*64
    if bad=='only_prepare':a=accepted
    elif bad=='old_A':a['study_id']='C5SAFE-HOSTASSURANCE-C-20261007-A'
    elif bad=='integer_grant':a['approved']=1
    elif bad=='script':sha='b'*64
    elif bad=='model':s['model_calls']=1
    elif bad=='snapshot':s['atomic_snapshot_calls']=1
    elif bad=='historical_match':s['historical_atomic_match_required_for_safety_Dispose']=True
    elif bad=='decision':accepted['actual_cleanup_execution_approved']=True
    if bad is None:b.authorize(s,f,a,d,accepted,sha)
    else:
        with pytest.raises(RuntimeError):b.authorize(s,f,a,d,accepted,sha)


def test_B_module_import_is_inert_and_snapshot_dispatch_never_called():
    assert 'Rhino' not in b.__dict__
    tree=ast.parse(Path(b.__file__).read_text())
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in
                   {'snapshot','dispatch','CreateHeadless','InvokeOnUiThread'} for n in ast.walk(tree))


def test_B_admission_is_permanent_even_without_effects(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);monkeypatch.setattr(b,'STATE',tmp_path);name=b.ID+'.admission.claim.json'
    b.publish(name,{'synthetic':True});before=(tmp_path/name).read_bytes()
    with pytest.raises(FileExistsError):b.publish(name,{'synthetic':False})
    assert (tmp_path/name).read_bytes()==before


def receipt():
    c,p,rows,o=values();s={'study_id':b.ID};f={'study_id':b.ID,'spec_sha256':b.digest(s),'ledger_logical_rows_sha256':b.digest(rows)}
    a={'study_id':b.ID,'actor':'repository_owner','approved':True,'spec_sha256':b.digest(s),'runtime_freeze_sha256':b.digest(f),'scope':b.SCOPE}
    claim={'study_id':b.ID,'runtime_freeze_sha256':b.digest(f),'replay_allowed':False}
    host={'record_count':58,'execution_authority':False,'seal_sha256':'e'*64}
    r={'study_id':b.ID,'runtime_freeze_sha256':b.digest(f),'status':'retired_C_manual_safety_closed_not_experiment_PASS',
       'field_remains_failure':True,'execution_authority':False,'complete_handler_absence_proven':False,
       'whole_host_zero_effects_proven':False,'memory_or_external_key_copy_erasure_proven':False,
       'child_idle_exact_remove_call_completed':True,'hub_idle_exact_remove_call_completed':True,
       'fixture_close_attempted':True,'fixture_registry_absent':True,
       'close_capture':{'fixture_serial':268435475,'fixture_registry_absent':True,'before_close_active_serial':268435457,
          'after_close_active_serial':268435457,'initial_active_sha256':b.ACTIVE_SHA,'before_close_active_sha256':b.ACTIVE_SHA,
          'after_close_active_sha256':b.ACTIVE_SHA,'fixture_before_close_native':copy.deepcopy(b.EMPTY)},
       'key_absence':{k:{'key_removed':True,'actual_absence_checked':True} for k in {'hub.key'}|{v+'/handoff.key' for v in ('read-lora',)+b.UNUSED}},
       'ledger_logical_rows_preserved':True,'ledger_before':rows,'ledger_after':copy.deepcopy(rows),
       'original_result_sha256':b.C_RESULT_SHA,'historical_HMAC_verified_without_replay':True,
       'current_empty_fixture_safety_observation':o,'host_receipt':host,
       **{k:0 for k in ('model_calls','gpu_calls','holdout_calls','tool_dispatches','new_subscriptions','atomic_snapshot_calls','ledger_updates')}}
    return copy.deepcopy([s,f,a,claim,claim,r,host])


@pytest.mark.parametrize('bad',[None,'key_missing','integer_key','active_changed','registry_live','ledger_changed',
                               'snapshot','old_grant','external','host','model','full_handler_claim'])
def test_independent_raw_B_safety_result_negative_controls(bad):
    s,f,a,ad,ef,r,host=receipt();host=copy.deepcopy(host);external=None
    if bad=='key_missing':r['key_absence'].pop('hub.key')
    elif bad=='integer_key':r['key_absence']['hub.key']['actual_absence_checked']=1
    elif bad=='active_changed':r['close_capture']['after_close_active_sha256']='0'*64
    elif bad=='registry_live':r['close_capture']['fixture_registry_absent']=False
    elif bad=='ledger_changed':r['ledger_after']['scene'][0]['revision']=0
    elif bad=='snapshot':r['atomic_snapshot_calls']=1
    elif bad=='old_grant':a['study_id']='C5SAFE-HOSTASSURANCE-C-20261007-A'
    elif bad=='external':external='0'*64
    elif bad=='host':host['seal_sha256']='0'*64
    elif bad=='model':r['model_calls']=1
    elif bad=='full_handler_claim':r['complete_handler_absence_proven']=True
    if bad is None:
        assert audit_manual_safety(s,f,a,ad,ef,r,b.digest(r),host)['original_C_remains_failure'] is True
    else:
        with pytest.raises(ValueError):audit_manual_safety(s,f,a,ad,ef,r,external or b.digest(r),host)
