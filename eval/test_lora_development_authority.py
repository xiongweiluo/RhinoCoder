"""Inert admission/budget tests; approvals below are synthetic temporary fixtures."""
import copy
import json

import pytest

from plugin.rhino_listener.c5_research_native import NativeError, digest
from training.lora_development_authority import validate_package, verify_approval, WorkBudget, APPROVAL_BASIS
from tools.build_lora_development_package import build, ROOT


def test_prepared_package_has_no_execution_authority(tmp_path):
    package = build()
    assert package == json.loads((ROOT / 'eval/lora-development/development-package-20261026.json').read_text())
    assert validate_package(package)['execution_authorized'] is False
    assert package['development_plan']['required_before_execution']['owner_development_execution_approval'] is None
    with pytest.raises(NativeError):
        verify_approval(package, {}, endpoint='mac', source_root=ROOT, state_root=tmp_path, now=1)


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
        state_root=package['endpoints']['mac']['state_root'], now=package['lease_end_epoch'] - 7199)
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
