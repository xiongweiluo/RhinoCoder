"""Owner-only prospective failed-step raw audit; never rewrites old verdicts."""
import hashlib
from pathlib import Path
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_research_channel import read_json
from training.c5_modelbridge_runtime import file_sha


def _read(path):
    return read_json(path.parent, path.name)


def verify_model_steps(result, slot, case, freeze, tokenizer):
    from training.c5_formal20_plan import model_view
    from training.c5_formal_reuse_model_wire import validate_response, rebind_observation
    from training.c5_rhino_adapter import step_input
    from training.c5_modelbridge_joint_audit import semantic
    from training.c5_contract import render_selection, render_invocation, parse_selection
    from training.c5_inventory import load_public_mcp_tools
    tools=load_public_mcp_tools()
    for step in result['steps']:
        response=step['response'];require(type(response) is dict,'slot_tail_incomplete_failed_model_evidence')
        sent,wire=response['wire_request'],response['wire_response']
        require(sent['task']==model_view(case) and sent['slot_id']==slot['slot_id'] and sent['step_index']==step['step_index']
            and sent['scene']==semantic(step['before']['native']),'slot_tail_model_scene_binding')
        observed=validate_response(wire,sent,freeze['model_identities'][slot['route']])
        require(rebind_observation(wire,sent,freeze['model_identities'][slot['route']],step['before']['state'])==step['observation'],
            'slot_tail_raw_model_observation')
        user=step_input(sent['task'],sent['scene']);selected=None
        for call in observed['calls']:
            prompt=(render_selection(tokenizer,user,tools).prompt if call['stage']=='selector'
                else render_invocation(tokenizer,user,tools,selected).prompt)
            require(hashlib.sha256(prompt.encode()).hexdigest()==call['prompt_sha256'],'slot_tail_raw_model_prompt')
            if call['stage']=='selector' and call.get('parsed'):selected=parse_selection(call['raw'],tools)


def verify_failed_sequence(directory, result, freeze):
    from training.c5_formal_reuse_model_native_audit import audit_lifecycle
    requests=sorted(directory.glob('request-*.json'));expected=[];executions=[]
    require(bool(requests) and [p.name for p in requests]==['request-%04d.json'%n for n in range(1,len(requests)+1)],'slot_tail_request_population')
    initial=_read(directory/'response-0001.json');require(initial['status']=='captured'
        and initial['native']==result['initial_native'],'slot_tail_initial_capture')
    prior=initial;expected.append(('capture',initial));failed_seq=None
    failures=[s for s in result['steps'] if 'failure' in s]
    require(len(failures)==1 and failures[0] is result['steps'][-1]
        and failures[0]['failure']['stage']=='native_execute','slot_tail_only_known_terminal_native_failure')
    for step in result['steps']:
        require(step['before']==prior and step['post_model_capture']==step['before'],'slot_tail_scene_chain')
        expected.extend([('capture',step['before']),('capture',step['post_model_capture'])])
        signing=directory/('signing-%d.json'%step['step_index'])
        if signing.exists():
            signed=_read(signing)
            require(signed['capture']==step['before'] and all(c==step['before'] for c in signed['signing_captures']),
                'slot_tail_signing_captures')
            expected.extend(('capture',c) for c in signed['signing_captures'])
        if 'failure' in step:
            require(signing.exists() and step['receipt'] is None,'slot_tail_failed_handoff_binding')
            failed_seq=len(expected)+1;failed=_read(directory/('response-%04d.json'%failed_seq))
            require(failed.get('status')=='failed_no_retry' and failed.get('error_type')=='NativeError'
                and failed.get('error')=='expired/oversized handoff TTL','slot_tail_only_known_ttl_refusal')
            sent=_read(directory/('request-%04d.json'%failed_seq))['envelope']['payload']
            require(signed['handoff_request_id']==sent['request_id'] and sent['expected']==step['before']['state'],
                'slot_tail_failed_handoff_binding')
            expected.append(('execute',failed));prior=step['before']
        elif step['receipt'] is not None:
            expected.append(('execute',step['receipt']))
            prior={'status':'captured','state':step['receipt']['after_state'],'native':step['receipt']['after'],
                'active_sha256':step['before']['active_sha256']}
        else:prior=step['post_model_capture']
    closed=_read(directory/('response-%04d.json'%(len(expected)+1)))
    stopped=_read(directory/('response-%04d.json'%(len(expected)+2)))
    expected.extend([('close',closed),('stop',stopped)])
    require(len(expected)==len(requests),'slot_tail_request_population')
    for i,(action,value) in enumerate(expected,1):
        sent=_read(directory/('request-%04d.json'%i));actual=_read(directory/('response-%04d.json'%i))
        require(actual==value and (sent['kind']=='execute' if action=='execute' else
            sent['kind']=='control' and sent['envelope']['payload']['action']==action),'slot_tail_native_response_binding')
    capture=closed['close_capture']
    require(capture['fixture_before_close_native']==prior['native'] and stopped['had_failure'] is True,
        'slot_tail_close_scene_changed')
    proof=audit_lifecycle(_read(directory/'bootstrap.json'),_read(directory/'engine-created.json'),closed,stopped,
        prior['native'],freeze['source_inventory_sha256'],key_present=(directory/'handoff.key').exists())
    require(proof['had_failure'] is True,'slot_tail_failure_erased')
    return failed_seq,failed,closed,stopped


