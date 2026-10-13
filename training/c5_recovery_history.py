"""Explicit A-D history import in the SAME global root, after NEW approval.

No deployment, migration or field effect on import. No directory enumeration
of keys or corpora. At most one recovery campaign in this versioned parent;
approved code revisions append to its ledger rather than creating another ID.
"""
import hashlib
import os
from pathlib import Path
from training.c5_reuse_evidence import canonical,exact,is_sha,require,sha,strict
from training.c5_recovery_policy import POLICY,RETIRED,require_grant,validate_scope
from training.c5_recovery_storage import EvidenceLog,directory,pinned_history,read_private,write_once

GLOBAL_ROOTS={
    'mac':'/Users/xiongweiluo/RhinoCoder/data/training/c5/c5-reuse-global-admission-v1',
    'gpu':'/data/c5-reuse-global-admission-v1',
}
V3_DIRECTORY='engineering-recovery-v3'

def validate_history(document):
    exact(document,('protocol','retirements','registry_file_sha256','historical_consumption_nonempty',
                    'old_no_go_preserved','old_active_grants_must_be_absent'))
    require(document['protocol']==POLICY['protocol']
            and document['historical_consumption_nonempty'] is True
            and document['old_no_go_preserved'] is True
            and document['old_active_grants_must_be_absent'] is True
            and set(document['retirements'])==set(RETIRED)
            and set(document['registry_file_sha256'])=={'mac','gpu'},'recovery_complete_a_to_d_history')
    for value in document['retirements'].values():
        exact(value,('retirement_raw_sha256','retired_grant_raw_sha256'))
        require(all(is_sha(h) for h in value.values()),'recovery_retirement_hash')
    mac=document['registry_file_sha256']['mac'];gpu=document['registry_file_sha256']['gpu']
    require(set(mac)=={'admission.lock','admission.sqlite','controller.consumed.json','host.consumed.json',
                      'followup-v2-genesis.json','followup-d-controller.consumed.json','followup-d-host.consumed.json'}
            and set(gpu)=={'followup-v2-genesis.json','followup-d-worker.consumed.json','followup-d-stop.consumed.json'}
            and all(is_sha(h) for values in (mac,gpu) for h in values.values()),
            'recovery_nonempty_c_and_d_consumption_required')
    return document

def history_guard(root,endpoint,document,*,expected_roots=None):
    roots=GLOBAL_ROOTS if expected_roots is None else expected_roots
    root=Path(root);validate_history(document)
    require(endpoint in ('mac','gpu') and str(root)==roots[endpoint]
            and root.name=='c5-reuse-global-admission-v1','recovery_same_global_root_required')
    pins={str(root/n):h for n,h in document['registry_file_sha256'][endpoint].items()}
    for instance,value in document['retirements'].items():
        state=root.parent/(instance+'-state')
        pins[str(state/'entry-retired-no-retry.json')]=value['retirement_raw_sha256']
        pins[str(state/'owner-approval.retired-no-retry.json')]=value['retired_grant_raw_sha256']
    bytes_guard=pinned_history(pins)
    def guard():
        directory(root);bytes_guard()
        require(set(os.listdir(root)) in (set(document['registry_file_sha256'][endpoint]),
                                         set(document['registry_file_sha256'][endpoint])|{V3_DIRECTORY}),
                'recovery_unknown_global_history')
        require(all(not os.path.lexists(root.parent/(instance+'-state')/'owner-approval.json')
                    for instance in RETIRED),'recovery_retired_grant_restored')
    guard();return guard

def open_campaign(root,endpoint,scope,document,*,create=False,grant=None,expected_roots=None):
    """Production uses the fixed roots; expected_roots is ONLY a CPU-fixture hook."""
    validate_scope(scope)
    require(scope['history_sha256']==sha(validate_history(document)),'recovery_history_binding')
    guard=history_guard(root,endpoint,document,expected_roots=expected_roots)
    parent=Path(root)/V3_DIRECTORY
    if create:
        require_grant(scope,grant)
        require(not os.path.lexists(parent),'recovery_single_campaign_parent_already_initialized')
        parent.mkdir(mode=0o700)
        write_once(parent,'campaign.json',{'campaign_id':scope['campaign_id'],'initial_scope_sha256':sha(scope),
                                          'history_sha256':sha(document)})
    directory(parent)
    record=strict(read_private(parent/'campaign.json'))
    exact(record,('campaign_id','initial_scope_sha256','history_sha256'))
    require(record['campaign_id']==scope['campaign_id'] and record['history_sha256']==sha(document),
            'recovery_no_replacement_namespace')
    names=set(os.listdir(parent));stops={n for n in names if n.startswith('qualified-stop-')}
    require(len(stops)<=POLICY['public_attempts_max'] and all(is_sha(n[len('qualified-stop-'):]) for n in stops)
            and names-stops==({'campaign.json'} if create else {'campaign.json','ledger'}),
            'recovery_campaign_population')
    # Initial binding persists; current revision is verified by Campaign replay.
    if create:
        return EvidenceLog(parent/'ledger',scope,guard,create=True)
    initial=strict(read_private(parent/'ledger'/'manifest.json'))['binding']
    require(sha(initial)==record['initial_scope_sha256'],'recovery_initial_scope_changed')
    return EvidenceLog(parent/'ledger',initial,guard)


def open_qualified_stop(campaign_parent,scope,qualification,history_guard,*,create=False,grant=None):
    """Supervisor initializes BEFORE load gate; all stop actors derive same path."""
    from training.c5_recovery_stop import CoordinatedStop
    parent=Path(campaign_parent);directory(parent)
    require(parent.name==V3_DIRECTORY,'recovery_stop_same_campaign_parent')
    record=strict(read_private(parent/'campaign.json'))
    validate_scope(scope)
    require(record['campaign_id']==scope['campaign_id'] and record['history_sha256']==scope['history_sha256'],
            'recovery_stop_campaign_binding')
    history_guard()
    if create:require_grant(scope,grant)
    root=parent/('qualified-stop-'+sha(qualification))
    binding={'qualification_sha256':sha(qualification),'campaign_id':scope['campaign_id'],
             'scope_sha256':sha(scope)}
    if create:
        existing=[p.name for p in parent.iterdir() if p.name.startswith('qualified-stop-')]
        require(len(existing)<POLICY['public_attempts_max'],'recovery_stop_target_limit')
    log=EvidenceLog(root,binding,history_guard,create=create)
    try:return CoordinatedStop(log,qualification)
    except BaseException:log.close();raise
