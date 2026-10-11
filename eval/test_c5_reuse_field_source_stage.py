"""Public-only deployment/update negatives; state/grants/old runs untouched."""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from training.c5_reuse_freeze_materials import build
from training.c5_reuse_evidence import canonical
from tools import stage_c5_reuse_field_source as module
from tools.check_c5_reuse_field_freeze import check

ROOT=Path(__file__).resolve().parents[1]


def packet(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'PARENTS',{'mac':tmp_path,'gpu':tmp_path})
    s,r,p,payload,review=build(ROOT,environment={},model_assets={},host_files={},host_acceptance={},gpu_process={},transport={})
    value={'endpoint':'mac','payload_base64':{n:base64.b64encode(b).decode() for n,b in payload.items()},
           'file_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in payload.items()}}
    raw=canonical(value)
    return raw,hashlib.sha256(raw).hexdigest(),value,review


def test_exact_public_bytes_stage_once_without_claim_keys_or_grant(tmp_path,monkeypatch):
    raw,pin,value,review=packet(tmp_path,monkeypatch)
    result=module.stage(raw,pin);root=tmp_path/(module.INSTANCE+'-source')
    assert result['files_individually_written_and_rechecked']==len(value['file_sha256'])
    assert not result['state_or_owner_grant_or_admission_created']
    assert {p.name for p in tmp_path.iterdir()}=={root.name}
    outcome=check(root,review['spec_sha256'],review['runtime_sha256'])
    assert outcome['source_population_exact'] and not outcome['candidate_execution_ready']
    with pytest.raises(FileExistsError):module.stage(raw,pin)


@pytest.mark.parametrize('change',['wrong_pin','private_key','missing_file','tampered_bytes','state','admission','symlink_parent'])
def test_unsafe_or_live_scope_is_rejected_before_public_deployment(tmp_path,monkeypatch,change):
    raw,pin,value,review=packet(tmp_path,monkeypatch)
    if change=='wrong_pin':pin='0'*64
    elif change=='private_key':
        value['payload_base64']['owner-approval.json']=base64.b64encode(b'{}').decode()
        value['file_sha256']['owner-approval.json']=hashlib.sha256(b'{}').hexdigest()
    elif change=='missing_file':value['payload_base64'].pop(module.PLAN)
    elif change=='tampered_bytes':value['payload_base64'][module.PLAN]=base64.b64encode(b'{}').decode()
    elif change=='state':(tmp_path/(module.INSTANCE+'-state')).mkdir()
    elif change=='admission':(tmp_path/'c5-reuse-global-admission-v1').mkdir()
    elif change=='symlink_parent':
        alias=tmp_path/'alias';alias.symlink_to(tmp_path);monkeypatch.setattr(module,'PARENTS',{'mac':alias,'gpu':alias})
    if change in ('private_key','missing_file','tampered_bytes'):raw=canonical(value);pin=hashlib.sha256(raw).hexdigest()
    with pytest.raises((ValueError,OSError)):module.stage(raw,pin)
    assert not (tmp_path/(module.INSTANCE+'-source')).exists()


def test_before_approval_only_three_frozen_records_may_change(tmp_path,monkeypatch):
    raw,pin,value,review=packet(tmp_path,monkeypatch);module.stage(raw,pin)
    v=json.loads(base64.b64decode(value['payload_base64'][module.PLAN]));v['resource_basis']['prior_cumulative_upper_bound_basis']='CPU fixture owner report'
    changed=canonical(v)+b'\n';value['payload_base64'][module.PLAN]=base64.b64encode(changed).decode()
    value['file_sha256'][module.PLAN]=hashlib.sha256(changed).hexdigest()
    r=json.loads(base64.b64decode(value['payload_base64'][module.RUNTIME]));r['source_files'][module.PLAN]=value['file_sha256'][module.PLAN]
    rraw=canonical(r)+b'\n';value['payload_base64'][module.RUNTIME]=base64.b64encode(rraw).decode()
    value['file_sha256'][module.RUNTIME]=hashlib.sha256(rraw).hexdigest()
    new=canonical(value);module.stage(new,hashlib.sha256(new).hexdigest(),update=True)
    root=tmp_path/(module.INSTANCE+'-source')
    assert (root/module.PLAN).read_bytes()==changed
    name='training/c5_contract.py';b=b'pass\n';value['payload_base64'][name]=base64.b64encode(b).decode();value['file_sha256'][name]=hashlib.sha256(b).hexdigest()
    r['source_files'][name]=value['file_sha256'][name];rraw=canonical(r)+b'\n'
    value['payload_base64'][module.RUNTIME]=base64.b64encode(rraw).decode();value['file_sha256'][module.RUNTIME]=hashlib.sha256(rraw).hexdigest()
    new=canonical(value)
    with pytest.raises(ValueError,match='only_freeze_records_mutable'):module.stage(new,hashlib.sha256(new).hexdigest(),update=True)
