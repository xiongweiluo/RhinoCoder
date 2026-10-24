"""Independent raw peer audit; does not import the generation producer."""
import re
from training.c5_reuse_evidence import canonical, exact, raw_sha, require, sha
from training.c5_reuse_field_scope import PROTOCOL
from training.c5_reuse_field_journal import replay_records
from training.c5_reuse_field_wire import envelope, validate_return
from training.c5_rhino_adapter import invoke_step, step_input
from training.c5_formal20_privacy import allowed

def audit_generation(values, binding, final_head=None, *, plans=None, tokenizer=None):
    """Independent attempt/return replay. Does not import or call generators."""
    replay_records(values, binding, 'worker', final_head)
    request = None
    pending = None
    attempts = returns = 0
    unknown = set()
    completed = {}
    retired = False
    stages = []
    outputs = {}
    failure_types = {}
    raw_observed = {}
    semantic_replay = plans is not None and tokenizer is not None
    if plans is not None:
        require(sha(plans) == binding['development_plan_sha256'], 'audit_development_plan')
    for row in values[1:]:
        kind, payload = row['kind'], row['payload']
        require(not retired, 'generation_event_after_unknown')
        if kind == 'request_intent':
            exact(payload, ('envelope',))
            require(request is None, 'generation_request_order')
            request = payload['envelope']
            require(canonical(request) == canonical(envelope(binding, request['request'])), 'generation_request_scope')
            key = (request['request']['slot_id'], request['request']['step_index'])
            require(key not in completed and len(completed) < 56
                    and (key[1] == 0 or completed.get((key[0],key[1]-1)) == 'schema_valid_not_authorized'),
                    'generation_duplicate_request_or_predecessor')
            if plans is not None:
                inner = request['request']
                p = plans.get(inner['slot_id'])
                require(p is not None and inner['route'] == p['route'] and inner['step_index'] < len(p['steps'])
                        and inner['task'] == p['steps'][inner['step_index']], 'audit_development_task')
            stages, outputs, failure_types, raw_observed = [], {}, {}, {}
        elif kind == 'generation_intent':
            exact(payload, ('request_sha256', 'ordinal', 'stage', 'prompt_raw', 'prompt_sha256'))
            require(request is not None and pending is None and type(payload['ordinal']) is int
                    and payload['ordinal'] == attempts and payload['request_sha256'] == sha(request)
                    and not unknown and len(stages) < 2 and attempts < 112
                    and payload['stage'] == ('selector','invocation')[len(stages)]
                    and type(payload['prompt_raw']) is str and payload['prompt_sha256'] == raw_sha(payload['prompt_raw'].encode()),
                    'generation_intent_binding')
            pending = payload; stages.append(payload); attempts += 1
        elif kind == 'generation_raw_observed':
            exact(payload, ('request_sha256','ordinal','raw_hex','observed_bytes','truncated'))
            require(pending is not None and type(payload['ordinal']) is int
                    and payload['ordinal'] == pending['ordinal']
                    and payload['request_sha256'] == pending['request_sha256']
                    and type(payload['raw_hex']) is str and len(payload['raw_hex']) <= 524288
                    and re.fullmatch(r'(?:[0-9a-f]{2})*',payload['raw_hex']) is not None
                    and type(payload['observed_bytes']) is int and payload['observed_bytes'] >= 0
                    and type(payload['truncated']) is bool
                    and len(bytes.fromhex(payload['raw_hex'])) == min(payload['observed_bytes'],262144)
                    and payload['truncated'] == (payload['observed_bytes'] > 262144)
                    and payload['ordinal'] not in raw_observed, 'generation_raw_observation')
            raw_observed[payload['ordinal']] = payload
        elif kind == 'generation_return':
            exact(payload, ('request_sha256', 'ordinal', 'raw'))
            require(pending is not None and type(payload['ordinal']) is int and payload['ordinal'] == pending['ordinal']
                    and payload['request_sha256'] == pending['request_sha256'], 'generation_return_order')
            raw = payload['raw']
            validate_return(raw,pending['prompt_sha256'],pending['stage'])
            observation = raw_observed.get(pending['ordinal'])
            require(observation is not None and not observation['truncated']
                    and bytes.fromhex(observation['raw_hex']) == raw['raw'].encode(), 'generation_raw_return_binding')
            outputs[pending['ordinal']] = raw
            returns += 1
            pending = None
        elif kind == 'generation_unknown':
            exact(payload, ('request_sha256','ordinal','error_type'))
            require(request is not None and payload['request_sha256'] == sha(request)
                    and type(payload['ordinal']) is int and stages
                    and payload['ordinal'] == stages[-1]['ordinal']
                    and payload['ordinal'] not in unknown,
                    'generation_unknown_binding')
            unknown.add(payload['ordinal'])
            require(type(payload['error_type']) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,60}', payload['error_type']),
                    'generation_error_type')
            failure_types[payload['ordinal']] = payload['error_type']
            pending = None
        elif kind == 'model_receipt':
            exact(payload, ('result',))
            result = payload['result']
            exact(result, ('protocol','scope_sha256','request_sha256','observation','generation_returns','status'))
            require(request is not None and pending is None and result['request_sha256'] == sha(request)
                    and result['scope_sha256'] == sha(binding) and result['protocol'] == PROTOCOL
                    and result['status'] == 'recorded_model_observation_not_native_permission'
                    and canonical(result['generation_returns']) == canonical([outputs[k] for k in sorted(outputs)]),
                    'generation_receipt_binding')
            if semantic_replay:
                position = 0
                def replay(prompt, stage):
                    nonlocal position
                    require(position < len(stages), 'audit_missing_stage')
                    item = stages[position]; position += 1
                    require(prompt == item['prompt_raw'] and stage == item['stage'], 'audit_prompt_semantics')
                    if item['ordinal'] in failure_types:
                        error = type(failure_types[item['ordinal']], (RuntimeError,), {})
                        raise error('recorded generation uncertainty')
                    require(item['ordinal'] in outputs, 'audit_missing_return')
                    return outputs[item['ordinal']]
                inner = request['request']
                user_step = step_input(inner['task'], inner['scene'])
                observed = invoke_step(tokenizer, replay, user_step,
                    privacy_guard=lambda rendered: rendered == user_step and allowed(inner['task'],inner['scene']))
                require(position == len(stages) and canonical(observed) == canonical(result['observation']),
                        'audit_raw_observation_replay')
            completed[(request['request']['slot_id'],request['request']['step_index'])] = result['observation']['status']
            retired = bool(unknown) or result['observation']['status'] == 'operational_failure_no_retry'
            request = None
        else:
            raise ValueError('generation_event_unknown')
    return {'recorded_generation_attempts': attempts, 'recorded_generation_returns': returns,
            'unknown_attempts': len(unknown) + int(pending is not None), 'requests_complete': len(completed),
            'coverage_complete': bool(completed) and request is None and pending is None and not unknown and not retired
                and final_head is not None and semantic_replay,
            'prompt_and_parser_semantics_recomputed': semantic_replay,
            'actual_model_generation_total_independently_proven': None,
            'external_witness_origin_verified': False, 'execution_ready': False}
