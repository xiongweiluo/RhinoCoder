"""Public, fixed retirement prerequisites for candidate C; no old-run effects."""
import hashlib
import os
import stat
from pathlib import Path
from .c5_reuse_field_scope import require

FAILURE='eval/c5/reuse-development-startup-failure-20261012.json'
POLICY={'study_id':'C5DEV-REUSE-20261011-A','instance_id':'reuse-dev-20261011-a',
    'spec_sha256':'32f02512402ada907f6ed07381417d7f91c41896acef79ec5fe9b5d037b6d900',
    'runtime_sha256':'6c27d31987bed8289b498fd547dd680402b0f526cd773bd58a5c09dfaa9b2ac6',
    'retirement_raw_sha256':'f098afe6e005e3ae09129bb44531ce3947e07d6592632d86a2c75af24f0f2978',
    'retired_approval_raw_sha256':'fcfe67c8382d7e2dd28dafd58bec37deea8a75e5686ef9e2b241ac6e0a9416f9',
    'public_failure_record_raw_sha256':'1dea93d52366135c36ee2a49ecb5605de87475a756da5ae4ef5bc3615798fd38',
    'recorded_model_requests':0,'recorded_slots_started':0,'recorded_slots_completed':0,
    'physical_generation_total_independently_proven':None,'retired_execution_restore_allowed':False,
    'new_development_requires_new_exact_two_hash_approval':True,'formal_consumption_authorized':False}


B_FAILURE='eval/c5/reuse-development-preparation-failure-20261012-b.json'
B_POLICY={'study_id': 'C5DEV-REUSE-20261012-B',
 'instance_id': 'reuse-dev-20261012-b',
 'spec_sha256': 'cdd2571e63f040fd145b56d6b322fb7914c0d63816b53eca762001f632131488',
 'runtime_sha256': '8b2243663e571113b8912174835fe0adde169ac451706f2829af7299fcbee1b4',
 'retirement_raw_sha256': '3110dd38a8b318150526394ae98e7b36233fa6ac91a64a2adb08a1f1b529afda',
 'retired_approval_raw_sha256': '175bb33bf80d2f7559f4ee6d03c6634225c9df4839ef5f84686cd5814dd57574',
 'public_failure_record_raw_sha256': '07eed8000f03ef49a35d9106499a9b8712cefc357e5e2c51d1510ff8b0582e2c',
 'recorded_model_requests': 0,
 'recorded_slots_started': 0,
 'recorded_slots_completed': 0,
 'physical_generation_total_independently_proven': None,
 'retired_execution_restore_allowed': False,
 'new_development_requires_new_exact_two_hash_approval': True,
 'formal_consumption_authorized': False}
FAILURES=(FAILURE,B_FAILURE)
POLICIES=[POLICY,B_POLICY]


def verify_record(root,plan,read):
    require(plan['predecessor']==POLICIES,'reuse_successor_declaration')
    for failure,policy in zip(FAILURES,POLICIES):
        require(hashlib.sha256(read(Path(root)/failure)).hexdigest()==policy['public_failure_record_raw_sha256'],
                'reuse_successor_original_failure_record')


def verify_retirement(parent,read):
    for policy in POLICIES:
        state=Path(parent)/(policy['instance_id']+'-state')
        info=state.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700
                and state.is_absolute() and state.resolve()==state
                and not os.path.lexists(state/'owner-approval.json'),'reuse_predecessor_remains_retired')
        for name,key in [('entry-retired-no-retry.json','retirement_raw_sha256'),
                         ('owner-approval.retired-no-retry.json','retired_approval_raw_sha256')]:
            require(hashlib.sha256(read(state/name,private=True)).hexdigest()==policy[key],
                    'reuse_predecessor_retirement_bytes')
