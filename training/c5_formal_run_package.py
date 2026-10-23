"""One approved package, the original campaign, finite pre-exposure recovery.

All mutation functions require the caller's real two-hash authority. Private
audit execution stays inside the owner's process; public views are closed.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_research_channel import read_json, publish_json
from plugin.rhino_listener.c5_run_package_policy import validate_policy, validate_layout, validate_migration
from training.c5_reuse_evidence import sha, exact


def replay_package_revision(state, row):
    p = row['payload']
    exact(p, ('scope', 'grant', 'previous_head_sha256', 'package', 'accounting_cutover'))
    from training.c5_recovery_policy import validate_scope, require_grant
    old, new = state['scope'], validate_scope(p['scope'])
    package = p['package']
    policy = validate_policy(package['policy'])
    validate_layout(package['layout']); migration = validate_migration(p['accounting_cutover'])
    require(not state['active'] and not state['formal_consumed'] and state['status'] in
            ('RETRYABLE_ENGINEERING', 'WAITING_OWNER', 'PREPARED', 'ATTEMPT_LIMIT_REACHED')
            and new!=old, 'run_package_revision_known_pause')
    require(all(new[k] == old[k] for k in ('campaign_id', 'phase', 'policy_sha256', 'history_sha256',
                'public_plan_sha256', 'contract_sha256'))
            and new['development_seconds_max'] == policy['gpu_residency_seconds_max']
            and new['generation_cutoff_epoch'] >= old['generation_cutoff_epoch'],
            'run_package_revision_preserves_research')
    grant = dict(p['grant'])
    require(grant.pop('previous_campaign_head_sha256') == p['previous_head_sha256']
            == row['previous_sha256'], 'run_package_revision_original_head')
    require_grant(new, grant)
    require(migration['legacy_first_load_epoch'] == state['first_load_epoch']
            and migration['prior_attempts_consumed'] == state['attempts']
            and migration['prior_campaign_head_sha256'] == p['previous_head_sha256']
            and migration['legacy_elapsed_debit_seconds'] >= state.get('charged_gpu_seconds',0)
            and migration['legacy_elapsed_debit_seconds'] < policy['gpu_residency_seconds_max'],
            'run_package_revision_keeps_consumption')
    state.update(scope=new, receipt=None, status='WAITING_OWNER', package=package,
                 accounting_cutover=migration, attempts_max=policy['global_preexposure_loads_max'],
                 charged_gpu_seconds=migration['legacy_elapsed_debit_seconds'], settled_attempts=state.get('settled_attempts',[]),
                 package_start_attempt=state['attempts'], package_owner_consent=False,package_preload_attempt=None)


def replay_package_event(state, kind, payload):
    require(state['package'] is not None, 'run_package_event_without_approved_package')
    if kind=='package_owner_session_confirmed':
        exact(payload,('scope_sha256','automatic_receipt_capture','manual_host_ready_attestation','before_model_loading'))
        require(not state['active'] and not state['formal_consumed'] and not state['package_owner_consent']
            and payload=={'scope_sha256':sha(state['scope']),'automatic_receipt_capture':True,
                'manual_host_ready_attestation':False,'before_model_loading':True},'run_package_actual_session_consent')
        state['package_owner_consent']=True
        state['receipt']={'package_session':payload}
        state['status']='PREPARED'
    elif kind == 'package_owner_custody_consent':
        exact(payload, ('scope_sha256', 'automatic_receipt_capture', 'manual_per_receipt_attestation'))
        require(not state['active'] and state['receipt'] is not None
                and payload == {'scope_sha256': sha(state['scope']), 'automatic_receipt_capture': True,
                                'manual_per_receipt_attestation': False}, 'run_package_owner_consent_binding')
        state['package_owner_consent'] = True
    elif kind=='package_preload_observed':
        exact(payload,('scope_sha256','attempt','host_ready_sha256','snapshot_sha256','manual_owner_attestation'))
        require(state['package_owner_consent'] and not state['active'] and not state['formal_consumed']
            and payload['scope_sha256']==sha(state['scope']) and payload['attempt']==state['attempts']+1
            and payload['manual_owner_attestation'] is False
            and all(type(payload[k]) is str and len(payload[k])==64 and all(c in '0123456789abcdef' for c in payload[k])
                    for k in ('host_ready_sha256','snapshot_sha256')), 'run_package_automatic_preload_is_not_manual_attestation')
        state['package_preload_attempt']=payload['attempt']
    elif kind == 'gpu_residency_settled':
        exact(payload, ('attempt', 'start_epoch', 'stop_epoch', 'charged_seconds', 'proof_sha256'))
        require(not state['active'] and payload['attempt'] == state['attempts']
                and payload['attempt'] not in state['settled_attempts']
                and payload['start_epoch'] == state['load_intent_epoch']
                and all(type(payload[k]) in (int, float) and __import__('math').isfinite(payload[k])
                        for k in ('start_epoch', 'stop_epoch', 'charged_seconds'))
                and 0 <= payload['stop_epoch']-payload['start_epoch'] <= payload['charged_seconds']
                and type(payload['proof_sha256']) is str and len(payload['proof_sha256']) == 64,
                'run_package_raw_residency_settlement')
        state['charged_gpu_seconds'] += payload['charged_seconds']
        state['settled_attempts'].append(payload['attempt'])
    else:
        raise ValueError('run_package_unknown_event')


def verify_package_prefix(package, rows):
    prefix = package['prior_campaign_events']
    require(rows[:len(prefix)] == prefix and prefix
            and prefix[-1]['record_sha256'] == package['timing_migration']['prior_campaign_head_sha256'],
            'run_package_original_campaign_prefix')


def activate_package(spec, freeze, grant):
    """Only the approval registrar calls this, never preparation or status."""
    from plugin.rhino_listener.c5_formal_reuse_scope import authority
    from training.c5_formal_reuse_revision import initial_scope, verify_endpoint
    from training.c5_formal_reuse_admission import ROOTS, NAMESPACE, FormalCampaign, campaign_scope, formal_replay
    from training.c5_recovery_storage import EvidenceLog
    from training.c5_recovery_policy import POLICY
    authority(spec, freeze, grant)
    package = spec['run_package']; validate_policy(package['policy'])
    log = EvidenceLog(ROOTS['mac']/NAMESPACE/'ledger', initial_scope(spec, freeze), verify_endpoint('mac', freeze))
    try:
        rows = log.rows(); verify_package_prefix(package, rows)
        current = formal_replay(log.binding, rows)
        if current['scope'] == campaign_scope(spec, freeze):
            require(current['attempts'] == package['timing_migration']['prior_attempts_consumed']
                    and not current['active'], 'run_package_already_consumed')
            return {'status': 'run_package_already_registered', 'research_restarted': False}
        require(rows == package['prior_campaign_events'], 'run_package_unreviewed_history_append')
        campaign = FormalCampaign(current['scope'], log)
        if current['status'] == 'PAUSED_RECONCILIATION':
            # Read-only audit of the immutable old actor. Never manufacture an
            # owner manual receipt or run an old model entry.
            proof = audit_previous_attempt(package)
            campaign.reconcile('startup', proof)
        current = campaign.observation()
        require(not current['active'] and not current['formal_consumed'], 'run_package_prior_cleanup_unknown')
        revised = campaign_scope(spec, freeze); head = log.rows()[-1]['record_sha256']
        migration = dict(package['timing_migration'])
        migration.update(cutover_epoch=time.time(), prior_campaign_head_sha256=head)
        validate_migration(migration)
        evidence = {'actor': 'repository_owner', 'approved': True, 'protocol': POLICY['protocol'],
                    'scope_sha256': sha(revised), 'spec_sha256': revised['spec_sha256'],
                    'runtime_sha256': revised['runtime_sha256'], 'policy_sha256': sha(POLICY),
                    'previous_campaign_head_sha256': head}
        campaign._event('run_package_revision_accepted', {'scope': revised, 'grant': evidence,
            'previous_head_sha256': head, 'package': package, 'accounting_cutover': migration})
        return {'status': 'run_package_registered_waiting_private_entry',
                'attempts_consumed': current['attempts'], 'first_load_epoch': current['first_load_epoch'],
                'research_restarted': False}
    finally:
        log.close()


def audit_previous_attempt(package):
    source = Path(package['previous_mac_source_root'])
    state = Path(package['previous_mac_attempt_root'])
    require(source.is_absolute() and state.is_absolute() and source.resolve() == source and state.resolve() == state,
            'run_package_prior_fixed_paths')
    # The source population is independently frozen by the package assembler.
    pins = package['previous_public_source_files']
    require({p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == set(pins)
            and all(not (source/n).is_symlink() and hashlib.sha256((source/n).read_bytes()).hexdigest() == h
                    for n, h in pins.items()), 'run_package_prior_actor_bytes')
    script = """import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from training.c5_formal_reuse_field_scope import scope
