"""Full native-control wire/SQLite synthetic run, NEVER real Rhino evidence."""
import copy
import math
import sys
from types import SimpleNamespace

import pytest

from eval.test_c5_research_session import Event
from plugin.rhino_listener import c5_research_session as session
from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_gate import ResearchGate
from plugin.rhino_listener.candidate_atomic_gate import RhinoAtomicGate
from tools import c5_native12_client as client
from tools.c5_native12_common import TASK,ID
import hashlib


class Native:
    def __init__(self,schemas):
        self.schemas=schemas
        self.scene={'unit':'Millimeters','objects':[],'groups':{}}
        self.serial,self.active_serial,self.initial_active_sha=2,1,'e'*64
        self.closed=False
        self.calls=[]
    def guard(self):
        if self.closed: raise NativeError('closed synthetic fixture')
    def target(self,alias,**kwargs):
        values=[o for o in self.scene['objects'] if o['alias']==alias]
        if len(values)!=1: raise NativeError('unknown synthetic alias')
        return values[0]
    def readback(self): return copy.deepcopy(self.scene)
    def close(self):
        self.guard(); self.closed=True
        return {'fixture_serial':2,'fixture_registry_absent':True,'initial_active_sha256':'e'*64,
                'before_close_active_sha256':'e'*64,'after_close_active_sha256':'e'*64,
                'before_close_active_serial':1,'after_close_active_serial':1,
                'fixture_before_close_native':self.readback()}
    def dispatch(self,name,args):
        self.calls.append(name)
        objects=self.scene['objects']
        if name in {'create_box','create_sphere','create_cylinder'}:
            if name=='create_box': alias,mn,mx,volume,faces='box-1',[0,0,0],[17,19,23],7429,6
            elif name=='create_sphere': alias,mn,mx,volume,faces='sphere-2',[-5,-5,-5],[5,5,5],500*math.pi/3,1
            else: alias,mn,mx,volume,faces='cylinder-3',[-3,-3,0],[3,3,7],63*math.pi,3
            objects.append({'alias':alias,'min':mn,'max':mx,'centroid':[(a+b)/2 for a,b in zip(mn,mx)],
                            'volume':volume,'solid':True,'face_count':faces,'layer':'Default','color':[0,0,0],
                            'groups':[],'geometry_sha256':digest({'alias':alias,'min':mn,'max':mx})})
        elif name in {'move_object','rotate_object','scale_object'}:
            box=self.target('box-1')
            if name=='move_object': mn,mx=[11,13,17],[28,32,40]
            elif name=='rotate_object': mn,mx=[-32,11,17],[-13,28,40]
            else: mn,mx=[-64,33,68],[-26,84,160]; box['volume']=178296
            box.update(min=mn,max=mx,centroid=[(a+b)/2 for a,b in zip(mn,mx)],geometry_sha256=digest([mn,mx]))
        elif name=='set_object_layer': self.target('box-1')['layer']='C5DEV::native12'
        elif name=='set_object_color': self.target('box-1')['color']=[37,83,149]
        elif name=='group_objects':
            for alias in ('box-1','cylinder-3'): self.target(alias)['groups']=['native12_group']
            self.scene['groups']={'native12_group':['box-1','cylinder-3']}
        elif name=='get_bounding_box':
            box=self.target('box-1')
            return {'object_id':'box-1','min':box['min'],'max':box['max'],'center':box['centroid']}
        elif name=='get_scene_summary':
            return {**self.readback(),'objects':[{k:o[k] for k in ('alias','min','max','layer','color','groups')} for o in objects]}
        elif name=='boolean_difference':
            self.scene['objects']=[self.target('box-1'),{'alias':'difference-4','min':[-3,-3,4],'max':[3,3,7],
                'centroid':[0,0,5.5],'volume':67*math.pi/3,'solid':True,'face_count':3,'groups':[],
                'geometry_sha256':'c'*64,'color':[0,0,0],'layer':'Default'}]
            self.scene['groups']={'native12_group':['box-1']}
        return {'synthetic_only_operation':name}


