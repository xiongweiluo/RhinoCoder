"""Inert admission/budget tests; approvals below are synthetic temporary fixtures."""
import copy
import json

import pytest

from plugin.rhino_listener.c5_research_native import NativeError, digest
from training.lora_development_authority import validate_package, verify_approval, WorkBudget, APPROVAL_BASIS
from tools.build_lora_development_package import build, ROOT


def test_prepared_package_has_no_execution_authority(tmp_path):
    package = build()
    frozen = json.loads((ROOT / 'eval/lora-development/development-package-r2-20261026.json').read_text())
    assert digest(frozen) == 'aa280fb64ba123e4d7f999f5b5cd7db4302c2c3bb1337f2c459da938d408df9e'
    assert validate_package(frozen)['execution_authorized'] is False
    assert {k: v for k, v in package.items() if k != 'source_files'} == {
        k: v for k, v in frozen.items() if k != 'source_files'}
    assert digest(package) != digest(frozen)  # CPU repair never rewrites or reuses R2 approval.
    r2_approval = json.loads((ROOT / 'eval/lora-development/owner-authorization-r2-20261026.json').read_text())['owner_approval']
    with pytest.raises(NativeError):
        verify_approval(package, r2_approval, endpoint='mac', source_root=ROOT, state_root=tmp_path, now=1)
    assert validate_package(package)['execution_authorized'] is False
    assert package['development_plan']['required_before_execution']['owner_development_execution_approval'] is None
    with pytest.raises(NativeError):
        verify_approval(package, {}, endpoint='mac', source_root=ROOT, state_root=tmp_path, now=1)
    original = json.loads((ROOT / 'eval/lora-development/development-package-20261026.json').read_text())
    assert digest(original) == 'c1cfb2f13d0c56fb58e65481cc413189016ed8589428a6af869e27f76febf249'
    old = json.loads((ROOT / 'eval/lora-development/owner-authorization-20261026.json').read_text())['owner_approval']
    with pytest.raises(NativeError):
        verify_approval(package, old, endpoint='mac', source_root=ROOT, state_root=tmp_path, now=1)


@pytest.mark.parametrize('fault', ['additional_recovery', 'prior_exposure', 'prior_charge', 'same_state', 'unbound_target'])
def test_continuation_cannot_erase_spent_budget_or_broaden_model_paths(fault):
    package = build()
    if fault == 'additional_recovery':
        package['limits']['max_load_attempts'] = package['development_plan']['limits']['max_load_attempts'] = 2
        package['limits']['max_infrastructure_recoveries'] = 1
    if fault == 'prior_exposure':
        package['continuation']['prior_review']['slot_claims_verified'] = 1
        package['continuation']['prior_review_sha256'] = digest(package['continuation']['prior_review'])
    if fault == 'prior_charge': package['continuation']['charged_prior_seconds'] = 0
    if fault == 'same_state': package['endpoints']['mac']['state_root'] = package['continuation']['prior_endpoints']['mac']['state_root']
    if fault == 'unbound_target': next(iter(package['model_path_bindings'].values()))['resolved_path'] = '/unrelated/asset'
    with pytest.raises((NativeError, ValueError)): validate_package(package)


@pytest.mark.parametrize('fault', ['bool_version', 'weights', 'input_scope', 'stop_target', 'cost', 'historical_grant'])
def test_scope_expansion_or_old_grant_refused(fault):
    package = build()
    if fault == 'bool_version': package['schema_version'] = True
    if fault == 'weights': package['model_identities']['current_lora'] = 'f' * 64
    if fault == 'input_scope': package['native_scope']['native']['lora-dev-00']['max_writes'] = 1
    if fault == 'stop_target': package['stop_policy']['target'] = 'all_python_processes'
    if fault == 'cost': package['resource_policy']['additional_cost_ceiling'] = 1
    if fault == 'historical_grant': package['study_id'] = 'c5-rhino-paired-20-reuse-v1'
    with pytest.raises(NativeError): validate_package(package)


def test_bound_paths_and_exact_owner_approval_are_both_required(tmp_path):
    package = build()
    package['endpoints']['mac']['source_root'] = str(ROOT)
    package['endpoints']['mac']['state_root'] = str(tmp_path / 'state-lora-development')
    approval = {'study_id': package['study_id'], 'actor': 'repository_owner', 'approved': True,
        'package_sha256': digest(package), 'approval_basis': APPROVAL_BASIS,
        'scope': 'one_bounded_public_development_no_training_no_final_test'}
    assert verify_approval(package, approval, endpoint='mac', source_root=ROOT,
        state_root=package['endpoints']['mac']['state_root'], now=1) == digest(package)
    with pytest.raises(NativeError): verify_approval(package, approval, endpoint='mac', source_root=ROOT, state_root=tmp_path, now=1)
    with pytest.raises(NativeError): verify_approval(package, approval, endpoint='mac', source_root=ROOT,
        state_root=package['endpoints']['mac']['state_root'],
        now=package['lease_end_epoch'] - package['limits']['gpu_residency_seconds'] + 1)
    package['source_files']['training/lora_development_scope.py'] = 'f' * 64
    approval['package_sha256'] = digest(package)
    with pytest.raises(NativeError): verify_approval(package, approval, endpoint='mac', source_root=ROOT,
        state_root=package['endpoints']['mac']['state_root'], now=1)


def test_budget_preserves_whole_window_and_cleanup_and_refuses_clock_reversal():
    limits = build()['limits']; now = [100]
    budget = WorkBudget(limits, 10000, first_wall=100, first_mono=100, wall=lambda: now[0], mono=lambda: now[0])
    budget.work(remaining_slots=32, loading=True)
    now[0] = 2501
    with pytest.raises(NativeError): budget.work(remaining_slots=32)
    budget.cleanup()
    now[0] = 2500
    with pytest.raises(NativeError): budget.remaining()
