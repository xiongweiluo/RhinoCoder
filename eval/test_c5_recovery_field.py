"""Actual adapter CPU gates; synthetic directories, no live grant/host/model."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from training.c5_reuse_evidence import canonical,sha,raw_sha,require,ZERO
from training.c5_recovery_policy import POLICY,require_grant
from training.c5_recovery_confirmation import snapshot,validate_receipt
from plugin.rhino_listener import c5_recovery_scope as field
from plugin.rhino_listener.c5_recovery_profile import RECOVERY_POLICY,PYTHON,GPU_FLAGS,ENTRY,PLAN
from plugin.rhino_listener.c5_reuse_field_scope import PROTOCOL,COMPARISON,LIMITS,validate_binding,common_scope
from training.c5_reuse_worker_loop import validate_begin,readiness,serve
from training.c5_recovery_field_permit import permit,validate as validate_permit
from training.c5_recovery_field_gpu_audit import audit_gpu_entry
from training.c5_recovery_field_audit import audit_ready,audit_failure
from training.c5_recovery_field_budget import FieldBudget
from training.c5_recovery_controller import Campaign
from training.c5_recovery_storage import EvidenceLog
from eval.test_c5_reuse_gpu_entry import Pipe
from eval.test_c5_model_transport import Tokenizer
ROOT=Path(__file__).resolve().parents[1]

def fixture(monkeypatch,tmp_path,attempt=1):
    monkeypatch.setattr(field,'PARENTS',{e:str(tmp_path/e) for e in ('mac','gpu')})
    oldspec=json.loads((ROOT/'eval/c5/reuse-followup-development-spec-20261012-d.json').read_bytes())
    plan=json.loads((ROOT/'eval/c5/reuse-followup-field-environment-plan-20261012-d.json').read_bytes())
    from training.c5_reuse_development_plan import public_plan
    plans=public_plan(ROOT)['task_plans']
    s={'protocol':PROTOCOL,'study_id':field.STUDY,'instance_id':field.INSTANCE,'phase':'development',
       'comparison':copy.deepcopy(COMPARISON),'limits':copy.deepcopy(LIMITS),
       'development_plan_sha256':sha(plans),'execution_ready':True,'private_formal_data_allowed':False,
       'default_route_change_allowed':False,'host_policy':dict(oldspec['host_policy'],instance_id=field.INSTANCE),
       'resources':{'lease_expiry_epoch':100900,'generation_cutoff_epoch':100000,'export_reserve_seconds':900,
           'development_seconds_max':18000,'formal_seconds_max':64800,'research_seconds_max':82800,
           'historical_cumulative_upper_bound_seconds':None,'original_16_hour_compliance_claimed':False,
           'old_budget_recredited':False,'unused_development_transferred_to_formal':False,
           'actual_lease_basis':'CPU_SYNTHETIC_NOT_ACTUAL_LEASE'},
       'recovery':{'policy':copy.deepcopy(POLICY),'history_sha256':'d'*64,'public_attempts_max':3,
           'minimum_attempt_window_seconds':16344,'all_attempts_disclosed':True,
           'owner_confirmation_before_loading':True,'new_blind_holdout_claimed':False,'previous_campaign_head_sha256':None}}
    plan['gpu_process'].update(python=PYTHON,entry=ENTRY,stop_policy=copy.deepcopy(POLICY))
    plan['environment']['gpu']['executable_sha256']='a'*64
    plan['minimum_attempt_window_seconds']=16344
    plan_raw=canonical(plan)
    r={'protocol':PROTOCOL,'study_id':field.STUDY,'instance_id':field.INSTANCE,'spec_sha256':sha(s),
       'source_files':{PLAN:raw_sha(plan_raw)},'environment_sha256':sha(plan['environment']),
       'model_assets_sha256':sha(plan['model_assets']),'host_readable_files_sha256':sha(plan['host_readable_files']),
       'resources':copy.deepcopy(s['resources']),'recovery':copy.deepcopy(s['recovery']),'execution_ready':True}
    b=field.material(s,r,endpoint='gpu',attempt=attempt,now=100)
    scope=b['recovery']['scope']
    g={'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],'scope_sha256':sha(scope),
       'spec_sha256':sha(s),'runtime_sha256':sha(r),'policy_sha256':sha(POLICY)}
    return s,r,plan,b,g,plans,plan_raw

def preload(b):
    snap=snapshot(b['recovery']['scope'],'e'*64,'f'*64)
    receipt={'actor':'repository_owner',**snap,'before_model_loading':True,'public_attempts_authorized':3,
             'human_origin_cryptographically_proven':False}
    return snap,receipt

def chain(rows):
    head=ZERO
    for i,row in enumerate(rows):
        row.update(seq=i,previous_sha256=head)
        row['record_sha256']=sha({k:v for k,v in row.items() if k!='record_sha256'});head=row['record_sha256']
    return head

def bundle(monkeypatch,tmp_path):
    from training.c5_reuse_control_journal import ControlJournal
    from training.c5_reuse_generation import GenerationPeer
    from training.c5_model_transport import request
    from training.c5_reuse_field_wire import frame,envelope
    from training.c5_reuse_development_plan import ORDER
    s,r,p,b,g,plans,plan_raw=fixture(monkeypatch,tmp_path)
    state=Path(b['paths']['state_root']);state.mkdir(mode=0o700,parents=True)
    class Registry:
        binding=b
        def claim(self,role):return {'study_id':b['study_id'],'role':role,'scope_sha256':sha(b),'replay_allowed':False}
    def generate(prompt,stage):
        raw='{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
        return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':raw_sha(prompt.encode()),'output_sha256':raw_sha(raw.encode())}
    peer=GenerationPeer(b,Registry(),plans,Tokenizer(),generate,lambda _:contextlib.nullcontext(),lambda:None,lambda:None)
    supervisor=ControlJournal(b,'supervisor');lifecycle=ControlJournal(b,'worker-lifecycle')
    argv=[PYTHON,*GPU_FLAGS,b['paths']['source_root']+'/'+ENTRY,'--serve','--attempt','1']
    parent={'pid':200,'uid':1000,'boot_id':p['gpu_process']['boot_id'],'start_ticks':1,
        'executable_sha256':'a'*64,'argv_sha256':raw_sha(b'\0'.join(a.encode() for a in argv)+b'\0'),
        'cwd':b['paths']['source_root']}
    q={'target':dict(parent,pid=201,start_ticks=2),'parent_pid':200,'model_loading_started':False}
    budget={'elapsed_wall_seconds':0,'start_epoch':100,'operational_cap_seconds':17940,'reserved_wall_seconds':18000,
        'stop_reserve_seconds':60,'within_reserved_wall_seconds':True,'prior_cumulative_upper_bound_seconds':None,
        'physical_gpu_release_independently_verified':None}
    supervisor.append('child_launch_intent',{'parent':parent,'worker_open_head_sha256':peer.journal.head,
                                           'policy_sha256':sha(POLICY),'budget':budget})
    supervisor.append('owned_child_qualified',q)
    lifecycle.append('model_loading_intent',{'qualification_sha256':sha(q),'worker_open_head_sha256':peer.journal.head})
    lifecycle.append('model_loaded',{'qualification_sha256':sha(q),'training':False,'parse_repair':False})
    ready=readiness(b,sha(q),peer.journal.head);snap,receipt=preload(b)
    begin={'kind':'reuse_begin_after_preload_confirmation','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b)),
        'preload_snapshot':snap,'preload_receipt':receipt,'host_baseline_head_sha256':'e'*64,'worker_readiness_sha256':sha(ready)}
    chunks=[frame(begin)]
    for slot in ORDER:
        inner=request(b['study_id'],slot,plans[slot]['route'],0,plans[slot]['steps'][0],
            {'unit':'Millimeters','objects':[],'groups':{}},
            {'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},b['runtime_sha256'],'new-'+slot)
        chunks.append(frame(envelope(b,inner)))
    chunks.append(frame({'kind':'reuse_worker_close','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b))}))
    serve(peer,Pipe(chunks),sha(q),lambda:None,lambda:None,lifecycle.append)
    lifecycle.append('worker_budget_observation',dict(budget,elapsed_wall_seconds=9))
    supervisor.append('coordinated_stop_observed',{'qualification_sha256':sha(q),'result':
        {'status':'already_exited','signal_attempts':0,'exit_observed':True,'error_type':None,'retry_signal_allowed':False}})
    supervisor.append('supervisor_final_observation',{'child_wait_status':0,'child_exit_reaped':True,
        'budget':dict(budget,elapsed_wall_seconds=10),'physical_gpu_release_verified':None,'whole_field_pass':False})
    return {'supervisor':copy.deepcopy(supervisor.rows),'lifecycle':copy.deepcopy(lifecycle.rows),
        'worker':copy.deepcopy(peer.journal.records),'binding':b,'plan':p,'resources':s['resources'],
        'spec':s,'runtime':r,'plan_raw':plan_raw,'supervisor_head':supervisor.head,
        'lifecycle_head':lifecycle.head,'worker_head':peer.journal.head,'plans':plans,'tokenizer':Tokenizer()}

def test_fixed_attempt_scope_and_public_contract(monkeypatch,tmp_path):
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path)
    assert RECOVERY_POLICY==POLICY
    validate_binding(b);require_grant(b['recovery']['scope'],g)
    other=field.material(s,r,endpoint='mac',attempt=1,now=100)
    assert common_scope(other)==common_scope(b)
    next_b=field.material(s,r,endpoint='gpu',attempt=2,now=100)
    assert common_scope(next_b)!=common_scope(b)
    assert next_b['paths']['admission_root']==b['paths']['admission_root']

@pytest.mark.parametrize('change',['attempt0','attempt4','boolattempt','history','formal','oldidentity','cap','lease','ready','private','route','contract','policy'])
def test_new_material_cannot_waive_existing_gates(monkeypatch,tmp_path,change):
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path);attempt=1
    if change=='attempt0':attempt=0
    elif change=='attempt4':attempt=4
    elif change=='boolattempt':attempt=True
    elif change=='history':s['recovery']['history_sha256']=None
    elif change=='formal':s['phase']='formal'
    elif change=='oldidentity':s['study_id']='C5DEV-REUSE-20261012-D'
    elif change=='cap':s['resources']['development_seconds_max']=999999
    elif change=='lease':s['resources']['lease_expiry_epoch']+=1
    elif change=='ready':s['execution_ready']=False
    elif change=='private':s['private_formal_data_allowed']=True
    elif change=='route':s['default_route_change_allowed']=True
    elif change=='contract':s['comparison']['training_allowed']=True
    else:s['recovery']['policy']['signals_per_qualified_target']=2
    r.update(spec_sha256=sha(s),resources=copy.deepcopy(s['resources']),recovery=copy.deepcopy(s['recovery']))
    with pytest.raises(ValueError):field.material(s,r,endpoint='gpu',attempt=attempt,now=100)

def test_actual_new_worker_protocol_and_independent_eight_generation_audit(monkeypatch,tmp_path):
    data=bundle(monkeypatch,tmp_path);result=audit_gpu_entry(**data)
    assert result['complete_eight_slot_entry_records'] and result['generation']['requests_complete']==8
    assert result['generation']['recorded_generation_attempts']==16 and result['recorded_signal_attempts']==0
    assert not result['whole_field_pass']

@pytest.mark.parametrize('change',['qualified_after_load','another_parent','argv','duplicate_stop','signal','ready_requests',
                                  'training','receipt','attempt_crosswire','recredited_budget','close_head','unknown_event'])
def test_rehashed_actual_adapter_raw_tampering_rejected(monkeypatch,tmp_path,change):
    b=bundle(monkeypatch,tmp_path)
    if change=='qualified_after_load':b['supervisor'][2]['payload']['model_loading_started']=True
    elif change=='another_parent':b['supervisor'][2]['payload']['parent_pid']=999
    elif change=='argv':b['supervisor'][1]['payload']['parent']['argv_sha256']='0'*64
    elif change=='duplicate_stop':b['supervisor'].insert(4,copy.deepcopy(b['supervisor'][3]))
    elif change=='signal':b['supervisor'][3]['payload']['result']['signal_attempts']=1
    elif change=='ready_requests':b['lifecycle'][3]['payload']['ready']['model_requests_before_ready']=True
    elif change=='training':b['lifecycle'][2]['payload']['training']=True
    elif change=='receipt':b['lifecycle'][4]['payload']['begin']['preload_receipt']['before_model_loading']=False
    elif change=='attempt_crosswire':b['lifecycle'][4]['payload']['begin']['scope_sha256']='0'*64
    elif change=='recredited_budget':b['supervisor'][-1]['payload']['budget']['start_epoch']=101
    elif change=='close_head':b['lifecycle'][5]['payload']['receipt']['worker_final_head_sha256']='0'*64
    else:b['supervisor'][3]['kind']='old_separate_stop'
    b['supervisor_head']=chain(b['supervisor']);b['lifecycle_head']=chain(b['lifecycle'])
    with pytest.raises(ValueError):audit_gpu_entry(**b)

def test_preload_begin_does_not_invent_after_ready_owner_confirmation(monkeypatch,tmp_path):
    s,r,p,b,g,_,_=fixture(monkeypatch,tmp_path);snap,receipt=preload(b)
    begin={'kind':'reuse_begin_after_preload_confirmation','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b)),
        'preload_snapshot':snap,'preload_receipt':receipt,'host_baseline_head_sha256':'e'*64,'worker_readiness_sha256':'a'*64}
    assert validate_begin(begin,b)==receipt
    begin['preload_receipt']['human_origin_cryptographically_proven']=True
    with pytest.raises(ValueError):validate_begin(begin,b)

def campaign(monkeypatch,tmp_path):
    s,r,p,b,g,_,_=fixture(monkeypatch,tmp_path)
    clock=[100.0];log=EvidenceLog(tmp_path/'ledger',b['recovery']['scope'],lambda:None,create=True)
    c=Campaign(b['recovery']['scope'],log,wall=lambda:clock[0]);snap,receipt=preload(b)
    c.confirm(snap,receipt);c.start();return c,b,g,clock

def test_read_only_linux_budget_mirror_preserves_clock_and_remaining_window(monkeypatch,tmp_path):
    c,b,g,clock=campaign(monkeypatch,tmp_path);budget=FieldBudget(c,wall=lambda:clock[0],mono=lambda:clock[0],persist=False)
    initial=len(c.log.rows());clock[0]+=700
    assert budget.check()==17240 and len(c.log.rows())==initial
    budget.require_attempt_window(16344);clock[0]+=1000
    with pytest.raises(ValueError,match='complete_remaining_attempt_window'):budget.require_attempt_window(16344)

def test_actual_load_permit_replay_includes_preload_and_consumption(monkeypatch,tmp_path):
    c,b,g,clock=campaign(monkeypatch,tmp_path);value=permit(c,b)
    assert validate_permit(value,b,g)['attempts']==1
    value['preload_confirmation']['receipt']['before_model_loading']=False
    with pytest.raises(ValueError):validate_permit(value,b,g)

@pytest.mark.parametrize('name',['training.c5_recovery_field_gpu','training.c5_recovery_field_ssh',
    'training.c5_recovery_field_mac','training.c5_recovery_field_gpu_audit','training.c5_recovery_field_eight_audit'])
def test_actual_adapter_import_never_imports_models(monkeypatch,tmp_path,name):
    code="import sys;sys.path.insert(0,sys.argv[1]);__import__(sys.argv[2]);assert not any(n in sys.modules for n in ('Rhino','torch','peft','transformers'));print('CPU_IMPORT_ONLY')"
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),name],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert result.stdout=='CPU_IMPORT_ONLY\n'

def test_rhino_safe_namespace_graph_has_no_training_or_ambient_aliases(tmp_path):
    code=r"""
