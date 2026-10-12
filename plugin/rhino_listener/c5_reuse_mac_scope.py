"""Readable Mac closure shared with the embedded entry; stdlib only."""
import hashlib
import os
from pathlib import Path
import stat
import sys
import re
import subprocess
import importlib.util
from datetime import datetime,timezone
from .c5_reuse_runtime_scope import approved_entry,read_bytes,MAC_PARENT
from .c5_reuse_field_scope import require, sha,COMPARISON

CODE_ROOTS=('/Applications/Rhino 8.app/Contents/','/Users/xiongweiluo/.rhinocode/',
    '/Users/xiongweiluo/Library/Application Support/McNeel/','/Users/xiongweiluo/.codex/worktrees/',
    '/opt/anaconda3/lib/')
EXACT_CODE=('/Applications/Rhino 8.app/Contents/MacOS/Rhinoceros','/opt/anaconda3/bin/python3.13')
AUDIT_TOKENIZER_ROOT=MAC_PARENT/'modelbridge-tokenizer'/COMPARISON['base_revision']
TOKENIZER_NAMES={'config.json','generation_config.json','merges.txt','tokenizer.json','tokenizer_config.json','vocab.json'}


def verify_audit_tokenizer(assets):
    require(assets['audit_tokenizer_dir']==str(AUDIT_TOKENIZER_ROOT)
            and set(assets['audit_tokenizer_files'])==TOKENIZER_NAMES,'reuse_fixed_audit_tokenizer')
    root=Path(assets['audit_tokenizer_dir'])
    require(root.resolve()==root and set(os.listdir(root))==TOKENIZER_NAMES,'reuse_audit_tokenizer_population')
    for name,expected in assets['audit_tokenizer_files'].items():
        require(hashlib.sha256(read_bytes(root/name,limit=16*1024*1024)).hexdigest()==expected,
                'reuse_audit_tokenizer_bytes')


def code_sha(path):
    path=Path(path)
    require(str(path) in EXACT_CODE or (any(str(path).startswith(p) for p in CODE_ROOTS)
            and path.suffix.lower() in ('.py','.so','.dll','.dylib','.rhp','.pyd')),'reuse_mac_public_code_only')
    require(path.is_absolute() and path.resolve()==path,'reuse_mac_code_alias')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and not before.st_mode&0o022,'reuse_mac_code_file')
        h=hashlib.sha256()
        while True:
            block=os.read(fd,1024*1024)
            if not block:break
            h.update(block)
        after=os.fstat(fd);named=path.lstat()
        require(all(getattr(before,k)==getattr(after,k)==getattr(named,k)
                    for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_nlink')),
                'reuse_mac_code_race')
        return h.hexdigest()
    finally:os.close(fd)


def verify_process_identity(process,*,embedded=False):
    require(type(process['pid']) is int and process['pid']>0 and type(process['uid']) is int,
            'reuse_accepted_mac_process')
    if embedded:require(os.getpid()==process['pid'],'reuse_accepted_rhino_pid')
    expected=process.get('mac_boot_session_uuid')
    require(type(expected) is str and re.fullmatch(r'[A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12}',expected),
            'reuse_accepted_mac_boot_session')
    boot=subprocess.run(['/usr/sbin/sysctl','-n','kern.bootsessionuuid'],capture_output=True,text=True,timeout=15,check=True)
    require(boot.stdout.strip().upper()==expected,'reuse_accepted_mac_boot_session')
    uid=subprocess.run(['/bin/ps','-p',str(process['pid']),'-o','uid='],capture_output=True,text=True,timeout=15,check=True)
    require(uid.stdout.strip()==str(process['uid']),'reuse_accepted_rhino_uid')
    observed=subprocess.run(['/bin/ps','-p',str(process['pid']),'-o','lstart='],capture_output=True,text=True,
        timeout=15,check=True,env={**os.environ,'TZ':'UTC'})
    started=datetime.strptime(' '.join(observed.stdout.split()),'%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc)
    require(started.strftime('%Y-%m-%dT%H:%M:%SZ')==process['start_time_utc_to_whole_second'],
            'reuse_accepted_rhino_start_identity')


def readable_scope(root,spec,runtime,plan,source,*,embedded=False,cleanup_only=False):
    """Identical actual interpreter/process/readable checks, no state or grant."""
    require(sha(plan['environment'])==runtime['environment_sha256']
            and sha(plan['host_readable_files'])==runtime['host_readable_files_sha256']
            and sha(plan['host_acceptance'])==spec['host_policy']['acceptance_record_sha256'],
            'reuse_mac_asset_binding')
    acceptance=plan['host_acceptance']
    require(acceptance['instance_id']==spec['instance_id']
            and all(acceptance[k] is True for k in ('owner_confirms_blank_active_document',
                'owner_confirms_exclusive_use_and_no_other_operations_during_research',
                'owner_accepts_readable_files_frozen_opaque_host_trusted_visible_checkpoints_only')),
            'reuse_current_host_acceptance')
    if not embedded:
        require(Path(sys.prefix).resolve()==Path('/opt/anaconda3')
                and sys.version==plan['environment']['mac']['python']
                and str(Path(sys.executable).resolve()) in plan['environment']['mac']['file_sha256'],
                'reuse_controller_interpreter')
    verify_process_identity(acceptance['process_observation'],embedded=embedded)
    def guard(*,cleanup_only=cleanup_only):
        value=source(cleanup_only=cleanup_only)
        for files in (plan['host_readable_files'],plan['environment']['mac']['file_sha256']):
            require(type(files) is dict and bool(files) and
                    all(code_sha(p)==expected for p,expected in files.items()),'reuse_mac_readable_bytes')
        if spec['resources'].get('resource_policy')=='incremental_reuse_unknown_history_v1':
            verify_audit_tokenizer(plan['model_assets'])
        if not embedded:
            frozen=plan['environment']['mac']['file_sha256']
            for module in tuple(sys.modules.values()):
                origin=getattr(module,'__file__',None)
                if not origin or str(origin).startswith('<'):continue
                p=Path(origin)
                if p.suffix=='.pyc':p=Path(importlib.util.source_from_cache(str(p)))
                require(p.is_absolute(),'reuse_controller_unresolved_origin')
                p=p.resolve()
                if p.is_relative_to(Path(root)):continue
                require(str(p) in frozen and code_sha(p)==frozen[str(p)],'reuse_controller_foreign_loaded_environment')
        return value
    guard()
    return guard


def mac_scope(root,*,embedded=False,private_prefixes=(),cleanup_only=False):
    spec,runtime,binding,plan,source=approved_entry(root,'mac',private_prefixes=private_prefixes,
                                                cleanup_only=cleanup_only)
    guard=readable_scope(root,spec,runtime,plan,source,embedded=embedded,cleanup_only=cleanup_only)
    return spec,runtime,binding,plan,guard
