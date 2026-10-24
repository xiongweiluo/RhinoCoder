"""Public metadata controls only: no private data, models, host or run state."""
import copy
import json
import subprocess
import sys

import pytest

from tools.check_c5_formal20_reuse_draft import ROOT, FILES, check, check_values, parse_public


def values():
    return [json.loads((ROOT / name).read_bytes()) for name in FILES]


def test_draft_cannot_be_execution_or_private_audit_authority():
    r = check()
    assert r['status'] == 'draft_boundaries_consistent_not_execution_authority'
    assert r['execution_ready'] is False
    assert r['formal_spec_sha256'] is r['formal_runtime_sha256'] is None
    assert r['model_or_rhino_calls'] == r['private_evidence_reads'] == 0


@pytest.mark.parametrize('path,value', [
    (('schema_version',), True),
    (('candidate_study_id',), 'c5-rhino-paired-20-v1'),
    (('source_baseline_commit',), '0' * 40),
    (('owner_data_reuse_decision', 'received'), False),
    (('owner_data_reuse_decision', 'prior_actual_generation_total'), 0),
    (('owner_data_reuse_decision', 'development_exposure_independently_verified'), True),
    (('dataset', 'family_count'), True),
    (('dataset', 'route_slots'), 39),
    (('dataset', 'slot_seed'), 20261004),
    (('dataset', 'public_commitment_sha256'), '0' * 64),
    (('dataset', 'family_merkle_root_sha256'), '0' * 64),
    (('dataset', 'new_independent_holdout_claimed'), True),
    (('dataset', 'original80_reuse_allowed'), True),
    (('dataset', 'task_replacement_allowed'), True),
    (('comparison', 'checkpoint'), 'checkpoint-66'),
    (('comparison', 'contract_id'), 'r-v5'),
    (('comparison', 'training_allowed'), True),
    (('comparison', 'parse_repair_allowed'), True),
    (('thresholds', 'lora_success_min'), 13),
    (('thresholds', 'duplicate_writes_max'), False),
    (('history', 'parent_claim_reset_allowed'), True),
    (('history', 'parent_entry_replay_allowed'), True),
    (('history', 'parent_result_rewrite_allowed'), True),
    (('resources', 'lease_expiry_epoch'), 1791576000),
    (('resources', 'prior_cumulative_upper_bound_seconds'), 9607.228115136008),
    (('resources', 'approved_remaining_gpu_seconds'), 18000),
    (('resources', 'export_reserve_seconds_min'), 0),
    (('resources', 'proposed_limits_seconds', 'development'), 3601),
    (('resources', 'rental_or_payment_authorized'), True),
    (('resources', 'old_lease_or_prior_ledger_reused_as_current_authority'), True),
    (('freeze', 'spec_sha256'), '0' * 64),
    (('freeze', 'runtime_sha256'), '0' * 64),
    (('freeze', 'live_development_exact_approval_received'), True),
    (('freeze', 'live_development_raw_audit_passed'), True),
    (('freeze', 'formal_exact_approval_received'), True),
    (('authority', 'execution_ready'), True),
    (('authority', 'private_data_or_decryption_access_authorized'), True),
    (('authority', 'model_or_rhino_calls_authorized'), True),
    (('authority', 'new_run_or_claim_creation_authorized'), True),
    (('authority', 'default_route_change_authorized'), True),
    (('authority', 'pr_merge_authorized'), True),
    (('authority', 'automatic_retry_allowed'), True),
])
def test_unfrozen_or_invented_facts_refused(path, value):
    artifacts = copy.deepcopy(values())
    target = artifacts[0]
    for k in path[:-1]:
        target = target[k]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        check_values(*artifacts)


@pytest.mark.parametrize('index', [1, 2, 3, 4])
def test_parent_artifact_rewrites_refused(index):
    artifacts = values()
    artifacts[index]['forged_future_authority'] = True
    with pytest.raises(ValueError):
        check_values(*artifacts)


def test_additional_draft_fields_cannot_carry_hidden_authority():
    artifacts = values()
    artifacts[0]['authority']['run_now'] = True
    with pytest.raises(ValueError):
        check_values(*artifacts)


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_duplicate_or_nonfinite_public_json_refused(raw):
    with pytest.raises(ValueError):
        parse_public(raw)


def test_cli_refuses_input_paths_without_echo_or_read():
    p = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check_c5_formal20_reuse_draft.py'),
        'synthetic-path-never-opened'], capture_output=True, text=True, check=False)
    assert p.returncode == 2 and not p.stdout
    assert p.stderr == 'public draft checker accepts no input paths\n'


def test_real_cpu_cli_has_no_execution_authority():
    p = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check_c5_formal20_reuse_draft.py')],
        capture_output=True, text=True, check=False)
    assert p.returncode == 0 and not p.stderr
    assert json.loads(p.stdout)['execution_ready'] is False