import importlib,sys,types
from pathlib import Path
root=Path(sys.argv[1]);prefix='cpu_recovery_cold'
for name,path in ((prefix,root),(prefix+'.plugin',root/'plugin'),(prefix+'.plugin.rhino_listener',root/'plugin/rhino_listener')):
    m=types.ModuleType(name);m.__path__=[str(path)];sys.modules[name]=m
for name in ('c5_recovery_mac_scope','c5_recovery_admission','c5_reuse_native_hub','c5_reuse_host_session','c5_host_observer_clr','c5_deferred_baseline'):
    importlib.import_module(prefix+'.plugin.rhino_listener.'+name)
assert not any(n in sys.modules for n in ('training','plugin','Rhino','torch','transformers','peft'))
print('CPU_RHINO_COLD_GRAPH_ONLY')
"""
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert result.stdout=='CPU_RHINO_COLD_GRAPH_ONLY\n'


def history_fixture(base,parents):
    from training.c5_recovery_policy import RETIRED
    from training.c5_recovery_history import validate_history
    names={'mac':('admission.lock','admission.sqlite','controller.consumed.json','host.consumed.json',
        'followup-v2-genesis.json','followup-d-controller.consumed.json','followup-d-host.consumed.json'),
        'gpu':('followup-v2-genesis.json','followup-d-worker.consumed.json','followup-d-stop.consumed.json')}
    pins={};retirements={}
    for endpoint,parent in parents.items():
        root=Path(parent)/'c5-reuse-global-admission-v1';root.mkdir(mode=0o700,parents=True);pins[endpoint]={}
        for n in names[endpoint]:
            raw=b'' if n=='admission.lock' else ('CPU_HISTORY_'+n).encode()
            p=root/n;p.write_bytes(raw);p.chmod(0o600);pins[endpoint][n]=raw_sha(raw)
        for instance in RETIRED:
            state=Path(parent)/(instance+'-state');state.mkdir(mode=0o700)
            values={}
            for name,key in (('entry-retired-no-retry.json','retirement_raw_sha256'),
                             ('owner-approval.retired-no-retry.json','retired_grant_raw_sha256')):
                raw=('CPU_RETIRED_'+instance+'_'+name).encode();p=state/name;p.write_bytes(raw);p.chmod(0o600);values[key]=raw_sha(raw)
            retirements[instance]=values
    return validate_history({'protocol':POLICY['protocol'],'retirements':retirements,'registry_file_sha256':pins,
        'historical_consumption_nonempty':True,'old_no_go_preserved':True,'old_active_grants_must_be_absent':True})

def test_actual_per_attempt_admission_never_changes_old_global_files(monkeypatch,tmp_path):
    from plugin.rhino_listener.c5_recovery_admission import initialize_roles
    from plugin.rhino_listener.c5_recovery_profile import HISTORY
    from training.c5_reuse_admission import AdmissionRegistry
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path)
    h=history_fixture(tmp_path,field.PARENTS);s['recovery']['history_sha256']=sha(h)
    r.update(spec_sha256=sha(s),recovery=copy.deepcopy(s['recovery']))
    b=field.material(s,r,endpoint='gpu',attempt=1,now=100)
    source=Path(b['paths']['source_root']);(source/'eval/c5').mkdir(parents=True)
    (source/HISTORY).write_bytes(canonical(h)+b'\n');(source/HISTORY).chmod(0o644)
    state=Path(b['paths']['state_root']);state.mkdir(mode=0o700,parents=True)
    root=Path(b['paths']['admission_root']);before={n:raw_sha((root/n).read_bytes()) for n in h['registry_file_sha256']['gpu']}
    registry=initialize_roles(b,h,lambda:None)
    assert registry.claim('worker')['scope_sha256']==sha(b)
    assert len(registry.audit()['rows'])==1
    with pytest.raises(FileExistsError):registry.claim('worker')
    with AdmissionRegistry(b) as reopen:assert len(reopen.audit()['rows'])==1
    assert before=={n:raw_sha((root/n).read_bytes()) for n in before}
    assert not (root/'engineering-recovery-v3').exists()

@pytest.mark.parametrize('change',['restored_grant','historical_bytes','unknown_history','missing_d'])
def test_actual_role_gate_rejects_history_reset(monkeypatch,tmp_path,change):
    from plugin.rhino_listener.c5_recovery_admission import verify_history
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path);h=history_fixture(tmp_path,field.PARENTS)
    s['recovery']['history_sha256']=sha(h);r.update(spec_sha256=sha(s),recovery=copy.deepcopy(s['recovery']))
    b=field.material(s,r,endpoint='gpu',attempt=1,now=100);root=Path(b['paths']['admission_root'])
    if change=='restored_grant':
        p=root.parent/'reuse-dev-20261012-d-state/owner-approval.json';p.write_bytes(b'CPU');p.chmod(0o600)
    elif change=='historical_bytes':(root/'followup-d-stop.consumed.json').write_bytes(b'CPU_RESET')
    elif change=='unknown_history':(root/'replacement-campaign').mkdir()
    else:(root/'followup-d-stop.consumed.json').unlink()
    with pytest.raises((ValueError,FileNotFoundError)):verify_history(b,h)

def bootstrap_fixture(monkeypatch,tmp_path,mode):
    import shutil
    from eval.test_c5_followup_embedded_bootstrap import DRIVER
    from eval.test_c5_host_assurance_v2 import data
    from plugin.rhino_listener.c5_recovery_profile import HISTORY
    from plugin.rhino_listener.c5_recovery_admission import initialize_roles
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path)
    h=history_fixture(tmp_path,field.PARENTS);s['recovery']['history_sha256']=sha(h)
    root=Path(field.paths('mac',1)['source_root']);root.mkdir(parents=True)
    for path in (ROOT/'plugin').rglob('*.py'):
        target=root/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);target.chmod(0o600)
    scope_path=root/'plugin/rhino_listener/c5_recovery_scope.py'
    text=scope_path.read_text().replace("PARENTS={'mac':'/Users/xiongweiluo/RhinoCoder/data/training/c5','gpu':'/data'}",
        'PARENTS='+repr(field.PARENTS));scope_path.write_text(text)
    for name in ('tools/run_c5_recovery_rhino_wrapper.py','tools/run_c5_recovery_rhino_entry.py',
                 'eval/c5/hostassurance-development-spec-20261007-d.json','eval/c5/rhino-runtime-schema-v1.json'):
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);target.chmod(0o600)
    path=root/HISTORY;path.write_bytes(canonical(h)+b'\n');path.chmod(0o600)
    r['source_files']={path.relative_to(root).as_posix():raw_sha(path.read_bytes()) for path in root.rglob('*') if path.is_file()}
    r.update(spec_sha256=sha(s),recovery=copy.deepcopy(s['recovery']))
    b=field.material(s,r,endpoint='mac',attempt=1,now=100)
    state=Path(b['paths']['state_root']);state.mkdir(parents=True,mode=0o700)
    initialize_roles(b,h,lambda:None)
    prepared={'study_id':b['study_id'],'spec_sha256':b['spec_sha256'],'runtime_sha256':b['runtime_sha256'],'model_calls':0,'private_formal_reads':0}
    for name,value in (('prepared.json',prepared),('hub.key',{'key_hex':'11'*32})):
        path=state/name;path.write_bytes(canonical(value)+b'\n');path.chmod(0o600)
    setup={'attempt':1,'spec_sha256':b['spec_sha256'],'runtime_sha256':b['runtime_sha256']}
    path=state.parent/'pending-host-setup.json';path.write_bytes(canonical(setup)+b'\n');path.chmod(0o600)
    f={'root':str(root),'spec':s,'runtime':r,'binding':b,'history':h,'grant':g,'snapshot':data()[0]}
    path=tmp_path/'cpu-bootstrap.json';path.write_text(json.dumps(f))
    text=DRIVER.replace('c5_followup_admission','c5_recovery_admission').replace('c5_followup_mac_scope','c5_recovery_mac_scope')
    text=text.replace('c5_followup_runtime_scope','c5_recovery_runtime_scope').replace('ReuseSourceGuard','SourceGuard')
    text=text.replace("return f['spec'],f['runtime'],f['binding'],{},lambda **kw:guard[0]()",
        "return f['spec'],f['runtime'],f['binding'],{},f['history'],f['grant'],lambda **kw:guard[0]()")
    start=text.index("    elif name.endswith('.c5_recovery_admission'):")
    end=text.index("    elif name.endswith('.c5_research_native'):",start)
    text=text[:start]+text[end:]
    text=text.replace('run_c5_followup_rhino_wrapper.py','run_c5_recovery_rhino_wrapper.py')
    driver=tmp_path/'cpu-bootstrap-driver.py';driver.write_text(text);return path,driver

@pytest.mark.parametrize('mode',['baseline','queued_request','dependency_failure','grant_failure','baseline_failure'])
def test_actual_recovery_rhino_wrapper_first_idle_and_no_ambient_imports(monkeypatch,tmp_path,mode):
    config,driver=bootstrap_fixture(monkeypatch,tmp_path,mode)
    result=subprocess.run([sys.executable,'-I','-S','-B',str(driver),str(config),mode],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['actual_host_or_model_calls']==0

@pytest.mark.skipif(sys.platform!='darwin',reason='macOS system Python 3.9 actual embedded grammar')
def test_actual_recovery_wrapper_on_python39(monkeypatch,tmp_path):
    config,driver=bootstrap_fixture(monkeypatch,tmp_path,'baseline')
    result=subprocess.run(['/usr/bin/python3','-I','-S','-B',str(driver),str(config),'baseline'],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['actual_host_or_model_calls']==0


def test_runtime_revision_has_distinct_material_roots_same_campaign_and_budget(monkeypatch,tmp_path):
    s,r,p,b,g,_,_=fixture(monkeypatch,tmp_path);old_root=b['paths']['state_root']
    r['source_files']['tools/cpu-fix.py']='b'*64
    revised=field.material(s,r,endpoint='gpu',attempt=1,now=100)
    assert revised['paths']['state_root']!=old_root
    assert revised['paths']['source_root']==b['paths']['source_root']
    assert revised['paths']['admission_root']==b['paths']['admission_root']
    assert revised['recovery']['scope']['campaign_id']==b['recovery']['scope']['campaign_id']
    assert revised['recovery']['scope']['development_seconds_max']==18000

def test_actual_pre_generation_proof_replayed_before_begin(monkeypatch,tmp_path):
    values=bundle(monkeypatch,tmp_path);b=values['binding']
    c_log=EvidenceLog(tmp_path/'campaign-log',b['recovery']['scope'],lambda:None,create=True)
    c=Campaign(b['recovery']['scope'],c_log,wall=lambda:100)
    snap,receipt=preload(b);c.confirm(snap,receipt);c.start();lp=permit(c,b)
    g={'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],'scope_sha256':sha(c.scope),
       'spec_sha256':b['spec_sha256'],'runtime_sha256':b['runtime_sha256'],'policy_sha256':sha(POLICY)}
    sup=values['supervisor'][:3];life=values['lifecycle'][:4];worker=values['worker'][:1]
    value={'binding':b,'supervisor':sup,'lifecycle':life,'worker':worker,
        'supervisor_head':sup[-1]['record_sha256'],'lifecycle_head':life[-1]['record_sha256'],
        'worker_head':worker[0]['record_sha256'],'qualified_identity':sup[2]['payload']['target'],
        'boot_id':sup[2]['payload']['target']['boot_id'],'model_or_cuda_calls':0,'private_formal_reads':0}
    ready=life[3]['payload']['ready'];anchor=audit_ready(value,b,ready,lp,g)
    assert anchor==sha(value)
    c.ready(anchor);c.begin(anchor)
    changed=copy.deepcopy(value);changed['lifecycle'][2]['payload']['training']=True
    changed['lifecycle_head']=chain(changed['lifecycle'])
    with pytest.raises(ValueError):audit_ready(changed,b,ready,lp,g)

@pytest.mark.parametrize('change',['not_revoked','wrong_revocation','other_gpu','still_present','gpu_active','native_unknown'])
def test_failure_retry_requires_independent_qualified_absence_and_native_cleanup(monkeypatch,tmp_path,change):
    s,r,p,b,g,_,_=fixture(monkeypatch,tmp_path)
    value={'binding':b,'cancelled_before_future_launch':True,
        'cancellation_record':{'binding_sha256':sha(b),'future_launch_allowed':False},
        'supervisor':[],'supervisor_head':None,'qualification':None,'shared_stop':None,
        'boot_id':p['gpu_process']['boot_id'],'target_proc_present':False,
        'compute_returncode':0,'compute_stdout':'','compute_stderr':'','gpu_returncode':0,
        'gpu_stdout':p['gpu_process']['gpu_uuid']+', 11\n','gpu_stderr':'','model_or_cuda_calls':0,'private_formal_reads':0}
    native=True
    if change=='not_revoked':value['cancelled_before_future_launch']=False
    elif change=='wrong_revocation':value['cancellation_record']['binding_sha256']='0'*64
    elif change=='other_gpu':value['gpu_stdout']='GPU-other, 11\n'
    elif change=='still_present':value['target_proc_present']=True
    elif change=='gpu_active':value['compute_stdout']='201, python, 19000\n'
    else:native=False
    if change in ('not_revoked','wrong_revocation'):
        with pytest.raises(ValueError):audit_failure(value,b,serve_capture={'complete_raw_capture':True},native_known=native,
            expected_gpu_uuid=p['gpu_process']['gpu_uuid'])
    else:
        proof=audit_failure(value,b,serve_capture={'complete_raw_capture':True},native_known=native,
            expected_gpu_uuid=p['gpu_process']['gpu_uuid'])
        assert not (proof['qualified_target_absent'] and proof['known_native_cleanup_complete'])

def test_owner_final_cannot_replace_missing_completion_with_preload_receipt(monkeypatch,tmp_path):
    from tools.run_c5_recovery_owner_custody import final_record
    s,r,p,b,g,_,_=fixture(monkeypatch,tmp_path);snap,receipt=preload(b)
    with pytest.raises((ValueError,KeyError)):
        final_record(b,snap,receipt,{}, {}, {},{})

def test_full_five_hour_ledger_capacity_includes_transition_reserve(monkeypatch,tmp_path):
    c,b,g,clock=campaign(monkeypatch,tmp_path)
    budget=FieldBudget(c,wall=lambda:clock[0],mono=lambda:clock[0])
    # Production checkpoints are <=300/minute. The expanded bound must keep
    # their RAW history, not delete old budget events when the cap is reached.
    for i in range(1,290):clock[0]=100+i*60;budget.check()
    assert len(c.log.rows())==291 and c.observation()['first_load_epoch']==100
    clock[0]=100+17940
    with pytest.raises(ValueError):budget.check()


@pytest.mark.skipif(sys.platform!='linux' or not hasattr(os,'pidfd_open'),reason='real Linux CPU fork/pidfd barrier')
@pytest.mark.parametrize('revised_boundary',(False,True))
def test_actual_gpu_supervisor_cpu_child_is_qualified_before_loader_and_stops_once(monkeypatch,tmp_path,revised_boundary):
    import shutil
    import time
    from training.c5_reuse_field_wire import frame,envelope
    from training.c5_reuse_development_plan import ORDER
    from training.c5_model_transport import request
    from plugin.rhino_listener.c5_recovery_profile import HISTORY
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path)
    h=history_fixture(tmp_path,field.PARENTS)
    s['recovery']['history_sha256']=sha(h)
    if revised_boundary:
        s['resources'].update(development_seconds_max=43200,research_seconds_max=108000)
        s['limits']['model_seconds']=360
    s['resources'].update(generation_cutoff_epoch=time.time()+50000,lease_expiry_epoch=time.time()+50900)
    # Keep exact 900-second export boundary in this CPU-only timestamp fixture.
    s['resources']['lease_expiry_epoch']=s['resources']['generation_cutoff_epoch']+900
    r.update(spec_sha256=sha(s),resources=copy.deepcopy(s['resources']),recovery=copy.deepcopy(s['recovery']))
    b=field.material(s,r,endpoint='gpu',attempt=1,now=time.time())
    g={'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],'scope_sha256':sha(b['recovery']['scope']),
       'spec_sha256':b['spec_sha256'],'runtime_sha256':b['runtime_sha256'],'policy_sha256':sha(POLICY)}
    root=Path(b['paths']['source_root']);(root/'eval/c5').mkdir(parents=True)
    (root/HISTORY).write_bytes(canonical(h)+b'\n')
    shutil.copyfile(ROOT/'eval/c5/hostassurance-development-spec-20261007-d.json',root/'eval/c5/hostassurance-development-spec-20261007-d.json')
    state=Path(b['paths']['state_root']);state.mkdir(mode=0o700,parents=True)
    f={'binding':b,'plan':p,'runtime':r,'history':h,'grant':g,'parents':field.PARENTS}
    config=tmp_path/'cpu-linux.json';config.write_text(json.dumps(f))
    driver=tmp_path/'cpu-linux-driver.py';driver.write_text(r"""
