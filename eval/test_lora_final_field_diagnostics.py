"""Public, deliberately invalid CPU fixtures; never final evaluation cases."""
import copy
import json
import pytest
from training.lora_final_case_check import field_details
from training.c5_formal20_plan import _schemas
from plugin.rhino_listener.c5_research_native import validate_native_arguments


@pytest.mark.parametrize('operation,args,path,reason', [
 ('create_box',{'width':1,'depth':1},'.height','missing_required_field'),
 ('create_box',{'width':'PRIVATE_VALUE','depth':1,'height':1},'.width','schema_type_or_array_limit'),
 ('create_box',{'width':0,'depth':1,'height':1},'.width','nonpositive_dimension'),
 ('create_box',{'width':100001,'depth':1,'height':1},'.width','numeric_bound'),
 ('create_box',{'width':1,'depth':1,'height':1,'PRIVATE_KEY':'PRIVATE_VALUE'},'.<unknown-field-4>','unknown_field'),
 ('move_object',{'object_id':'','translate_x':0,'translate_y':0,'translate_z':0},'.object_id','string_contract'),
 ('scale_object',{'object_id':'public-alias','scale_factor':[1,1]},'.scale_factor','vector_length'),
 ('scale_object',{'object_id':'public-alias','scale_factor':[1,0,1]},'.scale_factor[1]','nonpositive_scale'),
 ('scale_object',{'object_id':'public-alias','scale_factor':[1,'PRIVATE_VALUE',1]},'.scale_factor[1]','wrong_element_type'),
 ('rotate_object',{'object_id':'public-alias','angle_degrees':1,'axis':[0,0,0]},'.axis','zero_rotation_axis'),
 ('group_objects',{'object_ids':['public-alias','public-alias']},'.object_ids','duplicate_alias'),
 ('group_objects',{'object_ids':[]},'.object_ids','empty_alias_array'),
 ('set_object_color',{'object_ids':['public-alias'],'r':256,'g':0,'b':0},'.r','rgb_range'),
])
def test_diagnostics_locate_original_rejections_without_private_values(operation,args,path,reason):
    case={'fixture_recipe':[{'operation':operation,'arguments':args}]}; before=copy.deepcopy(case)
    with pytest.raises((ValueError,TypeError,RuntimeError)):
        validate_native_arguments(operation,args,_schemas())
    details=field_details(case)
    assert any(d['field']=='fixture_recipe[0].arguments'+path and d['reason']==reason for d in details)
    assert case==before
    output=json.dumps(details)
    assert all(secret not in output for secret in ['PRIVATE_KEY','PRIVATE_VALUE','public-alias'])


def test_assertion_type_errors_are_both_reported_even_when_seed_fails_first():
    case={'fixture_recipe':[{'operation':'create_box','arguments':{}}],
          'final_assertions':{'objects':None,'unchanged':{'PRIVATE_KEY':'PRIVATE_VALUE'}}}
    details=field_details(case)
    assert {'field':'final_assertions.objects','reason':'wrong_type','expected':'object'} in details
    assert {'field':'final_assertions.unchanged','reason':'wrong_type','expected':'array'} in details
    assert 'PRIVATE' not in json.dumps(details)


def test_valid_public_seed_has_no_advisory_errors():
    assert field_details({'fixture_recipe':[{'operation':'create_box','arguments':{'width':1,'depth':1,'height':1}}],
                          'final_assertions':{'objects':{},'unchanged':[]}})==[]
