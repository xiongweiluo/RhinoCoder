"""D admission in the original global root with immutable nonempty history.

No v1 SQLite writes, empty replacement registry, grant maker or migration on
import/construction. Only an exactly approved entry may call initialize().
The append-only role files are durable before any role effect; partial files
poison the registry. A file/hash binds a supplied anchor, not human origin.
"""
import fcntl,hashlib,os,sqlite3,stat,threading
from pathlib import Path
from contextlib import contextmanager
from .c5_reuse_field_scope import validate_binding,canonical,sha,strict,require
from .c5_reuse_admission import TABLE,ENDPOINT_ROLES
from .c5_followup_profile import STUDY,GENESIS,CONTINUATION
MANIFEST='followup-v2-genesis.json'
ROLES=('controller','host','worker','stop')
def name(role):return 'followup-d-'+role+'.consumed.json'

def read(p,*,empty=False):
    p=Path(p);require(p.is_absolute() and p.resolve()==p,'followup_admission_alias')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd);require(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_nlink==1
            and stat.S_IMODE(a.st_mode)==0o600 and (0 if empty else 1)<=a.st_size<=16777216,'followup_admission_file')
        raw=os.pread(fd,a.st_size+1,0);b=os.fstat(fd);c=p.lstat()
        require(len(raw)==a.st_size and all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in
            ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_nlink')),'followup_admission_race')
        return raw
    finally:os.close(fd)

def directory(root):
    st=root.lstat();require(root.is_absolute() and root.resolve()==root and stat.S_ISDIR(st.st_mode)
        and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o700,'followup_admission_directory')
    return st

def verify_history(root,endpoint,*,new_names=()):
    """Read-only old files. GPU's genesis imports Mac history, never zeroes it."""
    snapshot=GENESIS['legacy_snapshot'][endpoint]
    require(GENESIS['historical_consumed_rows_nonempty'] is True and len(GENESIS['legacy_snapshot']['mac']['rows'])==2
        and sha(GENESIS)==CONTINUATION['admission_genesis_sha256'],'followup_nonempty_history_genesis')
    if not os.path.lexists(root):
        require(endpoint=='gpu' and snapshot['exists'] is False and not new_names,'followup_missing_legacy');return
    directory(root);old=set(snapshot['file_sha256']);names=set(os.listdir(root))
    require(names==old|set(new_names),'followup_admission_unknown_population')
    def hashes():return {n:hashlib.sha256(read(root/n,empty=n=='admission.lock')).hexdigest() for n in sorted(old)}
    before=hashes();require(before==snapshot['file_sha256'],'followup_legacy_byte_drift')
    if snapshot['exists']:
        db=sqlite3.connect((root/'admission.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            require(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'followup_legacy_integrity')
            require(db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()==
                [('table','admission',TABLE),('index','sqlite_autoindex_admission_1',None)],'followup_legacy_schema')
            rows=[list(r) for r in db.execute('SELECT * FROM admission ORDER BY role')]
            require(rows==snapshot['rows'],'followup_legacy_rows')
        finally:db.close()
        for study,role,scope,tombstone in rows:
            value=strict(read(root/(role+'.consumed.json')))
            require(value=={'study_id':study,'role':role,'scope_sha256':scope,'replay_allowed':False}
                and sha(value)==tombstone,'followup_legacy_tombstone')
    else:require(endpoint=='gpu' and not old and snapshot['rows']==[],'followup_gpu_legacy_absence')
    require(before==hashes() and names==set(os.listdir(root)),'followup_legacy_changed')

def manifest(binding):
    return {'schema':2,'endpoint':binding['endpoint'],'genesis':GENESIS,'genesis_sha256':sha(GENESIS),
        'binding_sha256':sha(binding),'study_id':STUDY,'replay_allowed':False}

def write_once(root,filename,value):
    fd=os.open(root/filename,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        raw=canonical(value)+b'\n';offset=0
        while offset<len(raw):
            n=os.write(fd,raw[offset:]);require(n>0,'followup_admission_write');offset+=n
        os.fsync(fd)
    finally:os.close(fd)
    d=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(d)
    finally:os.close(d)

def initialize(binding):
    """Exactly-approved entry only; no claims or old-file modification."""
    validate_binding(binding);require(binding['study_id']==STUDY,'followup_study')
    root=Path(binding['paths']['admission_root']);verify_history(root,binding['endpoint'])
    if not os.path.lexists(root):root.mkdir(mode=0o700)
    write_once(root,MANIFEST,manifest(binding))
    with AdmissionRegistry(binding) as registry:
        result=registry.audit();require(result['new_rows']==[],'followup_initial_claim_absent')
    return {'nonempty_history_carried_forward':True,'new_role_claims':0,'whole_field_authority_verified':False}

class AdmissionRegistry:
    def __init__(self,binding,*,create=False):
        validate_binding(binding);require(binding['study_id']==STUDY and create is False,'followup_no_implicit_initialization')
        self.binding=strict(canonical(binding));self.root=Path(binding['paths']['admission_root'])
        self.identity=directory(self.root);self.mutex=threading.Lock();self.fd=None
        try:
            self.fd=os.open(self.root/MANIFEST,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with self._locked():self._audit_locked()
        except BaseException:self.close();raise
    @contextmanager
    def _locked(self):
        require(self.mutex.acquire(blocking=False),'followup_admission_busy');acquired=False
        try:
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB);acquired=True;yield
        finally:
            if acquired:fcntl.flock(self.fd,fcntl.LOCK_UN)
            self.mutex.release()
    def _audit_locked(self):
        current=directory(self.root)
        require((current.st_dev,current.st_ino)==(self.identity.st_dev,self.identity.st_ino),'followup_root_replaced')
        opened=os.fstat(self.fd);named=(self.root/MANIFEST).lstat()
        require((opened.st_dev,opened.st_ino)==(named.st_dev,named.st_ino),'followup_manifest_replaced')
        require(read(self.root/MANIFEST)==canonical(manifest(self.binding))+b'\n','followup_manifest_scope')
        allowed={name(r) for r in ENDPOINT_ROLES[self.binding['endpoint']]}
        present=set(os.listdir(self.root))&allowed
        verify_history(self.root,self.binding['endpoint'],new_names={MANIFEST}|present)
        rows=[]
        for role in sorted(ENDPOINT_ROLES[self.binding['endpoint']]):
            if name(role) not in present:continue
            value={'study_id':STUDY,'role':role,'scope_sha256':sha(self.binding),'replay_allowed':False}
            require(read(self.root/name(role))==canonical(value)+b'\n','followup_partial_or_unknown_consumption_no_retry')
            rows.append([STUDY,role,sha(self.binding),sha(value)])
        old=GENESIS['legacy_snapshot']['mac']['rows']
        return {'rows':old+rows,'new_rows':rows,'legacy_rows':old,'rows_sha256':sha(old+rows),
            'nonempty_history_carried_forward':True,'replay_allowed':False,'cross_host_global_coverage_proven':False}
    def audit(self):
        with self._locked():return self._audit_locked()
    def claim(self,role,*,fault=lambda boundary:None):
        require(role in ENDPOINT_ROLES[self.binding['endpoint']],'followup_endpoint_role')
        with self._locked():
            self._audit_locked()
            value={'study_id':STUDY,'role':role,'scope_sha256':sha(self.binding),'replay_allowed':False}
            write_once(self.root,name(role),value);fault('after_tombstone')
            self._audit_locked();return value
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
