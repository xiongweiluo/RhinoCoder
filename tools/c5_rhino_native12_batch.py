#! python 3
"""Explicit ScriptEditor native12 entry; requires frozen spec + NEW owner grant.

Not a product route, model, formal study or reusable B approval. Uses a fresh
private package; fixed-root engine claim precedes fixture creation. No retry.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/native12-development-state')
ID='C5DEV-NATIVE12-20261003-A'
OUTPUT=STATE/(ID+'-output')

# No cached/default Listener namespace is rebound or removed.
for name,loaded in tuple(sys.modules.items()):
    if (name.startswith(('rhino_research_','rhino_c5_')) or 'candidate_' in name) and getattr(loaded,'_SESSION',None) is not None:
        raise RuntimeError('another live research fixture exists; no reuse')
NAMESPACE='rhino_c5_'+uuid.uuid4().hex
loader=importlib.util.spec_from_file_location(NAMESPACE,ROOT/'plugin/rhino_listener/__init__.py',
                                            submodule_search_locations=[str(ROOT/'plugin/rhino_listener')])
package=importlib.util.module_from_spec(loader)
sys.modules[NAMESPACE]=package
loader.loader.exec_module(package)
native=importlib.import_module(NAMESPACE+'.c5_research_native')
channel=importlib.import_module(NAMESPACE+'.c5_research_channel')
provenance=importlib.import_module(NAMESPACE+'.c5_research_provenance')
atomic=importlib.import_module(NAMESPACE+'.candidate_atomic_gate')
gate_module=importlib.import_module(NAMESPACE+'.c5_research_gate')
sessions=importlib.import_module(NAMESPACE+'.c5_research_session')


def frozen_json(path):
    def pairs(items):
        result={}
        for k,v in items:
            native.require(k not in result,'duplicate frozen JSON key')
            result[k]=v
        return result
    native.require(path.resolve()==path and 0<path.stat().st_size<=1024*1024,'frozen path/size differs')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite frozen JSON')))


def start():
    import Rhino
    spec=frozen_json(ROOT/'eval/c5/native12-development-spec-20261003.json')
    freeze=frozen_json(ROOT/'eval/c5/native12-runtime-freeze-20261003.json')
    schemas=frozen_json(ROOT/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    approval=channel.read_json(STATE,'owner-approval.json')
    native.require(spec['probe_id']==ID and spec['fixed_state_root']==str(STATE) and freeze['probe_id']==ID
                   and freeze['spec_sha256']==native.digest(spec) and freeze['complete_native_probe_runtime'] is True
                   and spec['gpu_calls']==spec['model_calls']==spec['formal_holdout_calls']==0,
                   'fixed native-only scope differs')
    native.require(approval.get('approved') is True and approval=={'probe_id':ID,'actor':'repository_owner','approved':True,
                    'spec_sha256':native.digest(spec),'runtime_freeze_sha256':native.digest(freeze),
                    'approval_basis':'explicit repository_owner reply approving fixed C5 native twelve-tool development spec and source freeze'},
                   'new direct owner approval missing/differs')
    source=provenance.SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],project_prefixes=(NAMESPACE,))
    source()
    prepared=channel.read_json(OUTPUT,'prepared.json')
    native.require(prepared['runtime_freeze_sha256']==native.digest(freeze) and prepared['spec_sha256']==native.digest(spec), 'admission freeze differs')
    active=Rhino.RhinoDoc.ActiveDoc
    native.require(Rhino.RhinoApp.IsOnMainThread and active is not None,'usable UI document required')
    native.require(not native._all_objects(active),'a usable blank active document is required; never clear user geometry')
    # A permanent engine claim survives every crash, even before opening.
    channel.publish_json(STATE,ID+'.engine-started.json',{'probe_id':ID,'runtime_freeze_sha256':native.digest(freeze),'replay_allowed':False})
    package._SESSION={'state':'open_attempted_no_replay'}
    fixture=Rhino.RhinoDoc.CreateHeadless(None)
    native.require(fixture is not None,'headless creation failed; manual reconciliation')
    package._FIXTURE=fixture
    channel.publish_json(OUTPUT,'engine-created.json',{'fixture_serial':int(fixture.RuntimeSerialNumber),
                         'active_serial':int(active.RuntimeSerialNumber),'runtime_freeze_sha256':native.digest(freeze)})
    fixture.ModelUnitSystem=Rhino.UnitSystem.Millimeters
    fixture.ModelAbsoluteTolerance=0.000001
    backend=native.NativeDoc(fixture,active,schemas)
    durable=atomic.RhinoAtomicGate(OUTPUT/'fixture.sqlite3',str(fixture.RuntimeSerialNumber),lambda:atomic.rhino_scene_digest(fixture),create_ledger=True)
    secret=bytes.fromhex(channel.read_json(OUTPUT,'handoff.key')['key_hex'])
    task='C5独立未保存headless毫米夹具原生十二工具开发控制；不运行模型，不变更用户文档。'
    import hashlib
    gate=gate_module.ResearchGate(backend,durable,secret,native.digest(freeze),task_sha256=hashlib.sha256(task.encode()).hexdigest(),max_writes=10,max_reads=2)
    bridge=sessions.IdleBridge(gate,OUTPUT,key_name='handoff.key',source_sha256=freeze['source_inventory_sha256'],guard_source=source)
    # Retain the actual known fixture before any fallible attach operation.
    package._SESSION=bridge
    original_tick=bridge._callback
    def callback(sender,event):
        original_tick(sender,event)
        if bridge.stopped:
            package._SESSION=None
            package._FIXTURE=None
    bridge._callback=callback
    bridge.attach()
    print('C5_NATIVE12_APPROVED_SINGLE_ATTEMPT '+str(OUTPUT))


if __name__=='__main__': start()