def audit_failed_native_ttl(state, slot, case, result, freeze, tokenizer):
    read = _read
    from training.c5_research_audit import _tables
    from plugin.rhino_listener.c5_research_native import READS
    directory=state/slot['slot_id']
    sequence, failed, closed, stopped = verify_failed_sequence(directory, result, freeze)
    backups=read(directory/'database-backups.json')
    require(set(backups)=={'consent','fixture'} and all(file_sha(directory/(n+'-audit.sqlite3'))==h for n,h in backups.items()),'slot_tail_database_backup_binding')
    consent=_tables(directory/'consent-audit.sqlite3',('consent_requests','consent_events','c5_model_handoff'))
    ledger=_tables(directory/'fixture-audit.sqlite3',('candidate_write','c5_read'))
    sent=read(directory/('request-%04d.json'%sequence))['envelope']['payload'];rid=sent['request_id']
    context=failed.get('ttl_observation')
    require(type(context) is dict and set(context)=={'gate_epoch','expires_at','maximum_ttl_seconds'}
        and type(context['gate_epoch']) in (int,float) and context['expires_at']==sent['expires_at']
        and context['maximum_ttl_seconds']==300 and context['gate_epoch']>=sent['expires_at'],
        'slot_tail_expired_ttl_clock_proof_required')
    writes={r['idempotency_key']:r for r in ledger['candidate_write']};reads={r['request_id']:r for r in ledger['c5_read']}
    permits={r['request_id']:r for r in consent['consent_requests']};handoffs={r['request_id']:r for r in consent['c5_model_handoff']}
    require(hashlib.sha256(rid.encode()).hexdigest() not in writes and rid not in reads and not (directory/('execute-%04d.json'%sequence)).exists(),'slot_tail_failed_request_dispatched')
    require(handoffs[rid]['state']=='issued' and handoffs[rid]['payload_sha256']==digest(sent),'slot_tail_signature')
    if sent['operation'] not in READS:
        permit=permits[rid];require(permit['status']=='consumed' and digest(permit)==sent['consent_row_sha256'] and permit['task_sha256']==sent['task_sha256'] and permit['tool_name']==sent['operation'] and permit['arguments_sha256']==digest(sent['arguments']) and permit['expires_at']==sent['expires_at'],'slot_tail_signature')
        events=sorted((r for r in consent['consent_events'] if r['request_id']==rid),key=lambda r:r['event_id'])
        require([r['event_type'] for r in events]==['requested','approved','consumed','signed_handoff_issued'] and events[-1]['reason_code']==digest(sent),'slot_tail_signature')
    else:require(sent['consent_row_sha256'] is None and rid not in permits,'slot_tail_signature')
    completed=[]
    for p in sorted(directory.glob('request-*.json')):
        request=read(p);response=read(p.with_name(p.name.replace('request','response')))
        if request['kind']=='execute' and response.get('status')=='done':completed.append(response)
    # Preserve the original strict auditor's refusal for an issued, unexecuted
    # handoff. Do not delete rows/project a database to make that auditor pass.
    from training.c5_research_audit import audit_permission_execution
    original_passed=False; original_refusal=None
    try:audit_permission_execution(directory/'consent-audit.sqlite3',directory/'fixture-audit.sqlite3',completed,task_sha256=sent['task_sha256'],owner_freeze_sha256=digest(freeze));original_passed=True
    except Exception as error:
        require(str(error) in {'unaccounted reservation/permission','unaccounted model handoff'},'slot_tail_unexpected_permission_refusal')
        original_refusal=str(error)
    require(not original_passed,'slot_tail_component_population')
    used_handoffs={r['payload']['request_id'] for r in completed}
    require(used_handoffs|{rid}==set(handoffs) and len(handoffs)==len(consent['c5_model_handoff']),'slot_tail_component_population')
    require({r['payload']['request_id'] for r in completed if r['payload']['operation'] not in READS}|({rid} if rid in permits else set())==set(permits),'slot_tail_component_population')
    for r in completed:
        payload=r['payload'];key=hashlib.sha256(payload['request_id'].encode()).hexdigest()
        require(handoffs[payload['request_id']]['state']=='issued' and handoffs[payload['request_id']]['payload_sha256']==digest(payload),'slot_tail_signature')
        if payload['operation'] in READS:
            row=reads[payload['request_id']];require(row['state']=='done' and row['payload_sha256']==digest(payload) and row['result_sha256']==r['result_sha256'],'slot_tail_component_population')
        else:
            row=writes[key];permit=permits[payload['request_id']]
            require(row==r['ledger_row'] and row['state']=='done' and row['request_sha256']==digest({'operation':payload['operation'],'arguments':payload['arguments']}) and row['result_sha256']==r['result_sha256'] and permit['status']=='consumed' and digest(permit)==payload['consent_row_sha256'],'slot_tail_component_population')
    require({hashlib.sha256(r['payload']['request_id'].encode()).hexdigest() for r in completed if r['payload']['operation'] not in READS}==set(writes) and {r['payload']['request_id'] for r in completed if r['payload']['operation'] in READS}==set(reads),'slot_tail_component_population')
    from plugin.rhino_listener.c5_research_gate import ResearchGate
    gate=object.__new__(ResearchGate);gate.secret=bytes.fromhex(read(state/('audit-key-custody/'+slot['slot_id']+'.json'))['key_hex']);gate.owner_freeze=digest(freeze);gate.task_sha=sent['task_sha256'];gate.clock=lambda:sent['expires_at']
    reproduced=False
    try:gate._payload(read(directory/('request-%04d.json'%sequence))['envelope'])
    except Exception as error:reproduced=str(error)=='expired/oversized handoff TTL'
    require(reproduced,'slot_tail_last_tail')
    verify_model_steps(result, slot, case, freeze, tokenizer)
    require(not result.get('cleanup_errors') and result['close']=='closed' and result['stop']=='stopped'
        and result.get('stop_had_failure') is True,'slot_tail_cleanup_unknown')
    return {'raw_failed_step_verified':True,'cleanup_verified':True,'permission_safe':True,
        'failed_request_native_dispatches':0,'issued_rejected_handoffs':1,
        'original_strict_permission_auditor_passed':False,'original_permission_refusal':original_refusal,
        'ttl_boundary_reproduced':True,'task_result_rewritten':False,
        'resume_only_unattempted_safe':True,'quality_retry_authorized':False}
