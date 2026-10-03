"""Synthetic adapter controls; no model loader, Rhino or final task exposure."""
import copy
import json

import pytest

from training.c5_rhino_adapter import invoke_step, step_input
from training.tool_contract_candidate import ContractError


class Tokenizer:
    def apply_chat_template(self, messages, *, tools=None, **kwargs):
        return json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False)

    def __call__(self, text, **kwargs):
        return {"input_ids": [0]*100}


def scene():
    return {"unit": "Millimeters", "groups": {}, "objects": [
        {"alias": "测试-A", "min": [0, 0, 0], "max": [2, 3, 4], "layer": "Default", "color": [0, 0, 0], "groups": []}]}


@pytest.mark.parametrize("selector,status,count", [('not json', 'selector_contract_failure_no_dispatch', 1),
    ('{"tool":null}', 'abstained_no_dispatch', 1),
    ('{"tool":"delete_objects"}', 'unsupported_for_c5_no_dispatch', 1),
    ('{"tool":"create_box"}', 'schema_valid_not_authorized', 2)])
def test_strict_two_stage_no_oracle_or_dispatch(selector, status, count):
    calls = []
    def generate(prompt, stage):
        calls.append((prompt, stage))
        return {"raw": selector if stage == "selector" else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'}
    result = invoke_step(Tokenizer(), generate, "创建宽2深3高4的盒体")
    assert result["status"] == status and len(calls) == count
    assert result["repair_count"] == result["dispatch_count"] == 0
    if count == 2:
        inv = json.loads(calls[1][0])
        assert len(inv["tools"]) == 1 and inv["tools"][0]["function"]["name"] == "create_box"


@pytest.mark.parametrize("raw", ['```json\n{}\n```', '{"name":"create_box","arguments":{"width":2,"depth":3}}',
    '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4,"extra":1}}',
    '{"name":"create_box","arguments":{"width":2,"depth":3,"height":NaN}}',
    '{"name":"move_object","arguments":{}}', '{"name":"create_box","name":"create_box","arguments":{}}'])
def test_bad_invocation_never_repaired_or_recalled(raw):
    stages = []
    def generate(prompt, stage):
        stages.append(stage)
        return {"raw": '{"tool":"create_box"}' if stage == 'selector' else raw}
    result = invoke_step(Tokenizer(), generate, "创建宽2深3高4的盒体")
    assert stages == ['selector', 'invocation'] and result['status'] == 'invocation_contract_failure_no_dispatch'


def test_generator_failure_and_hash_tampering_no_retry():
    count = []
    def broken(*args): count.append(1); raise TimeoutError("CPU timeout")
    assert invoke_step(Tokenizer(), broken, "创建半径2的球体")['status'] == 'operational_failure_no_retry'
    assert count == [1]
    assert invoke_step(Tokenizer(), lambda *a: {"raw": '{"tool":null}', "output_sha256": "f"*64}, "不要执行任何工具")['status'] == 'operational_failure_no_retry'


def test_equivalent_scene_input_and_attribute_membership():
    first = scene()
    second = copy.deepcopy(first)
    assert step_input("只读查询测试-A的包围盒", first) == step_input("只读查询测试-A的包围盒", second)
    second['objects'][0]['max'][0] += 1
    assert step_input("只读查询测试-A的包围盒", first) != step_input("只读查询测试-A的包围盒", second)


@pytest.mark.parametrize("mutation", ['physical', 'unexpected', 'duplicate', 'bounds', 'membership'])
def test_semantic_scene_refuses_physical_ids_and_inconsistent_state(mutation):
    value = scene()
    if mutation == 'physical': value['objects'][0]['alias'] = '11111111-2222-3333-4444-555555555555'
    if mutation == 'unexpected': value['document_key'] = 'a'*64
    if mutation == 'duplicate': value['objects'].append(copy.deepcopy(value['objects'][0]))
    if mutation == 'bounds': value['objects'][0]['min'][0] = 8
    if mutation == 'membership': value['groups']['G'] = ['测试-A']
    with pytest.raises(ContractError): step_input("执行当前一步", value)
