#!/usr/bin/env python3
"""Public fixed-source staging only, before any new state/grant/admission.

Standalone stdlib bootstrap: never import deployed code. Initial creation is
O_EXCL; --update-freeze changes only spec/plan/runtime before any grant exists.
Explicit --refresh-public-source additionally requires the independently
pinned previous runtime SHA, exact old bytes/population and no new state.
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
import sqlite3
import sys

INSTANCE='reuse-dev-20261012-d'
PARENTS={'mac':Path('/Users/xiongweiluo/RhinoCoder/data/training/c5'),'gpu':Path('/data')}
SPEC='eval/c5/reuse-followup-development-spec-20261012-d.json'
PLAN='eval/c5/reuse-followup-field-environment-plan-20261012-d.json'
RUNTIME='eval/c5/reuse-followup-development-runtime-freeze-20261012-d.json'
MUTABLE={SPEC,PLAN,RUNTIME}
ACTUAL_PARENTS={Path('/Users/xiongweiluo/RhinoCoder/data/training/c5'),Path('/data')}
RETIREMENT_SHA='f098afe6e005e3ae09129bb44531ce3947e07d6592632d86a2c75af24f0f2978'
RETIRED_APPROVAL_SHA='fcfe67c8382d7e2dd28dafd58bec37deea8a75e5686ef9e2b241ac6e0a9416f9'
RETIRED_ENTRIES=(('reuse-dev-20261011-a',RETIREMENT_SHA,RETIRED_APPROVAL_SHA),
    ('reuse-dev-20261012-b','3110dd38a8b318150526394ae98e7b36233fa6ac91a64a2adb08a1f1b529afda',
     '175bb33bf80d2f7559f4ee6d03c6634225c9df4839ef5f84686cd5814dd57574'),
    ('reuse-dev-20261012-c','310797d0dfbe9e787424f62140f8dae460fcd443b7b23043ca5e6dc1e8befb80','359892d9adc45bc33a966bc013b5bc4f2a04b979100e760ee506f2edf2304225'))


GENESIS={'schema': 2, 'protocol': 'c5-disclosed-followup-admission-v2', 'study_id': 'C5DEV-REUSE-20261012-D', 'instance_id': 'reuse-dev-20261012-d', 'preparation_acceptance_sha256': 'a4910d60997083d0eb8eb68a2913da0d6dbbe8ac98bb2804462e2158dffec29d', 'global_roots': {'gpu': '/data/c5-reuse-global-admission-v1', 'mac': '/Users/xiongweiluo/RhinoCoder/data/training/c5/c5-reuse-global-admission-v1'}, 'legacy_snapshot': {'gpu': {'exists': False, 'file_sha256': {}, 'root_name': 'c5-reuse-global-admission-v1', 'rows': [], 'writes': 0}, 'mac': {'exists': True, 'file_sha256': {'admission.lock': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'admission.sqlite': '1d616f891b2f43015629d70e7c1ed6eed19ab288abc61d5403d1a0be1a0cd213', 'controller.consumed.json': '0ce2bd4f879e331ef6c8100cdc91e5f7a8ddfa079acc33a7a784eddac8aaa323', 'host.consumed.json': 'a1f829c678a1f248c2e36d566707d47f7fb32e7d3d7404d81ea6085573a8a8f6'}, 'root_name': 'c5-reuse-global-admission-v1', 'rows': [['C5DEV-REUSE-20261012-C', 'controller', 'eaa08c266a1d785774d14c9d6609d31f7a743aee38f3d1f008b880926a7173e7', '75ece512c33e19f10657c32307d3067889c7d12a512c1e11cf4cf08acfeb6df1'], ['C5DEV-REUSE-20261012-C', 'host', 'eaa08c266a1d785774d14c9d6609d31f7a743aee38f3d1f008b880926a7173e7', '721b68b73ca3e1ad7354791ff40d43c5435ef71e805127d5610aad47fa5728e9']], 'writes': 0}}, 'retirements': {'reuse-dev-20261011-a': {'active_grant_absent': True, 'retired_grant_raw_sha256': 'fcfe67c8382d7e2dd28dafd58bec37deea8a75e5686ef9e2b241ac6e0a9416f9', 'retirement_raw_sha256': 'f098afe6e005e3ae09129bb44531ce3947e07d6592632d86a2c75af24f0f2978'}, 'reuse-dev-20261012-b': {'active_grant_absent': True, 'retired_grant_raw_sha256': '175bb33bf80d2f7559f4ee6d03c6634225c9df4839ef5f84686cd5814dd57574', 'retirement_raw_sha256': '3110dd38a8b318150526394ae98e7b36233fa6ac91a64a2adb08a1f1b529afda'}, 'reuse-dev-20261012-c': {'active_grant_absent': True, 'retired_grant_raw_sha256': '359892d9adc45bc33a966bc013b5bc4f2a04b979100e760ee506f2edf2304225', 'retirement_raw_sha256': '310797d0dfbe9e787424f62140f8dae460fcd443b7b23043ca5e6dc1e8befb80'}}, 'original_c_failure_raw_sha256': 'f92a0bbf412500c094ceeaaabe166e7c3719f0490f9c4b32b3f32712457a41e0', 'maximum_additional_development_attempts': 1, 'historical_consumed_rows_nonempty': True, 'legacy_files_byte_preservation_required': True, 'original_no_go_preserved': True, 'new_blind_holdout_claimed': False}

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



def preparation_scope(parent):
    require(not os.path.lexists(parent/(INSTANCE+'-state')),'public_stage_no_grant_or_admission')
    require(not os.path.lexists(parent/(INSTANCE+'-external-custody')),'followup_stage_no_custody')
    registry=parent/'c5-reuse-global-admission-v1'
    # A's prepare created an empty shared registry. Preserve it; never clear,
    # rename or create a new registry to bypass a consumed/uncertain role.
    if parent in ACTUAL_PARENTS or os.path.lexists(registry):
        for instance,retirement,approval in RETIRED_ENTRIES:
            old=parent/(instance+'-state')
            i=old.lstat()
            require(old.resolve()==old and stat.S_ISDIR(i.st_mode) and i.st_uid==os.getuid()
                    and stat.S_IMODE(i.st_mode)==0o700 and not os.path.lexists(old/'owner-approval.json'),
                    'public_stage_predecessor_retired')
            for name,pin in [('entry-retired-no-retry.json',retirement),
                             ('owner-approval.retired-no-retry.json',approval)]:
                require(not (old/name).stat().st_mode&0o077 and sha(read(old/name))==pin,
                        'public_stage_predecessor_bytes')
    endpoint='mac' if parent==PARENTS['mac'] else 'gpu'
    expected=GENESIS['legacy_snapshot'][endpoint]
    if not os.path.lexists(registry):
        require(endpoint=='gpu' and expected['exists'] is False,'followup_stage_legacy_missing');return
    require(endpoint=='mac' and registry.resolve()==registry and stat.S_IMODE(registry.stat().st_mode)==0o700
        and registry.stat().st_uid==os.getuid() and set(os.listdir(registry))==set(expected['file_sha256']),'followup_stage_legacy_population')
    for name,pin in expected['file_sha256'].items():
        p=registry/name;i=p.lstat()
        require(p.resolve()==p and stat.S_ISREG(i.st_mode) and i.st_uid==os.getuid() and i.st_nlink==1
            and stat.S_IMODE(i.st_mode)==0o600,'followup_stage_legacy_file')
        raw=b'' if name=='admission.lock' and i.st_size==0 else read(p)
        require(sha(raw)==pin,'followup_stage_legacy_bytes')
    db=sqlite3.connect((registry/'admission.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        require(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            and [list(row) for row in db.execute('SELECT * FROM admission ORDER BY role')]==expected['rows'],'followup_stage_consumed_history')
    finally:db.close()


def stage(raw,expected_sha,*,update=False,refresh=False,previous_runtime_sha=None):
    require(type(raw) is bytes and 0<len(raw)<=32*1024*1024 and sha(raw)==expected_sha,'public_stage_external_package_sha')
    packet=json.loads(raw);require(set(packet)=={'endpoint','payload_base64','file_sha256'},'public_stage_package_shape')
    endpoint=packet['endpoint'];require(endpoint in PARENTS and type(update) is type(refresh) is bool
        and not (update and refresh),'public_stage_endpoint')
    parent=PARENTS[endpoint];root=parent/(INSTANCE+'-source')
    require(parent.is_absolute() and parent.resolve()==parent and parent.is_dir(),'public_stage_parent')
    preparation_scope(parent)
    names=set(packet['payload_base64']);require(names==set(packet['file_sha256']) and MUTABLE<=names
        and 0<len(names)<=513,'public_stage_population')
    payload={}
    for name in names:
        p=Path(name)
        require(not p.is_absolute() and '..' not in p.parts and str(p)==name and re.fullmatch(r'[a-zA-Z0-9_./-]+',name)
            and ((name.endswith('.py') and p.parts[0] in ('agent','training','tools','plugin','data_pipeline'))
                or name in MUTABLE|{'eval/c5/rhino-runtime-schema-v1.json',
                    'eval/c5/hostassurance-development-spec-20261007-d.json','eval/c5/c5-engineering-config.json','eval/c5/reuse-development-startup-failure-20261012.json',
                    'eval/c5/reuse-development-preparation-failure-20261012-b.json',
                    'eval/c5/reuse-development-startup-failure-20261012-c.json',
                    'eval/c5/reuse-followup-owner-preparation-acceptance-20261012-d.json',
                    'eval/c5/reuse-followup-resource-acceptance-20261012-d.json',
                    'eval/c5/reuse-followup-admission-genesis-20261012-d.json',
                    'eval/c5/reuse-followup-compatible-runtime-20261012-d.json',
                    'requirements.txt','requirements-training.txt'}),'public_stage_public_source_only')
        value=base64.b64decode(packet['payload_base64'][name],validate=True)
        require(0<len(value)<=2*1024*1024 and sha(value)==packet['file_sha256'][name],'public_stage_raw_bytes')
        payload[name]=value
    runtime=json.loads(payload[RUNTIME]);require(runtime['source_files']=={n:s for n,s in packet['file_sha256'].items()
                                                                           if n!=RUNTIME},'public_stage_runtime_inventory')
    if update or refresh:
        require(root.is_dir() and root.resolve()==root,'public_stage_existing_root')
        existing={p.relative_to(root).as_posix() for p in root.rglob('*') if not p.is_dir()}
        require(existing==names and not any(p.is_symlink() for p in root.rglob('*')),'public_stage_existing_population')
        previous=json.loads(read(root/RUNTIME))
        if refresh:
            canonical=json.dumps(previous,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
            require(sha(canonical)==previous_runtime_sha,'public_stage_previous_runtime_pin')
        for n in names:
            current=read(root/n)
            if n!=RUNTIME:require(sha(current)==previous['source_files'][n],'public_stage_previous_bytes')
            require(refresh or n in MUTABLE or current==payload[n],'public_stage_only_freeze_records_mutable')
    else:root.mkdir(mode=0o700)
    for name in sorted(names-{RUNTIME})+[RUNTIME]:
        if update and name not in MUTABLE:continue
        preparation_scope(parent)
        p=root/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=p.with_name('public-freeze-'+p.name) if update or refresh else p
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            value=payload[name];offset=0
            while offset<len(value):
                count=os.write(fd,value[offset:]);require(count>0,'public_stage_partial_write');offset+=count
            os.fsync(fd)
        finally:os.close(fd)
        if update or refresh:os.replace(target,p)
        require(read(p)==payload[name],'public_stage_readback')
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'endpoint':endpoint,'files_individually_written_and_rechecked':len(names),
        'package_raw_sha256':expected_sha,'state_or_owner_grant_or_admission_created':False,
        'model_calls':0,'rhino_calls':0,'private_formal_reads':0,'execution_ready':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--package-sha256',required=True);p.add_argument('--update-freeze',action='store_true')
    p.add_argument('--refresh-public-source',action='store_true');p.add_argument('--previous-runtime-sha256')
    a=p.parse_args();raw=sys.stdin.buffer.read(32*1024*1024+1)
    print(json.dumps(stage(raw,a.package_sha256,update=a.update_freeze,refresh=a.refresh_public_source,
                           previous_runtime_sha=a.previous_runtime_sha256),sort_keys=True))


if __name__=='__main__':main()
