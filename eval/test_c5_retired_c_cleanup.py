"""Pure cleanup precondition controls, no Rhino/GPU/delegate/key effects."""
import copy
import hashlib
import pytest
from tools.c5_hostassurance_retired_c_cleanup import validate_retired,digest,ORIGINAL_SHA,ACTIVE_SHA


def records():
    expected={'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64}
    payload={'owner_freeze_sha256':ORIGINAL_SHA,'operation':'get_scene_summary','arguments':{},
        'consent_row_sha256':None,'expected':expected,'request_id':'public-synthetic-read'}
    empty={'groups':{},'objects':[],'unit':'Millimeters'}
    result={'status':'modelbridge_fail_retired_no_replay','remote_process_exit_code':0,'holdout_calls':0,'hub_stop':None,
        'slots':[{'slot':s,'error':None,'close':{'status':'closed'},'stop':{'status':'stopped'}} for s in ['write-base','write-lora']]+
        [{'slot':'read-lora','error':'NativeError: unknown native acknowledgement; never guess cleanup','close':None,'stop':None}]}
    created={'active_serial':268435457,'fixture_serial':268435475,'python_major_minor':[3,9],
        'rhino_major':8,'rhino_version':'8.21.25188.17002','runtime_freeze_sha256':ORIGINAL_SHA}
    req={'kind':'execute','envelope':{'payload':payload,'signature':'c'*64}}
    res={'status':'done','payload':payload,'stable_idle_samples':3,'before':empty,'after':empty,'immediate_after':empty,
        'result':empty,'before_state':expected,'after_state':expected,'immediate_after_state':expected,
        'result_sha256':'d'*64,'settling_samples':[{'active_sha256':ACTIVE_SHA,'native':empty,'state':expected} for _ in range(3)]}
    row={'request_id':payload['request_id'],'payload_sha256':digest(payload),'state':'done','result_sha256':'d'*64}
    return copy.deepcopy([result,created,req,res,0,row])


def test_known_late_completed_empty_read_is_only_cleanup_precondition_not_quality_pass():
    data=records();assert validate_retired(*data)==data[2]['envelope']['payload']
    assert data[0]['status']=='modelbridge_fail_retired_no_replay'


@pytest.mark.parametrize('bad',['success','unfinished_worker','holdout','wrong_slot','old_fixture','changed_scene',
    'late_missing','no_stable','active_drift','write','unsettled','wrong_ledger','prior_not_closed'])
def test_unverified_or_wrong_owner_state_has_no_cleanup_admission(bad):
    r,c,q,s,w,l=records()
    if bad=='success':r['status']='passed'
    elif bad=='unfinished_worker':r['remote_process_exit_code']=None
    elif bad=='holdout':r['holdout_calls']=1
    elif bad=='wrong_slot':r['slots'][-1]['slot']='write-lora'
    elif bad=='old_fixture':c['fixture_serial']=268435474
    elif bad=='changed_scene':s['after']={'objects':['not-empty']}
    elif bad=='late_missing':s['status']='unknown'
    elif bad=='no_stable':s['stable_idle_samples']=2
    elif bad=='active_drift':s['settling_samples'][0]['active_sha256']='e'*64
    elif bad=='write':w=1
    elif bad=='unsettled':l['state']='reserved'
    elif bad=='wrong_ledger':l['request_id']='different'
    else:r['slots'][0]['close']['status']='unknown'
    with pytest.raises(RuntimeError):validate_retired(r,c,q,s,w,l)


def test_entry_import_has_no_rhino_or_live_effects():
    import tools.c5_hostassurance_retired_c_cleanup as module
    assert callable(module.main) and 'Rhino' not in module.__dict__


@pytest.mark.parametrize('mutation',[None,'old_study_grant','wrong_script','wrong_spec','wrong_runtime','integer_approval','model_expansion'])
def test_exact_new_cleanup_grant_binding_only(mutation):
    from pathlib import Path
    from tools.c5_hostassurance_retired_c_cleanup import binding,read,ID
    root=Path(__file__).resolve().parents[1]
    s=read(root/'eval/c5/hostassurance-c-cleanup-spec-20261007.json')
    f=read(root/'eval/c5/hostassurance-c-cleanup-runtime-20261007.json')
    a={'study_id':ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(s),
        'runtime_freeze_sha256':digest(f),
        'scope':'retired C only; known empty read-lora closure, seven ephemeral keys, exact two Idle and one AssemblyLoad detach; no replay'}
    script=f['cleanup_script_sha256']
    if mutation=='old_study_grant':a['study_id']='C5DEV-HOSTASSURANCE-20261007-C'
    elif mutation=='wrong_script':script='0'*64
    elif mutation=='wrong_spec':a['spec_sha256']='0'*64
    elif mutation=='wrong_runtime':a['runtime_freeze_sha256']='0'*64
    elif mutation=='integer_approval':a['approved']=1
    elif mutation=='model_expansion':s['model_calls']=1
    if mutation is None:binding(s,f,a,script)
    else:
        with pytest.raises(RuntimeError):binding(s,f,a,script)
