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
    scope, native, channel = load('c5_hostassurance_development_scope_d'),load('c5_research_native'),load('c5_research_channel')
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
    hub_type = load('c5_hostassurance_lifecycle_hub_d').HostAwareLifecycleHubD
    session_type = load('c5_host_assurance_session_d').HostAssuranceSessionD
    backend_type = load('c5_host_observer_clr').ClrObserverBackend
    admission_type = load('c5_deferred_baseline').DeferredBaselineAdmission
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
    def seal():
        assurance.seal_baseline()
        hub.preparing = False
    def ready():
        channel.publish_json(scope.STATE,'host-continuity-ready.json',{'study_id':scope.ID,
            'runtime_freeze_sha256':native.digest(freeze),'legacy_byte_closure_verified':False,
            'sealed_before_model_generation':True})
        print('C5_D_FIRST_IDLE_BASELINE_READY_NO_MODEL_STARTED')
    def failed(error_type):
        hub.blocked=True
        channel.publish_json(scope.STATE,'deferred-baseline.failed.json',{'study_id':scope.ID,
            'runtime_freeze_sha256':native.digest(freeze),'error_type':error_type,
            'replay_allowed':False,'manual_reconciliation_required':True})
    admission=admission_type(source_guard=source,seal=seal,publish_ready=ready,
        mark_failure=failed,dispatch=tick,publish_release=lambda:channel.publish_json(scope.STATE,
            'entry-return-release.json',{'study_id':scope.ID,'runtime_freeze_sha256':native.digest(freeze),
                'source_inventory_sha256':freeze['source_inventory_sha256'],'baseline_sealed':False,'replay_allowed':False}))
    def callback(sender,event):
        admission.tick(in_command=bool(getattr(Rhino.RhinoApp,'InCommand',False)),sender=sender,event=event)
        if hub.stopped: package._SESSION = None
    hub._callback = callback
    hub.attach()  # The handler exists, but cannot dispatch before release/seal.
    channel.publish_json(scope.STATE,'deferred-baseline.prepared.json',{'study_id':scope.ID,
        'runtime_freeze_sha256':native.digest(freeze),'baseline_sealed':False,'model_calls':0})
    package._ENTRY_RETURN_BARRIER=admission
    print('C5_D_QUEUED_WAIT_ENTRY_RETURN_AND_FIRST_IDLE_NO_MODEL_STARTED')
    return admission


if __name__ == '__main__': ENTRY_RETURN_BARRIER=start()
