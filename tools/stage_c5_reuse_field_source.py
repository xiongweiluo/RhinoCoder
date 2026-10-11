#!/usr/bin/env python3
"""Public fixed-source staging only, before any new state/grant/admission.

Standalone stdlib bootstrap: never import deployed code. Initial creation is
O_EXCL; --update-freeze changes only spec/plan/runtime before any grant exists.
No owner grant, keys, observers, model, fixture, old state, install or cleanup.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

INSTANCE='reuse-dev-20261011-a'
PARENTS={'mac':Path('/Users/xiongweiluo/RhinoCoder/data/training/c5'),'gpu':Path('/data')}
SPEC='eval/c5/reuse-development-spec-20261011-a.json'
PLAN='eval/c5/reuse-field-environment-plan-20261011-a.json'
RUNTIME='eval/c5/reuse-development-runtime-freeze-20261011-a.json'
MUTABLE={SPEC,PLAN,RUNTIME}


def require(ok,code):
    if not ok:raise ValueError(code)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(p):
    require(p.is_absolute() and p.resolve()==p,'public_stage_alias')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.getuid()
            and not st.st_mode&0o022 and 0<st.st_size<=2*1024*1024,'public_stage_file')
        raw=os.pread(fd,st.st_size+1,0);after=os.fstat(fd)
        require(len(raw)==st.st_size and (st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==
            (after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'public_stage_read_race')
        return raw
    finally:os.close(fd)


def stage(raw,expected_sha,*,update=False):
    require(type(raw) is bytes and 0<len(raw)<=32*1024*1024 and sha(raw)==expected_sha,'public_stage_external_package_sha')
    packet=json.loads(raw);require(set(packet)=={'endpoint','payload_base64','file_sha256'},'public_stage_package_shape')
    endpoint=packet['endpoint'];require(endpoint in PARENTS and type(update) is bool,'public_stage_endpoint')
    parent=PARENTS[endpoint];root=parent/(INSTANCE+'-source')
    require(parent.is_absolute() and parent.resolve()==parent and parent.is_dir(),'public_stage_parent')
    require(not os.path.lexists(parent/(INSTANCE+'-state'))
            and not os.path.lexists(parent/'c5-reuse-global-admission-v1'),'public_stage_no_grant_or_admission')
    names=set(packet['payload_base64']);require(names==set(packet['file_sha256']) and MUTABLE<=names
        and 0<len(names)<=513,'public_stage_population')
    payload={}
    for name in names:
        p=Path(name)
        require(not p.is_absolute() and '..' not in p.parts and str(p)==name and re.fullmatch(r'[a-zA-Z0-9_./-]+',name)
            and ((name.endswith('.py') and p.parts[0] in ('agent','training','tools','plugin','data_pipeline'))
                or name in MUTABLE|{'eval/c5/rhino-runtime-schema-v1.json',
                    'eval/c5/hostassurance-development-spec-20261007-d.json','eval/c5/c5-engineering-config.json',
                    'requirements.txt','requirements-training.txt'}),'public_stage_public_source_only')
        value=base64.b64decode(packet['payload_base64'][name],validate=True)
        require(0<len(value)<=2*1024*1024 and sha(value)==packet['file_sha256'][name],'public_stage_raw_bytes')
        payload[name]=value
    runtime=json.loads(payload[RUNTIME]);require(runtime['source_files']=={n:s for n,s in packet['file_sha256'].items()
                                                                           if n!=RUNTIME},'public_stage_runtime_inventory')
    if update:
        require(root.is_dir() and root.resolve()==root,'public_stage_existing_root')
        existing={p.relative_to(root).as_posix() for p in root.rglob('*') if not p.is_dir()}
        require(existing==names and not any(p.is_symlink() for p in root.rglob('*')),'public_stage_existing_population')
        previous=json.loads(read(root/RUNTIME))
        for n in names:
            current=read(root/n)
            if n!=RUNTIME:require(sha(current)==previous['source_files'][n],'public_stage_previous_bytes')
            require(n in MUTABLE or current==payload[n],'public_stage_only_freeze_records_mutable')
    else:root.mkdir(mode=0o700)
    for name in sorted(names):
        if update and name not in MUTABLE:continue
        p=root/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=p.with_name('public-freeze-'+p.name) if update else p
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            value=payload[name];offset=0
            while offset<len(value):
                count=os.write(fd,value[offset:]);require(count>0,'public_stage_partial_write');offset+=count
            os.fsync(fd)
        finally:os.close(fd)
        if update:os.replace(target,p)
        require(read(p)==payload[name],'public_stage_readback')
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'endpoint':endpoint,'files_individually_written_and_rechecked':len(names),
        'package_raw_sha256':expected_sha,'state_or_owner_grant_or_admission_created':False,
        'model_calls':0,'rhino_calls':0,'private_formal_reads':0,'execution_ready':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--package-sha256',required=True);p.add_argument('--update-freeze',action='store_true')
    a=p.parse_args();raw=sys.stdin.buffer.read(32*1024*1024+1)
    print(json.dumps(stage(raw,a.package_sha256,update=a.update_freeze),sort_keys=True))


if __name__=='__main__':main()
