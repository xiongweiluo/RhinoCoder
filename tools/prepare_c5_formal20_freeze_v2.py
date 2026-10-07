#!/usr/bin/env python3
"""Explicit tracked-code deployment and read-only formal manifest preparation.

Never reads private tasks/keys/ciphertext, creates formal run state/grant,
loads a model, invokes Rhino or consumes holdout. Each write is O_EXCL;
unknown/partial deployment must be inspected, not overwritten/replayed.
"""
import json
import os
import subprocess
from pathlib import Path

from plugin.rhino_listener.c5_formal20_scope_v2 import (
    STUDY_ID,MAC_SOURCE,MAC_STATE,REMOTE_SOURCE,REMOTE_STATE,SPEC_FILE,FREEZE_FILE)
from plugin.rhino_listener.c5_formal20_policy_v2 import validate_acceptance
from plugin.rhino_listener.c5_research_native import require,digest
from training.c5_model_transport import strict_json,LIMIT
from training.c5_modelbridge_runtime import file_sha
from training.c5_formal20_field_scope_v2 import external_origins
from tools.run_c5_formal20_worker_v2 import PUBLIC_FILES
from tools.c5_hostassurance_dev_client_d import ssh_args,TOKENIZER,preflight as old_cpu_preflight
from tools.prepare_c5_hostassurance_development_freeze_d import _write,verify_archive_population

ROOT=Path(__file__).resolve().parents[1]
FOLDERS={'agent','training','tools','plugin','data_pipeline','eval'}


def public(name):return strict_json((ROOT/name).read_bytes())


def mac_preflight():
    """Prime declared imports/renderer from excluded development text only."""
    import tools.c5_formal20_owner_run_v2
    import training.c5_formal20_joint_audit_v2
    require(tools.c5_formal20_owner_run_v2 is not None,'formal owner module import failed')
    cpu=old_cpu_preflight() # Existing four excluded train texts, never final data.
    return {**cpu,'mac_environment':external_origins()}


