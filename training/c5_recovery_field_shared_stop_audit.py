"""Pure independent replay of the common GPU stop log, including duplicates."""
from training.c5_reuse_evidence import exact,require,sha,ZERO
def audit_shared_stop(rows,log_binding,qualification,binding,*,expected_result):
    require(log_binding=={'qualification_sha256':sha(qualification),
        'campaign_id':binding['recovery']['scope']['campaign_id'],
        'scope_sha256':sha(binding['recovery']['scope'])} and type(rows) is list and len(rows)==2,
        'recovery_audit_shared_stop_population')
    head=ZERO
    for i,row in enumerate(rows):
        exact(row,('seq','previous_sha256','binding_sha256','kind','payload','record_sha256'))
        require(type(row['seq']) is int and row['seq']==i and row['previous_sha256']==head
            and row['binding_sha256']==sha(log_binding)
            and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),
            'recovery_audit_shared_stop_raw_chain')
        head=row['record_sha256']
    require(rows[0]['kind']=='stop_claim' and rows[0]['payload']=={'qualification_sha256':sha(qualification),'signals_max':1}
        and rows[1]['kind']=='stop_result' and expected_result==dict(rows[1]['payload'],retry_signal_allowed=False),
        'recovery_audit_shared_stop_join')
    result=rows[1]['payload'];exact(result,('status','signal_attempts','exit_observed','error_type'))
    require(result=={'status':'already_exited','signal_attempts':0,'exit_observed':True,'error_type':None},
        'recovery_audit_normal_exit_without_signal')
    return head
