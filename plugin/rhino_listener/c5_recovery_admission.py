"""Per-attempt O_EXCL role effects; original global root/history never written."""
import hashlib
import os
from pathlib import Path
from .c5_followup_admission import read,directory,write_once
from .c5_followup_runtime_scope import read_bytes
from .c5_reuse_field_scope import canonical,sha,strict,require
from .c5_recovery_profile import HISTORY,RECOVERY_POLICY
from .c5_recovery_scope import validate

ROLES={'mac':('host','controller'),'gpu':('worker',)}
def verify_history(binding,history):
    validate(binding);require(sha(history)==binding['recovery']['scope']['history_sha256'],'recovery_history_binding')
    require(history['protocol']==RECOVERY_POLICY['protocol'] and history['historical_consumption_nonempty'] is True
        and history['old_no_go_preserved'] is history['old_active_grants_must_be_absent'] is True,
        'recovery_history_preservation')
    require(set(history['retirements'])=={'reuse-dev-20261011-a','reuse-dev-20261012-b','reuse-dev-20261012-c','reuse-dev-20261012-d'}
        and set(history['registry_file_sha256'])=={'mac','gpu'}
        and set(history['registry_file_sha256']['mac'])=={'admission.lock','admission.sqlite','controller.consumed.json',
            'host.consumed.json','followup-v2-genesis.json','followup-d-controller.consumed.json','followup-d-host.consumed.json'}
        and set(history['registry_file_sha256']['gpu'])=={'followup-v2-genesis.json','followup-d-worker.consumed.json',
            'followup-d-stop.consumed.json'},'recovery_complete_nonempty_history')
    root=Path(binding['paths']['admission_root']);directory(root)
    names=set(history['registry_file_sha256'][binding['endpoint']])
    require(set(os.listdir(root)) in (names,names|{'engineering-recovery-v3'}),'recovery_global_history_population')
    pins={root/n:h for n,h in history['registry_file_sha256'][binding['endpoint']].items()}
    for instance,item in history['retirements'].items():
        state=root.parent/(instance+'-state')
        require(not os.path.lexists(state/'owner-approval.json'),'recovery_retired_grant_restored')
        pins[state/'entry-retired-no-retry.json']=item['retirement_raw_sha256']
        pins[state/'owner-approval.retired-no-retry.json']=item['retired_grant_raw_sha256']
    require(len(history['retirements'])==4 and all(hashlib.sha256(read(p,empty=p.name=='admission.lock')).hexdigest()==h
        for p,h in pins.items()),'recovery_history_byte_drift')
    return sha(history)

class AdmissionRegistry:
    def __init__(self,binding,*,create=False):
        validate(binding);require(create is False,'recovery_no_implicit_role_initialization')
        self.binding=strict(canonical(binding));self.root=Path(binding['paths']['state_root'])/'roles'
        self.history=strict(read_bytes(Path(binding['paths']['source_root'])/HISTORY))
        self.audit()
    def audit(self):
        verify_history(self.binding,self.history);directory(self.root)
        value={'binding_sha256':sha(self.binding),'attempt':self.binding['recovery']['attempt'],'scope_sha256':sha(self.binding['recovery']['scope'])}
        require(read(self.root/'manifest.json')==canonical(value)+b'\n','recovery_role_manifest')
        names=set(os.listdir(self.root));allowed={r+'.consumed.json' for r in ROLES[self.binding['endpoint']]}
        require(names-{'manifest.json'}<=allowed,'recovery_role_population')
        rows=[]
        for role in sorted(ROLES[self.binding['endpoint']]):
            p=self.root/(role+'.consumed.json')
            if not os.path.lexists(p):continue
            item={'study_id':self.binding['study_id'],'role':role,'scope_sha256':sha(self.binding),'replay_allowed':False}
            require(read(p)==canonical(item)+b'\n','recovery_role_partial_claim')
            rows.append([self.binding['study_id'],role,sha(self.binding),sha(item)])
        return {'rows':rows,'nonempty_history_carried_forward':True,'replay_allowed':False}
    def claim(self,role,*,fault=lambda boundary:None):
        require(role in ROLES[self.binding['endpoint']],'recovery_endpoint_role');self.audit()
        value={'study_id':self.binding['study_id'],'role':role,'scope_sha256':sha(self.binding),'replay_allowed':False}
        write_once(self.root,role+'.consumed.json',value);fault('after_tombstone');self.audit();return value
    def close(self):pass
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

def initialize_roles(binding,history,guard):
    """Caller has validated NEW grant and campaign attempt before this effect."""
    validate(binding);guard();verify_history(binding,history)
    root=Path(binding['paths']['state_root'])/'roles';root.mkdir(mode=0o700)
    write_once(root,'manifest.json',{'binding_sha256':sha(binding),'attempt':binding['recovery']['attempt'],
                                  'scope_sha256':sha(binding['recovery']['scope'])})
    guard();return AdmissionRegistry(binding)
