"""Portable schema and fake-scope checks; no native geometry quality claims."""
import ast
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugin.rhino_listener import c5_research_native as module
from training.c5_contract import CORE_INVOCATION_TOOLS
from training.c5_inventory import load_public_mcp_tools
from training.tool_contract_candidate import validate_arguments


def schemas():
    return {t['function']['name']: t['function']['parameters'] for t in load_public_mcp_tools()
            if t['function']['name'] in CORE_INVOCATION_TOOLS}


VALID = {
    'create_box': {'width': 2, 'depth': 3, 'height': 4},
    'create_sphere': {'radius': 2}, 'create_cylinder': {'radius': 2, 'height': 3},
    'move_object': {'object_id':'测试-A','translate_x':2,'translate_y':-3,'translate_z':4},
    'rotate_object': {'object_id':'A','angle_degrees':90,'axis':[0,0,1],'center_point':[0,0,0]},
    'scale_object': {'object_id':'A','scale_factor':[1,2,3],'center_point':None},
    'group_objects': {'object_ids':['A','B'],'group_name':None},
    'set_object_color': {'object_ids':['A'],'r':1.0,'g':2,'b':3},
    'set_object_layer': {'object_id':'A','layer_name':'C5::蓝色'},
    'boolean_difference': {'input0_ids':['A'],'input1_ids':['B']},
    'get_bounding_box': {'object_id':'A'}, 'get_scene_summary': {},
}


@pytest.mark.parametrize('operation', sorted(VALID))
def test_all_twelve_original_parameters_no_target_stripping(operation):
    tools = {t['function']['name']: t for t in load_public_mcp_tools()}
    args = copy.deepcopy(VALID[operation])
    validate_arguments(operation, args, tools[operation])
    assert module.validate_native_arguments(operation,args,schemas()) == args
    assert set(VALID) == module.CORE == set(CORE_INVOCATION_TOOLS)


@pytest.mark.parametrize('operation,args', [
    ('create_box',{'width':True,'depth':3,'height':4}), ('create_sphere',{'radius':0}),
    ('create_cylinder',{'radius':2,'height':float('nan')}),
    ('move_object',{'object_id':'11111111-2222-3333-4444-555555555555','translate_x':0,'translate_y':0,'translate_z':0}),
    ('move_object',{'object_id':'A','translate_x':100001,'translate_y':0,'translate_z':0}),
    ('scale_object',{'object_id':'A','scale_factor':[0,1,1]}),
    ('rotate_object',{'object_id':'A','angle_degrees':90,'axis':[0,0,0]}),
    ('rotate_object',{'object_id':'A','angle_degrees':90,'axis':[1,0]}),
    ('group_objects',{'object_ids':['A','A']}), ('group_objects',{'object_ids':[]}),
    ('set_object_color',{'object_ids':['A'],'r':256,'g':0,'b':0}),
    ('set_object_layer',{'object_id':'A','layer_name':'A\nB'}),
    ('boolean_difference',{'input0_ids':['A'],'input1_ids':['A']}),
    ('get_scene_summary',{'oracle':True}), ('delete_objects',{'object_ids':['A']})])
def test_execution_constraints_fail_without_repair(operation,args):
    original = copy.deepcopy(args)
    with pytest.raises(module.NativeError): module.validate_native_arguments(operation,args,schemas())
    assert args.keys() == original.keys()


def test_schema_bytes_and_python39_boundary_frozen():
    frozen = json.loads((Path(__file__).resolve().parent/'c5/rhino-runtime-schema-v1.json').read_text())
    assert frozen['core_parameters'] == schemas() and frozen['core_parameters_sha256'] == module.SCHEMA_SHA
    changed = schemas()
    changed['move_object']['properties'].pop('object_id')
    with pytest.raises(module.NativeError): module.validate_native_arguments('move_object',VALID['move_object'],changed)
    source = Path(module.__file__).read_text()
    ast.parse(source, feature_version=(3,9))
    assert 'from training' not in source and 'scriptcontext' not in source.split('"""',2)[-1]


