"""Synthetic owner-entry ordering and private-I/O negative controls only."""
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_channel import publish_json
from training.c5_startup_transport import startup_receipt


def test_non_owner_terminal_fails_before_scope_or_any_field(monkeypatch):
    from tools import c5_formal20_owner_run_v2 as entry
    monkeypatch.setattr(entry.sys,'stdin',SimpleNamespace(isatty=lambda:False))
    monkeypatch.setattr(entry,'scope',lambda:(_ for _ in ()).throw(AssertionError('no scope/field call')))
    with pytest.raises(NativeError):entry.run_interactive()


def test_native_zero_ready_decode_and_guard_still_inside_deadline(tmp_path,monkeypatch):
    from training import c5_formal20_adapters_v2 as adapters
    from plugin.rhino_listener.c5_formal20_policy_v2 import STUDY_ID
    elapsed=[0.0]
    freeze={}
    publish_json(tmp_path,'host-continuity-ready.json',{'study_id':STUDY_ID,
        'runtime_freeze_sha256':digest(freeze),'legacy_byte_closure_verified':False,
        'sealed_before_model_generation':True})
    monkeypatch.setattr(adapters.time,'monotonic',lambda:elapsed[0])
    adapter=adapters.NativeAdapterV2(tmp_path,{'hub_attach_timeout_seconds':180},freeze,
        guard=lambda:elapsed.__setitem__(0,elapsed[0]+100))
    with pytest.raises(NativeError):adapter.wait_zero_ready()


def test_failed_private_initialization_detected_without_waiting(tmp_path,monkeypatch):
    from training import c5_formal20_adapters_v2 as adapters
    publish_json(tmp_path,'formal20.hub-initialization.failed.json',{'synthetic':True})
    adapter=adapters.NativeAdapterV2(tmp_path,{'hub_attach_timeout_seconds':180},{},
        guard=lambda:pytest.fail('failure must precede guard/wait'))
    with pytest.raises(NativeError):adapter.start()


