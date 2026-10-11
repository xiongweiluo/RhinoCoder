"""Fixed new-development entry scope. Stdlib only; no model/Rhino effects.

This checks exact supplied owner records, not their human provenance. The
calling tool/operator must have the direct two-hash approval before executing
any entry. No fallback to an old study, source directory or owner grant.
"""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import time

from .c5_reuse_field_scope import bind, canonical, exact, require, sha, strict, is_sha

INSTANCE='reuse-dev-20261011-a'
MAC_PARENT=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5')
GPU_PARENT=Path('/data')
SPEC='eval/c5/reuse-development-spec-20261011-a.json'
RUNTIME='eval/c5/reuse-development-runtime-freeze-20261011-a.json'
PLAN='eval/c5/reuse-field-environment-plan-20261011-a.json'


def fixed_paths(endpoint):
    require(endpoint in ('mac','gpu'),'reuse_runtime_endpoint')
    parent=MAC_PARENT if endpoint=='mac' else GPU_PARENT
    return {'source_root':str(parent/(INSTANCE+'-source')),
            'state_root':str(parent/(INSTANCE+'-state')),
            'admission_root':str(parent/'c5-reuse-global-admission-v1')}


def read_bytes(path,limit=2*1024*1024,*,private=False):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path,'reuse_runtime_file_alias')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.getuid()
                and not before.st_mode & (0o077 if private else 0o022)
                and 0<before.st_size<=limit,'reuse_runtime_file')
        raw=os.pread(fd,before.st_size+1,0); after=os.fstat(fd); named=path.lstat()
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_nlink')
        require(len(raw)==before.st_size and all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in fields),
                'reuse_runtime_file_race')
        return raw
    finally: os.close(fd)


class ReuseSourceGuard:
    def __init__(self,root,files,*,private_prefixes=()):
        self.root=Path(root); self.files=dict(files); self.prefixes=('agent','training','tools','plugin','data_pipeline')+tuple(private_prefixes)
        require(self.root.is_absolute() and self.root.resolve()==self.root and 0<len(files)<=512,'reuse_source_root')
        self.expected=sha(files)
        for name,value in files.items():
            p=Path(name)
            require(type(name) is str and not p.is_absolute() and '..' not in p.parts and str(p)==name
                    and ((name.endswith('.py') and p.parts[0] in ('agent','training','plugin','tools','data_pipeline'))
                        or name in (SPEC,PLAN,'eval/c5/rhino-runtime-schema-v1.json',
                        'eval/c5/hostassurance-development-spec-20261007-d.json',
                        'training/configs/c5_lora_v1.json','requirements-training.txt'))
                    and is_sha(value),'reuse_source_public_population')

    def __call__(self):
        import hashlib
        for name,value in self.files.items():
            require(hashlib.sha256(read_bytes(self.root/name)).hexdigest()==value,'reuse_source_byte_drift')
        for name,module in tuple(sys.modules.items()):
            if name.split('.')[0] not in self.prefixes: continue
            origin=getattr(module,'__file__',None)
            if origin is None:
                paths=getattr(module,'__path__',())
                require(paths and all(Path(p).resolve().is_relative_to(self.root) for p in paths),'reuse_source_namespace')
                continue
            p=Path(origin)
            if p.suffix=='.pyc': p=Path(importlib.util.source_from_cache(str(p)))
            require(p.is_absolute() and p.resolve()==p and p.is_relative_to(self.root)
                    and p.relative_to(self.root).as_posix() in self.files,'reuse_source_loaded_origin')
        return self.expected


def approved_entry(root,endpoint,*,now=time.time,private_prefixes=()):
    root=Path(root)
    expected=fixed_paths(endpoint)
    require(root==Path(expected['source_root']) and root.resolve()==root,'reuse_fixed_entry_root')
    spec_raw=read_bytes(root/SPEC); runtime_raw=read_bytes(root/RUNTIME)
    spec,runtime=strict(spec_raw),strict(runtime_raw)
    require(runtime['endpoints']=={e:fixed_paths(e) for e in ('mac','gpu')},'reuse_fixed_endpoint_namespaces')
    state=Path(expected['state_root'])
    approval_raw=read_bytes(state/'owner-approval.json',private=True)
    approval=strict(approval_raw)
    binding=bind(spec,runtime,approval,now=now(),endpoint=endpoint)
    require(spec['instance_id']==INSTANCE and SPEC in runtime['source_files'] and PLAN in runtime['source_files'],
            'reuse_complete_entry_records')
    guard=ReuseSourceGuard(root,runtime['source_files'],private_prefixes=private_prefixes)
    guard()
    plan_raw=read_bytes(root/PLAN); plan=strict(plan_raw)
    def check():
        require(read_bytes(root/SPEC)==spec_raw and read_bytes(root/RUNTIME)==runtime_raw
                and read_bytes(state/'owner-approval.json',private=True)==approval_raw
                and read_bytes(root/PLAN)==plan_raw,'reuse_approved_records_changed')
        bind(spec,runtime,approval,now=now(),endpoint=endpoint)
        return guard()
    check()
    return spec,runtime,binding,plan,check
