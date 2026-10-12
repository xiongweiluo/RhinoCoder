"""Synthetic CPU files/processes only; never the actual study/root/grant."""
import base64,copy,hashlib,json,os,sqlite3,subprocess,sys,time,zlib
from pathlib import Path
import pytest
from plugin.rhino_listener import c5_followup_admission as admission
from plugin.rhino_listener import c5_followup_scope as scope
from plugin.rhino_listener.c5_followup_profile import STUDY,INSTANCE,CONTINUATION,GENESIS
from plugin.rhino_listener.c5_reuse_field_scope import PROTOCOL,COMPARISON,LIMITS
from training.c5_followup_diagnostics import CapturedStreams,CapturedPipe,RawFile
from training.c5_followup_mac_controller import MacController
ROOT=Path(__file__).resolve().parents[1]

def materials():
    old=json.loads((ROOT/'eval/c5/reuse-development-spec-20261012-c.json').read_bytes())
    old.update(study_id=STUDY,instance_id=INSTANCE,resources=scope.resources(),continuation=copy.deepcopy(CONTINUATION))
    old['host_policy']['instance_id']=INSTANCE
    endpoints={e:{'source_root':str(Path(p).parent/(INSTANCE+'-source')),'state_root':str(Path(p).parent/(INSTANCE+'-state')),'admission_root':p} for e,p in GENESIS['global_roots'].items()}
    runtime={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'spec_sha256':scope.sha(old),'endpoints':endpoints,
        'source_files':{'training/__init__.py':'a'*64},'environment_sha256':'a'*64,'model_assets_sha256':'a'*64,
        'host_readable_files_sha256':'a'*64,'host_policy':copy.deepcopy(old['host_policy']),'resources':scope.resources(),
        'execution_ready':True,'continuation':copy.deepcopy(CONTINUATION)}
    return old,runtime

def test_material_binding_is_pure_and_not_an_owner_grant():
    s,r=materials();v=scope.material(s,r,now=1791820000,endpoint='mac')
    assert not v['approval_origin_verified'] and not v['whole_field_authority_verified']
    old=json.loads((ROOT/'eval/c5/reuse-development-owner-exact-approval-and-preparation-20261012-c.json').read_bytes())
    with pytest.raises(ValueError):scope.bind(s,r,old,now=1791820000,endpoint='mac')

@pytest.mark.parametrize('mutation',['study','instance','history','retry','formal','resource','root','deadline','ready','int_alias'])
def test_old_identity_or_history_and_budget_bypass_cannot_bind(mutation):
    s,r=materials()
    if mutation=='study':s['study_id']='C5DEV-REUSE-20261012-C'
    elif mutation=='instance':s['instance_id']='reuse-dev-20261012-c'
    elif mutation=='history':s['continuation']['admission_genesis_sha256']='0'*64
    elif mutation=='retry':s['automatic_retry_allowed']=True
    elif mutation=='formal':s['private_formal_data_allowed']=True
    elif mutation=='resource':s['resources']['development_seconds_max']+=1
    elif mutation=='root':r['endpoints']['mac']['admission_root']+='/empty'
    elif mutation=='deadline':s['resources']['generation_cutoff_epoch']+=900
    elif mutation=='ready':s['execution_ready']=False
    else:s['continuation']['maximum_additional_development_attempts']=True
    r['spec_sha256']=scope.sha(s)
    with pytest.raises(ValueError):scope.material(s,r,now=1791820000,endpoint='mac')

def synthetic_registry(tmp_path,monkeypatch,endpoint):
    root=tmp_path/'c5-reuse-global-admission-v1';g=copy.deepcopy(GENESIS)
    if endpoint=='mac':
        root.mkdir(mode=0o700);(root/'admission.lock').touch(mode=0o600)
        db=sqlite3.connect(root/'admission.sqlite');db.execute(admission.TABLE);rows=[]
        for role in ('controller','host'):
            value={'study_id':'C5DEV-REUSE-20261012-C','role':role,'scope_sha256':'a'*64,'replay_allowed':False}
            row=[value['study_id'],role,value['scope_sha256'],scope.sha(value)];rows.append(row)
            p=root/(role+'.consumed.json');p.write_bytes(scope.canonical(value)+b'\n');p.chmod(0o600)
            db.execute('INSERT INTO admission VALUES (?,?,?,?)',row)
        db.commit();db.close();(root/'admission.sqlite').chmod(0o600)
        g['legacy_snapshot']['mac'].update(rows=rows,file_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()})
    c=copy.deepcopy(CONTINUATION);c['admission_genesis_sha256']=scope.sha(g)
    monkeypatch.setattr(admission,'GENESIS',g);monkeypatch.setattr(admission,'CONTINUATION',c)
    # Explicit CPU dependency injection; production validator stays strict and
    # production roots are never used by this file-I/O fixture.
    monkeypatch.setattr(admission,'validate_binding',lambda v:None)
    binding={'study_id':STUDY,'endpoint':endpoint,'paths':{'admission_root':str(root)},'runtime_sha256':'synthetic-d-only'}
    return root,binding

