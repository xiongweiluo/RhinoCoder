"""Actual worker control loop on CPU with injected public-only model/authority.

No real grant, SSH, GPU, private families or inference is accessed.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace
import pytest
from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_formal_reuse_scope import expected_grant,STUDY_ID
from eval.test_c5_formal_reuse_preparation import boundary
from training.c5_formal_reuse_model_wire import frame
import tools.run_c5_formal_reuse_worker as worker

@pytest.mark.parametrize('mutation',['actor','approved','runtime'])
def test_attempt_export_cannot_snapshot_wrong_parent_authority(tmp_path,monkeypatch,mutation):
    parent=tmp_path/'parent';parent.mkdir(mode=0o700);leaf=parent/'preload-1';leaf.mkdir(mode=0o700)
    spec,freeze={'synthetic':True},{'synthetic':True};grant=expected_grant(spec,freeze)
    grant['actor' if mutation=='actor' else 'approved' if mutation=='approved' else 'runtime_freeze_sha256']=\
        'not-owner' if mutation=='actor' else False if mutation=='approved' else '0'*64
    publish_json(parent,'owner-approval.json',grant);monkeypatch.setattr(worker,'REMOTE_STATE',parent)
    with pytest.raises(NativeError):worker.capture_parent_grant(leaf,spec,freeze,lambda:None)
    assert not (leaf/'owner-approval.json').exists()

def test_worker_bootstrap_stop_exports_original_parent_grant_from_its_own_attempt_leaf(tmp_path,monkeypatch):
    import training.c5_formal_reuse_admission as admission
    import training.c5_followup_gpu_loader as loader
    parent=tmp_path/'parent';parent.mkdir(mode=0o700);state=parent/'preload-1';state.mkdir(mode=0o700)
    spec={'study_id':STUDY_ID,'public_commitment_sha256':'c'*64,'max_model_requests':56,'max_generation_stages':112}
    freeze={'resource_boundary':boundary(),'source_inventory_sha256':'a'*64,'environment_sha256':'b'*64,
        'model_identities':{'base':'d'*64,'lora':'e'*64},'field_plan':{}}
    freeze_sha=digest(freeze);grant=expected_grant(spec,freeze)
    publish_json(parent,'owner-approval.json',grant)
    first=time.time()-1;publish_json(state,'load-permit.json',{'first_load_epoch':first})
    plans={'F%02d-%s'%(n,r):{'route':r,'task_sha256':'6'*64,'max_steps':1}
        for n in range(1,21) for r in ('base','lora')}
    bootstrap={'kind':'formal_bootstrap','study_id':STUDY_ID,'runtime_freeze_sha256':freeze_sha,
        'started':{'study_id':STUDY_ID,'spec_sha256':digest(spec),'runtime_freeze_sha256':freeze_sha,
            'public_commitment_sha256':spec['public_commitment_sha256'],'replay_allowed':False},'plans':plans}
    stop={'kind':'formal_stop','study_id':STUDY_ID,'runtime_freeze_sha256':freeze_sha}
    incoming=io.TextIOWrapper(io.BytesIO(frame(bootstrap)+frame(stop)))
    outgoing=io.TextIOWrapper(io.BytesIO());monkeypatch.setattr(sys,'stdin',incoming);monkeypatch.setattr(sys,'stdout',outgoing)
    monkeypatch.setattr(worker,'REMOTE_STATE',parent)
    monkeypatch.setattr(admission,'attempt_state',lambda endpoint,attempt:state)
    assets={'environment_sha256':freeze['environment_sha256'],'synthetic_cpu':True}
    monkeypatch.setattr(worker,'approved_scope',lambda:(spec,freeze,freeze_sha,lambda:None,assets,{},tmp_path))
    def fake_load(*a,**k):
        assert read_json(state,'owner-approval.json')==grant  # before any model construction
        return object(),lambda *a:pytest.fail('CPU control smoke must never generate'),lambda r:contextlib.nullcontext(),lambda:None
    monkeypatch.setattr(loader,'load',fake_load)
    fake_cuda=SimpleNamespace(get_device_name=lambda _: 'synthetic-no-GPU',max_memory_allocated=lambda:0,max_memory_reserved=lambda:0)
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(version=SimpleNamespace(cuda='synthetic'),cuda=fake_cuda))
    for name in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE'):monkeypatch.setenv(name,os.environ.get(name,''))
    old_handler=signal.getsignal(signal.SIGALRM);old_umask=os.umask(0o077);rfd,wfd=os.pipe()
    try:
        worker.serve_child(wfd,1)
        replies=[json.loads(line) for line in outgoing.buffer.getvalue().splitlines()]
        final=replies[-1]
        assert len(replies)==3 and final['status']=='formal_worker_stopped'
        assert final['raw_records']['owner-approval.json']==grant==read_json(parent,'owner-approval.json')
        assert 'owner-approval.json' in final['file_sha256']
        assert final['raw_records']['worker-summary.json']['requests']==0
        assert final['raw_records']['worker-summary.json']['generation_stages']==0
        assert final['resource']['start_epoch']==first and final['resource']['cap_seconds']==64800
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
        os.umask(old_umask);os.close(rfd);os.close(wfd)


def test_post_ready_authority_uses_original_budget_instead_of_requiring_a_second_full_window():
    import time,copy
    from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE,expected_grant,validate_materials
    from tools.prepare_c5_formal_reuse_freeze import assemble
    from training.c5_formal_reuse_runner import validate_authority
    from training.c5_formal_reuse_budget import FormalBudgetV2
    docs={n:json.loads((worker.ROOT/n).read_bytes()) for n in (SPEC_FILE,FREEZE_FILE)}
    spec=copy.deepcopy(docs[SPEC_FILE]);freeze=copy.deepcopy(docs[FREEZE_FILE])
    # This is a pure public-material fixture. It neither writes a grant nor
    # accesses private families, and it never enters the field runner.
    now=time.time();first=now-64700;cutoff=first+64800
    spec.update(model_generation_cutoff_epoch=cutoff,lease_expiry_epoch=cutoff+900,latest_owner_start_epoch=first)
    freeze['resource_boundary'].update(generation_cutoff_epoch=cutoff,provider_expiry_epoch=cutoff+900)
    freeze['spec_sha256']=digest(spec);grant=expected_grant(spec,freeze)
    clock=[now,100000.]
    budget=FormalBudgetV2(freeze['resource_boundary'],wall=lambda:clock[0],mono=lambda:clock[1],
        start={'wall':first,'mono':clock[1]-(now-first)})
    assert 0<budget.check()<=40.01
    with pytest.raises(NativeError):validate_materials(spec,freeze,check_time=True)
    assert validate_authority(spec,freeze,grant)==digest(freeze)
    clock[0]+=41;clock[1]+=41
    with pytest.raises(NativeError):budget.check()
