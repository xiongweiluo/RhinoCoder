#!/usr/bin/env python3
"""Standalone archived-C startup diagnosis. Reads only; never an entry grant.

Use the actual interpreter with -I -B, keeping installed cold dependencies.
No --serve/stop/export, fork, pidfd pin/signal, model/CUDA, state/grant/key,
SQLite write, Rhino call, subscription, source deployment or migration.
The operator diagnostic argv/main origin is not the original serve context.
"""
import argparse,ast,hashlib,json,os,stat,subprocess,sys,time,sqlite3
from pathlib import Path
SPEC='eval/c5/reuse-development-spec-20261012-c.json'
RUNTIME='eval/c5/reuse-development-runtime-freeze-20261012-c.json'
PLAN='eval/c5/reuse-field-environment-plan-20261012-c.json'
PARENTS={'mac':Path('/Users/xiongweiluo/RhinoCoder/data/training/c5'),'gpu':Path('/data')}
SPEC_SHA='10f821cacb0e5681c3b2f8286230eab7dfdd69102ed7ca3adf540f6cd2148446'
RUNTIME_SHA='160e74bb15497960d51d499f51bac6a8be67b38c0124af385296c1119ecedc24'
PINS=(('reuse-dev-20261011-a','f098afe6e005e3ae09129bb44531ce3947e07d6592632d86a2c75af24f0f2978','fcfe67c8382d7e2dd28dafd58bec37deea8a75e5686ef9e2b241ac6e0a9416f9'),
 ('reuse-dev-20261012-b','3110dd38a8b318150526394ae98e7b36233fa6ac91a64a2adb08a1f1b529afda','175bb33bf80d2f7559f4ee6d03c6634225c9df4839ef5f84686cd5814dd57574'),
 ('reuse-dev-20261012-c','310797d0dfbe9e787424f62140f8dae460fcd443b7b23043ca5e6dc1e8befb80','359892d9adc45bc33a966bc013b5bc4f2a04b979100e760ee506f2edf2304225'))
def need(ok,code):
    if not ok:raise ValueError(code)
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(v):return hashlib.sha256(canon(v)).hexdigest()
def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:need(k not in d,'diagnostic_duplicate_key');d[k]=v
        return d
    def constant(v):raise ValueError('diagnostic_nonfinite')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
