"""Python 3.9 formal field scope. No private reads or effects on import."""
from __future__ import annotations

import re
import time
import hashlib
from pathlib import Path

from .c5_research_native import digest, require
from .c5_formal20_policy_v2 import validate_formal_binding

STUDY_ID = 'c5-rhino-paired-20-v1'
MAC_SOURCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-source-v2')
MAC_STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-state-v2')
REMOTE_STATE = Path('/data/c5-rhino-formal20-state-v2')
REMOTE_SOURCE = Path('/data/RhinoCoder-c5-formal20-v2')
REMOTE_ENV = Path('/data/conda-envs/rhinocoder')
SSH_SOCKET = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/ssh-22159.control')
SSH_PORT = 22159
SSH_KNOWN_HOSTS = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/known-hosts-22159')
SSH_KNOWN_HOSTS_SHA = 'ae41a99e39f76b1be352f0098439b126fe5b8465c358b8dabbb7a71e53d2d1a9'
SPEC_FILE = 'eval/c5/rhino-formal20-spec-v2.json'
FREEZE_FILE = 'eval/c5/rhino-formal20-runtime-freeze-v2.json'
BASE_REVISION = 'c03e6d358207e414f1eca0bb1891e29f1db0e242'
BASE_IDENTITY = '63f7de2f37a997c829ec98eaf617cdc78808586bc9df1139a90c030c4d76ebae'
ADAPTER_IDENTITY = '305d72703270d16e93233d1d34ae27cdaddd777e4530afead88c7edb8dc22cae'
SHA = re.compile(r'[0-9a-f]{64}\Z')
SLOT = re.compile(r'F(?:0[1-9]|1[0-9]|20)-(?:base|lora)\Z')
SEED_OPS = frozenset({'create_box', 'create_cylinder', 'create_sphere', 'move_object',
    'rotate_object', 'scale_object', 'set_object_color', 'set_object_layer', 'group_objects'})


def file_sha(path):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path and path.is_file(),'frozen regular code file required')
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):value.update(block)
    return value.hexdigest()