import contextlib,json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);f=json.loads(Path(sys.argv[2]).read_bytes())
from plugin.rhino_listener import c5_recovery_scope as scope
scope.PARENTS=f['parents']
from training import c5_recovery_history as history
history.GLOBAL_ROOTS={e:str(Path(p)/'c5-reuse-global-admission-v1') for e,p in f['parents'].items()}
from training.c5_recovery_controller import Campaign
from training.c5_recovery_confirmation import snapshot
from training.c5_reuse_evidence import sha,raw_sha
from training.c5_reuse_process_identity import LinuxIdentity
from training import c5_recovery_field_gpu as gpu
from training import c5_followup_gpu_loader as loader
b=f['binding'];s=b['recovery']['scope'];g=f['grant']
log=history.open_campaign(b['paths']['admission_root'],'gpu',s,f['history'],create=True,grant=g)
c=Campaign(s,log);snap=snapshot(s,'e'*64,'f'*64)
receipt={'actor':'repository_owner',**snap,'before_model_loading':True,'public_attempts_authorized':3,'human_origin_cryptographically_proven':False}
c.confirm(snap,receipt);c.start()
gpu.entry_identity=lambda binding,plan:LinuxIdentity()(os.getpid())
loader.preflight=lambda *args:{}
class Tokenizer:
    def apply_chat_template(self,messages,*,tools=None,**kwargs):return json.dumps({'messages':messages,'tools':tools},ensure_ascii=False)
    def __call__(self,text,**kwargs):return {'input_ids':[0]*100}
