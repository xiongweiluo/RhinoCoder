"""Disabled complete material/population controls; no actual grant/deployment."""
import copy
import json
from pathlib import Path
import shutil

import pytest

from training.c5_reuse_freeze_materials import build,write_review,ENTRIES
from tools.check_c5_reuse_field_freeze import check
from training.c5_reuse_evidence import sha
from plugin.rhino_listener.c5_reuse_runtime_scope import SPEC,PLAN,RUNTIME
from plugin.rhino_listener.c5_reuse_field_scope import bind

ROOT=Path(__file__).resolve().parents[1]


def bundle(tmp_path):
    s,r,p,files,packet=build(ROOT,environment={'mac':{},'gpu':{}},model_assets={},host_files={},
        host_acceptance={'instance_id':'reuse-dev-20261011-a'},gpu_process={},transport={})
    destination=tmp_path/'review';write_review(destination,files,packet)
    return s,r,p,files,packet,destination


def test_complete_disabled_material_byte_check_does_not_fabricate_resource_fact(tmp_path):
    s,r,p,files,packet,destination=bundle(tmp_path)
    result=check(destination,sha(s),sha(r),review=True)
    assert result['source_population_exact'] and result['complete_closure_binding_verified']
    assert not result['candidate_execution_ready'] and not result['execution_ready']
    assert s['resources']['prior_cumulative_upper_bound_seconds'] is None
    assert s['execution_ready'] is r['execution_ready'] is packet['execution_ready'] is False
    assert set(ENTRIES)<=set(r['source_files']) and SPEC in files and PLAN in files
    assert len(r['source_files'])>280
    assert not any('owner-approval' in n or n.endswith('.key') for n in files)
    with pytest.raises(ValueError,match='development_freeze_not_ready'):bind(s,r,{},now=100,endpoint='mac')


@pytest.mark.parametrize('change',['missing','byte_drift','extra','symlink','fifo','group_write','hardlink','wrong_hash','plan'])
def test_every_source_byte_population_and_plan_are_independently_checked(tmp_path,change):
    s,r,p,files,packet,root=bundle(tmp_path);target=root/ENTRIES[0]
    if change=='missing':target.unlink()
    elif change=='byte_drift':target.write_text('raise RuntimeError()\n')
    elif change=='extra':(root/'extra.txt').write_text('extra')
    elif change=='symlink':target.unlink();target.symlink_to(ROOT/ENTRIES[0])
    elif change=='fifo':
        import os
        target.unlink();os.mkfifo(target,0o600)
    elif change=='group_write':target.chmod(0o620)
    elif change=='hardlink':
        import os
        os.link(target,tmp_path/'hardlink')
    elif change=='plan':(root/PLAN).write_text('{}')
    with pytest.raises((ValueError,OSError)):
        check(root,sha(s),'0'*64 if change=='wrong_hash' else sha(r),review=True)


@pytest.mark.parametrize('prior,basis',[(True,'reported'),(-1,'reported'),(36001,'reported'),(0,None),(0,''),(0,'x'*2049)])
def test_unusable_historical_count_is_never_a_new_balance_or_zero_default(prior,basis):
    with pytest.raises(ValueError):build(ROOT,environment={},model_assets={},host_files={},
        host_acceptance={},gpu_process={},transport={},prior_upper=prior,prior_basis=basis)


def test_retired_identity_cannot_qualify_new_rhino_hub(tmp_path):
    from plugin.rhino_listener.c5_reuse_native_hub import ReuseNativeHub
    from eval.test_c5_reuse_field_preparation import binding
    b=binding(tmp_path,endpoint='mac');old=copy.deepcopy(b);old['study_id']='C5DEV-HOSTASSURANCE-20261007-D'
    with pytest.raises(ValueError):ReuseNativeHub(old,{},None,{},None,lambda:None,None)


def test_cleanup_guard_can_follow_cutoff_without_restoring_dispatch(tmp_path):
    from eval.test_c5_reuse_field_preparation import binding
    from eval.test_c5_host_assurance_session import Backend
    from plugin.rhino_listener.c5_reuse_host_session import ReuseHostSession
    from training.c5_reuse_admission import AdmissionRegistry
    b=binding(tmp_path,endpoint='mac');Path(b['paths']['state_root']).mkdir(mode=0o700)
    late=[False];checks=[]
    def normal():
        checks.append('normal')
        if late[0]:raise ValueError('CPU cutoff')
        return 'f'*64
    def cleanup():checks.append('cleanup');return 'f'*64
    with AdmissionRegistry(b,create=True) as registry:
        session=ReuseHostSession(b,registry,Backend(),normal,'f'*64,cleanup_source=cleanup)
        session.seal_baseline();late[0]=True
        with pytest.raises(ValueError):session.checkpoint('expired')
        session.cleanup_checkpoint('close_only')
        receipt=session.finish()
        assert checks[-1]=='cleanup' and receipt['blocked'] and not receipt['execution_authority']
