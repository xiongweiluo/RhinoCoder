"""Owner-only prior-tail preservation. No writes, actors or historical rejudgment."""
import re, json
from pathlib import Path
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import require, digest
from training.c5_slot_tail_storage import evidence_inventory


def check_review(summary, settlement, reference):
    require(digest(summary)==reference['summary_sha256']
        and digest(settlement)==reference['settlement_sha256'], 'slot_tail_prior_public_anchor')
    require(summary['status']=='original_joint_review_procedure_finished_with_rejections'
        and summary['audit_procedure_finished'] is True
        and summary['full_original_raw_joint_gate_passed'] is False
        and summary['resume_authority'] is False and summary['research_restarted'] is False
        and summary['cleanup']['native_cleanup_verified'] is True
        and summary['cleanup']['host_continuity_audit_verified'] is True
        and summary['cleanup']['package_dispatcher_detached'] is True
        and summary['campaign_unchanged_during_close_audit'] is True
        and summary['all_original_nonkey_evidence_preserved'] is True,
        'slot_tail_prior_closed_review_not_original_pass')
    bad=[c for c in summary['components'] if c['status']!='verified']
    require(len(summary['components'])==33 and len(bad)==1
        and bad[0]['component']=='original_frozen_phase_auditor_unchanged'
        and bad[0]['public_error_literal']=='slot_final_exact_claim_population',
        'slot_tail_prior_exact_refusal_retained')
    require(summary['attempts_consumed']==settlement['attempts_consumed']==4
        and summary['campaign_head_sha256']==settlement['campaign_head_sha256']==reference['campaign_head_sha256']
        and summary['first_load_epoch']==settlement['first_load_epoch']==1792692329.837715
        and summary['gpu_charged_seconds']==settlement['gpu_charged_seconds_after']==70340.89651274681
        and summary['private_content_included'] is settlement['private_content_included'] is False,
        'slot_tail_prior_consume_clock_residency')
    return True


def verify_preservation(before, after, summary):
    require(digest(before)=='6b3cb059893852dc963284f6deade3577803e9b6cc59c617dea7f763b46889f9',
        'slot_tail_prior_before_inventory')
    return preservation_delta(before,after,summary)


def preservation_delta(before,after,summary):
    removed=set(before)-set(after);added=set(after)-set(before)
    expected_removed={n for n in before if n=='hub.key' or n.endswith('/handoff.key')}
    require(removed==expected_removed and len(removed)==30
        and all(before[n]==after[n] for n in set(before)&set(after)),
        'slot_tail_prior_original_evidence_changed')
    exact={'hub-'+k+'-0022.json' for k in ('request','response','client-time','service-time','host-check')}
    exact|={'hub-stop.json','host-continuity-terminal-receipt.json','host-continuity-seal.json'}
    require(exact-{'hub-client-time-0022.json'}<=added
        and all(n in exact or re.fullmatch(r'host-continuity-\d{4}\.json',n) for n in added)
        and len(added)==summary['cleanup']['preservation']['added_cleanup_evidence_files'],
        'slot_tail_prior_unexpected_append')


def verify_prior_private(reference, summary):
    # Actual owner invocation only; public assembler/agent never calls this.
    closure=Path(reference['review_root']);state=Path(reference['attempt_root'])
    before=read_json(closure,'original-before-inventory.json')
    after=evidence_inventory(state)
    verify_preservation(before,after,summary)
    private=read_json(closure,reference['private_proofs_name'])
    require(private['private_content_included'] is True
        and digest(private['proofs'])==reference['private_proofs_sha256'],
        'slot_tail_prior_private_proof_anchor')
    for component in summary['components']:
        if component['status']=='verified':
            require(digest(private['proofs'][component['component']])==component['proof_sha256'],
                'slot_tail_prior_component_proof_changed')
    terminal=read_json(state,'host-continuity-terminal-receipt.json')
    seal=read_json(state,'host-continuity-seal.json')
    require(digest(seal)==terminal['seal_sha256']==summary['cleanup']['terminal_seal_sha256']
        and terminal['record_count']==254,'slot_tail_prior_terminal_changed')
    from training.c5_host_assurance_audit import audit_host_continuity
    from plugin.rhino_listener.c5_research_gate import signature
    from hmac import compare_digest
    path=Path(reference['source_root'])/reference['runtime_file']
    require(path.resolve()==path and path.is_file() and path.stat().st_size<=16777216,
        'slot_tail_prior_public_runtime_path')
    old=json.loads(path.read_bytes())
    require(digest(old)==summary['runtime_sha256'],'slot_tail_prior_public_runtime_changed')
    audit_host_continuity(state,summary['study_id'],digest(old),old['source_inventory_sha256'],terminal['seal_sha256'],
        normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    sent=read_json(state,'hub-request-0022.json');key=read_json(state/'audit-key-custody','hub.json')
    require(sent['payload']['action']=='stop' and sent['payload']['slot_id'] is None
        and sent['payload']['owner_freeze_sha256']==digest(old)
        and compare_digest(sent['signature'],signature(bytes.fromhex(key['key_hex']),sent['payload'])),
        'slot_tail_prior_original_hub_stop_signature')
    pointer=read_json(state.parent,'rhino-active-attempt.json')
    require(pointer['attempt']==0 and pointer['runtime_sha256']==digest(old)
        and read_json(state.parent,'package-dispatcher-detached-'+pointer['nonce']+'.json')==pointer,
        'slot_tail_prior_dispatcher_detach_changed')
    require(evidence_inventory(state)==after,'slot_tail_prior_evidence_changed_during_check')
    return {'historical_original_gate_passed':False,'historical_refusal_retained':True,
        'old_phase_components_reused':32,'same_original_history_and_private_results':True,
        'current_package_execution_authority':False}
