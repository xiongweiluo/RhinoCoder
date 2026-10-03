"""Independent synthetic mass/topology/attribute negative controls only."""
import copy

import pytest

from training.c5_rhino_scorer import score_readback


def fixture():
    obj = {"alias": "box-1", "min": [0,0,0], "max": [2,3,4], "volume":24., "centroid":[1,1.5,2],
           "solid":True, "face_count":6, "edge_count":12, "vertices":[[0,0,0],[2,3,4]],
           "layer":"Default", "color":[0,0,0], "groups":[], "geometry_sha256":"a"*64}
    scene = {"unit":"Millimeters", "objects":[obj]}
    assertions = {"object_count":1, "objects":{"box-1":{k:v for k,v in obj.items() if k!='alias'}},
                  "unchanged":[], "read_result":None}
    return scene, assertions


def test_full_geometric_component_not_formal_quality_claim():
    scene, assertions = fixture()
    value = score_readback(scene, scene, assertions)
    assert value['geometry_passed'] and not value['formal_task_passed']


@pytest.mark.parametrize("field,value", [('volume',12.),('solid',False),('face_count',5),('face_count',6.),
    ('color',[0.,0,0]),('layer','Other'),('vertices',[[0,0,0],[2,3,3]]),('groups',['G']),('centroid',[1,2,2]),
    ('geometry_sha256','b'*64),('edge_count',11)])
def test_same_bbox_does_not_hide_mass_topology_or_attribute_failure(field,value):
    scene, assertions = fixture()
    after = copy.deepcopy(scene)
    after['objects'][0][field] = value
    result = score_readback(scene, after, assertions)
    assert not result['geometry_passed'] and 'box-1:'+field in result['failures']


def test_bbox_only_or_unknown_assertions_rejected():
    scene, assertions = fixture()
    assertions['objects']['box-1'] = {'min':[0,0,0], 'max':[2,3,4]}
    with pytest.raises(ValueError): score_readback(scene,scene,assertions)
    assertions['objects']['box-1']['readback_verified'] = True
    with pytest.raises(ValueError): score_readback(scene,scene,assertions)


def test_unchanged_targets_read_results_and_missing_volume_fail_closed():
    scene, assertions = fixture()
    assertions['unchanged'] = ['box-1']
    changed = copy.deepcopy(scene)
    changed['objects'][0]['layer'] = 'Other'
    assert 'box-1:unexpected_change' in score_readback(scene,changed,assertions)['failures']
    assertions['read_result'] = {'count':1}
    assert 'read_result' in score_readback(scene,scene,assertions)['failures']
    scene['objects'][0].pop('volume')
    assert not score_readback(scene,scene,assertions,read_result={'count':1})['geometry_passed']
