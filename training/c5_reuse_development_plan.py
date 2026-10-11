"""Read only the pinned public development plans, never private train/holdout.

Exact task text reuse does not reactivate the retired D run or its approval.
The historical exclusion is an owner statement, not new leakage proof.
"""
from training.c5_reuse_deployment import read_file
from training.c5_reuse_evidence import canonical, raw_sha, require, sha, strict
from training.c5_reuse_field_scope import STUDY

SOURCE = 'eval/c5/hostassurance-development-spec-20261007-d.json'
SOURCE_RAW_SHA256 = '9b192efd1d7d42e868ca1d8cbc4eaee1213bd144fe89c7a8d2dcd8ce4c224494'
ORDER = ('write-base', 'write-lora', 'read-lora', 'read-base', 'clarify-base',
         'clarify-lora', 'unsupported-lora', 'unsupported-base')


def public_plan(root):
    raw = read_file(root, SOURCE)
    require(raw_sha(raw) == SOURCE_RAW_SHA256, 'public_development_plan_source_drift')
    historical = strict(raw)
    plans = historical['task_plans']
    require(set(plans) == set(ORDER), 'public_development_plan_population')
    return {'study_id': STUDY, 'task_plans': plans, 'development_plan_sha256': sha(plans),
            'order': list(ORDER), 'slot_policies': historical['slot_policies'],
            'task_source': historical['task_source'], 'source_file': SOURCE,
            'source_file_sha256': SOURCE_RAW_SHA256, 'new_semantic_families': 0,
            'private_train_or_formal_reads': 0, 'historical_run_reactivated': False,
            'new_overlap_check_independently_proven': False, 'execution_ready': False}
