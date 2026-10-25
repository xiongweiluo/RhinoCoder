"""Pure new development wire and generation-return checks; no providers."""
import math
from training.c5_reuse_evidence import exact, raw_sha, require, sha, canonical, is_sha
from training.c5_reuse_field_scope import PROTOCOL, STUDY, validate_binding, common_scope
from training.c5_model_transport import validate_request
from training.c5_contract import DECODE_CONFIG
from training.c5_contract import CONTRACT_ID, parse_selection, parse_invocation
from training.c5_inventory import load_public_mcp_tools
from training.c5_rhino_adapter import step_input

FRAME_LIMIT=1024*1024


def frame(value):
    raw=canonical(value)+b'\n'
    require(0<len(raw)<=FRAME_LIMIT, 'field_frame_size')
    return raw


def approved_request(binding,sent,plans):
    require(sha(plans)==binding['development_plan_sha256'] and sent==envelope(binding,sent['request']), 'field_approved_plan')
    inner=sent['request']; p=plans.get(inner['slot_id'])
    require(p is not None and inner['route']==p['route'] and inner['step_index']<len(p['steps'])
            and inner['task']==p['steps'][inner['step_index']], 'field_unapproved_task_before_send')

def validate_return(value, prompt_sha, stage):
    exact(value, ('raw','tokens','seconds','prompt_sha256','output_sha256'))
    require(stage in ('selector', 'invocation'), 'peer_stage')
    require(is_sha(prompt_sha) and is_sha(value['prompt_sha256'])
            and type(value['raw']) is str and len(value['raw'].encode()) <= 262144
            and type(value['tokens']) is int and 0 <= value['tokens'] <= DECODE_CONFIG[stage+'_max_new_tokens']
            and type(value['seconds']) in (int,float) and math.isfinite(value['seconds']) and value['seconds'] >= 0
            and value['prompt_sha256'] == prompt_sha and value['output_sha256'] == raw_sha(value['raw'].encode()),
            'peer_raw_generation_binding')


def envelope(binding, request):
    validate_binding(binding)
    validate_request(request)
    require(request['probe_id'] == binding['study_id'] and request['runtime_freeze_sha256'] == binding['runtime_sha256'],
            'new_peer_request_scope')
    return {'protocol': PROTOCOL, 'scope_sha256': sha(common_scope(binding)), 'request': request}


def validate_peer_result(binding, sent, value):
    require(envelope(binding,sent['request'])==sent, 'peer_result_sent_scope')
    exact(value, ('protocol','scope_sha256','request_sha256','observation','generation_returns','status'))
    require(value['protocol']==PROTOCOL and value['scope_sha256']==sha(common_scope(binding))
            and value['request_sha256']==sha(sent)
            and value['status']=='recorded_model_observation_not_native_permission', 'peer_result_scope')
    observed=value['observation']
    keys={'contract_id','status','calls','user_step_sha256','scene_binding','name','arguments','repair_count','dispatch_count'}
    require(type(observed) is dict and set(observed) in (keys,keys|{'error_type'})
            and observed['contract_id']==CONTRACT_ID and observed['scene_binding'] is None
            and observed['user_step_sha256']==raw_sha(step_input(sent['request']['task'],sent['request']['scene']).encode())
            and all(type(observed[k]) is int and observed[k]==0 for k in ('repair_count','dispatch_count'))
            and observed['status'] in ('abstained_no_dispatch','unsupported_for_c5_no_dispatch',
                'selector_contract_failure_no_dispatch','invocation_contract_failure_no_dispatch',
                'schema_valid_not_authorized','operational_failure_no_retry'), 'peer_result_observation')
    calls,returns=observed['calls'],value['generation_returns']
    require(type(calls) is list and type(returns) is list and len(calls)<=2 and len(returns)<=len(calls), 'peer_result_calls')
    for index,call in enumerate(calls):
        require(type(call) is dict and set(call) in (
                {'stage','prompt_sha256','generation_attempted','parsed'},
                {'stage','prompt_sha256','generation_attempted','parsed','raw','output_sha256'})
                and call['stage']==('selector','invocation')[index]
                and is_sha(call['prompt_sha256'])
                and call['generation_attempted'] is True and type(call['parsed']) is bool, 'peer_result_call')
    if observed['status']=='operational_failure_no_retry':
        require(type(observed.get('error_type')) is str, 'peer_result_failure')
        for index,returned in enumerate(returns):
            validate_return(returned,calls[index]['prompt_sha256'],calls[index]['stage'])
        return observed  # Never an admissible permission; missing coverage stays unknown.
    require(len(returns)==len(calls) and len(calls)>0, 'peer_result_return_population')
    for call,returned in zip(calls,returns):
        validate_return(returned,call['prompt_sha256'],call['stage'])
        require(call.get('raw')==returned['raw'] and call.get('output_sha256')==returned['output_sha256'], 'peer_result_raw')
    if observed['status']=='schema_valid_not_authorized':
        require(len(calls)==2 and all(c['parsed'] for c in calls), 'peer_result_success')
        tools=load_public_mcp_tools()
        selected=parse_selection(calls[0]['raw'],tools)
        parsed=parse_invocation(calls[1]['raw'],selected,tools)
        require(parsed['name']==observed['name'] and parsed['arguments']==observed['arguments'], 'peer_result_parser_drift')
    else:
        require(observed['name'] is None and observed['arguments'] is None, 'peer_result_failed_call')
    return observed
