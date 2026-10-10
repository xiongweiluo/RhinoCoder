"""Read-only raw model/scene/permission/native binding component.

Not a whole engineering gate: actual source/import/assets/resource and full
lifecycle evidence are additional mandatory audits. Never loads a model or
uses expected tool/arguments to correct output. Tokenizer is supplied frozen.
"""
from __future__ import annotations

import hashlib

from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_research_channel import read_json
from training.c5_contract import render_selection,render_invocation,parse_selection,parse_invocation
from training.c5_inventory import load_public_mcp_tools
from training.c5_model_transport import validate_response,rebind_observation
from training.c5_research_audit import audit_permission_execution
from training.c5_rhino_adapter import step_input
from training.c5_rhino_scorer import score_readback


def semantic(native):
    require(set(native)=={'unit','objects','groups'},'exact raw native scene required')
    return {'unit':native['unit'],'groups':native['groups'],'objects':[
        {k:row[k] for k in ('alias','min','max','layer','color','groups')} for row in native['objects']]}


def audit_native_trace(directory,record,receipt,close,stop):
    """Bind every raw UI request and response; reject hidden extra dispatch."""
    requests=sorted(p.name for p in directory.glob('request-*.json'))
    responses=sorted(p.name for p in directory.glob('response-*.json'))
    require(requests==['request-%04d.json'%n for n in range(1,len(requests)+1)]
            and responses==['response-%04d.json'%n for n in range(1,len(requests)+1)],
            'native request/response sequence incomplete or extra')
    captures=[record['capture'],record['post_model_capture'],*record['signing_captures']]
    require(len(captures)>=2,'actual pre/post model captures missing')
    expected=[('control',c) for c in captures]
    if receipt is not None:expected.append(('execute',receipt))
    expected.extend((('close',close),('stop',stop)))
    require(len(requests)==len(expected) and len(requests)<=64,'native trace differs from approved actions')
    executed=[]
    for index,(kind,value) in enumerate(expected,1):
        sent=read_json(directory,'request-%04d.json'%index)
        response=read_json(directory,'response-%04d.json'%index)
        require(response==value,'raw native response differs from joint record')
        require(sent.get('kind')==('execute' if kind=='execute' else 'control'),'raw native action kind differs')
        if kind!='execute':
            require(sent['envelope']['payload']['action']==('capture' if kind=='control' else kind),
                    'raw native control action/order differs')
        else:
            require(sent['envelope']['payload']==receipt['payload'],'raw native execution payload differs')
            executed.append(index)
            immediate=read_json(directory,'execute-%04d.json'%index)
            require(immediate=={k:v for k,v in receipt.items() if k not in {
                'after','after_state','immediate_after','immediate_after_state','settling_samples','stable_idle_samples'}}
                | {'after':receipt['immediate_after'],'after_state':receipt['immediate_after_state']},
                'immediate native dispatch evidence differs')
    require(sorted(p.name for p in directory.glob('execute-*.json'))==[
        'execute-%04d.json'%n for n in executed],'extra raw native dispatch')
    return {'controls':len(requests)-len(executed),'native_dispatches':len(executed)}


