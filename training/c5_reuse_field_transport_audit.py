"""Independent two-endpoint raw join; imports neither channel nor peer producer."""
from training.c5_reuse_evidence import canonical, require, sha, strict
from training.c5_reuse_field_scope import common_scope
from training.c5_reuse_field_journal import replay_records
from training.c5_reuse_field_wire import approved_request, validate_peer_result, FRAME_LIMIT, frame
from training.c5_reuse_generation_audit import audit_generation

NATIVE_KINDS=frozenset(('native_handoff_open','native_handoff_intent','native_signing_capture',
    'native_no_permission','native_permission_intent','native_signed_handoff','native_dispatch_observed','native_handoff_retired'))


def audit_controller(rows,binding,head,plans):
    replay_records(rows,binding,'controller',head)
    request=None; sent=False; received=b''; completed=[]; intents=[]; retired=False; invalid=False; failed_model=False
    for row in rows[1:]:
        require(not retired and not failed_model,'field_wire_after_retirement')
        kind,p=row['kind'],row['payload']
        if kind=='wire_intent':
            require(request is None and set(p)=={'request_sha256','frame_hex'} and type(p['frame_hex']) is str
                    and len(p['frame_hex'])<=FRAME_LIMIT*2,'field_wire_intent')
            raw=bytes.fromhex(p['frame_hex']); request=strict(raw,limit=FRAME_LIMIT)
            approved_request(binding,request,plans)
            require(frame(request)==raw and sha(request)==p['request_sha256'], 'field_wire_request_bytes')
            key=(request['request']['slot_id'],request['request']['step_index'])
            require(key not in {v[0] for v in intents} and len(intents)<56,'field_wire_duplicate')
            intents.append((key,request)); sent=False; received=b''; invalid=False
        elif kind=='wire_sent':
            require(request is not None and not sent and set(p)=={'request_sha256','bytes'}
                    and p['request_sha256']==sha(request) and type(p['bytes']) is int
                    and p['bytes']==len(frame(request)), 'field_wire_sent')
            sent=True
        elif kind=='wire_received':
            require(request is not None and sent and set(p)=={'request_sha256','raw_hex','observed_bytes','truncated'}
                    and p['request_sha256']==sha(request) and type(p['observed_bytes']) is int
                    and p['observed_bytes']>=0 and type(p['truncated']) is bool
                    and type(p['raw_hex']) is str and len(p['raw_hex'])<=65536,'field_wire_received')
            raw=bytes.fromhex(p['raw_hex'])
            require(raw.hex()==p['raw_hex'] and len(raw)==min(32768,p['observed_bytes'])
                    and p['truncated']==(p['observed_bytes']>32768),'field_wire_received_bytes')
            received+=raw
            invalid=invalid or p['truncated'] or p['observed_bytes']==0 or len(received)>FRAME_LIMIT
        elif kind=='wire_ack':
            require(request is not None and sent and not invalid and set(p)=={'request_sha256','frame_sha256'}
                    and p['request_sha256']==sha(request) and 0<len(received)<=FRAME_LIMIT
                    and received.endswith(b'\n') and received.count(b'\n')==1,'field_wire_ack')
            result=strict(received,limit=FRAME_LIMIT)
            require(frame(result)==received and sha(result)==p['frame_sha256'],'field_wire_ack_bytes')
            observed=validate_peer_result(binding,request,result)
            failed_model=observed['status']=='operational_failure_no_retry'
            completed.append((request,result)); request=None
        elif kind=='wire_retired':
            require(set(p)=={'error_type'} and type(p['error_type']) is str,'field_wire_retired')
            retired=True
        elif kind in NATIVE_KINDS:
            pass  # Separate mandatory native reducer verifies these events.
        else: raise ValueError('field_wire_unknown_event')
    return {'intents':intents,'completed':completed,'retired':retired,
            'complete':bool(intents) and request is None and not retired and not invalid and head is not None}


def audit_join(controller,worker,mac,gpu,controller_head,worker_head,plans,tokenizer):
    require(mac['endpoint']=='mac' and gpu['endpoint']=='gpu'
            and common_scope(mac)==common_scope(gpu),'field_join_master_scope')
    control=audit_controller(controller,mac,controller_head,plans)
    generation=audit_generation(worker,gpu,worker_head,plans=plans,tokenizer=tokenizer)
    requests=[]; results=[]
    for row in worker:
        if row['kind']=='request_intent': requests.append(row['payload']['envelope'])
        elif row['kind']=='model_receipt': results.append(row['payload']['result'])
    matched=len(requests)==len(control['intents']) and len(results)==len(control['completed'])
    if matched:
        require(canonical(requests)==canonical([v[1] for v in control['intents']]),'field_join_request_bytes')
        require(canonical(results)==canonical([v[1] for v in control['completed']]),'field_join_response_bytes')
    return {'model_request_intents':len(control['intents']),'model_acknowledgements':len(control['completed']),
            'generation':generation,'complete_raw_join':matched and control['complete'] and generation['coverage_complete'],
            'actual_physical_generation_total_independently_proven':None,
            'native_permission_dispatch_cleanup_independently_verified':False,
            'external_witness_origin_verified':False,'execution_ready':False}
