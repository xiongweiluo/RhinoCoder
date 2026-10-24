"""New development scope checks only; no grant maker, loader or field calls.

These checks bind supplied records, not their human approval provenance.
Actual entry wiring and current environment/asset verification remain required.
The formal reuse phase is intentionally not admitted by this development scope.
"""
import re
from pathlib import Path

import hashlib
import json


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'reuse_scope_keys')


def is_sha(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


def strict(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 2 * 1024 * 1024, 'reuse_json_size')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'reuse_duplicate_key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('reuse_nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


STUDY = 'C5DEV-REUSE-20261011-A'
PROTOCOL = 'c5-reuse-field-development-v1'
APPROVAL_BASIS = 'direct repository_owner approval of new reuse development spec and complete runtime freeze'
COMPARISON = {
    'base_revision': 'c03e6d358207e414f1eca0bb1891e29f1db0e242',
    'adapter_sha256': '305d72703270d16e93233d1d34ae27cdaddd777e4530afead88c7edb8dc22cae',
    'checkpoint': 'checkpoint-132', 'contract_id': 'qwen25-v4-selector-v3-json-invoker-c5-v1',
    'training_allowed': False, 'parse_repair_allowed': False}
LIMITS = {'model_requests': 56, 'generation_stages': 112, 'slots': 40,
          'model_steps_per_slot': 3, 'native_messages_per_slot': 128,
          'hub_requests': 41, 'seeding_steps_per_fixture': 8,
          'normal_observations': 2048, 'cleanup_observations': 256,
          'journal_records': 4096, 'settlement_samples': 8, 'stable_samples': 3,
          'settlement_seconds': 60, 'startup_seconds': 180, 'model_seconds': 180,
          'native_seconds': 120}


def path(value):
    require(type(value) is str and Path(value).is_absolute()
            and '..' not in Path(value).parts and str(Path(value)) == value, 'field_path')
    return Path(value)


def bind(spec, runtime, approval, *, now):
    """Pure exact binding. No filesystem access or execution authority minting."""
    exact(spec, ('protocol', 'study_id', 'phase', 'instance_id', 'comparison', 'limits',
                 'resources', 'host_policy', 'execution_ready', 'automatic_retry_allowed',
                 'private_formal_data_allowed', 'default_route_change_allowed', 'development_plan_sha256'))
    exact(runtime, ('protocol', 'study_id', 'instance_id', 'spec_sha256', 'paths',
                    'source_files', 'environment_sha256', 'model_assets_sha256',
                    'host_readable_files_sha256', 'host_policy', 'resources', 'execution_ready'))
    require(spec['protocol'] == runtime['protocol'] == PROTOCOL
            and spec['study_id'] == runtime['study_id'] == STUDY
            and spec['phase'] == 'development' and type(spec['instance_id']) is str
            and re.fullmatch(r'reuse-dev-[a-z0-9-]{1,48}', spec['instance_id'])
            and spec['instance_id'] == runtime['instance_id'], 'new_development_identity')
    require(canonical(spec['comparison']) == canonical(COMPARISON)
            and canonical(spec['limits']) == canonical(LIMITS), 'field_contract_limits_drift')
    require(spec['execution_ready'] is runtime['execution_ready'] is True
            and all(spec[k] is False for k in ('automatic_retry_allowed', 'private_formal_data_allowed',
                                              'default_route_change_allowed')), 'development_freeze_not_ready')
    require(runtime['spec_sha256'] == sha(spec) and is_sha(spec['development_plan_sha256']), 'field_spec_binding')
    for name in ('environment_sha256', 'model_assets_sha256', 'host_readable_files_sha256'):
        require(is_sha(runtime[name]), 'field_asset_evidence_missing')
    require(type(runtime['source_files']) is dict and 0 < len(runtime['source_files']) <= 512
            and all(type(k) is str and re.fullmatch(r'(training|plugin|tools|eval|agent|mcp)/[a-zA-Z0-9_./-]+', k)
                    and not Path(k).is_absolute() and '..' not in Path(k).parts
                    and str(Path(k)) == k and is_sha(v) for k, v in runtime['source_files'].items()),
            'field_source_evidence_missing')
    resources = spec['resources']
    exact(resources, ('lease_expiry_epoch', 'generation_cutoff_epoch', 'export_reserve_seconds',
                      'prior_cumulative_upper_bound_seconds', 'remaining_gpu_seconds',
                      'development_seconds_max', 'formal_seconds_max', 'research_seconds_max',
                      'original_cumulative_seconds_max'))
    require(all(type(v) is int and v >= 0 for v in resources.values())
            and resources['export_reserve_seconds'] >= 900
            and resources['lease_expiry_epoch'] - resources['generation_cutoff_epoch']
                >= resources['export_reserve_seconds']
            and type(now) in (int, float) and 0 < now < resources['generation_cutoff_epoch']
            and 0 < resources['development_seconds_max'] <= 3600
            and 0 < resources['formal_seconds_max'] <= 18000
            and 0 < resources['research_seconds_max'] <= 21600
            and resources['development_seconds_max'] + resources['formal_seconds_max']
                <= resources['research_seconds_max']
            and resources['original_cumulative_seconds_max'] == 57600
            and resources['prior_cumulative_upper_bound_seconds'] + resources['remaining_gpu_seconds'] <= 57600
            and resources['research_seconds_max'] <= resources['remaining_gpu_seconds']
            and canonical(runtime['resources']) == canonical(resources), 'field_resource_boundary')
    host = spec['host_policy']
    exact(host, ('instance_id', 'accepted_by_owner', 'acceptance_record_sha256',
                 'readable_files_frozen', 'opaque_host_trusted', 'full_byte_closure_claimed',
                 'baseline_before_generation', 'new_events_after_baseline_allowed',
                 'external_readiness_and_final_capture_required'))
    require(host['instance_id'] == spec['instance_id'] and host['accepted_by_owner'] is True
            and is_sha(host['acceptance_record_sha256']) and host['readable_files_frozen'] is True
            and host['opaque_host_trusted'] is True and host['full_byte_closure_claimed'] is False
            and host['baseline_before_generation'] is True
            and host['new_events_after_baseline_allowed'] is False
            and host['external_readiness_and_final_capture_required'] is True
            and canonical(runtime['host_policy']) == canonical(host), 'field_new_host_policy')
    paths = runtime['paths']
    exact(paths, ('source_root', 'state_root', 'admission_root'))
    source, state, admission = (path(paths[k]) for k in ('source_root', 'state_root', 'admission_root'))
    require(source.name == spec['instance_id'] + '-source'
            and state.name == spec['instance_id'] + '-state'
            and admission.name == 'c5-reuse-global-admission-v1'
            and len({source, state, admission}) == 3
            and all(a not in b.parents for a in (source, state, admission)
                    for b in (source, state, admission) if a != b), 'field_path_identity')
    expected = {'study_id': STUDY, 'instance_id': spec['instance_id'], 'actor': 'repository_owner',
                'approved': True, 'spec_sha256': sha(spec), 'runtime_sha256': sha(runtime),
                'approval_basis': APPROVAL_BASIS}
    require(canonical(approval) == canonical(expected), 'field_exact_owner_approval')
    value = {'protocol': PROTOCOL, 'study_id': STUDY, 'instance_id': spec['instance_id'],
            'spec_sha256': sha(spec), 'runtime_sha256': sha(runtime), 'paths': paths,
            'limits': LIMITS, 'development_plan_sha256': spec['development_plan_sha256'],
            'whole_field_authority_verified': False,
            'approval_origin_verified': False, 'record_binding_verified': True}
    return strict(canonical(value))


def validate_binding(value):
    exact(value, ('protocol', 'study_id', 'instance_id', 'spec_sha256', 'runtime_sha256',
                  'paths', 'limits', 'development_plan_sha256', 'whole_field_authority_verified',
                  'approval_origin_verified', 'record_binding_verified'))
    require(value['protocol'] == PROTOCOL and value['study_id'] == STUDY
            and type(value['instance_id']) is str and re.fullmatch(r'reuse-dev-[a-z0-9-]{1,48}', value['instance_id'])
            and all(is_sha(value[k]) for k in ('spec_sha256', 'runtime_sha256', 'development_plan_sha256'))
            and value['record_binding_verified'] is True and value['whole_field_authority_verified'] is False
            and value['approval_origin_verified'] is False and canonical(value['limits']) == canonical(LIMITS),
            'field_validated_binding_shape')
    exact(value['paths'], ('source_root', 'state_root', 'admission_root'))
    source, state, admission = (path(value['paths'][k]) for k in ('source_root', 'state_root', 'admission_root'))
    require(source.name == value['instance_id'] + '-source'
            and state.name == value['instance_id'] + '-state'
            and admission.name == 'c5-reuse-global-admission-v1'
            and len({source, state, admission}) == 3
            and all(a not in b.parents for a in (source, state, admission)
                    for b in (source, state, admission) if a != b), 'field_path_identity')