def authority(spec, freeze, approval, *, clock=time.time, check_time=True):
    """Whole new v2 field gate. No old draft/host/capacity grant can run."""
    validate_formal_binding(spec, freeze, approval)
    require(spec.get('mac_source_root')==freeze.get('mac_source_root')==str(MAC_SOURCE)
        and freeze.get('repository_root_for_private_boundary')=='/Users/xiongweiluo/RhinoCoder',
        'formal source and owner worktree-boundary root differ')
    wrapper='#! python 3\nimport runpy\nscope = runpy.run_path("'+str(MAC_SOURCE)+'/tools/c5_rhino_formal20_arm_v2.py", run_name="__main__")\nscope["ENTRY_RETURN_BARRIER"].release_after_entry_return()\n'
    require(spec.get('entry_return_wrapper')==wrapper and spec.get('startup_timeout_seconds')==180,
        'formal deferred wrapper/startup contract differs')
    require(isinstance(spec, dict) and isinstance(freeze, dict) and isinstance(approval, dict)
        and spec.get('study_id') == freeze.get('study_id') == STUDY_ID
        and spec.get('execution_ready') is True and freeze.get('execution_ready') is True,
        'formal field freeze not ready')
    require(freeze.get('spec_sha256') == digest(spec) and approval == {
        'study_id': STUDY_ID, 'actor': 'repository_owner', 'approved': True,
        'spec_sha256': digest(spec), 'runtime_freeze_sha256': digest(freeze),
        'approval_basis': 'direct repository_owner approval of complete C5-6 formal20 spec and runtime freeze'},
        'new exact formal owner approval required')
    require(spec.get('family_count') == 20 and spec.get('route_slots') == 40
        and spec.get('base_revision') == BASE_REVISION
        and spec.get('adapter_sha256') == ADAPTER_IDENTITY
        and spec.get('contract_id') == 'qwen25-v4-selector-v3-json-invoker-c5-v1'
        and freeze.get('model_identities') == {'base': BASE_IDENTITY, 'lora': ADAPTER_IDENTITY},
        'formal model/contract/denominator differs')
    thresholds = {'lora_success_min': 14, 'paired_net_wins_min': 3,
        'difference_percentage_points_min': 15, 'critical_safety_errors_max': 0,
        'duplicate_writes_max': 0, 'unverified_cleanup_max': 0}
    require(spec.get('thresholds') == thresholds and all(type(spec['thresholds'][k]) is int for k in thresholds)
        and spec.get('slot_seed') == 20261003, 'formal threshold/order differs')
    require(spec.get('privacy_policy') == 'formal20-headless-public-labels-v1'
        and freeze.get('limited_host_readable_file_inventory_verified') is True
        and freeze.get('synthetic_field_probe_independent_audit_passed') is True,
        'formal privacy/import/development field gate not frozen')
    for key in ('original_final_entry_allowed', 'original_80_reuse_allowed', 'automatic_retry_allowed',
                'task_replacement_after_claim_allowed', 'default_route_change_allowed'):
        require(spec.get(key) is False, 'formal historical/replay/product boundary differs')
    for key in ('family_merkle_root_sha256', 'slot_order_sha256', 'public_commitment_sha256'):
        require(isinstance(spec.get(key), str) and SHA.fullmatch(spec[key]), 'formal public binding missing')
    fixed = {'mac_state_root': str(MAC_STATE), 'remote_state_root': str(REMOTE_STATE),
        'remote_source_root': str(REMOTE_SOURCE), 'remote_environment_root': str(REMOTE_ENV),
        'ssh_socket': str(SSH_SOCKET), 'ssh_host': '175.155.64.171', 'ssh_port': SSH_PORT, 'ssh_user': 'linux',
        'ssh_known_hosts_file': str(SSH_KNOWN_HOSTS), 'ssh_known_hosts_file_sha256': SSH_KNOWN_HOSTS_SHA}
    require(all(spec.get(k) == v for k, v in fixed.items()), 'formal fixed deployment differs')
    require(type(spec.get('per_request_timeout_seconds')) is int
        and 1 <= spec['per_request_timeout_seconds'] <= 180
        and type(spec.get('hub_attach_timeout_seconds')) is int
        and 1 <= spec['hub_attach_timeout_seconds'] <= 180, 'bounded formal transport timeouts required')
    require(type(spec.get('max_generation_stages')) is int and 40 <= spec['max_generation_stages'] <= 240,
        'formal generation ceiling differs')
    require(all(type(spec.get(k)) is int for k in ('model_generation_cutoff_epoch', 'lease_expiry_epoch',
        'export_reserve_seconds', 'formal_gpu_seconds_max'))
        and spec['export_reserve_seconds'] >= 900
        and spec['lease_expiry_epoch'] - spec['model_generation_cutoff_epoch'] >= spec['export_reserve_seconds']
        and 0 < spec['formal_gpu_seconds_max'] <= 18000, 'formal resource boundary missing')
    if check_time:
        require(clock() < spec['model_generation_cutoff_epoch'], 'formal generation cutoff reached')
    require(isinstance(freeze.get('source_files'), dict) and freeze['source_files']
        and digest(freeze['source_files']) == freeze.get('source_inventory_sha256')
        and isinstance(freeze.get('fixed_public_files'), dict)
        and {'eval/c5/rhino-runtime-schema-v1.json', 'eval/c5/c5-engineering-config.json',
             'eval/c5/gpu-formal-registry-20261001.json', 'requirements-training.txt', 'requirements.txt'}
            <= set(freeze['fixed_public_files']), 'complete formal source/config inventory missing')
    for key in ('environment_sha256', 'spec_file_sha256'):
        require(isinstance(freeze.get(key), str) and SHA.fullmatch(freeze[key]), 'formal environment/spec digest missing')
    require(isinstance(freeze.get('mac_environment'), dict) and freeze['mac_environment'].get('file_sha256')
        and isinstance(freeze.get('rhino_version'), str)
        and isinstance(freeze.get('rhino_environment_files'), dict) and freeze['rhino_environment_files'],
        'complete Mac/Rhino environment freeze missing')
    resource = freeze.get('resource_boundary')
    require(isinstance(resource, dict) and resource.get('owner_confirmed') is True
        and resource.get('formal_max_seconds') == spec['formal_gpu_seconds_max']
        and resource.get('generation_cutoff_epoch') == spec['model_generation_cutoff_epoch']
        and resource.get('provider_expiry_epoch') == spec['lease_expiry_epoch']
        and resource.get('export_reserve_seconds') == spec['export_reserve_seconds'], 'formal resource freeze differs')
    require(spec.get('max_generation_stages') == 112 and spec.get('max_model_requests') == 56,
        'fixed formal strata generation/request bound differs')
    require(resource.get('research_cumulative_max_seconds') == 21600
        and resource.get('original_cumulative_max_seconds') == 57600
        and resource.get('prior_research_seconds',0) >= 2407.228115136008
        and resource.get('prior_cumulative_seconds',0) >= 9607.228115136008,
        'new accepted formal resource/prior ledger missing')
    evidence=freeze.get('development_gate_audit',{})
    require(digest(evidence) == 'd244d95dd302652df61bef1f25815d4578a0e2d6d66c8d77266e52bf1b3c2015'
        and evidence.get('complete_C5_engineering_gate_passed') is True,
        'actual complete D independent audit required')
    return digest(freeze)


def native_plans(value):
    """Validate ONLY task/setup policy, never scorer labels or answers."""
    require(isinstance(value, dict) and set(value) == {'slot_order', 'plans'}
        and isinstance(value['slot_order'], list) and len(value['slot_order']) == 40
        and isinstance(value['plans'], dict), 'formal native plan shape')
    order = value['slot_order']
    require(all(isinstance(s, dict) and set(s) == {'slot_id', 'family_id', 'route'}
        and isinstance(s['slot_id'], str) and SLOT.fullmatch(s['slot_id'])
        and s['route'] in {'base', 'lora'} and s['slot_id'].endswith('-' + s['route']) for s in order)
        and len({s['slot_id'] for s in order}) == 40
        and set(value['plans']) == {s['slot_id'] for s in order}, 'formal native schedule differs')
    for index in range(0, 40, 2):
        a, b = order[index:index+2]
        require(a['family_id'] == b['family_id'] and {a['route'], b['route']} == {'base', 'lora'}
            and a['route'] == ('base' if index < 20 else 'lora'), 'formal pair counterbalance differs')
    for p in value['plans'].values():
        require(isinstance(p, dict) and set(p) == {'task_text', 'fixture_recipe', 'max_writes', 'max_reads'}
            and isinstance(p['task_text'], str) and 0 < len(p['task_text'].encode()) <= 4096
            and isinstance(p['fixture_recipe'], list) and len(p['fixture_recipe']) <= 8
            and all(type(p[k]) is int and 0 <= p[k] <= 3 for k in ('max_writes', 'max_reads')),
            'formal narrow native policy differs')
        for seed in p['fixture_recipe']:
            require(isinstance(seed, dict) and set(seed) == {'operation', 'arguments'}
                and seed['operation'] in SEED_OPS and isinstance(seed['arguments'], dict), 'formal seed recipe differs')
    return value
