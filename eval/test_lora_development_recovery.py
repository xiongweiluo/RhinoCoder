"""Real public components and deployed entry on CPU; no field grants/effects."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from plugin.rhino_listener.c5_research_channel import read_json, publish_json
from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener.lora_development_runtime import configuration, active_schedule, recovery_context
from tools.build_lora_development_package import ROOT, build_recovery
from tools.check_lora_development_source import PROBE
from training.lora_development_scope import DevelopmentJournal
from eval.test_lora_development_controller import setup, RUNTIME
from eval.test_lora_development_campaign import checks, register


@pytest.fixture
def stopped_campaign(tmp_path, monkeypatch):
    """Synthetic predecessor bytes only, in temporary roots, never field state."""
    from plugin.rhino_listener import lora_development_campaign as module
    original = json.loads((ROOT / 'eval/lora-development/development-package-campaign-v1-20261026.json').read_text())
    roots = {k: str(tmp_path / k) for k in ('mac', 'gpu')}
    monkeypatch.setattr(module, 'ROOTS', roots)
    original['campaign_policy']['roots'] = roots
    monkeypatch.setattr(module, 'PRIOR_POLICY_SHA', digest(original['campaign_policy']))
    # Build first from the untouched public proposal, then relocate the inert
    # package. Patching constants is confined to this synthetic lineage test.
    monkeypatch.setattr(module, 'PRIOR_POLICY_SHA', '0b051d6095ad3b6e750e72b76070c3cd36c19a9a8b499258f9e2b41526f75de3')
    package = build_recovery()
    policy = package['campaign_policy']; policy['roots'] = roots
    policy['resume']['prior_policy_sha256'] = digest(original['campaign_policy'])
    monkeypatch.setattr(module, 'PRIOR_POLICY_SHA', digest(original['campaign_policy']))
    for endpoint in ('mac', 'gpu'):
        module.initialize(original['campaign_policy'], module.owner_record(original['campaign_policy']), endpoint)
    mac, gpu = Path(roots['mac']), Path(roots['gpu'])
    claim = {'global_load_number': 4, 'revision_id': 1, 'package_sha256': module.PRIOR_PACKAGE_SHA}
    stop = {'status': 'gpu_stopped', 'package_sha256': module.PRIOR_PACKAGE_SHA, 'tasks_exposed': False,
            'stop': {'exit_observed': True, 'gpu_absence_verified': True}}
    publish_json(gpu, 'load-4.claim.json', claim); publish_json(gpu, 'load-4.settlement.json', stop)
    prior = mac / 'revisions/0001/state-lora-development'
    for name in ('controller', 'fixtures', 'gpu-campaign-review'): (prior / name).mkdir(parents=True, mode=0o700)
    publish_json(prior / 'gpu-campaign-review', 'load-4.claim.json', claim)
    publish_json(prior / 'gpu-campaign-review', 'load-4.settlement.json', stop)
    publish_json(prior / 'controller', 'failure.json', {'synthetic': True, 'model_requests': 0})
    review = policy['resume']['review']
    review['evidence_file_sha256'] = {p.relative_to(prior).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in prior.rglob('*') if p.is_file()}
    policy['resume']['review_sha256'] = digest(review)
    monkeypatch.setattr(module, 'RESUME_REVIEW_SHA', digest(review))
    publish_json(mac, 'run-0001.claim.json', {'revision_id': 1, 'package_sha256': module.PRIOR_PACKAGE_SHA})
    publish_json(mac, 'slot-lora-dev-00.claim.json', {'slot_id': 'lora-dev-00', 'package_sha256': module.PRIOR_PACKAGE_SHA, 'revision_id': 1})
    publish_json(mac, 'run-0001.settlement.json', {'revision_id': 1, 'package_sha256': module.PRIOR_PACKAGE_SHA,
        'cleanup_verified': True, 'slot_claims': 1, 'gpu_settlement_sha256': digest(stop)})
    evidence = checks(); evidence.update(repair_category='lifecycle_refactor', failed_load=4,
        failure_evidence_sha256=digest(stop), prior_mac_settlement=read_json(mac, 'run-0001.settlement.json'),
        semantic_change_review='approved_recovery_no_model_task_feedback_score_change')
    return module, package, evidence


def test_transition_requires_new_scope_and_consumes_only_fifth_load(stopped_campaign):
    module, package, evidence = stopped_campaign
    with pytest.raises(FileNotFoundError): module.Campaign(package, 'mac')
    mac_root = Path(module.ROOTS['mac']); old = (mac_root / 'slot-lora-dev-00.claim.json').read_bytes()
    for endpoint in ('mac', 'gpu'):
        module.adopt(package, module.owner_record(package['campaign_policy']), endpoint)
        module.adopt(package, module.owner_record(package['campaign_policy']), endpoint)  # exact idempotence
    mac = register(package, 'mac', evidence); gpu = register(package, 'gpu', evidence)
    mac.begin_run(); assert gpu.claim_load() == 5
    with pytest.raises(NativeError, match='maximum five'): gpu.claim_load()
    with pytest.raises(FileNotFoundError): mac.begin_run()  # active run has no settlement
    assert (mac_root / 'slot-lora-dev-00.claim.json').read_bytes() == old
    assert not (gpu.root / 'load-6.claim.json').exists()


@pytest.mark.parametrize('fault', ['missing_claim', 'changed_evidence', 'fifth_used', 'unknown_cleanup'])
def test_transition_never_hides_changed_or_unsettled_history(stopped_campaign, fault):
    module, package, evidence = stopped_campaign
    mac, gpu = Path(module.ROOTS['mac']), Path(module.ROOTS['gpu'])
    endpoint = 'mac'
    if fault == 'missing_claim': (mac / 'slot-lora-dev-00.claim.json').unlink()
    if fault == 'changed_evidence': (mac / 'revisions/0001/state-lora-development/controller/failure.json').write_text('{}')
    if fault == 'fifth_used':
        publish_json(gpu, 'load-5.claim.json', {'synthetic': True}); endpoint = 'gpu'
    if fault == 'unknown_cleanup':
        path = mac / 'run-0001.settlement.json'; row = json.loads(path.read_text()); row['cleanup_verified'] = False
        path.write_text(json.dumps(row)); path.chmod(0o600)
    with pytest.raises(NativeError): module.adopt(package, module.owner_record(package['campaign_policy']), endpoint)


def resumed(tmp_path, fault=None):
    controller, host, sessions, calls = setup(tmp_path, fault)
    package = build_recovery()
    directory = tmp_path / 'continued-journal'; directory.mkdir(mode=0o700)
    controller.journal = DevelopmentJournal(directory, package['development_plan'], RUNTIME,
                                           recovery=recovery_context(package))
    host.schedule = active_schedule(package)
    return controller, host, sessions, calls


def test_original_failure_preserved_and_only_31_pending_slots_run(tmp_path):
    controller, host, sessions, calls = resumed(tmp_path)
    before = copy.deepcopy(controller.journal.history)
    rows = controller.run()
    assert len(rows) == len(sessions) == 31 and len(calls) == 46
    assert rows[0]['identity']['slot_id'] == 'lora-dev-01'
    assert controller.journal.history == before
    assert before['lora-dev-00']['may_advance'] is False
    decision = read_json(controller.journal.root, 'selection.json')
    assert decision['selected_system'] == 'original' and decision['selection_complete'] is False
    assert decision['candidate_promoted'] is False and decision['success_gains'] is None
    assert all(s.closed for s in sessions) and host.finish()['owned_fixture_remaining'] is False
    with pytest.raises(NativeError, match='cannot be replayed'): controller.journal.start_slot('lora-dev-00')


def test_slot_preflight_failure_does_not_consume_another_task(tmp_path):
    controller, host, sessions, calls = resumed(tmp_path)
    def reject(): raise NativeError('synthetic bad environment')
    controller.guard = reject
    with pytest.raises(NativeError, match='bad environment'): controller.run()
    assert not list(controller.journal.root.glob('*.claim.json'))
    assert not sessions and not calls


def test_known_fixture_validation_failure_is_recorded_and_next_slot_runs(tmp_path, monkeypatch):
    controller, host, sessions, calls = resumed(tmp_path)
    import training.lora_development_controller as module
    original = module.validate_fixture_readback
    first = [True]
    def validate(case, native):
        if first[0]:
            first[0] = False
            raise NativeError('synthetic fixture mismatch before model request')
        return original(case, native)
    monkeypatch.setattr(module, 'validate_fixture_readback', validate)
    rows = controller.run()
    assert len(rows) == 31 and rows[0]['outcome'] == 'engineering_failure'
    assert rows[0]['may_advance'] is True and rows[1]['outcome'] == 'success'
    assert rows[0]['execution'] == {'model_request': 'not_sent', 'native_effect': 'none',
        'fixture_cleanup': 'verified', 'evidence_integrity': 'verified', 'resume_eligible': True}
    evidence = read_json(controller.state, 'lora-dev-01.evidence.json')
    assert evidence['score'] is None and evidence['failures'][0]['stage'] == 'fixture_validation'
    assert 'synthetic fixture mismatch' in evidence['failures'][0]['message']


@pytest.mark.parametrize('fault', ['model_unknown', 'native_unknown', 'close_unknown', 'ledger_forgery'])
def test_unknown_channels_stop_with_separate_failure_and_cleanup(tmp_path, fault):
    controller, host, sessions, calls = resumed(tmp_path, fault)
    rows = controller.run()
    assert len(rows) == 1 and rows[0]['outcome'] == 'engineering_failure' and not rows[0]['may_advance']
    evidence = read_json(controller.state, 'lora-dev-01.evidence.json')
    assert evidence['failures'][0]['message'] and evidence['failures'][0]['traceback']
    execution = rows[0]['execution']
    if fault == 'model_unknown':
        assert execution['model_request'] == 'response_unknown'
        assert execution['native_effect'] == 'none' and execution['fixture_cleanup'] == 'verified'
    if fault == 'native_unknown': assert execution['native_effect'] == 'unknown'
    if fault == 'close_unknown': assert execution['fixture_cleanup'] == 'unknown'
    if fault == 'ledger_forgery': assert execution['evidence_integrity'] == 'not_verified'


def test_primary_and_cleanup_errors_are_both_retained(tmp_path):
    controller, host, sessions, calls = resumed(tmp_path, 'close_unknown')
    def fail(_): raise TimeoutError('synthetic primary model failure')
    controller.model = fail
    controller.run()
    evidence = read_json(controller.state, 'lora-dev-01.evidence.json')
    assert evidence['failures'][0]['stage'] == 'model_request'
    assert any(r['stage'] == 'fixture_close' for r in evidence['failures'])
    assert evidence['execution']['fixture_cleanup'] == 'unknown'


def test_shared_config_rejects_drift_and_retains_all_task_model_score_contracts():
    package = build_recovery()
    prior = json.loads((ROOT / 'eval/lora-development/development-package-campaign-v1-20261026.json').read_text())
    for key in ('development_plan', 'native_scope', 'model_identities', 'assets', 'loader_policy', 'limits'):
        assert package[key] == prior[key]
    assert len(active_schedule(package)) == 31
    executed = json.loads((ROOT / 'eval/lora-development/development-package-recovery-20261026.json').read_text())
    contracts = ('training/c5_formal20_scorer.py', 'training/lora_development_cases.py',
                 'training/lora_development_wire.py', 'training/lora_development_read_permission.py')
    for name in contracts:
        assert executed['source_files'][name] == prior['source_files'][name]
    # A later common-chain refactor shares raw parsing. Executed package bytes
    # remain immutable; current prompt/parser parity has separate wire tests.
    for name in set(contracts) - {'training/lora_development_wire.py'}:
        assert package['source_files'][name] == prior['source_files'][name]
    package['runtime_policy']['operations']['gpu_ready_seconds'] += 1
    with pytest.raises(NativeError, match='contract differs'): configuration(package)


def test_actual_shipped_gpu_entry_cpu_check_has_no_authority_or_backends(tmp_path):
    package = build_recovery()
    for name, sha in package['source_files'].items():
        target = tmp_path / name; target.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / name).read_bytes(); assert hashlib.sha256(raw).hexdigest() == sha
        target.write_bytes(raw)
    (tmp_path / 'lora-development-package.json').write_text(json.dumps(package))
    # Reuse the isolated read-only import sandbox; then call the *real* entry's
    # --check branch. No test-only config, authorization or runtime constructor.
    probe = PROBE + "\nsys.argv = ['run_lora_development_gpu.py', '--check']\nimport tools.run_lora_development_gpu as entry\nentry.main()\n"
    result = subprocess.run([sys.executable, '-I', '-S', '-B', '-X',
        'pycache_prefix=' + str(tmp_path / 'never-created-cache'), '-c', probe, str(tmp_path), ''],
        cwd=tmp_path, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report['actual_entry_preparation_used'] and report['model_calls'] == report['rhino_calls'] == 0
    assert report['pending_slots'] == ['lora-dev-%02d' % n for n in range(1, 32)]
    assert not list(tmp_path.rglob('owner-approval.json')) and not list(tmp_path.rglob('*.claim.json'))
