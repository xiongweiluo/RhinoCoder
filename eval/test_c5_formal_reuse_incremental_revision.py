"""Public frozen prefix replay; no real grant, field state or model calls."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE,expected_grant
from plugin.rhino_listener.c5_formal_reuse_lineage import LINEAGE_FILE,FIRST
from plugin.rhino_listener.c5_research_native import NativeError
from training.c5_reuse_evidence import sha,canonical
from training.c5_recovery_storage import EvidenceLog,write_once
from training.c5_recovery_policy import POLICY
from training.c5_recovery_confirmation import snapshot
from training.c5_formal_reuse_admission import FormalCampaign,campaign_scope,require_startable
from training.c5_formal_reuse_supervisor import validate_load_permit,claim_gpu_role
import training.c5_formal_reuse_admission as admission
import training.c5_formal_reuse_revision as revision

ROOT=Path(__file__).resolve().parents[1]

def materials():
    return tuple(json.loads((ROOT/n).read_bytes()) for n in (SPEC_FILE,FREEZE_FILE))

def frozen_log(tmp_path):
    s,f=materials();lineage=f['incremental_revision'];initial=lineage['initial_campaign_scope']
    root=tmp_path/'c5-reuse-global-admission-v1';root.mkdir(mode=0o700)
    parent=root/admission.NAMESPACE;parent.mkdir(mode=0o700)
    write_once(parent,'campaign.json',{'campaign_id':initial['campaign_id'],'history_sha256':initial['history_sha256'],
        'initial_scope_sha256':sha(initial)})
    log=EvidenceLog(parent/'ledger',initial,lambda:None,create=True)
    for row in lineage['prior_campaign_events']:
        assert log.append(row['kind'],row['payload'])==row
    assert log.rows()[-1]['record_sha256']==lineage['prior_campaign_head_sha256']
    return s,f,root,log

def revision_grant(scope,head):
    return {'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],
        'scope_sha256':sha(scope),'spec_sha256':scope['spec_sha256'],'runtime_sha256':scope['runtime_sha256'],
        'policy_sha256':sha(POLICY),'previous_campaign_head_sha256':head}

def test_public_original_prefix_accepts_revision_and_second_load_preserving_first_clock(tmp_path):
    s,f,_,log=frozen_log(tmp_path);initial=f['incremental_revision']['initial_campaign_scope']
    c=FormalCampaign(initial,log,wall=lambda:FIRST+1000)
    try:
        assert c.observation()['status']=='RETRYABLE_ENGINEERING'
        revised=campaign_scope(s,f)
        c.accept_revision(revised,revision_grant(revised,log.rows()[-1]['record_sha256']))
        snap=snapshot(revised,'1'*64,'2'*64)
        c.confirm(snap,{'actor':'repository_owner',**snap,'before_model_loading':True,
            'public_attempts_authorized':0,'human_origin_cryptographically_proven':False})
        require_startable(c,2);assert c.start()==2
        permit={'scope':revised,'rows':log.rows(),'attempt':2,'first_load_epoch':FIRST}
        result=validate_load_permit(permit,s,f,2)
        assert result['attempts']==2 and result['first_load_epoch']==FIRST and not result['formal_consumed']
        # Current-scope rebinding of the old ledger would fail its original hashes.
        broken=copy.deepcopy(permit);broken['rows'][0]['binding_sha256']=sha(revised)
        with pytest.raises((ValueError,NativeError)):validate_load_permit(broken,s,f,2)
        broken=copy.deepcopy(permit);broken['first_load_epoch']+=1
        with pytest.raises((ValueError,NativeError)):validate_load_permit(broken,s,f,2)
    finally:log.close()

@pytest.mark.parametrize('field,change',[('development_seconds_max',86400),('history_sha256','9'*64),
    ('public_plan_sha256','9'*64),('contract_sha256','9'*64)])
def test_revision_cannot_reset_budget_or_change_history_dataset_contract(tmp_path,field,change):
    s,f,_,log=frozen_log(tmp_path);c=FormalCampaign(f['incremental_revision']['initial_campaign_scope'],log)
    try:
        revised=campaign_scope(s,f);revised[field]=change
        with pytest.raises((ValueError,NativeError)):
            c.accept_revision(revised,revision_grant(revised,log.rows()[-1]['record_sha256']))
        assert len(log.rows())==4 and c.observation()['first_load_epoch']==FIRST
    finally:log.close()

def test_activation_appends_once_only_and_keeps_all_original_prefix_bytes(tmp_path,monkeypatch):
    s,f,root,log=frozen_log(tmp_path);log.close()
    before={n:hashlib.sha256((root/admission.NAMESPACE/n).read_bytes()).hexdigest()
        for n in f['incremental_revision']['mac_campaign_prefix_files']}
    import plugin.rhino_listener.c5_formal_reuse_scope as scope
    monkeypatch.setattr(scope,'authority',lambda *args,**kw:None) # Synthetic authorization only.
    monkeypatch.setattr(revision,'verify_endpoint',lambda *args:lambda:None)
    monkeypatch.setitem(admission.ROOTS,'mac',root)
    a=revision.activate_mac(s,f,expected_grant(s,f));b=revision.activate_mac(s,f,expected_grant(s,f))
    assert a['attempts_consumed']==1 and a['first_load_epoch']==FIRST and a['research_restarted'] is False
    assert b['status']=='revision_already_registered_no_restart'
    assert all(hashlib.sha256((root/admission.NAMESPACE/n).read_bytes()).hexdigest()==h for n,h in before.items())
    log=EvidenceLog(root/admission.NAMESPACE/'ledger',f['incremental_revision']['initial_campaign_scope'],lambda:None)
    try:assert len(log.rows())==5
    finally:log.close()

def test_revised_gpu_role_uses_original_campaign_manifest_not_new_scope(tmp_path,monkeypatch):
    s,f=materials();root=tmp_path/'c5-reuse-global-admission-v1';root.mkdir(mode=0o700)
    parent=root/admission.NAMESPACE;parent.mkdir(mode=0o700)
    value={'scope_sha256':sha(f['incremental_revision']['initial_campaign_scope']),
        'first_load_epoch':FIRST,'history_sha256':sha(f['history']),'replay_allowed':False}
    write_once(parent,'campaign.json',value);write_once(parent,'worker-role-1.json',{'cpu_fixture_previous_role':True})
    monkeypatch.setitem(admission.ROOTS,'gpu',root)
    monkeypatch.setattr(admission,'history_guard',lambda *args,**kw:lambda:None)
    permit={'scope':campaign_scope(s,f),'first_load_epoch':FIRST}
    claim_gpu_role(permit,f,2)
    assert json.loads((parent/'campaign.json').read_bytes())==value
    assert json.loads((parent/'worker-role-2.json').read_bytes())['first_load_epoch']==FIRST

def test_revision_cannot_create_a_replacement_campaign(tmp_path,monkeypatch):
    s,f=materials();root=tmp_path/'c5-reuse-global-admission-v1';root.mkdir(mode=0o700)
    monkeypatch.setattr(admission,'authority',lambda *args,**kw:None)
    monkeypatch.setattr(admission,'history_guard',lambda *args,**kw:lambda:None)
    with pytest.raises((ValueError,NativeError),match='formal_reuse_revision_cannot_create_new_campaign'):
        admission.open_formal_campaign(s,f,expected_grant(s,f),f['history'],create=True,root=root)
    assert not (root/admission.NAMESPACE).exists()
