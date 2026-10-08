"""Custodian-only failed-run checks; CPU-injected reader, no field entry.

This is NOT the original full joint audit. Even successful checks cannot
certify host cleanup, GPU absence, quality, generation totals or C5 GO.
Never decrypts, loads a model, reads a key, repairs or resumes a run.
"""
import hashlib
import math

from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_formal20_plan import (
    STUDY_ID, family_merkle_root, slot_order, slot_order_sha256, validate_families,
)
from training.c5_formal20_public_progress import validate_progress


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
    progress = validate_progress(read('public-progress.json'))
    require(progress['runtime_freeze_sha256'] == digest(freeze)
            and progress['public_commitment_sha256'] == spec['public_commitment_sha256']
            and progress['phase'] == 'stopped_incomplete_no_replay'
            and progress['slots_attempted'] == progress['slots_finished'] == 0
            and progress['confirmed_generation_stages'] == 0
            and progress['counters_complete'] is False, 'incomplete progress differs')
    cases = validate_families(read('private-cases.json'))
    require(family_merkle_root(cases) == spec['family_merkle_root_sha256'],
            'existing private case commitment differs')
    order = slot_order(cases, seed=spec['slot_seed'])
    require(slot_order_sha256(order) == spec['slot_order_sha256'], 'existing schedule differs')
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
