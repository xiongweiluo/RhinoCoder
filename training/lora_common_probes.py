"""Two public mechanism probes, excluded from every final comparison.

Scripted calls test plumbing only. They are not model quality evidence and
are not a retry/replacement of any previous development or historical slot.
"""
import copy

from training.c5_formal20_plan import validate_case
from training.lora_development_cases import fixture_design


def public_probes():
    recipe, scene, initial = fixture_design()
    output = []
    specs = [
        ('COMMON-P01', 'multistep', 'write_translation_then_fresh_bbox',
         '将 box-1 沿 X 移动 2 毫米，然后读取一次它的新包围盒，结束。',
         [{'name': 'move_object', 'arguments': {'object_id': 'box-1', 'translate_x': 2, 'translate_y': 0, 'translate_z': 0}, 'read_result': None}]),
        ('COMMON-P02', 'error_recovery', 'repair_wrong_layer_color_then_readback',
         'box-1 的图层和颜色设置有误：先将图层修正为 C5-Fixed，再将颜色改为 RGB(60,70,80)，最后读取一次完整场景摘要。',
         [{'name': 'set_object_layer', 'arguments': {'object_id': 'box-1', 'layer_name': 'C5-Fixed'}, 'read_result': None},
          {'name': 'set_object_color', 'arguments': {'object_ids': ['box-1'], 'r': 60, 'g': 70, 'b': 80}, 'read_result': None}]),
    ]
    for family, layer, template, task, operations in specs:
        final = copy.deepcopy(initial); final['unchanged'] = ['box-2']
        after_scene = copy.deepcopy(scene)
        obj, assertion = after_scene['objects'][0], final['objects']['box-1']
        if layer == 'multistep':
            for k in ('min', 'max'):
                obj[k][0] += 2; assertion[k][0] += 2
            assertion['centroid'][0] += 2
            result = {'object_id': 'box-1', 'min': obj['min'], 'max': obj['max'], 'center': assertion['centroid']}
            operations.append({'name': 'get_bounding_box', 'arguments': {'object_id': 'box-1'}, 'read_result': result})
        else:
            for target in (obj, assertion): target.update(layer='C5-Fixed', color=[60, 70, 80])
            operations.append({'name': 'get_scene_summary', 'arguments': {}, 'read_result': after_scene})
        final['read_result'] = operations[-1]['read_result']
        output.append(validate_case({'schema_version': 1, 'family_id': family, 'template_family': template,
            'stratum': layer, 'primary_tool': None, 'task_text': task, 'fixture_recipe': recipe,
            'initial_assertions': initial, 'final_assertions': final, 'expected_operations': operations,
            'max_steps': len(operations), 'max_reads': 1, 'max_writes': len(operations) - 1}))
    return output
