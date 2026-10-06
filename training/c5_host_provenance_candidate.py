"""Pure synthetic design checks, NOT an admission policy or runtime auditor.

No file/process/CLR/model access. A successful check still forbids execution.
Opaque host metadata describes a declared trust boundary, never emitted-byte
or causal generator proof. Legacy formal scope/guards remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re

POLICY = 'c5-trusted-host-opaque-baseline-design-v1'
SHA = re.compile(r'[0-9a-f]{64}\Z')
ROLES = frozenset({'rhino_host', 'dotnet_runtime', 'python_runtime', 'pythonnet_generator', 'research_entry'})
KINDS = frozenset({'file_assembly', 'opaque_host_dynamic'})


class ProvenanceDesignError(ValueError):
    pass


def _require(condition, category):
    if not condition:
        raise ProvenanceDesignError(category)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _identity(value):
    _require(isinstance(value, str) and bool(SHA.fullmatch(value)), 'sha_identity_required')


def _files(value):
    _require(isinstance(value, dict) and 0 < len(value) <= 4096, 'bounded_file_inventory_required')
    for path, sha in value.items():
        _require(isinstance(path, str) and path.startswith('/') and len(path) <= 1024
            and '\x00' not in path and all(part not in {'.', '..', ''} for part in path.split('/')[1:]),
            'canonical_file_identity_required')
        _identity(sha)


def _assemblies(rows, files):
    _require(isinstance(rows, list) and 0 < len(rows) <= 1024, 'bounded_assembly_inventory_required')
    identities = set()
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {'name', 'instance_id', 'kind', 'file',
            'metadata_sha256', 'metadata_scope'}, 'assembly_record_shape')
        _require(isinstance(row['name'], str) and 0 < len(row['name']) <= 512
            and isinstance(row['kind'], str) and row['kind'] in KINDS and isinstance(row['instance_id'], str)
            and 0 < len(row['instance_id']) <= 128, 'assembly_identity_required')
        key = (row['name'], row['instance_id'])
        _require(key not in identities, 'duplicate_assembly_identity')
        identities.add(key)
        _identity(row['metadata_sha256'])
        if row['kind'] == 'file_assembly':
            _require(isinstance(row['file'], str) and row['file'] in files
                and row['metadata_scope'] == 'file_bytes_and_structure',
                'file_assembly_binding_missing')
        else:
            _require(row['file'] is None and row['metadata_scope'] == 'structure_only_not_code_bytes',
                'opaque_code_must_not_claim_byte_proof')


def validate_candidate(manifest, observation):
    """Validate fixture claims/identity continuity, never their real-world truth.

    Manifest must be declared before a controlled-process baseline is sealed.
    Its use in a real study would require a new frozen observer/auditor and a
    separately approved policy. Nothing here grants that future authority.
    """
    _require(isinstance(manifest, dict) and set(manifest) == {'policy', 'design_only', 'file_inventory',
        'file_roles', 'opaque_trust_assumptions', 'sealed_baseline'}, 'candidate_manifest_shape')
    _require(manifest['policy'] == POLICY and manifest['design_only'] is True, 'design_only_policy_required')
    files = manifest['file_inventory']
    _files(files)
    roles = manifest['file_roles']
    _require(isinstance(roles, dict) and set(roles) == ROLES
        and all(isinstance(p, str) and p in files for p in roles.values()),
        'required_host_generator_entry_roles_missing')
    _require(manifest['opaque_trust_assumptions'] == {
        'trusted_host_may_emit_unverifiable_code': True,
        'assembly_names_are_not_generator_proof': True,
        'no_untrusted_inprocess_code_assumed': True,
        'not_a_sandbox_against_local_host_compromise': True}, 'explicit_opaque_trust_boundary_required')
    baseline = manifest['sealed_baseline']
    keys = {'process_identity', 'project_files', 'python_origin_bindings', 'assemblies',
        'assembly_inventory_sha256', 'native_images_sha256', 'warmup_completed', 'baseline_sealed'}
    _require(isinstance(baseline, dict) and set(baseline) == keys, 'sealed_baseline_shape')
    _require(baseline['warmup_completed'] is True and baseline['baseline_sealed'] is True,
        'baseline_not_sealed_after_warmup')
    _identity(baseline['process_identity'])
    _identity(baseline['native_images_sha256'])
    _files(baseline['project_files'])
    _assemblies(baseline['assemblies'], files)
    _require(digest(baseline['assemblies']) == baseline['assembly_inventory_sha256'], 'baseline_inventory_digest_differs')
    bindings = baseline['python_origin_bindings']
    _require(isinstance(bindings, dict) and set(bindings) == {'CLR', 'clr'}, 'explicit_pythonnet_origin_bindings_required')
    for row in bindings.values():
        _require(isinstance(row, dict) and set(row) == {'origin', 'host_role', 'binding_scope', 'object_identity'}
            and row['origin'] == 'unknown' and row['host_role'] == 'pythonnet_generator'
            and row['binding_scope'] == 'controlled_process_opaque_host_assumption_not_causal_proof'
            and isinstance(row['object_identity'], str) and 0 < len(row['object_identity']) <= 128,
            'unknown_origin_not_declared_or_false_causal_proof')
    _require(isinstance(observation, dict) and set(observation) == keys | {'phase', 'model_input_is_data_only',
        'unattributed_load_events', 'event_stream_complete'}, 'observation_shape')
    _require(isinstance(observation['phase'], str)
        and observation['phase'] in {'pre_dispatch', 'post_dispatch', 'shutdown'}, 'bounded_observation_phase_required')
    _require(observation['model_input_is_data_only'] is True and observation['event_stream_complete'] is True
        and observation['unattributed_load_events'] == [], 'unexplained_or_missing_runtime_load_events')
    # Exact continuity includes instance identity, metadata changes, new types,
    # source bytes, native images and origin rebinding. Names alone never pass.
    _require(all(observation[k] == baseline[k] for k in keys), 'sealed_runtime_identity_changed')
    return {'status':'synthetic_provenance_design_constraints_validated_only', 'policy':POLICY,
        'candidate_manifest_sha256':digest(manifest),
        'opaque_assembly_count':sum(r['kind'] == 'opaque_host_dynamic' for r in baseline['assemblies']),
        'emitted_bytecode_or_causal_generator_origin_proven':False,
        'actual_runtime_evidence_verified':False, 'legacy_byte_closure_verified':False,
        'execution_ready':False, 'formal_admission_supported':False}