@pytest.mark.parametrize('endpoint',['mac','gpu'])
def test_same_root_nonempty_history_and_once_role_claim_preserve_old_bytes(tmp_path,monkeypatch,endpoint):
    root,b=synthetic_registry(tmp_path,monkeypatch,endpoint)
    old={p.name:p.read_bytes() for p in root.iterdir()} if root.exists() else {}
    admission.initialize(b)
    with admission.AdmissionRegistry(b) as registry:
        v=registry.audit();assert len(v['legacy_rows'])==2 and v['new_rows']==[]
        role='host' if endpoint=='mac' else 'worker';registry.claim(role)
        assert len(registry.audit()['new_rows'])==1
        with pytest.raises(FileExistsError):registry.claim(role)
    assert all((root/n).read_bytes()==raw for n,raw in old.items())
    with pytest.raises(ValueError):admission.initialize(b)

@pytest.mark.parametrize('change',['empty_history','extra','old_byte','partial_role','foreign_role','manifest_byte','replace_root'])
def test_unknown_history_or_partial_new_state_blocks_without_repair(tmp_path,monkeypatch,change):
    root,b=synthetic_registry(tmp_path,monkeypatch,'mac');admission.initialize(b)
    if change=='empty_history':admission.GENESIS['legacy_snapshot']['mac']['rows']=[]
    elif change=='extra':(root/'empty-replacement.json').write_bytes(b'{}')
    elif change=='old_byte':(root/'admission.lock').write_bytes(b'x')
    elif change=='partial_role':p=root/admission.name('host');p.write_bytes(b'{');p.chmod(0o600)
    elif change=='foreign_role':p=root/admission.name('worker');p.write_bytes(b'{}');p.chmod(0o600)
    elif change=='manifest_byte':(root/admission.MANIFEST).write_bytes(b'{}')
    else:
        with admission.AdmissionRegistry(b) as registry:
            root.rename(tmp_path/'old');root.mkdir(mode=0o700)
            with pytest.raises((ValueError,OSError)):registry.audit()
        return
    before={p.name:p.read_bytes() for p in root.iterdir()}
    with pytest.raises((ValueError,OSError)):admission.AdmissionRegistry(b)
    assert before=={p.name:p.read_bytes() for p in root.iterdir()}

def test_claim_write_error_leaves_poison_file_without_retry(tmp_path,monkeypatch):
    root,b=synthetic_registry(tmp_path,monkeypatch,'mac');admission.initialize(b)
    with admission.AdmissionRegistry(b) as registry:
        monkeypatch.setattr(admission.os,'write',lambda *a:(_ for _ in ()).throw(OSError('synthetic write fault')))
        with pytest.raises(OSError):registry.claim('host')
        assert (root/admission.name('host')).exists()
        with pytest.raises(ValueError):registry.audit()

@pytest.mark.parametrize('endpoint',['mac','gpu'])
def test_constructor_cannot_implicitly_initialize(tmp_path,monkeypatch,endpoint):
    root,b=synthetic_registry(tmp_path,monkeypatch,endpoint)
    with pytest.raises(ValueError):admission.AdmissionRegistry(b,create=True)
    assert not (root/admission.MANIFEST).exists()

def cpu_process(stdout,stderr,code):
    out=repr(base64.b64encode(zlib.compress(stdout)));err=repr(base64.b64encode(zlib.compress(stderr)))
    program='import sys,zlib,base64;sys.stdout.buffer.write(zlib.decompress(base64.b64decode('+out+')));sys.stdout.flush();sys.stderr.buffer.write(zlib.decompress(base64.b64decode('+err+')));sys.stderr.flush();sys.exit('+str(code)+')'
    return subprocess.Popen([sys.executable,'-I','-B','-c',program],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)

