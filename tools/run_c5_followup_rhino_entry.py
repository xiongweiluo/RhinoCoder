#!python3
"""Fixed new ScriptEditor entry. Complete two-hash grant before host effects.

Invoke with the separately frozen entry-return wrapper. No old state/grant,
model, task corpora, listener registration, retry or automatic host restart.
"""
import importlib
import json
from pathlib import Path
import sys
import types
import uuid

ROOT=Path(__file__).resolve().parents[1]


def start():
    sys.dont_write_bytecode=True
    for name,module in tuple(sys.modules.items()):
        if name.startswith(('rhino_research_','rhino_c5_')) and getattr(module,'_SESSION',None) is not None:
            raise RuntimeError('another live research owner; cannot replace it')
    prefix='rhino_c5_'+uuid.uuid4().hex
    for name,path in ((prefix,ROOT),(prefix+'.plugin',ROOT/'plugin'),
                      (prefix+'.plugin.rhino_listener',ROOT/'plugin/rhino_listener')):
        module=types.ModuleType(name);module.__path__=[str(path)];sys.modules[name]=module
    package=sys.modules[prefix]
    def load(name):return importlib.import_module(prefix+'.plugin.rhino_listener.'+name)
    # Resolve the complete inert dependency graph before any host effects.
    # Every project import stays inside this namespace; never alias a global
    # plugin package or alter the embedded interpreter's search path.
    try:
        spec,runtime,binding,plan,guard=load('c5_followup_mac_scope').mac_scope(ROOT,embedded=True,private_prefixes=(prefix,))
        native,channel=load('c5_research_native'),load('c5_research_channel')
        registry_type=load('c5_followup_admission').AdmissionRegistry
        hub_type=load('c5_reuse_native_hub').ReuseNativeHub
        session_type=load('c5_reuse_host_session').ReuseHostSession
        backend_type=load('c5_host_observer_clr').ClrObserverBackend
        admission_type=load('c5_deferred_baseline').DeferredBaselineAdmission
        for name in ('sqlite3','hmac','secrets','contextlib','collections','enum','typing'):
            importlib.import_module(name)
        guard()
    except BaseException:
        # No registry, Rhino import, document, subscription or callback exists
        # yet. Roll back only this invocation's provisional module namespace.
        for name in tuple(sys.modules):
            if name==prefix or name.startswith(prefix+'.'):sys.modules.pop(name)
        raise
    # Import of Rhino and every host operation are AFTER the complete grant.
    import Rhino
    require=native.require;state=Path(binding['paths']['state_root']);source_sha=native.digest(runtime['source_files'])
    policy=load('c5_reuse_public_plan').observer_policy(ROOT)
    require(sys.platform=='darwin' and list(sys.version_info[:2])==[3,9]
            and str(Rhino.RhinoApp.Version)==policy['expected_rhino_version'],'reuse_embedded_runtime')
    require(channel.read_json(state,'prepared.json')=={'study_id':binding['study_id'],
        'spec_sha256':binding['spec_sha256'],'runtime_sha256':binding['runtime_sha256'],
        'model_calls':0,'private_formal_reads':0},'reuse_exact_preparation')
    active=Rhino.RhinoDoc.ActiveDoc
    require(Rhino.RhinoApp.IsOnMainThread and active is not None and not native._all_objects(active),
            'exclusive blank main-thread document required')
    registry=registry_type(binding)
    package._REGISTRY=registry
    channel.publish_json(state,'new-hub-started.claim.json',{'study_id':binding['study_id'],
        'runtime_sha256':binding['runtime_sha256'],'replay_allowed':False})
    schemas=load('c5_followup_runtime_scope').strict(load('c5_followup_runtime_scope').read_bytes(
        ROOT/'eval/c5/rhino-runtime-schema-v1.json'))['core_parameters']
    channel.publish_json(state,'warmup.started.json',{'study_id':binding['study_id'],
        'runtime_freeze_sha256':binding['runtime_sha256'],'replay_allowed':False})
    doc=Rhino.RhinoDoc.CreateHeadless(None);require(doc is not None,'warmup opening unknown')
    package._WARMUP=doc
    doc.ModelUnitSystem=Rhino.UnitSystem.Millimeters;doc.ModelAbsoluteTolerance=0.000001
    warmup=native.NativeDoc(doc,active,schemas);before=warmup.readback()
    require(before['objects']==[] and before['groups']=={},'warmup not empty')
    import System
    for item in (Rhino.Geometry.Box,Rhino.Geometry.Interval,Rhino.Geometry.Plane,Rhino.Geometry.Point3d,
        Rhino.Geometry.Vector3d,Rhino.Geometry.Transform,Rhino.Geometry.Brep,Rhino.Geometry.VolumeMassProperties,
        Rhino.Geometry.Circle,Rhino.Geometry.Cylinder,Rhino.Geometry.Sphere,
        Rhino.DocObjects.ObjectAttributes,Rhino.DocObjects.ObjectColorSource,System.Drawing.Color,System.Guid):
        require(item is not None,'declared warmup type unavailable')
    closed=warmup.close();require(closed['fixture_registry_absent'] is True,'warmup close unknown')
    channel.publish_json(state,'warmup.result.json',{'study_id':binding['study_id'],
        'runtime_freeze_sha256':binding['runtime_sha256'],'before_native':before,'close_capture':closed,
        'tool_dispatches':0,'model_calls':0,'active_sha256':native.active_content_digest(active)})
    package._WARMUP=None
    backend=backend_type(policy,ROOT)
    assurance=session_type(binding,registry,backend,guard,source_sha,
                           cleanup_source=lambda:guard(cleanup_only=True))
    hub=hub_type(binding,runtime,registry,schemas,active,guard,assurance)
    package._SESSION=hub
    tick=hub._callback
    def seal():assurance.seal_baseline();hub.preparing=False
    def ready():
        value={'study_id':binding['study_id'],'runtime_sha256':binding['runtime_sha256'],
               'host_baseline_head_sha256':assurance.head,'generation_stages':0,'full_byte_closure_proven':False}
        channel.publish_json(state,'host-continuity-ready.json',value)
        print('C5_REUSE_HOST_EXTERNAL_READY '+json.dumps(value,sort_keys=True))
    def failed(error):
        hub.blocked=True
        channel.publish_json(state,'deferred-baseline.failed.json',{'error_type':error,'replay_allowed':False})
    admission=admission_type(source_guard=guard,seal=seal,publish_ready=ready,mark_failure=failed,dispatch=tick,
        publish_release=lambda:channel.publish_json(state,'entry-return-release.json',{
            'study_id':binding['study_id'],'runtime_sha256':binding['runtime_sha256'],
            'source_inventory_sha256':source_sha,'baseline_sealed':False,'replay_allowed':False}))
    def callback(sender,event):
        admission.tick(in_command=bool(getattr(Rhino.RhinoApp,'InCommand',False)),sender=sender,event=event)
        if hub.stopped:package._SESSION=None;registry.close()
    hub._callback=callback;hub.attach()
    channel.publish_json(state,'deferred-baseline.prepared.json',{'study_id':binding['study_id'],
        'runtime_sha256':binding['runtime_sha256'],'baseline_sealed':False,'model_calls':0})
    package._ENTRY_RETURN_BARRIER=admission
    return admission


if __name__=='__main__':ENTRY_RETURN_BARRIER=start()
