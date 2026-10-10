#!/usr/bin/env python3
"""Immutable narrow tracked-Python deployment; no observer execution/claim.

No GPU, Rhino, authentication, task/cipher/key or directory crawler. Reads
fixed historical *metadata* and already identified code files only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_host_observer_scope import SPEC,FREEZE,file_sha,public

DEPLOY=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/host-observer-source-20261006-A')
DIAGNOSTIC=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/field-rhino-readonly-20261006-v3.json')
FOLDERS={'agent','training','tools','plugin','data_pipeline','eval'}


def _write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def build():
    require(not DEPLOY.exists() and not (ROOT/FREEZE).exists(), 'observer deployment/freeze already exists; no overwrite')
    spec=public(SPEC)
    require(spec['source_root']==str(DEPLOY) and spec['observer_prepared'] is True,
        'fixed prepared observer spec required')
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True)
    require(not dirty.strip(),'commit all preparation before observer deployment')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    names=sorted(n for n in names if n.endswith('.py') and n.split('/')[0] in FOLDERS)
    require(0<len(names)<=512, 'observer source inventory bound')
    sources={name:file_sha(ROOT/name) for name in names}
    require(file_sha(DIAGNOSTIC)=='94210ee8c7e3cb165af24ecfd06b06d9e97fe8207643b31d12760c98d2a3b661',
        'fixed historical diagnostic metadata identity differs')
    metadata=json.loads(DIAGNOSTIC.read_bytes())
    paths=metadata['origin_diagnostics']['file_backed_partial_inventory']
    require(len(paths)==339,'fixed known-runtime diagnostic count differs')
    # All entries were previously inspected *code* origins, not discovered
    # holdout/data paths. Rehash current code, never read arbitrary JSON input.
    host={path:file_sha(Path(path)) for path in paths}
    freeze={'schema_version':1,'probe_id':spec['probe_id'],'spec_sha256':digest(spec),
        'spec_file_sha256':file_sha(ROOT/SPEC),'source_revision':revision,'source_root':str(DEPLOY),
        'source_files':sources,'source_inventory_sha256':digest(sources),
        'frozen_observed_host_files':host,'known_host_file_inventory_sha256':digest(host),
        'known_host_inventory_is_complete_closure':False,
        'historical_diagnostic_file_sha256':file_sha(DIAGNOSTIC),
        'formal_execution_ready':False,'complete_runtime_closure_claimed':False,
        'owner_exact_approval_received':False,
        'notes':['Prepared only. No subscription, canary, run claim or private input.',
            'Known code-file bytes are frozen, but dynamic code, native shared-cache images and newly observed origins remain explicit limitations.',
            'Existing host capability probe is not a clean baseline, new policy approval, field engineering gate or formal20 grant.']}
    DEPLOY.mkdir(mode=0o700)
    for name in names:
        raw=subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
        require(digest(raw.hex())==digest((ROOT/name).read_bytes().hex()), 'tracked deployment bytes differ')
        _write(DEPLOY/name,raw)
    _write(DEPLOY/SPEC,(ROOT/SPEC).read_bytes())
    raw=(json.dumps(freeze,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    _write(DEPLOY/FREEZE,raw)
    _write(ROOT/FREEZE,raw)
    require(all(file_sha(DEPLOY/name)==sha for name,sha in sources.items()), 'observer deployed source bytes differ')
    return {'probe_id':spec['probe_id'],'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
        'source_revision':revision,'source_files':len(sources),'known_host_files':len(host),
        'source_root':str(DEPLOY),'formal_execution_ready':False,'observer_executed':False}


if __name__=='__main__':print(json.dumps(build(),sort_keys=True))
