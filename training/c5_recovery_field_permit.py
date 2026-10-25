"""Recompute Mac load-intent prefix before Linux fork or model import."""
from training.c5_reuse_evidence import canonical,exact,require,sha,ZERO
from training.c5_recovery_controller import replay,Campaign
from training.c5_recovery_policy import require_grant
from training.c5_recovery_history import open_campaign

def permit(campaign,binding):
    state=campaign.observation()
    require(state['active'] and state['status']=='LOADING'
        and state['attempts']==binding['recovery']['attempt']
        and state['scope']==binding['recovery']['scope'],'recovery_permit_after_load_intent')
    rows=campaign.log.rows()
    return {'kind':'recovery_mac_load_permit','initial_scope':campaign.initial_scope,
        'scope':campaign.scope,'attempt':state['attempts'],'rows':rows,
        'head_sha256':rows[-1]['record_sha256'],'preload_confirmation':state['receipt']}

def validate(value,binding,grant):
    exact(value,('kind','initial_scope','scope','attempt','rows','head_sha256','preload_confirmation'))
    require(value['kind']=='recovery_mac_load_permit' and value['scope']==binding['recovery']['scope']
        and value['attempt']==binding['recovery']['attempt']
        and type(value['rows']) is list and 1<=len(value['rows'])<=512,'recovery_exact_load_permit')
    require_grant(value['scope'],grant);head=ZERO
    for index,row in enumerate(value['rows']):
        exact(row,('seq','previous_sha256','binding_sha256','kind','payload','record_sha256'))
        require(type(row['seq']) is int and row['seq']==index and row['previous_sha256']==head
            and row['binding_sha256']==sha(value['initial_scope'])
            and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),
            'recovery_load_permit_raw_chain')
        head=row['record_sha256']
    state=replay(value['initial_scope'],value['rows'])
    require(head==value['head_sha256'] and state['scope']==value['scope']
        and state['receipt']==value['preload_confirmation'] and state['active']
        and state['attempts']==value['attempt'] and state['status']=='LOADING',
        'recovery_load_permit_state')
    return state

def import_permit(root,binding,history,grant,value):
    """Mirror prefix only. GPU never invents controller consumption/confirmation."""
    validate(value,binding,grant)
    from pathlib import Path
    parent=Path(root)/'engineering-recovery-v3'
    create=not parent.exists()
    if create and value['initial_scope']!=value['scope']:
        from training.c5_recovery_history import history_guard
        from training.c5_recovery_storage import write_once,EvidenceLog
        # validate() above verified the NEW current grant and entire prior
        # revision/confirmation/load-intent chain before these effects.
        hg=history_guard(root,'gpu',history);parent.mkdir(mode=0o700)
        write_once(parent,'campaign.json',{'campaign_id':value['scope']['campaign_id'],
            'initial_scope_sha256':sha(value['initial_scope']),'history_sha256':sha(history)})
        log=EvidenceLog(parent/'ledger',value['initial_scope'],hg,create=True)
    else:log=open_campaign(root,'gpu',value['scope'],history,create=create,grant=grant)
    try:
        with log.locked():
            existing=log.rows();require(value['rows'][:len(existing)]==existing,'recovery_gpu_prefix_fork')
            for row in value['rows'][len(existing):]:
                require(log.append_locked(row['kind'],row['payload'])==row,'recovery_gpu_prefix_replication')
        return Campaign(value['scope'],log)
    except BaseException:log.close();raise
