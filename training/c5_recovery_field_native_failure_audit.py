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
