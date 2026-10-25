"""Bounded raw stdout/stderr files, drained independently of the protocol.

Files exist before launch. No process launcher/signaller, model or grant.
Overflow/error/unknown exit is evidence of incompleteness, never retry/pass.
"""
import hashlib,os,queue,selectors,stat,threading,time
from pathlib import Path
from training.c5_reuse_evidence import require
from training.c5_reuse_field_transport import FieldPipe
STDOUT_CAP=64*1024*1024
STDERR_CAP=262144
CHUNK=32768

class RawFile:
    def __init__(self,path,cap):
        require(type(cap) is int and 0<cap<=STDOUT_CAP,'followup_capture_cap')
        self.path=Path(path);self.fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        self.identity=os.fstat(self.fd);self.cap=cap;self.observed=0;self.retained=0
        self.all_sha=hashlib.sha256();self.prefix_sha=hashlib.sha256();self.eof=False;self.error=None
        self.lock=threading.Lock();self.sealed=False
    def feed(self,raw):
        require(type(raw) is bytes and 0<len(raw)<=CHUNK,'followup_capture_chunk')
        with self.lock:
            require(not self.sealed,'followup_capture_sealed')
            self.all_sha.update(raw);self.observed+=len(raw);prefix=raw[:max(0,self.cap-self.retained)]
            offset=0
            while offset<len(prefix):
                n=os.write(self.fd,prefix[offset:]);require(n>0,'followup_capture_write');offset+=n
            self.prefix_sha.update(prefix);self.retained+=len(prefix)
    def finish(self,status):
        with self.lock:
            require(not self.sealed,'followup_capture_no_refinish');self.sealed=True
            try:
                os.fsync(self.fd);a=os.fstat(self.fd);b=self.path.lstat()
                require(stat.S_ISREG(b.st_mode) and b.st_uid==os.getuid() and b.st_nlink==1 and stat.S_IMODE(b.st_mode)==0o600
                    and (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino)==(self.identity.st_dev,self.identity.st_ino)
                    and a.st_size==self.retained,'followup_capture_file_drift')
                check_fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW)
                try:
                    digest=hashlib.sha256()
                    while True:
                        block=os.read(check_fd,65536)
                        if not block:break
                        digest.update(block)
                    require(digest.hexdigest()==self.prefix_sha.hexdigest(),'followup_capture_persisted_bytes_drift')
                finally:os.close(check_fd)
            finally:os.close(self.fd)
            return {'name':self.path.name,'observed_bytes':self.observed,'retained_bytes':self.retained,
                'observed_bytes_sha256':self.all_sha.hexdigest(),'retained_bytes_sha256':self.prefix_sha.hexdigest(),
                'truncated':self.observed>self.cap,'eof_observed':self.eof,'exit_status':status,'error_type':self.error,
                'complete_raw_capture':self.eof and status is not None and self.observed<=self.cap and self.error is None,
                'execution_authority':False,'retry_allowed':False}

class CapturedStreams:
    def __init__(self,root,prefix,*,stdout_cap=STDOUT_CAP,stderr_cap=STDERR_CAP):
        root=Path(root);require(root.is_absolute() and root.resolve()==root and root.is_dir()
            and stat.S_IMODE(root.stat().st_mode)==0o700 and root.stat().st_uid==os.getuid(),'followup_capture_root')
        require(prefix in ('serve','stop','export'),'followup_capture_name')
        self.stdout=RawFile(root/(prefix+'-stdout.raw'),stdout_cap)
        try:self.stderr=RawFile(root/(prefix+'-stderr.raw'),stderr_cap)
        except BaseException:self.stdout.finish(None);raise
        self.queue=queue.Queue(maxsize=16);self.delivery_overflow=False;self.stop=threading.Event()
        self.threads=[];self.process=None;self.finished=False
    def start(self,process,*,protocol):
        require(self.process is None and not self.finished,'followup_capture_launch_once');self.process=process
        for stream,capture,deliver in ((process.stdout,self.stdout,protocol),(process.stderr,self.stderr,False)):
            os.set_blocking(stream.fileno(),False)
            t=threading.Thread(target=self._pump,args=(stream,capture,deliver),daemon=True)
            self.threads.append(t);t.start()
    def _pump(self,stream,capture,deliver):
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(stream.fileno(),selectors.EVENT_READ)
                while not self.stop.is_set():
                    if not selector.select(0.05):continue
                    try:raw=os.read(stream.fileno(),CHUNK)
                    except BlockingIOError:continue
                    if raw:capture.feed(raw)
                    else:capture.eof=True
                    if deliver and not self.delivery_overflow:
                        try:self.queue.put_nowait(raw)
                        except queue.Full:self.delivery_overflow=True
                    if not raw:break
        except BaseException as exc:capture.error=type(exc).__name__
    def check(self):
        require(not self.delivery_overflow and self.stdout.error is self.stderr.error is None
            and self.stdout.observed<=self.stdout.cap and self.stderr.observed<=self.stderr.cap,'followup_capture_limit_or_error_no_retry')
    def read(self,deadline):
        self.check()
        require(not self.delivery_overflow and self.stdout.error is None,'followup_protocol_delivery_unknown')
        remaining=deadline-time.monotonic();require(remaining>0,'followup_capture_read_deadline')
        try:raw=self.queue.get(timeout=remaining)
        except queue.Empty:raise TimeoutError('followup_capture_read_deadline')
        require(not self.delivery_overflow and self.stdout.error is None,'followup_protocol_delivery_unknown')
        self.check();return raw
    def finish(self):
        require(not self.finished,'followup_capture_finalize_once');self.finished=True
        deadline=time.monotonic()+2
        for t in self.threads:t.join(max(0,deadline-time.monotonic()))
        self.stop.set()
        for t in self.threads:t.join(0.2)
        require(not any(t.is_alive() for t in self.threads),'followup_capture_thread_unknown')
        status=None if self.process is None else self.process.poll()
        stdout=self.stdout.finish(status);stderr=self.stderr.finish(status)
        tail=sum(len(v) for v in list(self.queue.queue))
        return {'stdout':stdout,'stderr':stderr,'protocol_delivery_overflow':self.delivery_overflow,
            'unconsumed_protocol_tail_bytes':tail,'complete_raw_capture':stdout['complete_raw_capture'] and stderr['complete_raw_capture'],
            'execution_authority':False,'whole_field_pass':False,'retry_allowed':False}

class CapturedPipe(FieldPipe):
    def __init__(self,write_fd,read_fd,capture):
        super().__init__(write_fd,read_fd);self.capture=capture
    def read(self,deadline):return self.capture.read(deadline)
