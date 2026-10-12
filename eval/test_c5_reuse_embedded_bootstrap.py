"""Real run_path bootstrap in isolated CPU interpreters; no host/model calls.

The parent supplies synthetic authority and snapshot only. Child processes
have no project on sys.path and cannot import top-level plugin/training. The
actual wrapper, loader, admission, hub, host session and return barrier run;
only authority acquisition, Rhino types and CLR observation are CPU fakes.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from eval.test_c5_reuse_field_preparation import records
from eval.test_c5_host_assurance_v2 import data
from plugin.rhino_listener.c5_reuse_field_scope import bind,sha,canonical
from plugin.rhino_listener.c5_reuse_public_plan import public_plan,SOURCE
from training.c5_reuse_admission import AdmissionRegistry

ROOT=Path(__file__).resolve().parents[1]
DRIVER=r'''
import builtins,copy,importlib,json,os,runpy,sys,types
from pathlib import Path
f=json.loads(Path(sys.argv[1]).read_bytes());root=Path(f['root']);state=Path(f['binding']['paths']['state_root'])
mode=sys.argv[2];effects=[];paths=list(sys.path);original_main=sys.modules['__main__']
assert not any(p==str(root) for p in sys.path) and 'plugin' not in sys.modules
original_import=builtins.__import__
def checked_import(name,*args,**kwargs):
    if name.split('.')[0] in ('plugin','training','torch','transformers','peft','agent'):
        raise AssertionError('forbidden ambient/project/model import: '+name)
    if name=='Rhino':
        assert scope[0] and all(scope[0]+'.plugin.rhino_listener.'+n in sys.modules for n in (
            'c5_reuse_admission','c5_reuse_host_session','c5_reuse_native_hub','c5_host_observer_clr','c5_deferred_baseline'))
        effects.append('Rhino_import');sys.platform='darwin';sys.version_info=(3,9,10,'final',0)
    return original_import(name,*args,**kwargs)
builtins.__import__=checked_import
class Event:
    def __init__(self):self.handlers=[]
    def __iadd__(self,callback):self.handlers.append(callback);effects.append('idle_attached');return self
    def __isub__(self,callback):self.handlers.remove(callback);return self
    def fire(self):
        for callback in tuple(self.handlers):callback(None,None)
event=Event();active=types.SimpleNamespace(RuntimeSerialNumber=1)
def create(_):effects.append('fixture_created');return types.SimpleNamespace(RuntimeSerialNumber=90)
geometry=types.SimpleNamespace(**{n:object for n in ('Box','Interval','Plane','Point3d','Vector3d','Transform',
    'Brep','VolumeMassProperties','Circle','Cylinder','Sphere')})
rhino=types.ModuleType('Rhino');rhino.RhinoApp=types.SimpleNamespace(IsOnMainThread=True,InCommand=False,
    Version='8.21.25188.17002',Idle=event)
rhino.RhinoDoc=types.SimpleNamespace(ActiveDoc=active,CreateHeadless=create)
rhino.UnitSystem=types.SimpleNamespace(Millimeters='mm');rhino.Geometry=geometry
rhino.DocObjects=types.SimpleNamespace(ObjectAttributes=object,ObjectColorSource=object)
sys.modules['Rhino']=rhino
system=types.ModuleType('System');system.Drawing=types.SimpleNamespace(Color=object);system.Guid=object
sys.modules['System']=system
class Native:
    def __init__(self,doc,active,schemas):self.doc=doc;self.closed=False
    def readback(self):return {'objects':[],'groups':{}}
    def close(self):self.closed=True;effects.append('fixture_closed');return {'fixture_registry_absent':True}
class Backend:
    def __init__(self,*args):self.active=False;effects.append('backend_constructed')
    def subscribe(self):self.active=True;effects.append('host_subscribed')
    def unsubscribe(self):self.active=False;effects.append('host_unsubscribed')
    def snapshot(self):return copy.deepcopy(f['snapshot'])
    def drain_events(self):return {'events':[],'errors':[],'dropped':0}
original_module=importlib.import_module
scope=[None];guard=[None]
def loaded(name,*args,**kwargs):
    if mode=='dependency_failure' and name.endswith('.c5_reuse_host_session'):
        raise ImportError('injected inert dependency failure')
    m=original_module(name,*args,**kwargs)
    if name.endswith('.c5_reuse_mac_scope'):
        prefix=name.split('.')[0];scope[0]=prefix
        runtime_scope=original_module(prefix+'.plugin.rhino_listener.c5_reuse_runtime_scope')
        guard[0]=runtime_scope.ReuseSourceGuard(root,f['runtime']['source_files'],private_prefixes=(prefix,))
        def mac_scope(*args,**kwargs):
            effects.append('synthetic_grant_checked');guard[0]()
            if mode=='grant_failure':raise ValueError('injected unapproved scope')
            return f['spec'],f['runtime'],f['binding'],{},lambda **kw:guard[0]()
        m.mac_scope=mac_scope
    elif name.endswith('.c5_research_native'):
        m.NativeDoc=Native;m._all_objects=lambda doc:[];m.active_content_digest=lambda doc:'b'*64
    elif name.endswith('.c5_host_observer_clr'):m.ClrObserverBackend=Backend
    return m
importlib.import_module=loaded
before=set(os.listdir(state))
try:
    runpy.run_path(str(root/'tools/run_c5_reuse_rhino_wrapper.py'),run_name='__main__')
except (ImportError,ValueError,AssertionError) as exc:
    assert mode in ('dependency_failure','grant_failure','old_admission','old_host_session'),(type(exc).__name__,str(exc))
    expected=('injected inert dependency failure' if mode=='dependency_failure' else 'injected unapproved scope')
    if mode.startswith('old_'):assert str(exc).startswith('forbidden ambient/project/model import: plugin.')
    else:assert str(exc)==expected
    assert set(os.listdir(state))==before
    assert not any(n==scope[0] or n.startswith(scope[0]+'.') for n in sys.modules)
    assert not any(e in effects for e in ('Rhino_import','fixture_created','backend_constructed','idle_attached','host_subscribed'))
    assert not event.handlers
    print(json.dumps({'case':mode,'dependency_or_grant_failure_before_any_fake_host_effect':True,
        'provisional_namespace_removed':True,'actual_host_or_model_calls':0}));sys.exit(0)
assert mode in ('baseline','baseline_failure','queued_request')
assert sys.modules['__main__'] is original_main and list(sys.path)==paths
assert 'plugin' not in sys.modules and 'training' not in sys.modules
package=sys.modules[scope[0]];barrier=package._ENTRY_RETURN_BARRIER;hub=package._SESSION
assert barrier.state=='await_first_idle' and hub.preparing
assert effects.index('fixture_closed')<effects.index('idle_attached')
assert 'host_subscribed' not in effects and not (state/'host-continuity-ready.json').exists()
release=json.loads((state/'entry-return-release.json').read_bytes())
assert release['baseline_sealed'] is False and release['replay_allowed'] is False
assert len(event.handlers)==1
rhino.RhinoApp.InCommand=True;event.fire();assert barrier.state=='await_first_idle'
rhino.RhinoApp.InCommand=False
if mode=='baseline_failure':
    def broken():raise RuntimeError('CPU failed baseline')
    hub.assurance.backend.snapshot=broken
if mode=='queued_request':
    (state/'hub-request-0001.json').write_text('{}');(state/'hub-request-0001.json').chmod(0o600)
    def forbidden_tick(*args):
        effects.append('forbidden_dispatch');raise AssertionError('queued request dispatched during baseline callback')
    # The barrier owns the originally supplied bound method. Mutate its code
    # path, not the barrier, so a first-callback dispatch would fail.
    hub.handle=forbidden_tick
    hub.guard=forbidden_tick
event.fire()
if mode=='baseline_failure':
    assert barrier.state=='failed' and hub.blocked
    assert (state/'deferred-baseline.failed.json').exists() and not (state/'host-continuity-ready.json').exists()
    count=len(effects);event.fire();assert len(effects)==count and barrier.state=='failed'
else:
    assert barrier.state=='ready' and not hub.preparing and hub.seq==1 and not hub.blocked
    assert 'forbidden_dispatch' not in effects
    ready=json.loads((state/'host-continuity-ready.json').read_bytes())
    assert ready['host_baseline_head_sha256']==hub.assurance.head and ready['generation_stages']==0
    assert effects.count('host_subscribed')==1
    if mode=='baseline':event.fire();assert hub.seq==1 and effects.count('host_subscribed')==1
try:barrier.release_after_entry_return()
except Exception:pass
else:raise AssertionError('second entry return accepted')
package._REGISTRY.close()
assert sys.modules['__main__'] is original_main and list(sys.path)==paths
print(json.dumps({'case':mode,'complete_namespace_bootstrap_passed':True,'explicit_return_before_baseline':True,
    'first_idle_did_not_dispatch':True,'top_level_project_imports':False,'actual_host_or_model_calls':0}))
'''


def fixture(tmp_path,mode=None):
    spec,runtime,approval,_=records(tmp_path)
    root=Path(runtime['endpoints']['mac']['source_root']);root.mkdir(parents=True,mode=0o700)
    for p in (ROOT/'plugin').rglob('*.py'):
        target=root/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);target.chmod(0o600)
    for name in ('tools/run_c5_reuse_rhino_wrapper.py','tools/run_c5_reuse_rhino_entry.py',SOURCE,
                 'eval/c5/rhino-runtime-schema-v1.json'):
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);target.chmod(0o600)
    if mode in ('old_admission','old_host_session'):
        name='c5_reuse_admission.py' if mode=='old_admission' else 'c5_reuse_host_session.py'
        p=root/'plugin/rhino_listener'/name
        # Reintroduce the observed defect only in the synthetic CPU copy.
        p.write_text(p.read_text().replace('from .','from plugin.rhino_listener.'))
    runtime['source_files']={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*') if p.is_file()}
    spec['development_plan_sha256']=public_plan(ROOT)['development_plan_sha256']
    runtime['spec_sha256']=approval['spec_sha256']=sha(spec);approval['runtime_sha256']=sha(runtime)
    binding=bind(spec,runtime,approval,now=100,endpoint='mac')
    state=Path(binding['paths']['state_root']);state.mkdir(mode=0o700)
    with AdmissionRegistry(binding,create=True):pass
    prepared={'study_id':binding['study_id'],'spec_sha256':binding['spec_sha256'],
              'runtime_sha256':binding['runtime_sha256'],'model_calls':0,'private_formal_reads':0}
    for name,value in [('prepared.json',prepared),('hub.key',{'key_hex':'11'*32})]:
        p=state/name;p.write_bytes(canonical(value)+b'\n');p.chmod(0o600)
    f={'root':str(root),'spec':spec,'runtime':runtime,'binding':binding,'snapshot':data()[0]}
    p=tmp_path/'cpu-synthetic-input.json';p.write_text(json.dumps(f));driver=tmp_path/'cpu-driver.py';driver.write_text(DRIVER)
    return p,driver


@pytest.mark.parametrize('mode',['baseline','queued_request','dependency_failure','grant_failure','baseline_failure','old_admission','old_host_session'])
def test_actual_run_path_wrapper_without_top_level_plugin_in_isolated_cpu(tmp_path,mode):
    config,driver=fixture(tmp_path,mode)
    result=subprocess.run([sys.executable,'-I','-S','-B',str(driver),str(config),mode],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    result=json.loads(result.stdout.splitlines()[-1]);assert result['actual_host_or_model_calls']==0


@pytest.mark.skipif(sys.platform!='darwin',reason='macOS system Python 3.9 compatibility check')
def test_same_complete_bootstrap_on_python39(tmp_path):
    config,driver=fixture(tmp_path)
    result=subprocess.run(['/usr/bin/python3','-I','-S','-B',str(driver),str(config),'baseline'],
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['complete_namespace_bootstrap_passed']
