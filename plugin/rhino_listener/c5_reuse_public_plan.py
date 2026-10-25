"""Pinned public eight slots, usable in Rhino Python 3.9 without training init."""
import hashlib
from pathlib import Path
from .c5_reuse_runtime_scope import read_bytes
from .c5_reuse_field_scope import STUDY, sha, strict, require

SOURCE = 'eval/c5/hostassurance-development-spec-20261007-d.json'
SOURCE_RAW_SHA256 = '9b192efd1d7d42e868ca1d8cbc4eaee1213bd144fe89c7a8d2dcd8ce4c224494'
ORDER = ('write-base', 'write-lora', 'read-lora', 'read-base', 'clarify-base',
         'clarify-lora', 'unsupported-lora', 'unsupported-base')


def public_plan(root):
    raw = read_bytes(Path(root)/SOURCE)
    require(hashlib.sha256(raw).hexdigest()==SOURCE_RAW_SHA256,'public_development_plan_source_drift')
    historical = strict(raw)
    plans = historical['task_plans']
    require(set(plans)==set(ORDER),'public_development_plan_population')
    return {'study_id':STUDY,'task_plans':plans,'development_plan_sha256':sha(plans),
            'order':list(ORDER),'slot_policies':historical['slot_policies'],
            'task_source':historical['task_source'],'source_file':SOURCE,
            'source_file_sha256':SOURCE_RAW_SHA256,'new_semantic_families':0,
            'private_train_or_formal_reads':0,'historical_run_reactivated':False,
            'new_overlap_check_independently_proven':False,'execution_ready':False}


def observer_policy(root):
    # The retired public document supplies type/read-root policy only.
    public_plan(root)
    policy = strict(read_bytes(Path(root)/SOURCE))['observer_backend']
    policy['code_read_roots'] = [str(Path(root)) if p.startswith('/Users/xiongweiluo/RhinoCoder/data/training/c5/')
                               else p for p in policy['code_read_roots']]
    policy['code_read_roots'] = list(dict.fromkeys(policy['code_read_roots']))
    return policy
