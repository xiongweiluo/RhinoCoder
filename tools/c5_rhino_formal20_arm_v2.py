#! python 3
"""New exact formal arm, no private task read before consumption/readiness.

One empty warmup, one Idle delegate and one AssemblyLoad subscription.
This entry is never run under capacity/preparation consent alone.
"""
import importlib
import json
import sys
import types
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def start():
    import Rhino
    for name,module in tuple(sys.modules.items()):
        if name.startswith(('rhino_research_','rhino_c5_')) and getattr(module,'_SESSION',None) is not None:
            raise RuntimeError('another live research owner; cannot replace it')
    prefix='rhino_c5_'+uuid.uuid4().hex
    for name,path in ((prefix,ROOT),(prefix+'.plugin',ROOT/'plugin'),
                      (prefix+'.plugin.rhino_listener',ROOT/'plugin/rhino_listener')):
        module=types.ModuleType(name);module.__path__=[str(path)];sys.modules[name]=module
    package=sys.modules[prefix]
    def load(name):return importlib.import_module(prefix+'.plugin.rhino_listener.'+name)
    protocol,native,channel=load('c5_formal20_scope_v2'),load('c5_research_native'),load('c5_research_channel')
    def public(name):
        path=ROOT/name
        native.require(path.resolve()==path and path.is_file() and 0<path.stat().st_size<=1048576,
            'bounded fixed formal public file required')
        def pairs(items):
            value={}
            for k,v in items:
                native.require(k not in value,'duplicate formal public key');value[k]=v
            return value
        return json.loads(path.read_bytes(),object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite formal public JSON')))
    spec,freeze=public(protocol.SPEC_FILE),public(protocol.FREEZE_FILE)
    approval=channel.read_json(protocol.MAC_STATE,'owner-approval.json')
    protocol.authority(spec,freeze,approval)
    native.require(ROOT==protocol.MAC_SOURCE,'fixed new formal Mac source root required')
    binding=load('c5_formal20_policy_v2').validate_formal_binding(spec,freeze,approval)
    provenance=load('c5_research_provenance')
    project=provenance.SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],project_prefixes=(prefix,))
    def source():
        project()
        native.require(sys.version_info[:2]==(3,9) and str(Rhino.RhinoApp.Version)==freeze['rhino_version'],
            'formal embedded runtime differs')
        native.require(protocol.file_sha(ROOT/protocol.SPEC_FILE)==freeze['spec_file_sha256']
            and native.digest(public(protocol.FREEZE_FILE))==native.digest(freeze)
            and channel.read_json(protocol.MAC_STATE,'owner-approval.json')==approval,
            'formal embedded exact grant/spec/runtime drift')
        native.require(all(protocol.file_sha(Path(n))==sha for n,sha in freeze['rhino_environment_files'].items())
            and all(protocol.file_sha(ROOT/n)==sha for n,sha in freeze['fixed_public_files'].items()),
            'formal known readable host/public bytes drift; opaque host not proven')
        return freeze['source_inventory_sha256']
    source()
    state=protocol.MAC_STATE
    native.require(not (state/'formal20.started.json').exists()
        and channel.read_json(state,'formal20.zero-prepared.json')=={'study_id':protocol.STUDY_ID,
            'runtime_freeze_sha256':native.digest(freeze),'private_rows_read':0,'model_calls':0},
        'new zero-stage preparation required before private consumption')
    active=Rhino.RhinoDoc.ActiveDoc
    native.require(Rhino.RhinoApp.IsOnMainThread and active is not None and not native._all_objects(active),
        'usable research-exclusive empty active document required')
    channel.publish_json(state,'formal20.hub-admission.claim.json',{'action':'attach','study_id':protocol.STUDY_ID,
        'runtime_freeze_sha256':native.digest(freeze),'replay_allowed':False})
    channel.publish_json(state,'formal20.hub-started.claim.json',{'study_id':protocol.STUDY_ID,
        'runtime_freeze_sha256':native.digest(freeze),'replay_allowed':False})
    for name in ('sqlite3','hmac','secrets','contextlib','collections','enum','typing'):
        importlib.import_module(name)
    hub_type=load('c5_formal20_hub_v2').FormalArm
    session_type=load('c5_formal20_host_session_v2').FormalHostSession
    backend_type=load('c5_host_observer_clr').ClrObserverBackend
    admission_type=load('c5_deferred_baseline').DeferredBaselineAdmission
    schemas=public('eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    channel.publish_json(state,'warmup.started.json',{'study_id':protocol.STUDY_ID,
        'runtime_freeze_sha256':native.digest(freeze),'replay_allowed':False})
    doc=Rhino.RhinoDoc.CreateHeadless(None)
    native.require(doc is not None,'formal empty warmup opening unknown')
    package._WARMUP=doc
    doc.ModelUnitSystem=Rhino.UnitSystem.Millimeters;doc.ModelAbsoluteTolerance=0.000001
    warmup=native.NativeDoc(doc,active,schemas);before=warmup.readback()
    native.require(before['objects']==[] and before['groups']=={},'formal warmup not empty')
    import System
    for item in (Rhino.Geometry.Box,Rhino.Geometry.Interval,Rhino.Geometry.Plane,Rhino.Geometry.Point3d,
        Rhino.Geometry.Vector3d,Rhino.Geometry.Transform,Rhino.Geometry.Brep,Rhino.Geometry.VolumeMassProperties,
        Rhino.Geometry.Circle,Rhino.Geometry.Cylinder,Rhino.Geometry.Sphere,
        Rhino.DocObjects.ObjectAttributes,Rhino.DocObjects.ObjectColorSource,System.Drawing.Color,System.Guid):
        native.require(item is not None,'formal declared warmup type unavailable')
    close=warmup.close();native.require(close['fixture_registry_absent'] is True,'formal warmup close unknown')
    channel.publish_json(state,'warmup.result.json',{'study_id':protocol.STUDY_ID,
        'runtime_freeze_sha256':native.digest(freeze),'before_native':before,'close_capture':close,
        'tool_dispatches':0,'model_calls':0,'active_sha256':native.active_content_digest(active)})
    package._WARMUP=None
    assurance=session_type(state,binding,backend_type(spec['observer_backend'],ROOT),source,freeze['source_inventory_sha256'])
    arm=hub_type(state,spec,freeze,schemas,source,active,assurance);package._SESSION=arm
    def ready():
        channel.publish_json(state,'host-continuity-ready.json',{'study_id':protocol.STUDY_ID,
            'runtime_freeze_sha256':native.digest(freeze),'legacy_byte_closure_verified':False,'sealed_before_model_generation':True})
        print('C5_FORMAL20_HOST_READY_ZERO_PRIVATE_ROWS')
    def failed(error_type):
        arm.blocked=True
        channel.publish_json(state,'deferred-baseline.failed.json',{'study_id':protocol.STUDY_ID,
            'runtime_freeze_sha256':native.digest(freeze),'error_type':error_type,'replay_allowed':False,
            'manual_reconciliation_required':True})
    barrier=admission_type(source_guard=source,seal=assurance.seal_baseline,publish_ready=ready,
        mark_failure=failed,dispatch=arm.tick,publish_release=lambda:channel.publish_json(state,
            'entry-return-release.json',{'study_id':protocol.STUDY_ID,'runtime_freeze_sha256':native.digest(freeze),
                'source_inventory_sha256':freeze['source_inventory_sha256'],'baseline_sealed':False,'replay_allowed':False}))
    def callback(sender,event):
        barrier.tick(in_command=bool(getattr(Rhino.RhinoApp,'InCommand',False)),sender=sender,event=event)
        if arm.stopped:package._SESSION=None
    arm._callback=callback
    source();Rhino.RhinoApp.Idle+=callback
    channel.publish_json(state,'deferred-baseline.prepared.json',{'study_id':protocol.STUDY_ID,
        'runtime_freeze_sha256':native.digest(freeze),'baseline_sealed':False,'model_calls':0})
    package._ENTRY_RETURN_BARRIER=barrier
    print('C5_FORMAL20_ARM_WAIT_ENTRY_RETURN_NO_PRIVATE_READ')
    return barrier


if __name__=='__main__':ENTRY_RETURN_BARRIER=start()