from training.c5_formal_reuse_admission import open_formal_campaign
from training.c5_formal_reuse_failure_audit import audit_preexposure_failure
from plugin.rhino_listener.c5_research_channel import read_json
s,f,g,guard=scope(check_time=False)
c=open_formal_campaign(s,f,g,f['history'])
try:
 guard();p=Path(sys.argv[2]);proof=audit_preexposure_failure(p,s,f,c,read_json(p,'host-continuity-terminal-receipt.json'));guard()
 print(json.dumps(proof,sort_keys=True))
finally:c.log.close()
"""
    from plugin.rhino_listener.c5_followup_profile import MAC_FLAGS
    result = subprocess.run(['/opt/anaconda3/bin/python3.13', *MAC_FLAGS, '-c', script, str(source), str(state)],
                            capture_output=True, timeout=180)
    require(result.returncode == 0, 'run_package_original_failure_evidence_incomplete')
    proof = json.loads(result.stdout)
    require(set(proof) == {'raw_anchor_sha256', 'capture_complete', 'qualified_target_absent',
                          'known_native_cleanup_complete', 'private_exposure_absent'}
            and all(proof[k] is True for k in proof if k != 'raw_anchor_sha256'),
            'run_package_original_failure_proof')
    return proof


def automatic_reconcile(campaign, state, spec, freeze, *, error='startup'):
    """Evidence-driven decision. Missing/ambiguous proof pauses, never retires."""
    from training.c5_formal_reuse_failure_audit import audit_preexposure_failure
    value = campaign.observation()
    if value['formal_consumed']:
        return 'FORMAL_CONSUMED_NO_RETRY'
    terminal = read_json(state, 'host-continuity-terminal-receipt.json')
    proof = audit_preexposure_failure(state, spec, freeze, campaign, terminal)
    settle_known_load(campaign,state,digest(proof))
    return campaign.reconcile(error, proof)


def settle_known_load(campaign,state,proof_sha):
    value=campaign.observation()
    settlement=read_json(state,'resource-settlement.json')
    final=read_json(state,'export-supervisor-original.json')['final']
    require(final['child_exit_reaped'] is True and type(final['child_wait_status']) is int,
            'run_package_settlement_requires_original_exit')
    start=value['load_intent_epoch'];stop=max(final['epoch'],settlement['stop_epoch'])
    if value['attempts'] not in value['settled_attempts']:
        campaign._event('gpu_residency_settled',{'attempt':value['attempts'],'start_epoch':start,
            'stop_epoch':stop,'charged_seconds':max(stop-start,settlement['elapsed_seconds_including_load_and_idle']),
            'proof_sha256':proof_sha})


def capture_owner_receipt(state, spec, freeze, *, output=print):
    """Actual journal receipt, displayed and durably saved under prior consent.

    This is explicitly not a claim of manual external-terminal attestation.
    """
    terminal = read_json(state, 'host-continuity-terminal-receipt.json')
    require(terminal['study_id'] == spec['study_id'], 'run_package_actual_receipt_scope')
    from training.c5_host_assurance_audit import audit_host_continuity
    audit_host_continuity(state, spec['study_id'], digest(freeze), freeze['source_inventory_sha256'],
                          terminal['seal_sha256'], normal_limit=2048, cleanup_limit=256, journal_limit=4096)
    output('C5_FORMAL_REUSE_HOST_EXTERNAL_RECEIPT ' + json.dumps(terminal, sort_keys=True))
    value = {'receipt': terminal, 'custody': 'owner_authorized_automatic_capture',
             'manual_external_receipt_attestation': False, 'runtime_sha256': digest(freeze)}
    if not (state/'owner-automatic-receipt-custody.json').exists():
        publish_json(state, 'owner-automatic-receipt-custody.json', value)
    else:
        require(read_json(state, 'owner-automatic-receipt-custody.json') == value, 'run_package_receipt_changed')
    return terminal


def public_status(campaign, state):
    from training.c5_formal_reuse_public_progress import read_public_progress
    v = campaign.observation(); package = v.get('package')
    return {'schema_version': 1, 'study_id': v['scope']['campaign_id'],
            'package_id': package['layout']['package_id'] if package else None,
            'status': v['status'], 'attempts_consumed': v['attempts'], 'attempts_max': v['attempts_max'],
            'first_load_epoch': v['first_load_epoch'], 'private_exposure_recorded': v['formal_consumed'],
            'gpu_charged_seconds': v.get('charged_gpu_seconds'),
            'current_load_unsettled':v['active'] or (package is not None and v['attempts']>v['package_start_attempt'] and v['attempts'] not in v['settled_attempts']),
            'timeline_elapsed_seconds':max(0,time.time()-v['first_load_epoch']) if v['first_load_epoch'] else 0,
            'lease_expiry_epoch':package['lease_expiry_epoch'] if package else None,
            'legacy_wall_policy_rejudged':False,
            'progress': read_public_progress(state), 'private_content_included': False,
            'owner_audit_summary_present': (state/'owner-public-audit-summary.json').is_file()}
