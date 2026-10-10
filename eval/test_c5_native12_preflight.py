"""Native12 fixed-scope controls only; no admission, engine, GPU or Rhino."""
import ast
import hashlib
import json
import math
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_research_native import CORE,NativeError,digest,validate_native_arguments
from tools import c5_native12_common as common


def test_development_spec_has_all_original_tools_and_zero_model_scope():
    spec=common.read_public(common.SPEC_PATH)
    schemas=common.read_public(common.ROOT/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    assert len(spec['steps'])==12 and {s['name'] for s in spec['steps']}==CORE
    assert spec['model_calls']==spec['gpu_calls']==spec['formal_holdout_calls']==0
    assert spec['signed_write_requests_max']==10 and spec['signed_read_requests_max']==2
    for step in spec['steps']: validate_native_arguments(step['name'],step['arguments'],schemas)
    # Independent analytic cylinder-minus-sphere volume: z=4..5 ring, 5..7 full disk.
    volume=math.pi*((5**3/3-16*5)-(4**3/3-16*4)+9*(7-5))
    assert math.isclose(volume,spec['independent_assertions']['difference_final']['volume_pi_multiple']*math.pi,rel_tol=1e-12)


def setup_scope(monkeypatch):
    spec=common.read_public(common.SPEC_PATH)
    schemas=common.read_public(common.ROOT/'eval/c5/rhino-runtime-schema-v1.json')
    files={'frozen.py':'a'*64}
    freeze={'probe_id':common.ID,'spec_sha256':digest(spec),'source_files':files,
            'source_inventory_sha256':digest(files),'complete_native_probe_runtime':True}
    approval={'probe_id':common.ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
              'runtime_freeze_sha256':digest(freeze),'approval_basis':common.APPROVAL_BASIS}
    monkeypatch.setattr(common,'read_public',lambda p:spec if p==common.SPEC_PATH else freeze if p==common.FREEZE_PATH else schemas)
    monkeypatch.setattr(common,'read_json',lambda *args:approval)
    return spec,freeze,approval


@pytest.mark.parametrize('change',['actor','basis','spec','freeze','approval','probe','complete'])
def test_no_agent_wrong_grant_or_incomplete_freeze_unblocks_native_probe(monkeypatch,change):
    spec,freeze,approval=setup_scope(monkeypatch)
    if change=='actor': approval['actor']='agent'
    if change=='basis': approval['approval_basis']='assumed from R B'
    if change=='spec': approval['spec_sha256']='b'*64
    if change=='freeze': approval['runtime_freeze_sha256']='b'*64
    if change=='approval': approval['approved']=False
    if change=='probe': approval['probe_id']='RSDEV-TWO-WRITE-20261002-B'
    if change=='complete': freeze['complete_native_probe_runtime']=False
    with pytest.raises(NativeError): common.fixed_scope()


def test_exact_owner_scope_only_satisfies_preflight_not_execution(monkeypatch):
    spec,freeze,approval=setup_scope(monkeypatch)
    value=common.fixed_scope()
    assert value[0]==spec and value[-1]==approval


def test_batch_python39_has_no_training_model_default_listener_or_dynamic_outputs():
    source=(common.ROOT/'tools/c5_rhino_native12_batch.py').read_text()
    ast.parse(source,feature_version=(3,9))
    imports=[n.module or '' for n in ast.walk(ast.parse(source)) if isinstance(n,ast.ImportFrom)]
    assert not any(n.startswith('training') for n in imports)
    assert 'from_pretrained' not in source and 'run_c5_final_remote' not in source
    assert "channel.publish_json(STATE,ID+'.engine-started.json'" in source
    assert source.index("ID+'.engine-started.json'") < source.index('Rhino.RhinoDoc.CreateHeadless')
