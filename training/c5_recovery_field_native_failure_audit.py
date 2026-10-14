"""Independent known first hub cleanup for recoverable pre-slot failures.

Partially opened fixtures require a separate raw reconciliation; a producer
boolean cannot authorize a retry. This reducer reads retained ORIGINAL private
audit key custody only after the exact-approved attempt, never in preparation.
"""
import hmac
import os
from pathlib import Path
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_channel import read_json
from training.c5_reuse_evidence import require,sha
from training.c5_reuse_native_audit import replay_native
from training.c5_lifecycle_timing_audit import audit_phase
from training.c5_host_assurance_audit import audit_host_continuity,audit_request_checkpoint_bindings
from training.c5_reuse_development_plan import ORDER

def audit_known_first_hub_stop(rows,binding,head,runtime):
    replay_native(rows,binding,head)
    if len(rows)==12:return audit_known_first_fixture_stop(rows,binding,head,runtime)
    require([r['kind'] for r in rows]==['native_controller_open','host_ready_before_remote_launch',
        'controller_retired_no_retry','failure_cleanup_intent','failure_cleanup_observed',
        'failure_cleanup_attempts_observed'],'recovery_native_failure_requires_known_pre_slot_raw')
    state=Path(binding['paths']['state_root']);source=sha(runtime['source_files'])
    require(rows[1]['payload']['release']==read_json(state,'entry-return-release.json')
        and rows[1]['payload']['ready']==read_json(state,'host-continuity-ready.json')
        and rows[1]['payload']['release']['source_inventory_sha256']==source
        and rows[3]['payload']=={'action':'stop','scope':'known_hub_only'}
        and rows[5]['payload']['errors']==[],'recovery_native_known_hub_cleanup_order')
    request=read_json(state,'hub-request-0001.json');response=read_json(state,'hub-response-0001.json')
    key=read_json(state/'audit-key-custody','hub.json');secret=bytes.fromhex(key['key_hex'])
    require(key['runtime_sha256']==binding['runtime_sha256'] and len(secret)==32
        and hmac.compare_digest(request['signature'],signature(secret,request['payload']))
        and request['payload']['action']=='stop' and request['payload']['slot_id'] is None
        and request['payload']['owner_freeze_sha256']==binding['runtime_sha256']
        and rows[4]['payload']=={'action':'stop','receipt':response}
        and response==read_json(state,'hub-stop.json') and response['status']=='hub_stopped'
        and response['opened_slots']==[] and response['unused_keys_removed']==list(ORDER)
        and response['hub_key_absence']=={'key_removed':True,'actual_absence_checked':True}
        and response['hook_removed_in_same_callback'] is True and response['had_failure'] is False,
        'recovery_native_signed_first_hub_stop')
    require({p.name for p in state.glob('hub-request-*.json')}=={'hub-request-0001.json'}
        and {p.name for p in state.glob('hub-response-*.json')}=={'hub-response-0001.json'}
        and not os.path.lexists(state/'hub.key')
        and all(not os.path.lexists(state/slot/'handoff.key') for slot in ORDER),
        'recovery_native_no_open_fixture_and_dispatch_keys_absent')
    for role,name in (('hub','hub-service-time-0001.json'),('client','hub-client-time-0001.json')):
        audit_phase(read_json(state,name),role=role,sequence=1,freeze_sha=binding['runtime_sha256'],
                    request=request,response=response,cap=120)
    terminal=read_json(state,'host-continuity-terminal-receipt.json')
    host=audit_host_continuity(state/'host',binding['study_id'],binding['runtime_sha256'],source,terminal['seal_sha256'],
        normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    require(host['limited_visible_continuity_verified'] and terminal['blocked'] is False,'recovery_native_known_limited_detach')
    audit_request_checkpoint_bindings(state,(),binding['runtime_sha256'],journal_limit=4096,host_root=state/'host')
    return {'known_native_cleanup_complete':True,'raw_anchor_sha256':sha({'native_head':head,'host':host,'terminal':terminal}),
            'full_host_closure_or_memory_erasure_proven':False}


def audit_known_first_fixture_stop(rows,binding,head,runtime):
    """First model exchange failed BEFORE native dispatch; exact raw cleanup only.

    Missing ORIGINAL private signature input remains an error and reconciliation
    pause. This never repairs historical keys or promotes eight-slot evidence.
    """
    import hashlib
    import sqlite3
    from training.c5_modelbridge_joint_audit import audit_lifecycle
    from training.c5_lifecycle_joint_audit import audit_native_timing
    replay_native(rows,binding,head)
    require([r['kind'] for r in rows]==['native_controller_open','host_ready_before_remote_launch',
        'slot_open_intent','slot_model_scene','controller_retired_no_retry','failure_cleanup_intent',
        'failure_cleanup_observed','failure_cleanup_intent','failure_cleanup_observed',
        'failure_cleanup_intent','failure_cleanup_observed','failure_cleanup_attempts_observed'],
        'recovery_first_fixture_exact_partial_trace')
    state=Path(binding['paths']['state_root']);slot=ORDER[0];directory=state/slot
    require(rows[2]['payload']=={'slot_id':slot} and rows[3]['payload']['slot_id']==slot
        and rows[-1]['payload']['errors']==[]
        and [rows[i]['payload'] for i in (5,7,9)]==[
            {'action':'close','scope':'known_current_fixture_only'},
            {'action':'stop','scope':'known_current_fixture_only'},
            {'action':'stop','scope':'known_hub_only'}],'recovery_first_fixture_known_targets')
    source=sha(runtime['source_files']);ready=rows[1]['payload']
    require(ready['release']==read_json(state,'entry-return-release.json')
        and ready['ready']==read_json(state,'host-continuity-ready.json')
        and ready['release']['source_inventory_sha256']==source,'recovery_partial_preload_join')
    key=read_json(state/'audit-key-custody',slot+'.json');secret=bytes.fromhex(key['key_hex'])
    require(len(secret)==32 and key['runtime_sha256']==binding['runtime_sha256'],'recovery_original_fixture_key_custody')
    responses=(rows[3]['payload']['capture'],rows[6]['payload']['receipt'],rows[8]['payload']['receipt'])
    require({p.name for p in directory.glob('request-*.json')}=={'request-%04d.json'%i for i in (1,2,3)}
        and {p.name for p in directory.glob('response-*.json')}=={'response-%04d.json'%i for i in (1,2,3)}
        and not list(directory.glob('execute-*.json')),'recovery_partial_no_dispatch_population')
    for i,(action,response) in enumerate(zip(('capture','close','stop'),responses),1):
        message=read_json(directory,'request-%04d.json'%i);envelope=message['envelope'];payload=envelope['payload']
        require(message['kind']=='control' and payload['action']==action
            and payload['owner_freeze_sha256']==binding['runtime_sha256']
            and payload['task_sha256']==hashlib.sha256(rows[3]['payload']['request']['request']['task'].encode()).hexdigest()
            and hmac.compare_digest(envelope['signature'],signature(secret,payload))
            and read_json(directory,'response-%04d.json'%i)==response,'recovery_partial_fixture_signature_join')
    capture,close,stop=responses
    life=audit_lifecycle(read_json(directory,'bootstrap.json'),read_json(directory,'engine-created.json'),
        close,stop,capture['native'],source,key_present=os.path.lexists(directory/'handoff.key'))
    require(life['had_failure'] is False,'recovery_partial_fixture_cleanup_unknown')
    audit_native_timing(directory,binding['runtime_sha256'])
    db=sqlite3.connect((directory/'fixture.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:
        require(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            and all(db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]==0 for name in ('candidate_write','c5_read')),
            'recovery_partial_native_dispatch_not_absent')
    finally:db.close()
    key=read_json(state/'audit-key-custody','hub.json');hub_secret=bytes.fromhex(key['key_hex'])
    require(len(hub_secret)==32 and key['runtime_sha256']==binding['runtime_sha256'],'recovery_original_hub_key_custody')
    require({p.name for p in state.glob('hub-request-*.json')}=={'hub-request-0001.json','hub-request-0002.json'}
        and {p.name for p in state.glob('hub-response-*.json')}=={'hub-response-0001.json','hub-response-0002.json'},
        'recovery_partial_hub_population')
    for i,action in enumerate(('open','stop'),1):
        request=read_json(state,'hub-request-%04d.json'%i);payload=request['payload']
        require(payload['action']==action and payload['slot_id']==(slot if i==1 else None)
            and payload['owner_freeze_sha256']==binding['runtime_sha256']
            and hmac.compare_digest(request['signature'],signature(hub_secret,payload)),'recovery_partial_hub_signature')
    hub=read_json(state,'hub-stop.json')
    require(hub==rows[10]['payload']['receipt']==read_json(state,'hub-response-0002.json')
        and read_json(state,'hub-response-0001.json')=={'status':'slot_opened','slot_id':slot,
            'fixture_serial':read_json(directory,'engine-created.json')['fixture_serial']}
        and hub['status']=='hub_stopped' and hub['source_sha256']==source
        and hub['active_serial']==read_json(directory,'bootstrap.json')['active_serial']
        and hub['active_sha256']==close['active_sha256']
        and hub['hub_key_absence']=={'key_removed':True,'actual_absence_checked':True}
        and hub['opened_slots']==[slot] and hub['unused_keys_removed']==list(ORDER[1:])
        and hub['had_failure'] is False and hub['hook_removed_in_same_callback'] is True
        and not os.path.lexists(state/'hub.key')
        and all(not os.path.lexists(state/s/'handoff.key') for s in ORDER),'recovery_partial_all_dispatch_keys_absent')
    audit_native_timing(state,binding['runtime_sha256'],hub=True)
    terminal=read_json(state,'host-continuity-terminal-receipt.json')
    host=audit_host_continuity(state/'host',binding['study_id'],binding['runtime_sha256'],source,terminal['seal_sha256'],
        normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    require(host['limited_visible_continuity_verified'] and terminal['blocked'] is False,'recovery_partial_host_detach')
    audit_request_checkpoint_bindings(state,(slot,),binding['runtime_sha256'],journal_limit=4096,host_root=state/'host')
    return {'known_native_cleanup_complete':True,'raw_anchor_sha256':sha({'native_head':head,'host':host,'terminal':terminal}),
        'fixture_control_signatures_verified':3,'hub_control_signatures_verified':2,
        'complete_eight_gate_passed':False,'quality':None,'full_host_closure_or_memory_erasure_proven':False}
