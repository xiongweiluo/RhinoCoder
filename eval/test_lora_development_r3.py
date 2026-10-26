"""Two retired batches and one proposed load, using only CPU synthetic state."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener import lora_development_admission as admission
from tools.build_lora_development_package import ROOT, build_r3
from training.lora_development_authority import validate_package, verify_approval, WorkBudget


def test_r3_scope_and_old_approvals_cannot_carry_forward(tmp_path):
    package = build_r3()
    assert validate_package(package)['execution_authorized'] is False
    r2 = json.loads((ROOT / 'eval/lora-development/development-package-r2-20261026.json').read_text())
    assert package['native_scope'] == r2['native_scope']
    for key in ('model_identities', 'assets', 'loader_policy', 'stop_policy', 'host_policy', 'model_path_bindings'):
        assert package[key] == r2[key]
    for suffix in ('', '-r2'):
        approval = json.loads((ROOT / ('eval/lora-development/owner-authorization' + suffix + '-20261026.json')).read_text())['owner_approval']
        with pytest.raises(NativeError, match='new exact owner'):
            verify_approval(package, approval, endpoint='mac', source_root=ROOT, state_root=tmp_path, now=1)


@pytest.mark.parametrize('fault', ['missing_batch', 'duplicate_batch', 'review_changed', 'review_rehashed',
    'old_state', 'old_source', 'substituted_prior', 'erase_load', 'erase_time', 'fifth_load',
    'recovery', 'extra_seconds', 'longer_slot'])
def test_r3_cannot_erase_history_expand_bounds_or_reuse_state(fault):
    p = build_r3(); c = p['continuation']; rows = c['predecessors']
    if fault == 'missing_batch': rows.pop()
    if fault == 'duplicate_batch': rows[1] = copy.deepcopy(rows[0])
    if fault in {'review_changed', 'review_rehashed'}:
        rows[1]['prior_review']['slot_claims_verified'] = 1
        if fault == 'review_rehashed': rows[1]['prior_review_sha256'] = digest(rows[1]['prior_review'])
    if fault == 'old_state': p['endpoints']['mac']['state_root'] = rows[1]['prior_endpoints']['mac']['state_root']
    if fault == 'old_source': p['endpoints']['gpu']['source_root'] = rows[0]['prior_endpoints']['gpu']['source_root']
    if fault == 'substituted_prior': rows[1]['prior_endpoints']['mac']['state_root'] += '-other'
    if fault == 'erase_load': c['prior_load_attempts'] = 0
    if fault == 'erase_time': c['charged_prior_seconds'] = 0
    if fault == 'fifth_load': c['cumulative_load_attempts_limit'] = 5
    if fault == 'recovery': p['limits']['max_infrastructure_recoveries'] = 1
    if fault == 'extra_seconds': p['limits']['gpu_residency_seconds'] += 1
    if fault == 'longer_slot': p['limits']['slot_seconds'] += 1
    with pytest.raises((NativeError, ValueError)): validate_package(p)


@pytest.mark.parametrize('fault', [None, 'r1_live', 'r2_live', 'r1_undetached', 'r2_undetached',
    'r1_key', 'r2_key', 'r2_current', 'r2_wrong_source', 'foreign_session'])
def test_two_retired_sessions_are_checked_individually_without_mutation(monkeypatch, fault):
    p = build_r3(); modules = {}; settlements = {}; keys = set()
    for i, row in enumerate(p['continuation']['predecessors'], 1):
        endpoint = row['prior_endpoints']['mac']; state = Path(endpoint['state_root'])
        session = SimpleNamespace(runtime=row['prior_package_sha256'], state=state / 'host',
            stopped=fault != 'r%d_live' % i, host=SimpleNamespace(current='active' if fault == 'r2_current' and i == 2 else None))
        modules['rhino_lora_r%d' % i] = SimpleNamespace(__path__=[endpoint['source_root']], _SESSION=session)
        settlements[(state / 'host', 'host-settlement.json')] = {
            'runtime_sha256': row['prior_package_sha256'], 'status': 'host_stopped',
            'exact_delegate_remove_returned': fault != 'r%d_undetached' % i}
        if fault == 'r%d_key' % i: keys.add(state / 'host-secret.json')
    if fault == 'r2_wrong_source': modules['rhino_lora_r2'].__path__ = ['/different/source']
    if fault == 'foreign_session':
        modules['rhino_research_other'] = SimpleNamespace(_SESSION=SimpleNamespace(runtime='unrelated'))
    before = repr(modules)
    monkeypatch.setattr(admission, 'read_json', lambda path, name: settlements[(path, name)])
    monkeypatch.setattr(admission.os.path, 'lexists', lambda path: path in keys)
    if fault is None: admission.sessions_available(modules, p)
    else:
        with pytest.raises(NativeError): admission.sessions_available(modules, p)
    assert repr(modules) == before


def test_full_window_and_cleanup_reserve_include_prior_charge():
    p = build_r3(); now = [0.0]
    assert p['continuation']['charged_prior_seconds'] + p['limits']['gpu_residency_seconds'] == 7200
    budget = WorkBudget(p['limits'], 10000, first_wall=0, first_mono=0,
                        wall=lambda: now[0], mono=lambda: now[0])
    now[0] = 671
    budget.work(remaining_slots=32, loading=True)
    now[0] += .01
    with pytest.raises(NativeError): budget.work(remaining_slots=32, loading=True)
    budget.cleanup()
