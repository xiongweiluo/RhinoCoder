#!/usr/bin/env python3
"""Narrow committed source deployment + read-only manifests, never execution.

No study state, approval, key, subscriber, model loader or holdout file.
Each deployment/freeze is O_EXCL. Only explicit tracked code/public config
is transmitted; never a working-tree tarball or authentication material.
"""
from __future__ import annotations

import json
import io
import os
import subprocess
import tarfile
from pathlib import Path

from plugin.rhino_listener.c5_hostassurance_development_scope_c import (
    ID,MAC_SOURCE,REMOTE_SOURCE,REMOTE_STATE,SPEC,FREEZE,TRANSITION,CONSENT,public,
)
from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_model_transport import strict_json,LIMIT
from training.c5_modelbridge_runtime import file_sha
from tools.c5_hostassurance_dev_client_c import preflight,ssh_args

ROOT=Path(__file__).resolve().parents[1]
DIAGNOSTIC=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/field-rhino-readonly-20261006-v3.json')
FOLDERS={'agent','training','tools','plugin','data_pipeline','eval'}
PUBLIC=('requirements-training.txt','requirements.txt','eval/c5/rhino-runtime-schema-v1.json',
    'eval/c5/c5-engineering-config.json','eval/c5/gpu-formal-registry-20261001.json',TRANSITION,CONSENT)


def _write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def verify_archive_population(archive,names):
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:*') as stream:
        rows=stream.getmembers()
    require(all(r.isfile() and not r.issym() and not r.islnk() for r in rows), 'regular file archive only')
    actual=[r.name for r in rows]
    require(len(actual)==len(names) and set(actual)==set(names)
        and all(not Path(n).name.startswith('._') for n in actual),
        'archive contains unexpected metadata/directory/file; never transfer it')