def build():
    require(not MAC_SOURCE.exists() and not MAC_STATE.exists() and not (ROOT/FREEZE_FILE).exists(),
        'new formal source/state/freeze must be absent; no overwrite')
    require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True).strip(),
        'commit reviewed code first; never package dirty worktree')
    spec=public(SPEC_FILE)
    proposal=public('eval/c5/formal20-observation-capacity-proposal-20261007.json')
    accepted=public('eval/c5/formal20-capacity-owner-acceptance-20261007.json')
    validate_acceptance(proposal,accepted)
    audit=public('eval/c5/hostassurance-development-independent-audit-20261007-d.json')
    require(digest(audit)=='d244d95dd302652df61bef1f25815d4578a0e2d6d66c8d77266e52bf1b3c2015'
        and audit['complete_C5_engineering_gate_passed'] is True,'complete actual D gate missing')
    require(spec['study_id']==STUDY_ID and spec['field_protocol_version']==2
        and spec['execution_ready'] is True and spec['owner_approval_received'] is False,'new prepared formal spec required')
    # No artifact location from the private public-commitment metadata is used.
    from tools.c5_formal20_public_preflight import preflight
    commitment=preflight(ROOT/'eval/c5/rhino-formal20-public-commitment-v1.json')
    require(commitment['public_commitment_sha256']==spec['public_commitment_sha256'],'registered public commitment differs')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    code=sorted(n for n in tracked if n.endswith('.py') and n.split('/')[0] in FOLDERS)
    require(0<len(code)<512,'bounded complete tracked source inventory required')
    names=sorted(set(code)|set(PUBLIC_FILES)|{SPEC_FILE})
    require(set(names)<=set(tracked) and all(not n.startswith('/') and '..' not in Path(n).parts
        and '\n' not in n for n in names),'explicit tracked code/public paths only')
    sources={n:file_sha(ROOT/n) for n in code}
    cpu=mac_preflight()
    previous=public('eval/c5/hostassurance-development-runtime-freeze-20261007-d.json')
    # Known readable files retain their prior identity; dynamic/opaque host
    # is NOT declared freshly inspected or byte-proven. Actual new baseline
    # happens only in the precisely approved formal zero-stage arm.
    host={n:file_sha(Path(n)) for n in previous['frozen_observed_host_files']}
    require(host==previous['frozen_observed_host_files'],'known previously frozen host file drift')
    age=Path(subprocess.check_output(['which','age'],text=True).strip()).resolve(strict=True)
    age_sha=file_sha(age)
    MAC_SOURCE.mkdir(mode=0o700)
    for n in names:
        raw=subprocess.check_output(['git','show',revision+':'+n],cwd=ROOT)
        require(raw==(ROOT/n).read_bytes(),'tracked Git/working source differs')
        _write(MAC_SOURCE/n,raw)
    archive=subprocess.check_output(['tar','--no-xattrs','--no-mac-metadata','-czf','-','-T','-'],
        cwd=MAC_SOURCE,input=('\n'.join(names)+'\n').encode())
    verify_archive_population(archive,names)
    command='test ! -e '+str(REMOTE_SOURCE)+' && test ! -e '+str(REMOTE_STATE)+' && mkdir -m 700 '+str(REMOTE_SOURCE)+' && tar -xzf - -C '+str(REMOTE_SOURCE)
    subprocess.run(ssh_args()+[command],input=archive,check=True,timeout=180)
    prefix='cd '+str(REMOTE_SOURCE)+' && /data/conda-envs/rhinocoder/bin/python -B -m tools.run_c5_formal20_worker_v2 '
    assets=strict_json(subprocess.check_output(ssh_args()+[prefix+'preflight'],timeout=180))
    imports=strict_json(subprocess.check_output(ssh_args()+[prefix+'import-preflight'],timeout=180))
    fixed={n:file_sha(ROOT/n) for n in PUBLIC_FILES}
    require(assets['source_files']==sources and assets['fixed_public_files']==fixed
        and assets['environment_sha256']==imports['environment_sha256']
        and imports['cuda_initialized'] is False and imports['model_loaded'] is False
        and imports['generation_calls']==0 and assets['environment']['missing_metadata_files']==['pip:../../../bin/pip3.13'],
        'actual formal dependency/source/model identities differ')
    resource=public('eval/c5/rhino-resource-boundary-v7-formal20-20261007.json')['formal_resource_boundary']
    freeze={'schema_version':1,'study_id':STUDY_ID,'field_protocol_version':2,'execution_ready':True,
        'spec_sha256':digest(spec),'spec_file_sha256':file_sha(ROOT/SPEC_FILE),'source_revision':revision,
        'mac_source_root':str(MAC_SOURCE),'remote_source_root':str(REMOTE_SOURCE),
        'repository_root_for_private_boundary':'/Users/xiongweiluo/RhinoCoder',
        'source_files':sources,'source_inventory_sha256':digest(sources),'fixed_public_files':fixed,
        'mac_environment':cpu['mac_environment'],'tokenizer_dir':str(TOKENIZER),
        'tokenizer_file_sha256':cpu['tokenizer_files'],'rhino_version':previous['rhino_version'],
        'rhino_environment_files':host,'limited_host_readable_file_inventory_verified':True,
        'known_readable_host_inventory_is_complete_closure':False,
        'environment':assets['environment'],'environment_sha256':assets['environment_sha256'],
        'model_identities':{'base':digest(assets['snapshot']),'lora':assets['adapter_sha256']},
        'model_assets':{'base_manifest_sha256':'5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd',
            'base_file_identities':assets['snapshot'],'adapter_files':assets['adapter_files']},
        'gpu_readonly_observation':assets['gpu_observation'],'gpu_loader_import_preflight':imports,
        'missing_metadata_files':assets['environment']['missing_metadata_files'],
        'host_assurance':spec['host_assurance'],'lifecycle_protocol':spec['lifecycle_protocol'],
        'capacity_proposal':proposal,'capacity_acceptance':accepted,
        'host_transition_spec':public('eval/c5/host-assurance-transition-spec-v2-20261006.json'),
        'host_transition_consent':public('eval/c5/host-assurance-transition-owner-approval-v2-20261006.json'),
        'development_gate_audit':audit,'synthetic_field_probe_independent_audit_passed':True,
        'resource_boundary':resource,'decryption_executable':str(age),'decryption_executable_sha256':age_sha,
        'legacy_byte_closure_verified':False,'new_exact_owner_approval_received':False,'study_executed':False,
        'actual_new_formal_host_baseline_observed':False,'formal_holdout_rows_read':0,
        'execution_ready_meaning':'complete prepared freeze, NOT execution authority; separate exact two-hash approval required'}
    raw=(json.dumps(freeze,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    require(len(raw)<=LIMIT,'bounded complete formal freeze required')
    _write(MAC_SOURCE/FREEZE_FILE,raw);_write(ROOT/FREEZE_FILE,raw)
    remote='test ! -e '+str(REMOTE_SOURCE/FREEZE_FILE)+' && umask 077 && tee '+str(REMOTE_SOURCE/FREEZE_FILE)+' >/dev/null'
    subprocess.run(ssh_args()+[remote],input=raw,check=True,timeout=30)
    require(all(file_sha(MAC_SOURCE/n)==sha for n,sha in sources.items()),'formal deployed Mac bytes differ')
    return {'study_id':STUDY_ID,'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
        'source_revision':revision,'source_file_count':len(sources),'known_host_file_count':len(host),
        'new_field_operations':0,'model_generation_calls':0,'formal_holdout_rows_read':0,
        'execution_authorized':False,'legacy_byte_closure_verified':False}


if __name__=='__main__':print(json.dumps(build(),sort_keys=True))
