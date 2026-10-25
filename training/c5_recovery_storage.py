"""Private append-only evidence. No implicit migration or history clearing."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import threading
from training.c5_reuse_evidence import canonical,is_sha,require,sha,strict,ZERO

def read_private(path,*,empty=False):
    path=Path(path);require(path.is_absolute() and path.resolve()==path,'recovery_file_alias')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_nlink==1
                and stat.S_IMODE(a.st_mode)==0o600 and (0 if empty else 1)<=a.st_size<=1048576,
                'recovery_private_file')
        raw=os.pread(fd,a.st_size+1,0);b=os.fstat(fd);c=path.lstat()
        require(len(raw)==a.st_size and all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in
                ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')),
                'recovery_file_race')
        return raw
    finally:os.close(fd)

def write_once(root,name,value):
    require(Path(name).name==name,'recovery_file_name')
    raw=canonical(value)+b'\n'
    fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        offset=0
        while offset<len(raw):
            n=os.write(fd,raw[offset:]);require(n>0,'recovery_write');offset+=n
        os.fsync(fd)
    finally:os.close(fd)
    d=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(d)
    finally:os.close(d)

def directory(root):
    s=root.lstat()
    require(root.is_absolute() and root.resolve()==root and stat.S_ISDIR(s.st_mode)
            and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'recovery_private_directory')
    return s

class EvidenceLog:
    """Same-parent flock, O_EXCL/fsync events, reopenable after process exit.

    A partial file remains evidence and blocks new effects; no auto repair.
    The caller binds its immutable manifest and historical byte guard.
    """
    def __init__(self,root,binding,history_guard,*,create=False):
        self.root=Path(root);self.binding=strict(canonical(binding));self.history_guard=history_guard
        history_guard()
        if create:
            self.root.mkdir(mode=0o700)
            write_once(self.root,'manifest.json',{'binding':self.binding,'history_preserved':True})
        self.identity=directory(self.root)
        self.mutex=threading.RLock()
        self.fd=os.open(self.root/'manifest.json',os.O_RDONLY|os.O_NOFOLLOW)
        try:
            with self.locked():self.rows()
        except BaseException:self.close();raise

    @contextmanager
    def locked(self,*,blocking=True):
        self.mutex.acquire()
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB))
        except BaseException:self.mutex.release();raise
        try:
            s=directory(self.root);f=os.fstat(self.fd);p=(self.root/'manifest.json').lstat()
            require((s.st_dev,s.st_ino)==(self.identity.st_dev,self.identity.st_ino)
                    and (f.st_dev,f.st_ino)==(p.st_dev,p.st_ino),'recovery_log_replaced')
            require(read_private(self.root/'manifest.json')==canonical(
                    {'binding':self.binding,'history_preserved':True})+b'\n','recovery_manifest_changed')
            self.history_guard();yield
        finally:
            fcntl.flock(self.fd,fcntl.LOCK_UN);self.mutex.release()

    def rows(self):
        names=set(os.listdir(self.root))-{'manifest.json'}
        require(len(names)<=512 and names=={'event-%04d.json'%i for i in range(len(names))},
                'recovery_log_population')
        rows=[];head=ZERO
        for i in range(len(names)):
            raw=read_private(self.root/('event-%04d.json'%i));row=strict(raw)
            require(raw==canonical(row)+b'\n' and set(row)==
                    {'seq','previous_sha256','binding_sha256','kind','payload','record_sha256'}
                    and row['seq']==i and row['previous_sha256']==head
                    and row['binding_sha256']==sha(self.binding)
                    and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),
                    'recovery_raw_chain')
            rows.append(row);head=row['record_sha256']
        return rows

    def append_locked(self,kind,payload):
        rows=self.rows();require(len(rows)<512,'recovery_log_capacity')
        value={'seq':len(rows),'previous_sha256':rows[-1]['record_sha256'] if rows else ZERO,
               'binding_sha256':sha(self.binding),'kind':kind,'payload':payload}
        value['record_sha256']=sha(value);write_once(self.root,'event-%04d.json'%len(rows),value)
        self.history_guard();return value

    def append(self,kind,payload):
        with self.locked():return self.append_locked(kind,payload)
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

def pinned_history(paths):
    """Explicit old public evidence only. No corpus/key enumeration."""
    pins={Path(p):h for p,h in paths.items()}
    require(pins and all(is_sha(h) for h in pins.values()),'recovery_history_required')
    def guard():
        for p,h in pins.items():
            require(hashlib.sha256(read_private(p,empty=p.name=='admission.lock')).hexdigest()==h,
                    'recovery_legacy_bytes_changed')
    guard();return guard