def build():
    require(not MAC_SOURCE.exists() and not (ROOT/FREEZE).exists(), 'new source/freeze already exists; do not overwrite')
    require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True).strip(),
        'commit reviewed preparations first; never package dirty checkout')
    spec=public(ROOT,SPEC)
    require(spec['study_id']==ID and spec['execution_ready'] is True, 'complete prepared spec required')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    code=sorted(n for n in tracked if n.endswith('.py') and n.split('/')[0] in FOLDERS)
    require(0<len(code)<512, 'new complete tracked code inventory bound')
    names=sorted(set(code)|set(PUBLIC)|{SPEC})
    require(set(names)<=set(tracked) and all('\n' not in n and not n.startswith('/') and '..' not in Path(n).parts
        for n in names), 'explicit tracked code/public paths only')
    sources={n:file_sha(ROOT/n) for n in code}
    sources['eval/c5/rhino-runtime-schema-v1.json']=file_sha(ROOT/'eval/c5/rhino-runtime-schema-v1.json')
    cpu=preflight(include_manifest=True)
    # Previous file-origin metadata only; no task/cipher/key/private corpus.
    require(file_sha(DIAGNOSTIC)=='94210ee8c7e3cb165af24ecfd06b06d9e97fe8207643b31d12760c98d2a3b661',
        'historical observed code inventory identity differs')
    known=json.loads(DIAGNOSTIC.read_bytes())['origin_diagnostics']['file_backed_partial_inventory']
    require(len(known)==339,'expected known host inventory differs')
    host={p:file_sha(Path(p)) for p in known}
    MAC_SOURCE.mkdir(mode=0o700)
    for n in names:
        raw=subprocess.check_output(['git','show',revision+':'+n],cwd=ROOT)
        require(raw==(ROOT/n).read_bytes(),'deployed tracked source differs')
        _write(MAC_SOURCE/n,raw)
    # Only the list above is in this transport, not the repository/worktree.
    archive=subprocess.check_output(['tar','--no-xattrs','--no-mac-metadata','-czf','-','-T','-'],
        cwd=MAC_SOURCE,input=('\n'.join(names)+'\n').encode())
    verify_archive_population(archive,names)
    command='test ! -e '+str(REMOTE_SOURCE)+' && test ! -e '+str(REMOTE_STATE)+' && mkdir -m 700 '+str(REMOTE_SOURCE)+' && tar -xzf - -C '+str(REMOTE_SOURCE)
    subprocess.run(ssh_args()+[command],input=archive,check=True,timeout=180)
    prefix='cd '+str(REMOTE_SOURCE)+' && /data/conda-envs/rhinocoder/bin/python -B -m tools.run_c5_hostassurance_dev_worker_c '
    assets=strict_json(subprocess.check_output(ssh_args()+[prefix+'preflight'],timeout=180))
    imports=strict_json(subprocess.check_output(ssh_args()+[prefix+'import-preflight'],timeout=180))
    fixed={n:file_sha(ROOT/n) for n in PUBLIC if n!='eval/c5/rhino-runtime-schema-v1.json'}
    require(assets['source_files']==sources and assets['fixed_public_files']==fixed
        and assets['environment_sha256']==imports['environment_sha256']
        and imports['cuda_initialized'] is False and imports['model_loaded'] is False
        and imports['generation_calls']==0 and assets['environment']['missing_metadata_files']==['pip:../../../bin/pip3.13'],
        'new actual GPU file/import/pip inventory differs')
    v5=public(ROOT,'eval/c5/rhino-resource-boundary-v5-20261006.json')
    boundary={'owner_confirmed':True,'provider_expiry_epoch':v5['owner_reported_expiry_epoch'],
        'hard_stop_epoch':v5['owner_reported_expiry_epoch'],'export_reserve_seconds':900,
        'development_max_seconds':3104,'prior_cumulative_seconds':7695.654411741009,
        'original_cumulative_max_seconds':57600}
    freeze={'schema_version':1,'study_id':ID,'probe_id':ID,'execution_ready':True,
        'spec_sha256':digest(spec),'spec_file_sha256':file_sha(ROOT/SPEC),'source_revision':revision,
        'mac_source_root':str(MAC_SOURCE),'remote_source_root':str(REMOTE_SOURCE),
        'source_files':sources,'source_inventory_sha256':digest(sources),'fixed_public_files':fixed,
        'mac_environment':cpu['mac_environment'],'tokenizer_files':cpu['tokenizer_files'],
        'max_input_plus_output_reserve_tokens':cpu['max_input_plus_output_reserve_tokens'],
        'rhino_version':'8.21.25188.17002','embedded_python_major_minor':[3,9],
        'frozen_observed_host_files':host,'known_host_file_inventory_sha256':digest(host),
        'known_host_inventory_is_complete_closure':False,
        'environment':assets['environment'],'environment_sha256':assets['environment_sha256'],
        'gpu_readonly_observation':assets['gpu_observation'],'gpu_loader_import_preflight':imports,
        'missing_metadata_files':assets['environment']['missing_metadata_files'],
        'model_identities':{'base':digest(assets['snapshot']),'lora':assets['adapter_sha256']},
        'model_assets':{'base_manifest_sha256':'5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd',
            'base_file_identities':assets['snapshot'],'adapter_files':assets['adapter_files']},
        'host_assurance':spec['host_assurance'],'resource_boundary':boundary,
        'provider_timestamp_independently_verified':False,'lease_basis':'direct owner report v5; no provider-account access',
        'legacy_byte_closure_verified':False,'complete_runtime_closure_claimed':False,'formal_execution_ready':False,
        'new_exact_owner_approval_received':False,'study_executed':False,
        'execution_ready_meaning':'freeze prepared, NOT execution authority; direct owner exact two-hash approval still required'}
    raw=(json.dumps(freeze,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    require(len(raw)<=LIMIT, 'bounded full freeze required')
    _write(MAC_SOURCE/FREEZE,raw)
    _write(ROOT/FREEZE,raw)
    remote='test ! -e '+str(REMOTE_SOURCE/FREEZE)+' && umask 077 && tee '+str(REMOTE_SOURCE/FREEZE)+' >/dev/null'
    subprocess.run(ssh_args()+[remote],input=raw,check=True,timeout=30)
    require(all(file_sha(MAC_SOURCE/n)==sha for n,sha in sources.items()),'new Mac source verification differs')
    return {'study_id':ID,'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
        'source_revision':revision,'source_file_count':len(sources),'known_host_file_count':len(host),
        'readonly_gpu_imports_verified':True,'model_generation_calls':0,'holdout_rows_read':0,
        'execution_authorized':False,'legacy_byte_closure_verified':False}


if __name__=='__main__':print(json.dumps(build(),sort_keys=True))
