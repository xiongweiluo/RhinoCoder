#!python3
"""Fresh fixed study entry; exact new grant before warmup/subscription/fixture.

Does not open a private task file or execute an old probe. Unknown failure
retains the actual owner and raw evidence; no automatic retry/reconciliation.
"""
import importlib
import json
import sys
import types
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def start():
    import Rhino
    for name, module in tuple(sys.modules.items()):
        if name.startswith(('rhino_research_','rhino_c5_')) and getattr(module,'_SESSION',None) is not None:
            raise RuntimeError('another live research owner; cannot replace it')
    # Empty containers; never run unrelated Listener/package init side effects.
    prefix = 'rhino_c5_'+uuid.uuid4().hex
    for name,path in ((prefix,ROOT),(prefix+'.plugin',ROOT/'plugin'),
        (prefix+'.plugin.rhino_listener',ROOT/'plugin/rhino_listener')):
        module = types.ModuleType(name); module.__path__ = [str(path)]; sys.modules[name] = module
    package = sys.modules[prefix]
    namespace = prefix+'.plugin.rhino_listener'
    def load(name): return importlib.import_module(namespace+'.'+name)
    scope, native, channel = load('c5_hostassurance_development_scope'),load('c5_research_native'),load('c5_research_channel')
    spec,freeze,approval,binding,source = scope.scope(ROOT,private_prefixes=(prefix,))
    native.require(sys.version_info[:2] == (3,9) and str(Rhino.RhinoApp.Version) == freeze['rhino_version'],
        'actual embedded Python/Rhino differs')
    prepared = channel.read_json(scope.STATE,'prepared.json')
    native.require(prepared == {'probe_id':scope.ID,'runtime_freeze_sha256':native.digest(freeze),
        'model_calls':0,'holdout_calls':0}, 'new exact preparation required')
    active = Rhino.RhinoDoc.ActiveDoc
    native.require(Rhino.RhinoApp.IsOnMainThread and active is not None and not native._all_objects(active),
        'research-exclusive blank active document required; never clear user scene')
    channel.publish_json(scope.STATE,scope.ID+'.hub-started.claim.json',{'probe_id':scope.ID,
        'runtime_freeze_sha256':native.digest(freeze),'replay_allowed':False})
    schemas = scope.public(ROOT,'eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    # Declared stdlib/controller imports occur ONLY after the exact new grant.
    for name in ('sqlite3','hmac','secrets','contextlib','collections','enum','typing'):
        importlib.import_module(name)
    hub_type = load('c5_hostassurance_development_hub').HostAwareDevelopmentHub
    session_type = load('c5_host_assurance_session').HostAssuranceSession
    backend_type = load('c5_host_observer_clr').ClrObserverBackend
    # Sole empty warmup fixture: no tool dispatch or geometry/model writes.
    channel.publish_json(scope.STATE,'warmup.started.json',{'study_id':scope.ID,
        'runtime_freeze_sha256':native.digest(freeze),'replay_allowed':False})
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    native.require(doc is not None,'warmup fixture opening unknown')
    package._WARMUP = doc  # Retain partial creation identity, never guess close.
    doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
    doc.ModelAbsoluteTolerance = 0.000001
    warmup = native.NativeDoc(doc,active,schemas)
    before = warmup.readback()
    native.require(before['objects'] == [] and before['groups'] == {},'warmup not empty')
    # Resolve full backend type references, no dispatch/forced model operation.
    import System
    for item in (Rhino.Geometry.Box,Rhino.Geometry.Interval,Rhino.Geometry.Plane,Rhino.Geometry.Point3d,
        Rhino.Geometry.Vector3d,Rhino.Geometry.Transform,Rhino.Geometry.Brep,Rhino.Geometry.VolumeMassProperties,
        Rhino.Geometry.Circle,Rhino.Geometry.Cylinder,Rhino.Geometry.Sphere,
        Rhino.DocObjects.ObjectAttributes,Rhino.DocObjects.ObjectColorSource,System.Drawing.Color,System.Guid):
        native.require(item is not None,'declared warmup type unavailable')
    closed = warmup.close()
    native.require(closed['fixture_registry_absent'] is True,'warmup close registry absence unknown')
    channel.publish_json(scope.STATE,'warmup.result.json',{'study_id':scope.ID,
        'runtime_freeze_sha256':native.digest(freeze),'before_native':before,'close_capture':closed,
        'tool_dispatches':0,'model_calls':0,'active_sha256':native.active_content_digest(active)})
    package._WARMUP = None
    backend = backend_type(spec['observer_backend'],ROOT)
    assurance = session_type(scope.STATE,binding,backend,source,freeze['source_inventory_sha256'])
    hub = hub_type(state=scope.STATE,spec=spec,freeze=freeze,schemas=schemas,active=active,byte_guard=source)
    package._SESSION = hub
    hub.assurance = assurance
    tick = hub._callback
    def callback(sender,event):
        tick(sender,event)
        if hub.stopped: package._SESSION = None
    hub._callback = callback
    hub.attach()  # Declare actual delegate/constructor warmup before sealing.
    assurance.seal_baseline()
    hub.preparing = False
    channel.publish_json(scope.STATE,'host-continuity-ready.json',{'study_id':scope.ID,
        'runtime_freeze_sha256':native.digest(freeze),'legacy_byte_closure_verified':False,
        'sealed_before_model_generation':True})
    print('C5_NEW_HOSTASSURANCE_DEVELOPMENT_READY_NO_MODEL_STARTED')


if __name__ == '__main__': start()
