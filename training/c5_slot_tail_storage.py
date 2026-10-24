"""Bounded owner-private evidence copy. Never called by public preparation."""
import hashlib, os, stat
from pathlib import Path
from plugin.rhino_listener.c5_research_native import require
from plugin.rhino_listener.c5_slot_tail_policy import POLICY


def evidence_inventory(root):
    require(root.resolve()==root and root.is_dir() and not root.is_symlink(), 'slot_tail_evidence_root')
    rows={};total=0
    # Finish finite metadata checks before opening any private file bytes.
    for p in sorted(root.rglob('*')):
        info=p.lstat();require(not stat.S_ISLNK(info.st_mode),'slot_tail_evidence_symlink')
        if stat.S_ISDIR(info.st_mode):continue
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
            and not stat.S_IMODE(info.st_mode)&0o022 and info.st_size<=POLICY['evidence_file_bytes_max'],
            'slot_tail_evidence_file_scope')
        total+=info.st_size
        require(total<=POLICY['evidence_total_bytes_max'] and len(rows)<POLICY['evidence_files_max'],
            'slot_tail_evidence_population_cap')
        if p.name.endswith('-audit.sqlite3-wal'):require(info.st_size==0,'slot_tail_nonempty_audit_wal')
        rows[p.relative_to(root).as_posix()]={'bytes':info.st_size,'mode':stat.S_IMODE(info.st_mode),
            'inode':info.st_ino,'mtime_ns':info.st_mtime_ns}
    for name,value in rows.items():
        p=root/name;require(p.resolve()==p,'slot_tail_evidence_symlink')
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);h=hashlib.sha256()
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            while True:
                chunk=stream.read(1048576)
                if not chunk:break
                h.update(chunk)
            after=os.fstat(stream.fileno())
        require((before.st_ino,before.st_mtime_ns,before.st_size)==(value['inode'],value['mtime_ns'],value['bytes'])
            and all((getattr(before,k)==getattr(after,k)==getattr(p.stat(),k))
                for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_mode','st_uid','st_nlink')),
            'slot_tail_evidence_changed')
        value['sha256']=h.hexdigest()
    return rows


def copy_evidence(original,destination):
    before=evidence_inventory(original);destination.mkdir(mode=0o700)
    for name,value in before.items():
        target=destination/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);h=hashlib.sha256()
        with (original/name).open('rb') as source,os.fdopen(fd,'wb') as out:
            while True:
                chunk=source.read(1048576)
                if not chunk:break
                out.write(chunk);h.update(chunk)
        require(h.hexdigest()==value['sha256'],'slot_tail_copy_source_changed')
    require(evidence_inventory(original)==before,'slot_tail_original_changed_during_copy')
    return before
