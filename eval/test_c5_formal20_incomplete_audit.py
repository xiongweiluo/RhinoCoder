"""Existing public synthetic families ONLY; no real state or holdout reads."""
import copy
import hashlib
import json

import pytest

from eval.test_c5_formal20_preparation import cases20
from plugin.rhino_listener.c5_research_native import digest
from training.c5_formal20_plan import STUDY_ID, family_merkle_root, slot_order, slot_order_sha256
from training.c5_formal20_public_progress import validate_progress
from training.c5_formal20_incomplete_audit import audit_pre_slot_failure


def records():
    cases = cases20()
    order = slot_order(cases, seed=20261003)
    spec = {'study_id': STUDY_ID, 'public_commitment_sha256': 'a' * 64,
            'family_merkle_root_sha256': family_merkle_root(cases),
            'slot_seed': 20261003, 'slot_order_sha256': slot_order_sha256(order)}
    freeze = {'study_id': STUDY_ID, 'spec_sha256': digest(spec), 'resource_boundary': {'synthetic': True}}
    native = {'slot_order': order, 'plans': {}}
    models = {}
    by_id = {c['family_id']: c for c in cases}
    for s in order:
        c = by_id[s['family_id']]
        native['plans'][s['slot_id']] = {k: c[k] for k in
                ('task_text', 'fixture_recipe', 'max_writes', 'max_reads')}
        models[s['slot_id']] = {'route': s['route'], 'max_steps': c['max_steps'],
                'task_sha256': hashlib.sha256(c['task_text'].encode()).hexdigest()}
    values = {'formal20.started.json': {'study_id': STUDY_ID, 'spec_sha256': digest(spec),
            'runtime_freeze_sha256': digest(freeze), 'public_commitment_sha256': 'a' * 64,
            'replay_allowed': False},
            'formal20.run-result.json': {'study_id': STUDY_ID, 'status': 'formal_incomplete_no_replay',
                'slots_attempted': 0, 'route_slots_required': 40, 'error_type': 'BrokenPipeError',
                'c5_6_gate_claim': False},
            'private-cases.json': cases, 'model-plans-hashed.json': models,
            'native-prepared.json': {'study_id': STUDY_ID, 'native_plans_sha256': digest(native),
                'runtime_freeze_sha256': digest(freeze)},
            'resource-settlement.json': {'study_id': STUDY_ID, 'status': 'formal_mac_driver_finished',
                'elapsed_seconds_including_load_and_idle': 1512.0, 'cap_seconds': 18000,
                'start_epoch': 1000.0, 'stop_epoch': 3505.0,
                'resource_boundary_sha256': digest(freeze['resource_boundary']), 'replay_allowed': False}}
    values['public-progress.json'] = validate_progress({'schema_version': 1, 'study_id': STUDY_ID,
            'phase': 'stopped_incomplete_no_replay', 'sequence': 3, 'started_claim_present': True,
            'route_slots_required': 40, 'slots_attempted': 0, 'slots_finished': 0,
            'confirmed_generation_stages': 0, 'counters_complete': False, 'elapsed_seconds': 12.0,
            'runtime_freeze_sha256': digest(freeze), 'public_commitment_sha256': 'a' * 64,
            'formal_execution_authority': False, 'private_content_included': False,
            'replay_allowed': False, 'independent_audit_complete': False})
    return spec, freeze, values


def test_checks_are_redacted_and_never_certify_quality_safety_or_zero_model_calls():
    spec, freeze, values = records()
    before = copy.deepcopy(values)
    names = []
    def read(name):
        names.append(name)
        return values[name]
    summary = audit_pre_slot_failure(read, spec, freeze)
    assert len(names) == len(set(names)) == 7
    assert set(names) == set(values)
    assert before == values
    assert summary['actual_generation_total'] is None
    assert summary['paired_summary'] is None
    assert not summary['full_joint_audit_complete']
    assert not summary['host_continuity_verified']
    assert not summary['host_cleanup_verified']
    assert not summary['remote_gpu_absence_verified']
    assert not summary['replay_allowed']
    output = json.dumps(summary)
    for c in values['private-cases.json']:
        assert c['task_text'] not in output and c['family_id'] not in output
        assert c['template_family'] not in output
    assert 'native_plans_sha256' not in output and 'task_sha256' not in output


@pytest.mark.parametrize('name', list(records()[2]))
def test_missing_record_refuses_without_disclosing_private_content(name):
    spec, freeze, values = records()
    del values[name]
    with pytest.raises(KeyError):
        audit_pre_slot_failure(values.__getitem__, spec, freeze)


@pytest.mark.parametrize('name,key,value', [
    ('formal20.started.json', 'replay_allowed', True),
    ('formal20.started.json', 'replay_allowed', 0),
    ('formal20.run-result.json', 'slots_attempted', False),
    ('formal20.run-result.json', 'error_type', 'private task sentinel'),
    ('formal20.run-result.json', 'c5_6_gate_claim', 0),
    ('public-progress.json', 'counters_complete', True),
    ('public-progress.json', 'confirmed_generation_stages', 1),
    ('native-prepared.json', 'native_plans_sha256', 'b' * 64),
    ('resource-settlement.json', 'elapsed_seconds_including_load_and_idle', float('nan')),
    ('resource-settlement.json', 'start_epoch', 4000),
    ('resource-settlement.json', 'resource_boundary_sha256', 'b' * 64),
])
def test_drift_or_out_of_scope_failure_is_rejected(name, key, value):
    spec, freeze, values = records()
    values[name][key] = value
    with pytest.raises(RuntimeError) as error:
        audit_pre_slot_failure(values.__getitem__, spec, freeze)
    assert 'private task sentinel' not in str(error.value)


def test_changed_existing_case_or_hashed_model_plan_refuses():
    for mutate in ('case', 'model'):
        spec, freeze, values = records()
        if mutate == 'case':
            values['private-cases.json'][0]['task_text'] += ' CHANGED'
        else:
            values['model-plans-hashed.json']['F01-base']['max_steps'] += 1
        with pytest.raises(RuntimeError):
            audit_pre_slot_failure(values.__getitem__, spec, freeze)