@pytest.mark.parametrize('model_already_settled',(False,True))
def test_readiness_precedes_path_prompts_and_permanent_claim_precedes_private_loader(tmp_path,monkeypatch,model_already_settled):
    from tools import c5_formal20_owner_run_v2 as entry
    from plugin.rhino_listener.c5_formal20_policy_v2 import STUDY_ID
    events=[]
    spec={'study_id':STUDY_ID,'public_commitment_sha256':'a'*64,'latest_owner_start_epoch':9999999999}
    freeze={'source_inventory_sha256':'b'*64,'environment_sha256':'c'*64,
        'model_identities':{'base':'d'*64,'lora':'e'*64},'resource_boundary':{},
        'repository_root_for_private_boundary':'/synthetic-repository'}
    monkeypatch.setattr(entry,'MAC_STATE',tmp_path)
    monkeypatch.setattr(entry.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr(entry.sys,'stderr',SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr(entry,'scope',lambda:(spec,freeze,{},lambda:None))
    monkeypatch.setattr(entry,'commitment',lambda _: {})
    class Budget:
        def __init__(self,_):pass
        def check(self):pass
        def settle(self,*a):events.append('settled')
    class Native:
        def __init__(self,*a,**k):pass
        def arm(self):events.append('arm')
        def wait_zero_ready(self):
            events.append('host-ready')
            publish_json(tmp_path,'host-continuity-ready.json',{'synthetic':True})
            publish_json(tmp_path,'formal20.hub-started.claim.json',{'synthetic':True})
    class Model:
        process=object() if model_already_settled else None
        bootstrapped=not model_already_settled
        def __init__(self,*a,**k):pass
        def stop_zero(self):pytest.fail('settled known process must not be stopped/published a second time')
        def start_zero(self):
            events.append('model-ready')
            publish_json(tmp_path,'worker-startup-ready.json',startup_receipt(STUDY_ID,digest(freeze),'b'*64,
                'c'*64,freeze['model_identities']))
    class Runner:
        def __init__(self,**k):pass
        def run(self,loader):
            events.append('formal-started');publish_json(tmp_path,'formal20.started.json',{'synthetic':True})
            loader()
            if model_already_settled:
                publish_json(tmp_path,'worker-process-exit.json',{'exit_code':0,'replay_allowed':False})
            return {'study_id':STUDY_ID,'status':'synthetic','slots_attempted':40,
                'route_slots_required':40,'error_type':None,'c5_6_gate_claim':False}
    def prompt(_):
        assert events[:3]==['arm','host-ready','model-ready']
        assert not (tmp_path/'formal20.started.json').exists()
        events.append('private-path-prompt');return '/synthetic-private-path'
    def loader(*a,**k):
        def load():
            assert (tmp_path/'formal20.started.json').exists();events.append('private-loader');return []
        return load
    monkeypatch.setattr(entry,'FormalBudgetV2',Budget);monkeypatch.setattr(entry,'NativeAdapterV2',Native)
    monkeypatch.setattr(entry,'ModelAdapterV2',Model);monkeypatch.setattr(entry,'FormalRunner',Runner)
    monkeypatch.setattr(entry.getpass,'getpass',prompt);monkeypatch.setattr(entry,'sealed_loader',loader)
    monkeypatch.setattr(entry,'verify_private_metadata',lambda *a:events.append('metadata-only'))
    assert entry.run_interactive()['slots_attempted']==40
    assert events==['arm','host-ready','model-ready','private-path-prompt','private-path-prompt',
        'metadata-only','formal-started','private-loader','settled']


def test_frozen_source_without_git_uses_explicit_worktree_boundary_root(tmp_path,monkeypatch):
    from tools.c5_rhino_formal20_owner_exclusion import _worktrees
    import tools.c5_rhino_formal20_owner_exclusion as exclusion
    root=tmp_path/'synthetic-repo';root.mkdir()
    invoked=[]
    def git(args,**kwargs):
        invoked.append(kwargs['cwd']);return ('worktree '+str(root)+'\n\n').encode()
    monkeypatch.setattr(exclusion.subprocess,'check_output',git)
    assert _worktrees(repository_root=root)==[root.resolve()] and invoked==[root]


def test_late_owner_start_fails_before_claim_or_any_private_path(tmp_path,monkeypatch):
    from tools import c5_formal20_owner_run_v2 as entry
    monkeypatch.setattr(entry.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr(entry.sys,'stderr',SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr(entry,'MAC_STATE',tmp_path)
    monkeypatch.setattr(entry,'scope',lambda:({'latest_owner_start_epoch':0},{},{},lambda:None))
    monkeypatch.setattr(entry,'commitment',lambda _:(_ for _ in ()).throw(AssertionError('no later operation')))
    with pytest.raises(NativeError):entry.run_interactive()
    assert not list(tmp_path.iterdir())


def test_arm_does_not_open_private_plans_without_global_owner_consumption(tmp_path,monkeypatch):
    from plugin.rhino_listener import c5_formal20_hub_v2 as module
    monkeypatch.setattr(module,'active_content_digest',lambda _: 'a'*64)
    import sys
    monkeypatch.setitem(sys.modules,'Rhino',SimpleNamespace(RhinoApp=SimpleNamespace(InCommand=False)))
    arm=module.FormalArm(tmp_path,{}, {}, {},lambda:'a'*64,SimpleNamespace(RuntimeSerialNumber=1),None)
    opened=[];original=module.read_json
    def watch(directory,name):
        opened.append(name)
        if name=='native-plans.json':raise AssertionError('no private plans before owner started')
        return original(directory,name)
    monkeypatch.setattr(module,'read_json',watch)
    arm.tick();assert not opened
    publish_json(tmp_path,'native-prepared.json',{'synthetic':True})
    with pytest.raises(FileNotFoundError):arm.tick()
    assert arm.blocked and opened==['formal20.started.json']
