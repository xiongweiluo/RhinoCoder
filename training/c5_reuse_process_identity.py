"""Read the one supplied Linux PID; never discover or kill by name."""
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

from training.c5_reuse_evidence import require
from training.c5_reuse_stop import PidfdOperations, target


def stable_file_sha(path):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path,'reuse_identity_executable_alias')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'reuse_identity_regular_executable')
        value=hashlib.sha256()
        while True:
            block=os.read(fd,1024*1024)
            if not block:break
            value.update(block)
        after=os.fstat(fd); named=path.lstat()
        require(all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in
                    ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_nlink')),
                'reuse_identity_executable_race')
        return value.hexdigest()
    finally:os.close(fd)


class LinuxIdentity:
    def __init__(self,root=Path('/proc')):
        require(sys.platform=='linux' or root!=Path('/proc'),'reuse_linux_identity_required')
        self.root=Path(root)

    def _raw(self,path,limit):
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode),'reuse_proc_regular')
            raw=os.read(fd,limit+1)
            require(0<len(raw)<=limit,'reuse_proc_size')
            return raw
        finally:os.close(fd)

    def _stat(self,pid):
        require(type(pid) is int and pid>1,'reuse_proc_pid')
        raw=self._raw(self.root/str(pid)/'stat',16384).decode('ascii')
        prefix,tail=raw.rsplit(') ',1)
        fields=tail.split()
        require(prefix.split(' (',1)[0]==str(pid) and len(fields)>=20
                and fields[0] not in ('Z','X','x'),'reuse_proc_live_stat')
        return int(fields[1]),int(fields[19])

    def parent(self,pid):return self._stat(pid)[0]

    def __call__(self,pid):
        parent,start=self._stat(pid)
        proc=self.root/str(pid)
        uid=proc.stat().st_uid
        boot=self._raw(self.root/'sys/kernel/random/boot_id',128).decode('ascii').strip()
        require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot),'reuse_boot_id')
        executable=(proc/'exe').resolve(strict=True)
        cwd=(proc/'cwd').resolve(strict=True)
        argv=self._raw(proc/'cmdline',65536)
        require(argv.endswith(b'\0'),'reuse_proc_argv')
        result={'pid':pid,'uid':uid,'boot_id':boot,'start_ticks':start,
                'executable_sha256':stable_file_sha(executable),
                'argv_sha256':hashlib.sha256(argv).hexdigest(),'cwd':str(cwd)}
        require(self._stat(pid)==(parent,start) and proc.stat().st_uid==uid
                and (proc/'exe').resolve(strict=True)==executable
                and (proc/'cwd').resolve(strict=True)==cwd
                and self._raw(proc/'cmdline',65536)==argv,'reuse_proc_identity_race')
        target(result)
        return result


class OwnedPidfdOperations(PidfdOperations):
    def __init__(self,guard):
        reader=LinuxIdentity()
        super().__init__(guard,reader)
        self.parent=reader.parent
