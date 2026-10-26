"""Authenticated synthetic exchanges, never historical/raw model evidence."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_research_native import NativeError, digest
from training.c5_rhino_adapter import invoke_step
from training.lora_development_cases import fixture_design
from training.lora_development_scope import field_views
from training.lora_development_wire import (check_predecessor, host_response, model_response,
    reparse_response, request_from_host, user_step, validate_request)
from tools.audit_lora_development_token_budget import public_contexts
from training.lora_dev_feedback import render_progress
from eval.test_lora_dev_contracts import TextTokenizer

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / 'eval/lora-development/proposed-development-plan.json').read_text())
VIEWS = field_views(PLAN)['model']
RUNTIME, IDENTITY, SECRET = 'a' * 64, 'b' * 64, b'c' * 32
BINDING = {'document_key': 'd' * 64, 'revision': 0, 'scene_sha256': 'e' * 64}


def capture(slot, sequence=1):
    scene = fixture_design()[1]
    request = {'action': 'capture'}
    value = {'status': 'captured', 'native': scene, 'state': BINDING}
    signed = host_response(SECRET, RUNTIME, slot, sequence, request, value)
    return request, signed


def first(slot='lora-dev-02'):
    req, signed = capture(slot)
    return request_from_host(model_views=VIEWS, runtime=RUNTIME, slot=slot, step_index=0,
        secret=SECRET, capture=signed, capture_request=req, capture_sequence=1)


def fixed_response(sent, selection='{"tool":"get_bounding_box"}',
                   invocation='{"name":"get_bounding_box","arguments":{"object_id":"box-2"}}'):
    rows = []
    def generate(prompt, stage):
        raw = selection if stage == 'selector' else invocation
        row = {'stage': stage, 'raw': raw, 'tokens': 8, 'seconds': .01,
               'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
               'output_sha256': hashlib.sha256(raw.encode()).hexdigest()}
        rows.append(row)
        return row
    observed = invoke_step(TextTokenizer(), generate, user_step(sent), scene_binding=sent['binding'],
                           privacy_guard=lambda _: True)
    return model_response(sent, observed, rows, IDENTITY)


def second():
    sent = first()
    observed = reparse_response(fixed_response(sent), sent, model_views=VIEWS, runtime=RUNTIME,
                                identity=IDENTITY, tokenizer=TextTokenizer())
    payload = {'operation': observed['name'], 'arguments': observed['arguments'], 'expected': BINDING,
               'owner_freeze_sha256': RUNTIME, 'task_sha256': hashlib.sha256(sent['task'].encode()).hexdigest()}
    request = {'action': 'execute', 'envelope': {'payload': payload}}
    result = {'object_id': 'box-2', 'min': [20, 0, 0], 'max': [24, 6, 8]}
    receipt = {'status': 'done', 'payload': payload, 'before_state': BINDING, 'after_state': BINDING,
               'before': sent['scene'], 'after': sent['scene'], 'result': result, 'result_sha256': digest(result)}
    previous = {'step_index': 0, 'observation': observed, 'request': request, 'sequence': 2,
                'envelope': host_response(SECRET, RUNTIME, sent['slot_id'], 2, request, receipt)}
    req, signed = capture(sent['slot_id'], 3)
    args = dict(model_views=VIEWS, runtime=RUNTIME, slot=sent['slot_id'], step_index=1,
                secret=SECRET, capture=signed, capture_request=req, capture_sequence=3, previous=previous)
    return sent, observed, args


def test_receipt_origin_is_checked_before_projecting_minimal_feedback():
    original, observed, args = second()
    sent = request_from_host(**args)
    check_predecessor(sent, original, observed)
    assert sent['progress'] == {'status': 'done', 'operation': 'get_bounding_box', 'target_alias': 'box-2'}
    assert 'raw' not in sent and 'receipt' not in sent and 'result' not in sent
    assert 'expected_operations' not in json.dumps(sent) and 'next_action' not in json.dumps(sent)
    # GPU gets a scene binding and evidence commitment, no native signing key.
    assert 'signature' not in json.dumps(sent) and 'key' not in sent


@pytest.mark.parametrize('fault', ['tamper', 'cross_slot', 'cross_runtime', 'wrong_exchange',
    'wrong_sequence', 'unknown', 'wrong_model_operation', 'changed_document', 'bad_result_hash'])
def test_false_or_cross_scope_feedback_never_reaches_model_request(fault):
    _, _, args = second()
    args = copy.deepcopy(args)
    previous = args['previous']
    p = previous['envelope']['payload']
    if fault == 'tamper': p['value']['payload']['arguments']['object_id'] = 'box-1'
    if fault == 'cross_slot': p['slot_id'] = 'lora-dev-03'
    if fault == 'cross_runtime': p['runtime_sha256'] = 'f' * 64
    if fault == 'wrong_exchange': previous['request']['action'] = 'capture'
    if fault == 'wrong_sequence': previous['sequence'] = 3
    if fault == 'wrong_model_operation': previous['observation']['arguments'] = {'object_id': 'box-1'}
    if fault in {'unknown', 'changed_document', 'bad_result_hash'}:
        value = p['value']
        if fault == 'unknown': value['status'] = 'unknown'
        if fault == 'changed_document': value['after_state'] = {**BINDING, 'document_key': 'f' * 64}
        if fault == 'bad_result_hash': value['result_sha256'] = 'f' * 64
        previous['envelope'] = host_response(SECRET, RUNTIME, args['slot'], 2, previous['request'], value)
    with pytest.raises((NativeError, ValueError)):
        request_from_host(**args)


@pytest.mark.parametrize('system_slot', ['lora-dev-00', 'lora-dev-02'])
@pytest.mark.parametrize('raw', ['{"tool":null}', '{"tool":"get_scene_summary"}', 'invalid'])
def test_both_systems_reparse_the_same_unchanged_raw_contract(system_slot, raw):
    sent = first(system_slot)
    response = fixed_response(sent, raw, '{"name":"get_scene_summary","arguments":{}}')
    observed = reparse_response(response, sent, model_views=VIEWS, runtime=RUNTIME,
        identity=IDENTITY, tokenizer=TextTokenizer())
    assert observed == response['observation'] and observed['repair_count'] == observed['dispatch_count'] == 0


@pytest.mark.parametrize('fault', ['model', 'request', 'parsed_args', 'prompt', 'raw', 'extra_stage', 'tokens'])
def test_reparse_rejects_corruption_or_forged_success(fault):
    sent = first()
    response = fixed_response(sent)
    if fault == 'model': response['model_identity_sha256'] = 'f' * 64
    if fault == 'request': response['request_sha256'] = 'f' * 64
    if fault == 'parsed_args': response['observation']['arguments']['object_id'] = 'box-1'
    if fault == 'prompt': response['generations'][0]['prompt_sha256'] = 'f' * 64
    if fault == 'raw': response['generations'][0]['raw'] = '{"tool":null}'
    if fault == 'extra_stage': response['generations'].append(response['generations'][-1])
    if fault == 'tokens': response['generations'][0]['tokens'] = 129
    with pytest.raises(NativeError):
        reparse_response(response, sent, model_views=VIEWS, runtime=RUNTIME,
                         identity=IDENTITY, tokenizer=TextTokenizer())


def test_wire_rejects_task_change_and_worker_detects_wrong_predecessor():
    prior, observed, args = second()
    sent = request_from_host(**args)
    changed = copy.deepcopy(sent); changed['task'] += ' extra'
    with pytest.raises(NativeError): validate_request(changed, VIEWS, RUNTIME)
    changed = copy.deepcopy(prior); changed['system'] = 'original'
    with pytest.raises(NativeError): check_predecessor(sent, changed, observed)
    with pytest.raises(NativeError): check_predecessor(sent, None, None)


def test_render_refactor_preserves_all_previously_audited_public_input_bytes():
    # Expected bytes are stored input commitments; no real tokenizer repetition.
    # Reconstruct the old renderer by its literal contract, not a new oracle.
    from training.c5_rhino_adapter import step_input
    from tools.audit_lora_development_token_budget import TemplateCapture, canonical
    from training.c5_contract import CORE_INVOCATION_TOOLS, render_invocation, render_selection
    from training.c5_inventory import load_public_mcp_tools
    for floats, name in [(False, 'token-budget-audit-20261026.json'),
                         (True, 'token-budget-native-floats-20261026.json')]:
        old = json.loads((ROOT / 'eval/lora-development' / name).read_text())
        contexts = public_contexts(native_floats=floats)
        tools, tokenizer = load_public_mcp_tools(), TemplateCapture()
        for row in contexts:
            row['templates'] = [json.loads(render_selection(tokenizer, row['user_step'], tools).prompt)] + [
                json.loads(render_invocation(tokenizer, row['user_step'], tools, op).prompt)
                for op in CORE_INVOCATION_TOOLS]
        payload = {'contexts': contexts, 'tokenizer_files': old['tokenizer_files']}
        assert hashlib.sha256(canonical(payload).encode()).hexdigest() == old['input_sha256']
