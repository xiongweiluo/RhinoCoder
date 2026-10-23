"""Owner-only raw pre-exposure reconciliation; never launches or signals.

Missing evidence stays PAUSED_RECONCILIATION. Failure after global exposure
always consumes the sealed set, irrespective of operational cleanup results.
"""
import hashlib
import hmac
import os
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID
from training.c5_host_assurance_audit import audit_host_continuity
from training.c5_formal_reuse_evidence_audit import audit_supervisor

def audit_preexposure_failure(state,spec,freeze,campaign,terminal,*,package_recovery=False,prior_release_observation=None):
    current=campaign.observation()
    eligible=current['status']=='PAUSED_RECONCILIATION' and not current['active']
    if package_recovery:
        require('run_package' in freeze and current.get('package')==freeze['run_package'],
            'run_package_recovery_requires_current_approved_scope')
        eligible=current['status'] in ('LOADING','READY','PAUSED_RECONCILIATION','RETRYABLE_ENGINEERING')
    require(eligible and current['formal_consumed'] is False
        and current['attempts']==int(state.name.split('-')[-1]),
        'formal_reuse_failure_requires_unconsumed_paused_campaign')
    rows=campaign.log.rows()
    require(not any(r['kind'] in ('private_exposure_intent','generation_begin_intent') for r in rows),
        'formal_reuse_failure_private_exposure_sticky')
    forbidden=('formal20.started.json','private-cases.json','native-plans.json','native-prepared.json',
        'formal20.hub-initialization.claim.json','worker-bootstrap-request.json')
    require(all(not os.path.lexists(state/n) for n in forbidden)
        and not list(state.glob('*-model-request.json'))
        and not list(state.glob('hub-request-*.json')),'formal_reuse_failure_no_private_or_dispatch_prefix')
    permit=read_json(state,'load-permit.json')
    require(rows[:len(permit['rows'])]==permit['rows'] and permit['first_load_epoch']==current['first_load_epoch'],
        'formal_reuse_failure_original_campaign_permit')
    response=read_json(state,'preload-abort.response.json');request=read_json(state,'preload-abort.request.json')
    key=read_json(state/'audit-key-custody','hub.json')
    require(key['runtime_sha256']==digest(freeze) and request['payload']=={
        'action':'abort_uninitialized_native','runtime_freeze_sha256':digest(freeze)}
        and hmac.compare_digest(request['signature'],signature(bytes.fromhex(key['key_hex']),request['payload'])),
        'formal_reuse_failure_original_abort_signature')
    require(response['status']=='preload_aborted' and response['runtime_freeze_sha256']==digest(freeze)
        and response['request_sha256']==digest(request) and response['host_terminal']==terminal
        and response['hook_removed_in_same_callback'] is True
        and type(response['private_rows_read_by_native_arm']) is int
        and response['private_rows_read_by_native_arm']==0,'formal_reuse_failure_native_abort_binding')
    labels={'F%02d-%s'%(n,r) for n in range(1,21) for r in ('base','lora')}
    removed=response['unused_keys_removed']
    require(type(removed) is list and len(removed)==40 and {r['slot_id'] for r in removed}==labels,
        'formal_reuse_failure_exact_unused_key_removal')
    for label in labels:
        require(not os.path.lexists(state/label/'handoff.key')
            and not list((state/label).glob('request-*.json')),'formal_reuse_failure_unused_native_slot')
    require(all(set(r)=={'slot_id','key_removed','actual_absence_checked'}
        and r['key_removed'] is r['actual_absence_checked'] is True for r in removed)
        and response['hub_key_absence']=={'key_removed':True,'actual_absence_checked':True}
        and not os.path.lexists(state/'hub.key'),'formal_reuse_failure_hub_key_absent')
    host=audit_host_continuity(state,STUDY_ID,digest(freeze),freeze['source_inventory_sha256'],
        terminal['seal_sha256'],normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    require(host['limited_visible_continuity_verified'] is True,'formal_reuse_failure_host_continuity_unknown')
    supervisor=audit_supervisor(state,spec,freeze,completed=False,**({'prior_release_observation':prior_release_observation} if prior_release_observation is not None else {}))
    anchor={'campaign_head_sha256':rows[-1]['record_sha256'],'host':host,'native_abort':response,
        'qualified_gpu':supervisor,'raw_capture':read_json(state,'raw-streams-final.json')}
    if prior_release_observation is not None:anchor['prior_release_observation']=prior_release_observation
    return {'raw_anchor_sha256':digest(anchor),'capture_complete':True,'qualified_target_absent':True,
        'known_native_cleanup_complete':True,'private_exposure_absent':True}