def synthetic(tmp_path,monkeypatch):
    state=tmp_path/'state'; state.mkdir(mode=0o700)
    output=state/'output'; output.mkdir(mode=0o700)
    spec=client.fixed_scope.__globals__['read_public'](client.ROOT/'eval/c5/native12-development-spec-20261003.json')
    schemas=client.fixed_scope.__globals__['read_public'](client.ROOT/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    freeze={'source_files':{'synthetic.py':'a'*64},'source_inventory_sha256':'f'*64}
    approval={'synthetic_fixture_only':True}
    monkeypatch.setattr(client,'scope',lambda:(spec,freeze,schemas,approval,lambda:'f'*64))
    monkeypatch.setattr(client,'STATE',state); monkeypatch.setattr(client,'OUTPUT',output)
    for kind in ('admission.claim','engine-started'):
        publish_json(state,ID+'.'+kind+'.json',{'probe_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    publish_json(output,'handoff.key',{'key_hex':(b'x'*32).hex()})
    publish_json(output,'engine-created.json',{'fixture_serial':2,'active_serial':1,'runtime_freeze_sha256':digest(freeze),
                 'python_major_minor':[3,9],'rhino_major':8,'rhino_version':'SYNTHETIC_RHINO8_NOT_ACTUAL','python_version':'SYNTHETIC_PY39_NOT_ACTUAL'})
    backend=Native(schemas)
    durable=RhinoAtomicGate(output/'fixture.sqlite3','synthetic-only',lambda:digest(backend.scene),create_ledger=True)
    gate=ResearchGate(backend,durable,b'x'*32,digest(freeze),task_sha256=hashlib.sha256(TASK.encode()).hexdigest(),max_writes=10,max_reads=2)
    rhino=SimpleNamespace(RhinoApp=SimpleNamespace(IsOnMainThread=True,Idle=Event()),RhinoDoc=SimpleNamespace(ActiveDoc=SimpleNamespace(RuntimeSerialNumber=1)))
    monkeypatch.setitem(sys.modules,'Rhino',rhino)
    monkeypatch.setattr(session,'active_content_digest',lambda _:'e'*64)
    bridge=session.IdleBridge(gate,output,key_name='handoff.key',source_sha256='f'*64,guard_source=lambda:'f'*64)
    bridge.attach()
    def exchange(self,kind,envelope):
        bridge.seq=self.seq
        publish_json(output,'request-%04d.json'%self.seq,{'kind':kind,'envelope':envelope})
        try:
            result=bridge.handle({'kind':kind,'envelope':envelope})
            if result is None:
                for _ in range(3): result=bridge.settle()
            else: publish_json(output,'response-%04d.json'%self.seq,result)
        except NativeError as exc:
            bridge.blocked=True
            result={'status':'failed_no_retry','error_type':'NativeError','error':str(exc),'seq':self.seq,'manual_review_required':True}
            publish_json(output,'response-%04d.json'%self.seq,result)
        self.seq+=1
        return result
    monkeypatch.setattr(client.FixedClient,'exchange',exchange)
    return backend,output


def test_full_fixed_wire_and_independent_all_step_audit_are_cpu_only(tmp_path,monkeypatch):
    backend,output=synthetic(tmp_path,monkeypatch)
    result=client.drive()
    assert result['status']=='native12_execution_complete_not_independently_audited' and result['cleanup_verified']
    audit=client.audit()
    assert audit['signed_write_requests']==10 and audit['signed_read_requests']==2
    assert audit['model_calls']==audit['gpu_calls']==audit['formal_holdout_calls']==0
    assert not audit['complete_C5_engineering_gate_passed'] and not audit['formal_quality_claim']
    assert len(backend.calls)==12 and backend.closed and not (output/'handoff.key').exists()
    with pytest.raises(FileExistsError): client.drive()  # Driver restart cannot recover or replay.


def test_incorrect_native_read_result_not_accepted_as_geometry_success(tmp_path,monkeypatch):
    backend,output=synthetic(tmp_path,monkeypatch)
    original=backend.dispatch
    def wrong(name,args):
        result=original(name,args)
        if name=='get_bounding_box': result['center']=[0,0,0]
        return result
    monkeypatch.setattr(backend,'dispatch',wrong)
    assert client.drive()['cleanup_verified']
    with pytest.raises(NativeError): client.audit()