def fake_native(monkeypatch):
    active = SimpleNamespace(RuntimeSerialNumber=1)
    doc = SimpleNamespace(RuntimeSerialNumber=2,IsHeadless=True,Path=None,ModelUnitSystem='Millimeters')
    rhino = SimpleNamespace(RhinoApp=SimpleNamespace(IsOnMainThread=True),RhinoDoc=SimpleNamespace(ActiveDoc=active))
    monkeypatch.setitem(sys.modules,'Rhino',rhino)
    monkeypatch.setattr(module,'active_content_digest',lambda _: 'a'*64)
    monkeypatch.setattr(module,'_all_objects',lambda _: [])
    return module.NativeDoc(doc,active,schemas()),rhino


@pytest.mark.parametrize('mutation',['active','thread','headless','unit','path','content','closed'])
def test_native_scope_guard_rejects_before_dispatch(monkeypatch,mutation):
    backend,rhino = fake_native(monkeypatch)
    if mutation == 'active': rhino.RhinoDoc.ActiveDoc = SimpleNamespace(RuntimeSerialNumber=3)
    if mutation == 'thread': rhino.RhinoApp.IsOnMainThread = False
    if mutation == 'headless': backend.doc.IsHeadless = False
    if mutation == 'unit': backend.doc.ModelUnitSystem = 'Meters'
    if mutation == 'path': backend.doc.Path = '/some/user/document.3dm'
    if mutation == 'content': monkeypatch.setattr(module,'active_content_digest',lambda _: 'b'*64)
    if mutation == 'closed': backend.closed = True
    with pytest.raises(module.NativeError): backend.guard()


def test_active_document_cannot_be_fixture(monkeypatch):
    backend,rhino = fake_native(monkeypatch)
    with pytest.raises(module.NativeError): module.NativeDoc(backend.active,backend.active,schemas())


def test_unknown_duplicate_alias_and_semantic_projection(monkeypatch):
    backend,_ = fake_native(monkeypatch)
    with pytest.raises(module.NativeError): backend.target('unknown')
    obj = SimpleNamespace(Attributes=SimpleNamespace(Name='A'))
    monkeypatch.setattr(module,'_all_objects',lambda _: [obj,obj])
    with pytest.raises(module.NativeError): backend.objects()
    row = {'alias':'A','min':[0,0,0],'max':[2,3,4],'layer':'Default','color':[0,0,0],'groups':[],
           'volume':24.,'geometry_sha256':'a'*64,'oracle_score':True}
    monkeypatch.setattr(backend,'readback',lambda: {'unit':'Millimeters','groups':{},'objects':[row]})
    semantic = backend.semantic_scene()
    assert 'volume' not in semantic['objects'][0] and 'oracle_score' not in semantic['objects'][0]


@pytest.mark.parametrize('still_live',[False,True])
def test_close_requires_absent_registry_not_dispose_flag(monkeypatch,still_live):
    backend,rhino = fake_native(monkeypatch)
    closed = []
    backend.doc.Dispose = lambda:closed.append(True)
    monkeypatch.setattr(backend,'readback',lambda:{'unit':'Millimeters','objects':[],'groups':{}})
    rhino.RhinoDoc.FromRuntimeSerialNumber = lambda serial:backend.doc if still_live else None
    if still_live:
        with pytest.raises(module.NativeError): backend.close()
    else:
        receipt = backend.close()
        assert receipt['fixture_registry_absent'] and receipt['after_close_active_sha256'] == 'a'*64
    assert closed == [True] and backend.closed


def test_nested_layer_find_uses_integer_notfound_sentinel(monkeypatch):
    backend,rhino=fake_native(monkeypatch)
    layers=[]
    searches=[]
    class Layers:
        def FindByFullPath(self,name,not_found):
            assert type(not_found) is int and not_found == -1
            searches.append(name)
            return -1
        def Add(self,layer):
            layer.Id='synthetic-layer-'+str(len(layers))
            layers.append(layer)
            return len(layers)-1
        def __getitem__(self,index): return layers[index]
    backend.doc.Layers=Layers()
    rhino.DocObjects=SimpleNamespace(Layer=lambda:SimpleNamespace())
    monkeypatch.setattr(module,'_writable_layer',lambda *args:True)
    assert backend._layer('C5DEV::native12') == 1
    assert searches == ['C5DEV','C5DEV::native12'] and layers[1].ParentLayerId==layers[0].Id