def read(path,*,private=False,limit=2097152,allow_empty=False):
    path=Path(path);need(path.is_absolute() and path.resolve()==path,'diagnostic_alias')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_nlink==1 and not a.st_mode&(0o077 if private else 0o022) and (0<=a.st_size<=limit if allow_empty else 0<a.st_size<=limit),'diagnostic_file')
        raw=os.pread(fd,a.st_size+1,0);b=os.fstat(fd);c=path.lstat()
        need(len(raw)==a.st_size and all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_nlink')),'diagnostic_file_race')
        return raw
    finally:os.close(fd)
def retired(parent):
    result={}
    for instance,a,b in PINS:
        d=parent/(instance+'-state');i=d.lstat();need(d.resolve()==d and stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid() and stat.S_IMODE(i.st_mode)==0o700 and not os.path.lexists(d/'owner-approval.json'),'diagnostic_retired_state')
        for name,pin in [('entry-retired-no-retry.json',a),('owner-approval.retired-no-retry.json',b)]:need(hashlib.sha256(read(d/name,private=True)).hexdigest()==pin,'diagnostic_retirement_pin')
        result[instance]={'retirement_raw_sha256':a,'retired_grant_raw_sha256':b,'active_grant_absent':True}
    return result
TABLE='CREATE TABLE admission (study TEXT NOT NULL, role TEXT NOT NULL, scope_sha256 TEXT NOT NULL, tombstone_sha256 TEXT NOT NULL, PRIMARY KEY(study,role))'
def registry_snapshot(parent,endpoint):
    d=parent/'c5-reuse-global-admission-v1'
    if not os.path.lexists(d):
        need(endpoint=='gpu','diagnostic_mac_registry_missing')
        return {'exists':False,'rows':[],'file_sha256':{},'root_name':d.name,'writes':0}
    need(endpoint=='mac' and d.resolve()==d and stat.S_IMODE(d.stat().st_mode)==0o700 and d.stat().st_uid==os.getuid(),'diagnostic_registry_directory')
    expected={'admission.lock','admission.sqlite','controller.consumed.json','host.consumed.json'}
    need(set(os.listdir(d))==expected,'diagnostic_registry_population')
    hashes={n:hashlib.sha256(read(d/n,private=True,limit=16777216,allow_empty=n=='admission.lock')).hexdigest() for n in sorted(expected)}
    db=sqlite3.connect((d/'admission.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        need(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'diagnostic_registry_integrity')
        need(db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()==[('table','admission',TABLE),('index','sqlite_autoindex_admission_1',None)],'diagnostic_registry_schema')
        rows=[list(x) for x in db.execute('SELECT * FROM admission ORDER BY role').fetchall()]
    finally:db.close()
    need(len(rows)==2 and [x[1] for x in rows]==['controller','host'] and all(x[0]=='C5DEV-REUSE-20261012-C' for x in rows),'diagnostic_consumed_rows')
    for study,role,scope,tombstone in rows:
        value=decode(read(d/(role+'.consumed.json'),private=True));need(value=={'study_id':study,'role':role,'scope_sha256':scope,'replay_allowed':False} and sha(value)==tombstone,'diagnostic_registry_tombstone')
    need(set(os.listdir(d))==expected and hashes=={n:hashlib.sha256(read(d/n,private=True,limit=16777216,allow_empty=n=='admission.lock')).hexdigest() for n in sorted(expected)},'diagnostic_registry_changed')
    return {'exists':True,'rows':rows,'file_sha256':hashes,'root_name':d.name,'writes':0}
def primitive_guard(capabilities):
    need(type(capabilities) is dict and set(capabilities)=={'platform','fork','pidfd_open','pidfd_send_signal'} and type(capabilities['platform']) is str and all(type(capabilities[k]) is bool for k in ('fork','pidfd_open','pidfd_send_signal')),'diagnostic_primitive_schema')
    return capabilities['platform']=='linux' and all(capabilities[k] for k in ('fork','pidfd_open','pidfd_send_signal'))
def static_boundaries(source):
    tree=ast.parse(source);f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='supervise')
    first=f.body[0];expected=ast.parse("sys.platform=='linux' and hasattr(os,'fork') and hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal')",mode='eval').body
    need(isinstance(first,ast.Expr) and isinstance(first.value,ast.Call) and ast.dump(first.value.args[0])==ast.dump(expected),'diagnostic_first_guard_expression')
    calls=[n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='AdmissionRegistry']
    need(len(calls)==1,'diagnostic_supervisor_registry_call')
    call=calls[0];create=next((k.value for k in call.keywords if k.arg=='create'),None)
    return {'supervisor_registry_uses_default_create_false':create is None,'original_remote_failure_proven_by_static_check':False}
def diagnose(endpoint):
    need(not sys.flags.no_site,'diagnostic_site_required_for_cold_dependencies')
    parent=PARENTS[endpoint];root=parent/'reuse-dev-20261012-c-source'
    need(root.resolve()==root and os.getuid()==(501 if endpoint=='mac' else 1000),'diagnostic_root_uid')
    old=retired(parent);before=registry_snapshot(parent,endpoint)
    s,r,p=(decode(read(root/n)) for n in (SPEC,RUNTIME,PLAN));need(sha(s)==SPEC_SHA and sha(r)==RUNTIME_SHA and r['spec_sha256']==SPEC_SHA,'diagnostic_archived_hashes')
    names=set(r['source_files'])|{RUNTIME};need({x.relative_to(root).as_posix() for x in root.rglob('*') if x.is_file()}==names and not any(x.is_symlink() for x in root.rglob('*')),'diagnostic_source_population')
    for n,v in r['source_files'].items():
        path=Path(n);need(not path.is_absolute() and '..' not in path.parts,'diagnostic_source_name');need(hashlib.sha256(read(root/n)).hexdigest()==v,'diagnostic_source_byte')
    # Only the already-byte-verified archived project is imported. The new
    # diagnostic __main__ is deliberately outside its guard and not claimed
    # as the original serve caller; no approved_entry/bind/grant is supplied.
    sys.path.insert(0,str(root))
    from plugin.rhino_listener.c5_reuse_runtime_scope import ReuseSourceGuard
    from training.c5_reuse_gpu_loader import validate_plan
    validate_plan(s,r,p)
    from training.c5_reuse_gpu_supervisor import supervise,independent_stop
    from training.c5_reuse_development_plan import public_plan
    public_plan(root);guard=ReuseSourceGuard(root,r['source_files']);guard()
    process={}
    if endpoint=='gpu':
        from training.c5_reuse_process_identity import LinuxIdentity
        observed=LinuxIdentity()(os.getpid());expected=[p['gpu_process']['python'],'-I','-B',str(root/p['gpu_process']['entry']),'--serve']
        expected_sha=hashlib.sha256(b'\0'.join(x.encode() for x in expected)+b'\0').hexdigest()
        need(observed['argv_sha256']!=expected_sha,'diagnostic_must_not_be_serve')
        import threading,signal
        process={'identity_of_diagnostic_process_only':observed,'expected_archived_serve_argv':expected,'diagnostic_argv_is_serve':False,
          'diagnostic_cwd_matches_source':observed['cwd']==str(root),'uid_matches':observed['uid']==p['gpu_process']['uid'],
          'boot_matches':observed['boot_id']==p['gpu_process']['boot_id'],'thread_count':threading.active_count(),
          'pidfd_open_available':hasattr(os,'pidfd_open'),'pidfd_send_signal_available':hasattr(signal,'pidfd_send_signal'),'fork_available':hasattr(os,'fork'),
          'frozen_first_primitive_guard_would_pass':primitive_guard({'platform':sys.platform,'fork':hasattr(os,'fork'),'pidfd_open':hasattr(os,'pidfd_open'),'pidfd_send_signal':hasattr(signal,'pidfd_send_signal')}),
          'first_guard_rejection_if_missing_apis':'reuse_linux_owned_child_primitives',
          'model_packages_imported':any(n in sys.modules for n in ('torch','transformers','peft'))}
        for name,args in [('gpu',['--query-gpu=uuid,memory.used','--format=csv,noheader,nounits']),('compute',['--query-compute-apps=pid','--format=csv,noheader,nounits'])]:
            q=subprocess.run(['nvidia-smi']+args,capture_output=True,text=True,check=True,timeout=20);process[name]=q.stdout.strip().splitlines()
    else:
        from plugin.rhino_listener.c5_reuse_mac_scope import verify_process_identity
        need(Path(sys.executable).resolve()==Path('/opt/anaconda3/bin/python3.13') and Path(sys.prefix).resolve()==Path('/opt/anaconda3'),'diagnostic_mac_interpreter')
        verify_process_identity(p['host_acceptance']['process_observation']);process={'accepted_rhino_identity_readonly_checked':True,'rhino_calls':0,'diagnostic_cwd':str(Path.cwd())}
    after=registry_snapshot(parent,endpoint);need(before==after and old==retired(parent),'diagnostic_state_changed');guard()
    return {'status':'readonly_archived_startup_diagnosis_not_execution_authority','endpoint':endpoint,'epoch':time.time(),
      'spec_sha256':SPEC_SHA,'runtime_sha256':RUNTIME_SHA,'source_files_verified':len(r['source_files']),
      'retirements':old,'registry_before':before,'registry_after':after,'process':process,
      'static_boundaries':static_boundaries(read(root/'training/c5_reuse_gpu_supervisor.py')),
      'original_serve_argv_or_stderr_reconstructed':False,'diagnostic_main_in_archived_source_closure':False,
      'installed_model_and_complete_environment_bytes_rehashed':False,'model_or_rhino_calls':0,'fork_pidfd_pin_signal_or_registry_mutations':0,
      'owner_grant_used':False,'new_study_or_candidate_created':False,'execution_authority':False,'execution_ready':False}
def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--endpoint',choices=('mac','gpu'),required=True);args=a.parse_args()
    print(json.dumps(diagnose(args.endpoint),sort_keys=True),flush=True)
if __name__=='__main__':main()
