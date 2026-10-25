"""Grant-free material/host-denial boundaries; synthetic CPU fixtures only."""
import copy
from pathlib import Path
import subprocess
import sys

import pytest

from eval.test_c5_reuse_field_preparation import records
from plugin.rhino_listener.c5_reuse_field_scope import check_candidate_materials,sha
from plugin.rhino_listener import c5_reuse_mac_scope as scope


def test_material_preflight_needs_no_owner_grant_and_confers_no_authority(tmp_path):
    spec,runtime,unused_owner_fixture,_=records(tmp_path)
    result=check_candidate_materials(spec,runtime,now=100,endpoint='mac')
    assert result=={'spec_sha256':sha(spec),'runtime_sha256':sha(runtime),
        'candidate_materials_bound':True,'execution_authority':False,'owner_grant_used':False}
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('instance',['reuse-dev-20261011-a','reuse-dev-20261012-b'])
def test_retired_instance_is_denied_even_after_relabeling_study_and_hashes(tmp_path,instance):
    spec,runtime,_,_=records(tmp_path)
    spec['instance_id']=runtime['instance_id']=instance
    spec['host_policy']['instance_id']=instance
    runtime['host_policy']=copy.deepcopy(spec['host_policy']);runtime['spec_sha256']=sha(spec)
    with pytest.raises(ValueError,match='new_development_identity'):
        check_candidate_materials(spec,runtime,now=100,endpoint='mac')
    assert not list(tmp_path.iterdir())


def test_actual_host_identity_denial_stops_shared_readable_check_before_any_source_or_asset_action(tmp_path,monkeypatch):
    # The production entry and grant-free tool share readable_scope. A denied
    # syscall must propagate before its source callback/readable-byte loop.
    executable='/opt/anaconda3/bin/python3.13';calls=[]
    monkeypatch.setattr(sys,'prefix','/opt/anaconda3');monkeypatch.setattr(sys,'executable',executable)
    acceptance={'instance_id':'cpu','owner_confirms_blank_active_document':True,
        'owner_confirms_exclusive_use_and_no_other_operations_during_research':True,
        'owner_accepts_readable_files_frozen_opaque_host_trusted_visible_checkpoints_only':True,
        'process_observation':{}}
    plan={'environment':{'mac':{'python':sys.version,'file_sha256':{executable:'a'*64}}},
        'host_readable_files':{},'host_acceptance':acceptance}
    spec={'instance_id':'cpu','host_policy':{'acceptance_record_sha256':sha(acceptance)}}
    runtime={'environment_sha256':sha(plan['environment']),'host_readable_files_sha256':sha({})}
    def denied(*args,**kwargs):
        calls.append('host_identity')
        raise subprocess.CalledProcessError(1,['/usr/sbin/sysctl','-n','kern.bootsessionuuid'])
    def forbidden(*args,**kwargs):raise AssertionError('action after denied host identity')
    monkeypatch.setattr(scope,'verify_process_identity',denied);monkeypatch.setattr(scope,'code_sha',forbidden)
    with pytest.raises(subprocess.CalledProcessError):scope.readable_scope(tmp_path,spec,runtime,plan,forbidden)
    assert calls==['host_identity'] and not list(tmp_path.iterdir())
