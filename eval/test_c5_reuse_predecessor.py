"""Candidate-B retirement and unchanged shared registry controls; CPU only."""
import json
import hashlib
import os
from pathlib import Path
import sqlite3

import pytest

from plugin.rhino_listener.c5_reuse_predecessor import POLICY,verify_retirement
from plugin.rhino_listener.c5_reuse_runtime_scope import read_bytes
from plugin.rhino_listener.c5_reuse_field_scope import bind,canonical
from eval.test_c5_reuse_field_preparation import binding
from training.c5_reuse_admission import AdmissionRegistry
from tools.stage_c5_reuse_field_source import preparation_scope

ROOT=Path(__file__).resolve().parents[1]


def legacy(tmp_path):
    b=binding(tmp_path,endpoint='mac');parent=Path(b['paths']['state_root']).parent
    state=parent/'reuse-dev-20261011-a-state';state.mkdir(mode=0o700)
    failure=json.loads((ROOT/'eval/c5/reuse-development-startup-failure-20261012.json').read_bytes())
    approval=json.loads((ROOT/'eval/c5/reuse-development-owner-exact-approval-20261012.json').read_bytes())['approval']
    for name,value,pin in [('entry-retired-no-retry.json',failure['retirement']['record'],POLICY['retirement_raw_sha256']),
        ('owner-approval.retired-no-retry.json',approval,POLICY['retired_approval_raw_sha256'])]:
        p=state/name;p.write_bytes(canonical(value)+b'\n');p.chmod(0o600)
        assert hashlib.sha256(p.read_bytes()).hexdigest()==pin
    return b,parent,state


def test_retirement_binding_and_existing_empty_registry_are_readonly(tmp_path):
    b,parent,state=legacy(tmp_path)
    with AdmissionRegistry(b,create=True):pass
    registry=Path(b['paths']['admission_root'])
    before={p.name:p.read_bytes() for p in registry.iterdir()}
    verify_retirement(parent,read_bytes);preparation_scope(parent)
    assert before=={p.name:p.read_bytes() for p in registry.iterdir()}
    assert not (parent/'reuse-dev-20261012-b-state').exists()
    assert set(registry.iterdir())=={registry/'admission.lock',registry/'admission.sqlite'}


@pytest.mark.parametrize('change',['restored_grant','missing_retirement','drift_retirement','missing_saved_approval',
    'drift_saved_approval','alias_retirement','hardlink_retirement','public_directory','public_record','nonempty_registry',
    'tombstone','schema','extra','alias_database','hardlink_database'])
def test_no_restore_unknown_registry_or_new_namespace_bypass(tmp_path,change):
    b,parent,state=legacy(tmp_path)
    with AdmissionRegistry(b,create=True):pass
    reg=Path(b['paths']['admission_root']);ret=state/'entry-retired-no-retry.json'
    if change=='restored_grant':(state/'owner-approval.json').write_text('{}')
    elif change=='missing_retirement':ret.unlink()
    elif change=='drift_retirement':ret.write_text('{}')
    elif change=='missing_saved_approval':(state/'owner-approval.retired-no-retry.json').unlink()
    elif change=='drift_saved_approval':(state/'owner-approval.retired-no-retry.json').write_text('{}')
    elif change=='alias_retirement':
        copy=tmp_path/'saved';ret.rename(copy);ret.symlink_to(copy)
    elif change=='hardlink_retirement':os.link(ret,tmp_path/'alias')
    elif change=='public_directory':state.chmod(0o755)
    elif change=='public_record':ret.chmod(0o644)
    elif change=='tombstone':(reg/'host.consumed.json').write_text('{}')
    elif change=='extra':(reg/'other.json').write_text('{}')
    elif change=='alias_database':
        p=reg/'admission.sqlite';copy=tmp_path/'database';p.rename(copy);p.symlink_to(copy)
    elif change=='hardlink_database':os.link(reg/'admission.sqlite',tmp_path/'database')
    else:
        db=sqlite3.connect(reg/'admission.sqlite')
        try:
            if change=='nonempty_registry':db.execute('INSERT INTO admission VALUES (?,?,?,?)',('old','host','a'*64,'b'*64))
            else:db.execute('CREATE TABLE foreign_table(x)')
            db.commit()
        finally:db.close()
    with pytest.raises((ValueError,OSError)):preparation_scope(parent)
    assert not (parent/'reuse-dev-20261012-b-source').exists() and not (parent/'reuse-dev-20261012-b-state').exists()


def test_old_exact_approval_and_retired_study_are_not_candidate_b_authority():
    s=json.loads((ROOT/'eval/c5/reuse-development-spec-20261011-a.json').read_bytes())
    r=json.loads((ROOT/'eval/c5/reuse-development-runtime-freeze-20261011-a.json').read_bytes())
    a=json.loads((ROOT/'eval/c5/reuse-development-owner-exact-approval-20261012.json').read_bytes())['approval']
    with pytest.raises(ValueError,match='new_development_identity'):bind(s,r,a,now=1791760000,endpoint='mac')