def load(root,inventory,guard,budget,**kwargs):
    from training.c5_reuse_control_journal import read_control
    rows=read_control(Path(b['paths']['state_root'])/'supervisor',b,'supervisor')
    q=rows[-1]['payload'];assert rows[-1]['kind']=='owned_child_qualified' and q['target']['pid']==os.getpid()
    stop=Path(b['paths']['admission_root'])/'engineering-recovery-v3'/('qualified-stop-'+sha(q))
    assert stop.is_dir() and json.loads((stop/'manifest.json').read_bytes())['binding']['qualification_sha256']==sha(q)
    marker=Path(b['paths']['state_root'])/'CPU-QUALIFIED-BEFORE-LOAD.json';marker.write_text(json.dumps({'qualified_before_load':True,'actual_model_calls':0}))
    def generate(prompt,stage):
        raw='{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
        return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':raw_sha(prompt.encode()),'output_sha256':raw_sha(raw.encode())}
    return Tokenizer(),generate,lambda _:contextlib.nullcontext(),lambda:None
loader.load=load
result=gpu.supervise(b,f['plan'],f['runtime'],f['history'],g,lambda **kw:None,c)
print('CPU_SUPERVISOR_RESULT '+json.dumps(result),file=sys.stderr,flush=True)
log.close()
""")
    child=subprocess.Popen([sys.executable,'-I','-B',str(driver),str(ROOT),str(config)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        import selectors
        with selectors.DefaultSelector() as select:
            select.register(child.stdout,selectors.EVENT_READ)
            assert select.select(30),'CPU worker failed to publish ready'
        line=child.stdout.readline();ready=json.loads(line)
        snap,receipt=preload(b)
        begin={'kind':'reuse_begin_after_preload_confirmation','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b)),
            'preload_snapshot':snap,'preload_receipt':receipt,'host_baseline_head_sha256':'e'*64,'worker_readiness_sha256':sha(ready)}
        child.stdin.write(frame(begin));child.stdin.flush()
        # The frozen stream protocol forbids pipelined frames. Wait for the
        # actual durable begin receipt before sending the first RPC.
        received=state/'worker-lifecycle/raw-0004.json'
        deadline=time.monotonic()+10
        while not received.exists():
            assert child.poll() is None,'CPU supervisor exited before begin receipt'
            assert time.monotonic()<deadline,'CPU begin receipt timed out'
            time.sleep(0.01)
        assert json.loads(received.read_bytes())['kind']=='worker_begin_record_received'
        messages=[]
        for slot in ORDER:
            inner=request(b['study_id'],slot,plans[slot]['route'],0,plans[slot]['steps'][0],
                {'unit':'Millimeters','objects':[],'groups':{}},{'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},
                b['runtime_sha256'],'cpu-'+slot)
            child.stdin.write(frame(envelope(b,inner)));child.stdin.flush()
            with selectors.DefaultSelector() as select:
                select.register(child.stdout,selectors.EVENT_READ)
                assert select.select(30),'CPU request response timed out'
            line=child.stdout.readline()
            assert line,'CPU worker exited before response'
            messages.append(json.loads(line))
        child.stdin.write(frame({'kind':'reuse_worker_close','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b))}));child.stdin.flush()
        with selectors.DefaultSelector() as select:
            select.register(child.stdout,selectors.EVENT_READ)
            assert select.select(30),'CPU worker close timed out'
        line=child.stdout.readline();assert line,'CPU worker exited before close receipt'
        messages.append(json.loads(line))
        stdout,stderr=child.communicate(timeout=30)
        assert child.returncode==0,stderr.decode()
        assert not stdout,stdout.decode()
        assert len(messages)==9
        assert messages[-1]['kind']=='reuse_worker_closed' and messages[-1]['requests']==8
        final=json.loads(stderr.decode().split('CPU_SUPERVISOR_RESULT ')[-1])
        assert final['child_exit_success'] and final['child_exit_reaped']
        assert json.loads((state/'CPU-QUALIFIED-BEFORE-LOAD.json').read_bytes())['actual_model_calls']==0
        stops=list((Path(b['paths']['admission_root'])/'engineering-recovery-v3').glob('qualified-stop-*'))
        assert len(stops)==1
        result=json.loads((stops[0]/'event-0001.json').read_bytes())['payload']
        assert result=={'status':'already_exited','signal_attempts':0,'exit_observed':True,'error_type':None}
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=5)


@pytest.mark.parametrize('mode',('ready-proof','failure-proof','stop','export'))
def test_actual_proof_command_retains_both_cpu_streams(monkeypatch,tmp_path,mode):
    from training import c5_recovery_field_ssh as transport
    from training.c5_reuse_control_journal import ControlJournal
    from types import SimpleNamespace
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path)
    b=field.material(s,r,endpoint='mac',attempt=1,now=100)
    state=Path(b['paths']['state_root']);state.mkdir(mode=0o700,parents=True)
    session=transport.FieldSSHSession.__new__(transport.FieldSSHSession)
    session.binding=b;session.attempt=1;session.lifecycle=ControlJournal(b,'controller-lifecycle')
    monkeypatch.setattr(transport,'command',lambda name,attempt:[sys.executable,'-I','-B','-c',
        "import sys;print('CPU_PUBLIC_PROOF');print('CPU_DIAGNOSTIC',file=sys.stderr)"])
    result=session._captured_command(mode)
    assert result.returncode==0
    assert (state/(mode+'-stdout.raw')).read_bytes()==b'CPU_PUBLIC_PROOF\n'
    assert (state/(mode+'-stderr.raw')).read_bytes()==b'CPU_DIAGNOSTIC\n'
    proof=session.lifecycle.rows[-1]['payload']
    assert proof['complete_raw_capture'] and proof['stdout']['name']==mode+'-stdout.raw'
    assert proof['stderr']['name']==mode+'-stderr.raw'

@pytest.mark.parametrize('error,category',(
    (TimeoutError('followup_capture_read_deadline'),'transport'),
    (ValueError('field_pipe_deadline'),'transport'),
    (ValueError('field_whole_exchange_deadline'),'transport'),
    (ValueError('followup_capture_limit_or_error_no_retry'),'capture'),
    (TimeoutError('recovery_shared_budget_exhausted'),'integrity'),
    (ValueError('followup_capture_persisted_bytes_drift'),'integrity'),
    (ValueError('unknown_failure'),'integrity'),
    (KeyboardInterrupt(),'cancelled')))
def test_actual_entry_failure_classification_keeps_unknowns_closed(error,category):
    from tools.run_c5_recovery_mac_entry import failure_category
    assert failure_category(error)==category


def test_revision_material_12_hours_360_seconds_keeps_legacy_bindings(monkeypatch,tmp_path):
    s,r,p,old,g,plans,raw=fixture(monkeypatch,tmp_path)
    s['resources'].update(development_seconds_max=43200,research_seconds_max=108000)
    s['limits']['model_seconds']=360
    r.update(spec_sha256=sha(s),resources=s['resources'])
    new=field.material(s,r,endpoint='gpu',attempt=2,now=100)
    assert new['limits']['model_seconds']==360 and new['recovery']['scope']['development_seconds_max']==43200
    validate_binding(old);validate_binding(new)


def test_qualified_watchdog_uses_bound_request_deadline_and_larger_shared_reservation():
    from training.c5_reuse_gpu_supervisor import Watchdog,PACKET
    clock=[100.];limits=dict(LIMITS,model_seconds=360)
    w=Watchdog(100.,43140,clock=lambda:clock[0],limits=limits)
    for code in (b'L',b'B',b'R'):w.feed(PACKET.pack(code,100.))
    clock[0]=280.;assert w.check()==180
    clock[0]=460.
    with pytest.raises(ValueError,match='watchdog_deadline'):w.check()


def test_original_fixture_key_private_custody_survives_dispatch_key_cleanup(monkeypatch,tmp_path):
    from training.c5_recovery_field_mac import retain_fixture_audit_key
    from plugin.rhino_listener.c5_research_channel import read_json
    import stat
    private=tmp_path/'private';private.mkdir(mode=0o700)
    original=bytes(range(32));retain_fixture_audit_key(private,'write-base',original,'a'*64)
    record=read_json(private,'write-base.json')
    assert bytes.fromhex(record['key_hex'])==original and record['runtime_sha256']=='a'*64
    assert stat.S_IMODE((private/'write-base.json').stat().st_mode)==0o600
    with pytest.raises(FileExistsError):retain_fixture_audit_key(private,'write-base',original,'a'*64)


def test_partial_failure_cannot_be_promoted_without_original_private_key(monkeypatch,tmp_path):
    from training import c5_recovery_field_native_failure_audit as audit
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path);b=field.material(s,r,endpoint='mac',attempt=1,now=100)
    state=Path(b['paths']['state_root']);state.mkdir(mode=0o700,parents=True)
    from plugin.rhino_listener.c5_research_channel import publish_json
    release={'source_inventory_sha256':sha(r['source_files'])};publish_json(state,'entry-return-release.json',release)
    publish_json(state,'host-continuity-ready.json',{})
    kinds=['native_controller_open','host_ready_before_remote_launch','slot_open_intent','slot_model_scene',
        'controller_retired_no_retry','failure_cleanup_intent','failure_cleanup_observed','failure_cleanup_intent',
        'failure_cleanup_observed','failure_cleanup_intent','failure_cleanup_observed','failure_cleanup_attempts_observed']
    payloads=[{'binding':b},{'release':release,'ready':{}},{'slot_id':'write-base'},{'slot_id':'write-base'}, {},
        {'action':'close','scope':'known_current_fixture_only'},{}, {'action':'stop','scope':'known_current_fixture_only'}, {},
        {'action':'stop','scope':'known_hub_only'}, {}, {'errors':[]}]
    rows=[{'seq':i,'previous_sha256':ZERO,'scope_sha256':sha(b),'kind':k,'payload':p} for i,(k,p) in enumerate(zip(kinds,payloads))]
    head=chain(rows)
    with pytest.raises(FileNotFoundError):audit.audit_known_first_hub_stop(rows,b,head,r)


@pytest.mark.parametrize('corrupt',('none','fixture_signature','hub_signature','dispatch_key','hidden_dispatch','hub_source'))
def test_actual_cpu_native_first_exchange_timeout_keeps_original_keys_and_audits_cleanup(tmp_path,monkeypatch,corrupt):
    from eval import test_c5_reuse_native_entry as cpu
    from training.c5_recovery_field_mac import MacController
    from training.c5_recovery_field_native_failure_audit import audit_known_first_hub_stop
    from plugin.rhino_listener.c5_research_channel import read_json,publish_json
    from types import SimpleNamespace
    monkeypatch.setattr(cpu,'MacController',MacController)
    runner,external,peer,mr,gr,hub,event,public,runtime,calls=cpu.setup(tmp_path,monkeypatch)
    Original=runner.session_factory
    class TimeoutSession(Original):
        def __init__(self,*args):
            super().__init__(*args);self.capture=SimpleNamespace(check=lambda:None);self.diagnostics_spent=False
            def exchange(_):raise TimeoutError('CPU first whole exchange timeout')
            self.channel.exchange=exchange
        def finalize_diagnostics(self):return {'cpu_only':True}
    runner.session_factory=TimeoutSession
    try:
        with pytest.raises(TimeoutError):runner.drive(external)
        assert runner.session.stops==1 and hub.stopped and not event.handlers and calls==[]
        state=runner.state;slot=state/'write-base'
        assert (state/'audit-key-custody/write-base.json').exists() and not (slot/'handoff.key').exists()
        if corrupt in ('fixture_signature','hub_signature'):
            p=slot/'request-0001.json' if corrupt=='fixture_signature' else state/'hub-request-0001.json'
            v=read_json(p.parent,p.name)
            if corrupt=='fixture_signature':v['envelope']['signature']='0'*64
            else:v['signature']='0'*64
            p.write_text(json.dumps(v));p.chmod(0o600)
        elif corrupt=='hub_source':
            p=state/'hub-stop.json';v=read_json(state,p.name);v['source_sha256']='0'*64
            p.write_text(json.dumps(v));p.chmod(0o600)
        elif corrupt=='dispatch_key':publish_json(slot,'handoff.key',{'key_hex':bytes(range(32)).hex()})
        elif corrupt=='hidden_dispatch':publish_json(slot,'execute-0001.json',{'status':'done'})
        if corrupt=='none':
            result=audit_known_first_hub_stop(runner.journal.rows,runner.binding,runner.journal.head,runtime)
            assert result['known_native_cleanup_complete'] and result['fixture_control_signatures_verified']==3
            assert result['hub_control_signatures_verified']==2 and result['quality'] is None and not result['complete_eight_gate_passed']
        else:
            with pytest.raises((ValueError,cpu.NativeError)):audit_known_first_hub_stop(runner.journal.rows,runner.binding,runner.journal.head,runtime)
    finally:mr.close();gr.close()


@pytest.mark.parametrize('duration,allowed',((200,True),(360,False)))
def test_actual_peer_and_framed_channel_share_frozen_whole_request_deadline(monkeypatch,tmp_path,duration,allowed):
    from training.c5_reuse_generation import GenerationPeer
    from training.c5_reuse_field_transport import FieldModelChannel
    from training.c5_model_transport import request
    from training.c5_reuse_field_wire import envelope,frame
    s,r,p,b,g,plans,raw=fixture(monkeypatch,tmp_path)
    s['limits']['model_seconds']=360;r['spec_sha256']=sha(s)
    gpu=field.material(s,r,endpoint='gpu',attempt=1,now=100);mac=field.material(s,r,endpoint='mac',attempt=1,now=100)
    for binding in (mac,gpu):Path(binding['paths']['state_root']).mkdir(mode=0o700,parents=True)
    class Registry:
        def __init__(self,b):self.binding=b
        def claim(self,role):return {'study_id':self.binding['study_id'],'role':role,'scope_sha256':sha(self.binding),'replay_allowed':False}
    clock=[100.]
    def generate(prompt,stage):
        if stage=='selector':clock[0]+=duration
        raw='{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
        return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':raw_sha(prompt.encode()),'output_sha256':raw_sha(raw.encode())}
    peer=GenerationPeer(gpu,Registry(gpu),plans,Tokenizer(),generate,lambda _:contextlib.nullcontext(),lambda:None,lambda:None,clock=lambda:clock[0])
    class Pipe:
        def write(self,raw,deadline):self.raw=frame(peer.infer(json.loads(raw)));return len(raw)
        def read(self,deadline):assert deadline==460.;return self.raw
    channel=FieldModelChannel(mac,Registry(mac),Pipe(),lambda:None,lambda:None,plans,clock=lambda:clock[0])
    task=plans['write-base']['steps'][0]
    sent=envelope(mac,request(mac['study_id'],'write-base','base',0,task,{'unit':'Millimeters','objects':[],'groups':{}},
        {'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},mac['runtime_sha256'],'cpu-duration'))
    if allowed:assert channel.exchange(sent)['observation']['status']=='schema_valid_not_authorized'
    else:
        with pytest.raises(ValueError,match='deadline'):channel.exchange(sent)
        assert channel.journal.blocked and len(channel.spent)==1
