"""Read-only lineage verification and explicit already-approved revision append.

No new study, retry, model, role, private rows, clock reset, or old grant change.
The append writer is called only by the human-approval registrar.
"""
import hashlib
from pathlib import Path
from plugin.rhino_listener.c5_formal_reuse_lineage import validate_lineage
from plugin.rhino_listener.c5_research_native import require
from training.c5_reuse_evidence import sha,strict
from training.c5_recovery_storage import read_private,EvidenceLog

def initial_scope(spec,freeze):
    from training.c5_formal_reuse_admission import campaign_scope
    value=freeze.get('incremental_revision')
    return campaign_scope(spec,freeze) if value is None else validate_lineage(value)

def verify_endpoint(endpoint,freeze):
    from training.c5_formal_reuse_admission import ROOTS,NAMESPACE,history_guard
    value=freeze.get('incremental_revision')
    if value is None:return lambda:None
    validate_lineage(value);require(endpoint in ('mac','gpu'),'formal_reuse_revision_endpoint')
    root=Path(value['prior_'+endpoint+'_source_root'])
    pins=value['prior_public_source_files']
    require(root.resolve()==root and root.is_dir()
        and {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}==set(pins),
        'formal_reuse_prior_source_population')
    require(all(not (root/n).is_symlink() and (root/n).resolve()==root/n
        and hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in pins.items()),
        'formal_reuse_prior_source_bytes')
    prefix=value[endpoint+'_campaign_prefix_files'];parent=ROOTS[endpoint]/NAMESPACE
    if endpoint=='mac':
        proof=Path(value['prior_mac_state_root'])/'preload-1/independent-preexposure-failure-proof.json'
        require(hashlib.sha256(read_private(proof)).hexdigest()==value['prior_failure_proof_sha256']
            and strict(read_private(proof))==value['prior_failure_proof'],'formal_reuse_prior_failure_audit_bytes')
    def guard():
        history_guard(endpoint,freeze['history'])()
        require(all(hashlib.sha256(read_private(parent/n)).hexdigest()==h for n,h in prefix.items()),
            'formal_reuse_original_campaign_prefix_changed')
    guard();return guard

def activate_mac(spec,freeze,grant):
    """Append one exact revision only after direct owner hash approval."""
    from plugin.rhino_listener.c5_formal_reuse_scope import authority
    from training.c5_formal_reuse_admission import ROOTS,NAMESPACE,campaign_scope,FormalCampaign
    from training.c5_recovery_policy import POLICY
    authority(spec,freeze,grant)
    guard=verify_endpoint('mac',freeze);value=freeze['incremental_revision']
    initial=validate_lineage(value);parent=ROOTS['mac']/NAMESPACE
    require(strict(read_private(parent/'campaign.json'))=={'campaign_id':initial['campaign_id'],
        'history_sha256':initial['history_sha256'],'initial_scope_sha256':sha(initial)},
        'formal_reuse_original_campaign_manifest')
    log=EvidenceLog(parent/'ledger',initial,guard)
    try:
        from training.c5_formal_reuse_admission import formal_replay
        observed=formal_replay(initial,log.rows());revised=campaign_scope(spec,freeze)
        if observed['scope']==revised:
            require(observed['attempts']==1 and not observed['formal_consumed'] and not observed['active'],
                'formal_reuse_revision_already_consumed')
            return {'status':'revision_already_registered_no_restart','first_load_epoch':observed['first_load_epoch']}
        require(observed['scope']==value['prior_scope'] and observed['status']=='RETRYABLE_ENGINEERING'
            and observed['attempts']==1 and observed['first_load_epoch']==value['formal_first_load_epoch']
            and not observed['formal_consumed'] and not observed['active']
            and len(log.rows())==value['prior_campaign_rows']
            and log.rows()[-1]['record_sha256']==value['prior_campaign_head_sha256'],
            'formal_reuse_revision_requires_original_known_pause')
        campaign=FormalCampaign(observed['scope'],log)
        evidence={'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],
            'scope_sha256':sha(revised),'spec_sha256':revised['spec_sha256'],'runtime_sha256':revised['runtime_sha256'],
            'policy_sha256':sha(POLICY),'previous_campaign_head_sha256':value['prior_campaign_head_sha256']}
        campaign.accept_revision(revised,evidence)
        after=campaign.observation()
        require(after['first_load_epoch']==value['formal_first_load_epoch'] and after['attempts']==1
            and not after['formal_consumed'],'formal_reuse_revision_did_not_reset_history')
        return {'status':'incremental_revision_registered_waiting_owner','attempts_consumed':1,
            'first_load_epoch':after['first_load_epoch'],'research_restarted':False}
    finally:log.close()
