"""Custodian-only failed-run checks; CPU-injected reader, no field entry.

This is NOT the original full joint audit. Even successful checks cannot
certify host cleanup, GPU absence, quality, generation totals or C5 GO.
Never decrypts, loads a model, reads a key, repairs or resumes a run.
"""
import hashlib
import math
import json
import random

STUDY_ID = 'c5-rhino-paired-20-v1'


def require(ok, reason):
    if not ok: raise RuntimeError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def family_merkle_root(cases):
    require(isinstance(cases, list) and len(cases) == 20, 'existing case population differs')
    nodes = sorted(hashlib.sha256(canonical(case)).digest() for case in cases)
    while len(nodes) > 1:
        if len(nodes) % 2: nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[n] + nodes[n + 1]).digest() for n in range(0, len(nodes), 2)]
    return nodes[0].hex()


def slot_order(cases, seed):
    ids = sorted(c['family_id'] for c in cases)
    require(len(set(ids)) == 20 and type(seed) is int, 'existing family identity/seed differs')
    random.Random(seed).shuffle(ids)
    result = []
    for n, family in enumerate(ids):
        routes = ('base', 'lora') if n < 10 else ('lora', 'base')
        result.extend({'slot_id': 'F%02d-%s' % (n + 1, route), 'family_id': family, 'route': route}
            for route in routes)
    return result


def audit_pre_slot_failure(read, spec, freeze):
    """Read ONLY the seven enumerated existing evidence records via owner I/O.

    Scope is this pre-slot incomplete failure, not arbitrary partial studies.
    A future frozen custodian entry must bind actual source/runtime identity
    before providing ``read``. This module itself is not execution authority.
    No raw private record, task/family ID, hash of a task, or answer is returned.
    """
    require(spec['study_id'] == freeze['study_id'] == STUDY_ID
            and freeze['spec_sha256'] == digest(spec), 'failed audit public binding differs')
    started = read('formal20.started.json')
    require(digest(started) == digest({'study_id': STUDY_ID, 'spec_sha256': digest(spec),
            'runtime_freeze_sha256': digest(freeze),
            'public_commitment_sha256': spec['public_commitment_sha256'],
            'replay_allowed': False}), 'consumption binding differs')
    result = read('formal20.run-result.json')
    require(digest(result) == digest({'study_id': STUDY_ID, 'status': 'formal_incomplete_no_replay',
            'slots_attempted': 0, 'route_slots_required': 40,
            'error_type': 'BrokenPipeError', 'c5_6_gate_claim': False})
            and type(result['slots_attempted']) is int, 'pre-slot failure scope differs')
    progress = read('public-progress.json')
    require(set(progress) == {'schema_version', 'study_id', 'phase', 'sequence',
        'started_claim_present', 'route_slots_required', 'slots_attempted', 'slots_finished',
        'confirmed_generation_stages', 'counters_complete', 'elapsed_seconds',
        'runtime_freeze_sha256', 'public_commitment_sha256', 'formal_execution_authority',
        'private_content_included', 'replay_allowed', 'independent_audit_complete'}
        and type(progress['schema_version']) is int and progress['schema_version'] == 1
        and progress['study_id'] == STUDY_ID and progress['started_claim_present'] is True
        and type(progress['route_slots_required']) is int and progress['route_slots_required'] == 40
        and all(progress[k] is False for k in ('formal_execution_authority', 'private_content_included',
            'replay_allowed', 'independent_audit_complete')), 'closed incomplete progress differs')
    require(all(type(progress[k]) is int and 0 <= progress[k] <= 256 for k in
        ('sequence', 'slots_attempted', 'slots_finished', 'confirmed_generation_stages'))
        and type(progress['elapsed_seconds']) in (int, float)
        and math.isfinite(progress['elapsed_seconds']) and progress['elapsed_seconds'] >= 0,
        'incomplete progress counter types differ')
    require(progress['runtime_freeze_sha256'] == digest(freeze)
            and progress['public_commitment_sha256'] == spec['public_commitment_sha256']
            and progress['phase'] == 'stopped_incomplete_no_replay'
            and progress['slots_attempted'] == progress['slots_finished'] == 0
            and progress['confirmed_generation_stages'] == 0
            and progress['counters_complete'] is False, 'incomplete progress differs')
    cases = read('private-cases.json')
    require(family_merkle_root(cases) == spec['family_merkle_root_sha256'],
            'existing private case commitment differs')
    order = slot_order(cases, spec['slot_seed'])
    require(digest(order) == spec['slot_order_sha256'], 'existing schedule differs')
    by_id = {c['family_id']: c for c in cases}
    native = {'slot_order': order, 'plans': {}}
    models = {}
    for slot in order:
        case = by_id[slot['family_id']]
        native['plans'][slot['slot_id']] = {k: case[k] for k in
                ('task_text', 'fixture_recipe', 'max_writes', 'max_reads')}
        models[slot['slot_id']] = {'route': slot['route'],
                'task_sha256': hashlib.sha256(case['task_text'].encode()).hexdigest(),
                'max_steps': case['max_steps']}
    require(read('native-prepared.json') == {'study_id': STUDY_ID,
            'native_plans_sha256': digest(native), 'runtime_freeze_sha256': digest(freeze)},
            'existing native preparation binding differs')
    require(digest(read('model-plans-hashed.json')) == digest(models), 'existing model plan binding differs')
    resource = read('resource-settlement.json')
    require(set(resource) == {'study_id', 'status', 'elapsed_seconds_including_load_and_idle',
            'cap_seconds', 'start_epoch', 'stop_epoch', 'resource_boundary_sha256', 'replay_allowed'}
            and resource['study_id'] == STUDY_ID and resource['status'] == 'formal_mac_driver_finished'
            and resource['resource_boundary_sha256'] == digest(freeze['resource_boundary'])
            and resource['replay_allowed'] is False, 'existing resource binding differs')
    for key in ('elapsed_seconds_including_load_and_idle', 'cap_seconds', 'start_epoch', 'stop_epoch'):
        require(type(resource[key]) in (int, float) and math.isfinite(resource[key])
                and resource[key] >= 0, 'finite resource observation required')
    wall = resource['stop_epoch'] - resource['start_epoch']
    require(wall >= 0, 'resource wall interval invalid')
    return {'study_id': STUDY_ID, 'status': 'owner_partial_failure_checks_not_full_joint_audit',
            'spec_sha256': digest(spec), 'runtime_freeze_sha256': digest(freeze),
            'consumption_and_existing_cases_binding_verified': True,
            'existing_40_plan_schedule_binding_verified': True,
            'case_semantic_or_arguments_schema_revalidated': False,
            'recorded_slots_attempted': 0, 'recorded_slots_finished': 0,
            'recorded_generation_stages': 0, 'actual_generation_total': None,
            'model_quality_scores_available': False, 'paired_summary': None,
            'reported_resource_monotonic_seconds': resource['elapsed_seconds_including_load_and_idle'],
            'reported_resource_wall_seconds': wall,
            'resource_discrepancy_cause_verified': False,
            'external_host_receipt_captured': False,
            'host_continuity_verified': False, 'host_cleanup_verified': False,
            'remote_gpu_absence_verified': False, 'full_joint_audit_complete': False,
            'c5_6_gate_claim': False, 'c5_7_decision': 'not_decided_here',
            'model_or_rhino_calls': 0, 'cipher_or_identity_reads': 0,
            'private_content_included': False, 'replay_allowed': False,
            'formal_execution_authority': False, 'default_route_changed': False}
