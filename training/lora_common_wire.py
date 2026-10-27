"""Original prompt contract for the shared twelve-tool execution chain.

Only verified current scene and original task reach the prompt. Transport
predecessor metadata binds actual execution; it is never model feedback.
No tasks, models, native host, authority or network access on import.
"""
from __future__ import annotations

import hashlib

from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.lora_development_channel import PROTOCOL, detached, verify_host
from training.c5_formal20_privacy import allowed
from training.c5_modelbridge_joint_audit import semantic
from training.c5_rhino_adapter import step_input
from training.lora_comparison_plan import FINAL_STUDY, PROBE_STUDY, DIAGNOSTIC_STUDY
from training.lora_development_scope import _sha
from training.lora_development_wire import reparse_generations


def validate_request(value, model_views, runtime):
    value = detached(value)
    require(set(value) == {'protocol', 'study_id', 'runtime_sha256', 'slot_id', 'route', 'system',
        'step_index', 'task', 'scene', 'binding', 'predecessor', 'host_evidence_sha256'}, 'exact original request required')
    plan = model_views.get(value['slot_id'])
    require(plan is not None and value['protocol'] == PROTOCOL
            and value['study_id'] in {FINAL_STUDY, PROBE_STUDY, DIAGNOSTIC_STUDY}
            and all(value[k] == plan[k] for k in ('study_id', 'route', 'system', 'task'))
            and value['system'] == 'original' and value['runtime_sha256'] == _sha(runtime)
            and type(value['step_index']) is int and 0 <= value['step_index'] < plan['max_steps'],
            'request outside frozen common contract')
    binding = value['binding']
    require(set(binding) == {'document_key', 'revision', 'scene_sha256'}
            and type(binding['revision']) is int and binding['revision'] >= 0, 'actual binding required')
    for key in ('document_key', 'scene_sha256'): _sha(binding[key])
    _sha(value['host_evidence_sha256'])
    previous = value['predecessor']
    if value['step_index'] == 0:
        require(previous is None, 'unexpected predecessor')
    else:
        require(type(previous) is dict and set(previous) == {'step_index', 'observation_sha256', 'after_state'}
                and previous['step_index'] == value['step_index'] - 1
                and previous['after_state'] == binding, 'actual completed predecessor required')
        _sha(previous['observation_sha256'])
    require(allowed(value['task'], value['scene']), 'task/scene privacy refused')
    step_input(value['task'], value['scene'])
    return value


def user_step(sent):
    return step_input(sent['task'], sent['scene'])


def request_from_host(*, model_views, runtime, slot, step_index, secret, capture, capture_request,
                      capture_sequence, previous=None):
    plan = model_views[slot]
    require(capture_request == {'action': 'capture'}, 'capture required')
    current = verify_host(capture, secret=secret, runtime=runtime, slot=slot,
        sequence=capture_sequence, request=capture_request, study=plan['study_id'])
    require(current.get('status') == 'captured', 'incomplete capture')
    prior = None
    if step_index:
        require(type(previous) is dict and set(previous) == {'step_index', 'observation', 'envelope', 'request', 'sequence'}
                and previous['step_index'] == step_index - 1 and previous['sequence'] < capture_sequence
                and previous['request'].get('action') == 'execute', 'immediate execution required')
        receipt = verify_host(previous['envelope'], secret=secret, runtime=runtime, slot=slot,
            sequence=previous['sequence'], request=previous['request'], study=plan['study_id'])
        p, observed = receipt['payload'], previous['observation']
        require(receipt.get('status') == 'done' and previous['request']['envelope']['payload'] == p
                and observed['status'] == 'schema_valid_not_authorized'
                and p['operation'] == observed['name'] and p['arguments'] == observed['arguments']
                and p['expected'] == observed['scene_binding'] == receipt['before_state']
                and p['owner_freeze_sha256'] == runtime
                and p['task_sha256'] == hashlib.sha256(plan['task'].encode()).hexdigest()
                and receipt['after_state'] == current['state']
                and receipt['after_state']['document_key'] == receipt['before_state']['document_key']
                and digest(receipt['after']) == digest(current['native'])
                and receipt['result_sha256'] == digest(receipt['result']), 'noncontiguous native execution')
        prior = {'step_index': step_index - 1, 'observation_sha256': digest(observed),
                 'after_state': receipt['after_state']}
    else:
        require(previous is None, 'first step has predecessor')
    sent = {'protocol': PROTOCOL, 'study_id': plan['study_id'], 'runtime_sha256': runtime,
        'slot_id': slot, 'route': plan['route'], 'system': 'original', 'step_index': step_index,
        'task': plan['task'], 'scene': semantic(current['native']), 'binding': current['state'],
        'predecessor': prior, 'host_evidence_sha256': digest({'capture': capture, 'previous': previous})}
    return validate_request(sent, model_views, runtime)


def check_predecessor(sent, previous_request, previous_observation):
    if sent['step_index'] == 0:
        require(previous_request is None and previous_observation is None, 'unexpected worker predecessor')
        return
    require(type(previous_request) is dict and type(previous_observation) is dict
            and all(previous_request[k] == sent[k] for k in ('study_id', 'slot_id', 'route', 'system', 'task', 'runtime_sha256'))
            and previous_request['step_index'] + 1 == sent['step_index']
            and previous_observation['status'] == 'schema_valid_not_authorized'
            and sent['predecessor']['observation_sha256'] == digest(previous_observation)
            and previous_request['binding']['document_key'] == sent['binding']['document_key']
            and previous_request['binding']['revision'] <= sent['binding']['revision'], 'worker predecessor differs')


def reparse_response(value, sent, *, model_views, runtime, identity, tokenizer):
    sent = validate_request(sent, model_views, runtime)
    return reparse_generations(value, sent, identity=identity, tokenizer=tokenizer, rendered=user_step(sent))