@pytest.mark.parametrize('code',[0,7])
def test_actual_cpu_double_stream_drains_and_retains_nonzero_exit(tmp_path,code):
    tmp_path.chmod(0o700);c=CapturedStreams(tmp_path,'serve');p=cpu_process(b'frame\n',b'original synthetic error\n',code)
    c.start(p,protocol=True);pipe=CapturedPipe(p.stdin.fileno(),p.stdout.fileno(),c)
    data=b''
    while True:
        raw=pipe.read(time.monotonic()+5)
        if not raw:break
        data+=raw
    p.wait(timeout=5);v=c.finish()
    assert data==b'frame\n' and v['complete_raw_capture'] and v['stderr']['exit_status']==code
    assert (tmp_path/'serve-stderr.raw').read_bytes()==b'original synthetic error\n'
    assert not v['whole_field_pass'] and not v['execution_authority']
    with pytest.raises(ValueError):c.finish()

def test_large_double_stream_never_deadlocks_or_claims_complete_truncated_capture(tmp_path):
    tmp_path.chmod(0o700);c=CapturedStreams(tmp_path,'stop',stdout_cap=17,stderr_cap=13)
    stdout=b'x'*262144;stderr=b'y'*262144;p=cpu_process(stdout,stderr,3);c.start(p,protocol=False)
    p.wait(timeout=10);v=c.finish()
    assert not v['complete_raw_capture'] and v['stdout']['observed_bytes_sha256']==hashlib.sha256(stdout).hexdigest()
    assert v['stderr']['observed_bytes_sha256']==hashlib.sha256(stderr).hexdigest()
    assert (tmp_path/'stop-stdout.raw').read_bytes()==stdout[:17]
    assert (tmp_path/'stop-stderr.raw').read_bytes()==stderr[:13]
    with pytest.raises(ValueError):c.check()

def test_missing_launch_or_exit_never_complete(tmp_path):
    tmp_path.chmod(0o700);c=CapturedStreams(tmp_path,'serve');v=c.finish()
    assert not v['complete_raw_capture'] and v['stdout']['exit_status'] is None

def test_persisted_prefix_drift_cannot_be_sealed_complete(tmp_path):
    p=tmp_path/'raw';c=RawFile(p,10);c.feed(b'1234');c.eof=True;p.write_bytes(b'xxxx')
    with pytest.raises(ValueError,match='persisted_bytes_drift'):c.finish(0)

@pytest.mark.parametrize('stop_error,native_error,journal_error',[(False,False,False),(True,False,False),(True,True,False),(True,True,True)])
def test_actual_driver_failure_always_attempts_first_native_and_capture_once(stop_error,native_error,journal_error):
    calls=[];runner=MacController.__new__(MacController);runner.spent=False
    class Journal:
        def append(self,*args):
            if journal_error:raise OSError('synthetic journal failure')
    class Session:
        stop_spent=False;diagnostics_spent=False
        def independent_stop(self):
            self.stop_spent=True;calls.append('gpu')
            if stop_error:raise RuntimeError('synthetic unknown gpu stop')
        def finalize_diagnostics(self):self.diagnostics_spent=True;calls.append('capture')
    runner.journal=Journal();runner.session=Session()
    def native():
        calls.append('native')
        if native_error:raise ValueError('synthetic cleanup unknown')
    runner._known_native_cleanup=native
    def failure(_):raise EOFError('primary startup failure')
    runner._drive=failure
    with pytest.raises(EOFError,match='primary'):runner.drive(None)
    assert calls==['gpu','native','capture']
    with pytest.raises(ValueError,match='no_retry'):runner.drive(None)
    assert calls==['gpu','native','capture']

@pytest.mark.parametrize('legacy',[False,True])
def test_new_transport_requires_new_entry_and_retained_raw_stderr(legacy):
    from training.c5_followup_ssh import POLICY,validate_transport
    from training.c5_reuse_ssh import POLICY as OLD
    value={'policy':copy.deepcopy(OLD if legacy else POLICY),'ssh_executable_sha256':'a'*64}
    if legacy:
        with pytest.raises(ValueError):validate_transport(value)
    else:validate_transport(value)