def audit_model_native_chain(records,receipts,consent_db,fixture_db,*,task,freeze_sha,model_identity,tokenizer):
    """Every issued model observation must match one raw native receipt.

    records include actual pre-generation UI captures plus wire requests and
    responses. Failed/abstained observations must have ZERO dispatch. The
    corpus/scorer never participates in prompt construction or raw reparsing.
    Whole route-task and lifecycle outcome are intentionally NOT inferred.
    """
    require(isinstance(records,list) and isinstance(receipts,list),'complete raw record lists required')
    tools = load_public_mcp_tools()
    by_id = {r['payload']['request_id']:r for r in receipts}
    require(len(by_id)==len(receipts),'duplicate native execution')
    used,seen = set(),set()
    calls = 0
    for record in records:
        require(set(record)=={'capture','post_model_capture','signing_captures','request','response','handoff_request_id'},
                'exact raw joint record required')
        capture,sent,response = record['capture'],record['request'],record['response']
        post=record['post_model_capture']
        require(post['status']=='captured' and post['state']==capture['state']
                and post['native']==capture['native'],'actual post-model scene differs')
        require(isinstance(record['signing_captures'],list) and len(record['signing_captures']) <= 48
                and all(c['status']=='captured' and c['state']==post['state'] and c['native']==post['native']
                        for c in record['signing_captures']),'actual permission-stage scene differs')
        require(sent['request_id'] not in seen and sent['runtime_freeze_sha256']==freeze_sha,'duplicate/wrong raw model request')
        seen.add(sent['request_id'])
        require(sent['task']==task and sent['binding_sha256']==digest(capture['state'])
                and sent['scene']==semantic(capture['native']),'actual model scene/task differs from UI capture')
        observed = validate_response(response,sent,model_identity)
        user_step = step_input(task,sent['scene'])
        selected = None
        for call in observed['calls']:
            expected = (render_selection(tokenizer,user_step,tools).prompt if call['stage']=='selector'
                        else render_invocation(tokenizer,user_step,tools,selected).prompt)
            require(call['prompt_sha256']==hashlib.sha256(expected.encode()).hexdigest(),'actual same-contract prompt differs')
            calls += 1
            if call.get('parsed') and call['stage']=='selector': selected = parse_selection(call['raw'],tools)
        handoff = record['handoff_request_id']
        if handoff is None:
            # A legal-but-denied call is not task success. Policy audit must
            # separately explain it; this component only proves zero dispatch.
            continue
        require(record['signing_captures'],'no fresh native scene read at permission decision')
        require(observed['status']=='schema_valid_not_authorized','failed/abstained model dispatched')
        rebound = rebind_observation(response,sent,model_identity,capture['state'])
        parsed = parse_invocation(observed['calls'][1]['raw'],selected,tools)
        receipt = by_id.get(handoff)
        require(receipt is not None and handoff not in used and receipt['before_state']==capture['state']
                and receipt['before']==capture['native'] and receipt['payload']['expected']==rebound['scene_binding']
                and receipt['payload']['operation']==parsed['name']
                and receipt['payload']['arguments']==parsed['arguments'],'raw model/native operation or scene binding differs')
        require(receipt.get('stable_idle_samples')==3 and len(receipt.get('settling_samples',[])) >= 3
                and receipt['settling_samples'][-1]==receipt['settling_samples'][-2]==receipt['settling_samples'][-3]
                and receipt['settling_samples'][-1]['native']==receipt['after']
                and receipt['settling_samples'][-1]['state']==receipt['after_state'],'native readback not stably settled')
        used.add(handoff)
    require(used==set(by_id),'unaccounted/extra native execution')
    ledger = audit_permission_execution(consent_db,fixture_db,receipts,
             task_sha256=hashlib.sha256(task.encode()).hexdigest(),owner_freeze_sha256=freeze_sha,
             handoff_table='c5_model_handoff')
    return {'status':'raw_model_scene_permission_native_chain_verified_component_only',
            'model_generation_calls':calls,'native_executions':len(receipts),'ledger':ledger,
            'source_assets_environment_verified':False,'lifecycle_verified':False,
            'complete_C5_engineering_gate_passed':False,'formal_task_passed':False}


def audit_lifecycle(bootstrap,created,close,stop,last_native,source_sha,*,key_present):
    """Cross-bind raw actual lifecycle without trusting cleanup success flags."""
    require(close['status']=='closed' and stop['status']=='stopped' and key_present is False,
            'known close/stop and actual key absence required')
    c = close['close_capture']
    require(created['fixture_serial']==bootstrap['fixture_serial']==c['fixture_serial']
            and created['active_serial']==bootstrap['active_serial']==c['before_close_active_serial']==c['after_close_active_serial']
            and c['fixture_registry_absent'] is True and c['fixture_before_close_native']==last_native
            and close['key_absence']=={'key_removed':True,'actual_absence_checked':True}
            and stop['hook_removed_in_same_callback'] is True
            and close['source_sha256']==stop['source_sha256']==bootstrap['source_sha256']==source_sha,
            'fixture/source/key/unhook lifecycle identity differs')
    require(c['initial_active_sha256']==c['before_close_active_sha256']==c['after_close_active_sha256']
            ==bootstrap['active_sha256']==close['active_sha256']==stop['active_sha256'],
            'activity document content changed')
    require(created['rhino_major']==8 and created['python_major_minor']==[3,9], 'native runtime family differs')
    return {'status':'raw_lifecycle_component_verified','had_failure':stop['had_failure'],
            'formal_task_passed':False,'complete_C5_engineering_gate_passed':False}


def audit_geometry(before,after,frozen_assertions,*,read_result=None):
    # Keep the existing independent solid/mass/topology/non-target scorer.
    return score_readback(before,after,frozen_assertions,read_result=read_result)
