"""Synthetic CPU-only authorization/continuation checks; no live grants or models."""
import ast
import copy
import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from plugin.rhino_listener import lora_development_campaign as module
from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import NativeError, digest
from tools.build_lora_development_package import ROOT, build_campaign
from training.lora_development_authority import validate_package, verify_approval, WorkBudget
from training.lora_development_scope import DevelopmentJournal


def checks(**changes):
    return dict(commit='a' * 40, ci_run_id=1,
        ci={n: 'success' for n in ('impact', 'python', 'ui', 'release', 'validate')},
        cpu_evidence_sha256=['b' * 64], reason='Synthetic startup repair', repair_category='initial',
        failed_load=None, failure_evidence_sha256=None, prior_mac_settlement=None,
        semantic_change_review='no_research_contract_change', **changes)


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    # Production roots are never touched; even the sticky markers are temporary.
    monkeypatch.setattr(module, 'ROOTS', {k: str(tmp_path / k) for k in ('mac', 'gpu')})
    p = build_campaign()
    for endpoint in ('mac', 'gpu'):
        module.initialize(p['campaign_policy'], module.owner_record(p['campaign_policy']), endpoint)
    return p


def register(p, endpoint, evidence=None):
    source = Path(p['endpoints'][endpoint]['source_root'])
    for name in p['source_files']:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    # A permitted targeted startup-only source change, protected inference AST unchanged.
    loader = source / 'training/lora_development_loader.py'
    if hashlib.sha256(loader.read_bytes()).hexdigest() != p['source_files']['training/lora_development_loader.py']:
        loader.write_bytes(loader.read_bytes() + b'\n# Synthetic targeted import repair.\n')
    c = module.Campaign(p, endpoint); c.register(evidence or checks(), source)
    return c


def stop(p, *, exposed=False, clean=True):
    return {'status': 'gpu_stopped' if clean else 'gpu_cleanup_unknown', 'package_sha256': digest(p),
        'tasks_exposed': exposed, 'stop': {'exit_observed': clean, 'gpu_absence_verified': clean}}


def result(p, gpu):
    return {'gpu': gpu, 'host': {'status': 'host_stopped', 'exact_delegate_remove_returned': True},
        'key_removal': {'actual_absence_checked': True}, 'elapsed_seconds': 123.0}


def revised(p):
    q = copy.deepcopy(p); q['revision_id'] += 1
    for endpoint, root in module.ROOTS.items():
        base = root + '/revisions/%04d' % q['revision_id']
        q['endpoints'][endpoint].update(source_root=base + '/source', state_root=base + '/state-lora-development')
    name = 'training/lora_development_loader.py'
    q['source_files'][name] = hashlib.sha256((ROOT / name).read_bytes() + b'\n# Synthetic targeted import repair.\n').hexdigest()
    return q


def test_unchanged_research_scope_and_no_old_approval(campaign, tmp_path):
    p = campaign
    assert validate_package(p)['execution_authorized'] is False
    from tools.build_lora_development_package import build_r3
    old = build_r3()
    for key in ('model_identities', 'assets', 'native_scope', 'loader_policy', 'host_policy', 'stop_policy'):
        assert p[key] == old[key]
    assert p['limits']['gpu_residency_seconds'] is None
    assert p['development_plan']['resource_status']['cost_ceiling'] is None
    assert p['campaign_policy']['baseline_loads'] == 3 and p['campaign_policy']['max_loads'] == 5
    with pytest.raises(NativeError, match='new exact owner'):
        verify_approval(p, {}, endpoint='mac', source_root=ROOT, state_root=tmp_path, now=1)


@pytest.mark.parametrize('fault', ['model', 'feedback', 'score', 'task', 'budget', 'loads', 'slot',
    'data', 'root', 'prior_path', 'prior_result', 'reset_count', 'renewal', 'remove_source'])
def test_contract_or_protected_source_change_requires_new_approval(campaign, fault):
    p = copy.deepcopy(campaign)
    if fault == 'model': p['model_identities']['current_lora'] = 'f' * 64
    if fault in {'feedback', 'score', 'task'}:
        name = {'feedback': 'training/lora_development_controller.py',
                'score': 'training/lora_development_scope.py', 'task': 'training/lora_development_cases.py'}[fault]
        p['source_files'][name] = 'f' * 64
    if fault == 'budget': p['limits']['gpu_residency_seconds'] = 7200
    if fault == 'loads': p['limits']['max_load_attempts'] = 2
    if fault == 'slot': p['limits']['slot_seconds'] = 151
    if fault == 'data': p['evidence_policy']['old_private_materials'] = True
    if fault == 'root': p['endpoints']['gpu']['state_root'] += '-reset'
    if fault == 'prior_path': p['campaign_policy']['baseline_predecessors'][0]['prior_endpoints']['mac']['state_root'] += '-reset'
    if fault == 'prior_result': p['campaign_policy']['baseline_predecessors'][0]['prior_review']['load_attempts_consumed'] = 0
    if fault == 'reset_count': p['campaign_policy']['baseline_loads'] = 0
    if fault == 'renewal': p['resource_policy']['new_paid_service_or_renewal'] = True
    if fault == 'remove_source': p['source_files'].pop('data_pipeline/training_views.py')
    with pytest.raises((NativeError, ValueError)): validate_package(p)


def test_exact_revision_needs_ci_cpu_and_inference_preservation(campaign):
    p = campaign
    source = Path(p['endpoints']['gpu']['source_root'])
    c = register(p, 'gpu')
    c.revision()
    for fault in ('ci', 'cpu', 'semantic'):
        row = checks()
        if fault == 'ci': row['ci']['python'] = 'failure'
        if fault == 'cpu': row['cpu_evidence_sha256'] = []
        if fault == 'semantic': row['semantic_change_review'] = 'changed_score'
        with pytest.raises(NativeError): c.register(row, source)
    # Loader is startup-mutable but generation/weight-loading contract is protected.
    q = revised(p); loader = 'training/lora_development_loader.py'
    target = Path(q['endpoints']['gpu']['source_root'])
    shutil.copytree(source, target)
    raw = (target / loader).read_text().replace('def load(', 'def changed_load(')
    (target / loader).write_text(raw); q['source_files'][loader] = hashlib.sha256(raw.encode()).hexdigest()
    with pytest.raises(NativeError, match='fragments required'):
        module.Campaign(q, 'gpu').register(checks(), target)


def test_global_four_five_then_stop_and_preserve_settlements(campaign):
    p = campaign; mac = register(p, 'mac'); gpu = register(p, 'gpu')
    mac.begin_run(); assert gpu.claim_load() == 4
    receipt = stop(p); gpu.settle_load(4, receipt); mac.settle_run(result(p, receipt))
    q = revised(p)
    evidence = checks(); evidence.update(repair_category='dependency', failed_load=4,
        failure_evidence_sha256=digest(receipt), prior_mac_settlement=read_json(mac.root, 'run-0001.settlement.json'))
    mac2 = register(q, 'mac', evidence); gpu2 = register(q, 'gpu', evidence)
    mac2.begin_run(); assert gpu2.claim_load() == 5
    receipt2 = stop(q); gpu2.settle_load(5, receipt2); mac2.settle_run(result(q, receipt2))
    with pytest.raises(NativeError, match='maximum five'): gpu2.claim_load()
    assert read_json(gpu.root, 'load-4.settlement.json') == receipt
    assert len(mac2.retired()) == 3  # Immutable R1/R2 and previous campaign revision.


@pytest.mark.parametrize('fault', ['no_repair', 'bad_failure_hash', 'cleanup_unknown', 'exposed', 'mac_unknown'])
def test_no_blind_or_unsettled_retry(campaign, fault):
    p = campaign; gpu = register(p, 'gpu'); mac = register(p, 'mac'); mac.begin_run()
    assert gpu.claim_load() == 4
    receipt = stop(p, exposed=fault == 'exposed', clean=fault != 'cleanup_unknown')
    gpu.settle_load(4, receipt); mac.settle_run(result(p, receipt))
    q = revised(p)
    if fault == 'no_repair': q['source_files'] = dict(p['source_files'])
    evidence = checks(); evidence.update(repair_category='dependency', failed_load=4,
        failure_evidence_sha256='0' * 64 if fault == 'bad_failure_hash' else digest(receipt),
        prior_mac_settlement=read_json(mac.root, 'run-0001.settlement.json'))
    if fault == 'mac_unknown': evidence['prior_mac_settlement']['cleanup_verified'] = False
    gpu2 = register(q, 'gpu', evidence)
    with pytest.raises(NativeError): gpu2.claim_load()
    assert not (gpu.root / 'load-5.claim.json').exists()


def test_global_slot_claim_and_concurrent_or_reopened_run_cannot_replay(campaign, tmp_path):
    p = campaign; mac = register(p, 'mac'); mac.begin_run()
    journal_root = tmp_path / 'journal'; journal_root.mkdir(mode=0o700)
    journal = DevelopmentJournal(journal_root, p['development_plan'], digest(p), campaign=mac)
    journal.start_slot('lora-dev-00')
    with pytest.raises(FileExistsError): journal.start_slot('lora-dev-00')
    with pytest.raises(NativeError, match='consumed slots'): mac.begin_run()
    assert len(list(mac.root.glob('slot-*.claim.json'))) == 1


def test_deleted_or_renamed_ledger_is_never_reinitialized(campaign):
    p = campaign; root = Path(module.ROOTS['gpu'])
    shutil.rmtree(root)
    with pytest.raises(FileExistsError):
        module.initialize(p['campaign_policy'], module.owner_record(p['campaign_policy']), 'gpu')
    with pytest.raises((NativeError, FileNotFoundError)): module.Campaign(p, 'gpu')


def test_lease_only_clock_allows_over_two_hours_but_preserves_cleanup():
    limits = build_campaign()['limits']; now = [100.0]
    b = WorkBudget(limits, 30000, first_wall=100, first_mono=100,
                   wall=lambda: now[0], mono=lambda: now[0])
    now[0] = 10000; b.work(remaining_slots=32, loading=True)
    now[0] = 29101
    with pytest.raises(NativeError): b.work()
    b.cleanup()
    now[0] = 30000
    with pytest.raises(NativeError): b.cleanup()


def test_host_campaign_source_parses_on_embedded_python39():
    for name in ('plugin/rhino_listener/lora_development_campaign.py',
                 'plugin/rhino_listener/lora_development_admission.py', 'tools/run_lora_development_rhino.py'):
        ast.parse((ROOT / name).read_text(), feature_version=(3, 9))


def test_supervisor_consumes_global_intent_before_child_and_accounts_unknown_cost(campaign, monkeypatch):
    from training import lora_development_gpu_entry as gpu_entry
    p = campaign; c = register(p, 'gpu')
    state = Path(p['endpoints']['gpu']['state_root']); state.mkdir(mode=0o700)
    sent, children = [], []
    monkeypatch.setattr(gpu_entry, 'JsonPipe', lambda *a: SimpleNamespace(send=lambda x, t: sent.append(x)))
    monkeypatch.setattr(gpu_entry, 'sys', SimpleNamespace(stdin=SimpleNamespace(fileno=lambda: 1),
                                                       stdout=SimpleNamespace(fileno=lambda: 2)))
    monkeypatch.setattr(gpu_entry, 'gpu_absent', lambda pid: True)
    # Fixed synthetic clocks: tests do not depend on the real lease date.
    monkeypatch.setattr(gpu_entry.time, 'time', lambda: p['lease_end_epoch'] - 10000)
    monkeypatch.setattr(gpu_entry, 'WorkBudget', lambda *args, **kwargs:
        WorkBudget(*args, **kwargs, wall=lambda: p['lease_end_epoch'] - 10000))
    class Child:
        def __init__(self, *args, **kwargs):
            assert read_json(c.root, 'load-4.claim.json')['package_sha256'] == digest(p)
            children.append(self); self.pipe = self
        def send(self, *args): pass
        def receive(self, *args): raise EOFError('synthetic startup import failure')
        def close(self): return {'pid': 123, 'exit_observed': True, 'signals': []}
    monkeypatch.setattr(gpu_entry, 'OwnedChild', Child)
    settled = gpu_entry.supervise(Path(p['endpoints']['gpu']['source_root']), p, state)
    assert len(children) == 1 and settled['global_load_number'] == 4
    assert settled['status'] == 'gpu_stopped' and settled['tasks_exposed'] is False
    assert settled['additional_cost'] is None and settled['paid_resource_actions'] == 0
    assert read_json(c.root, 'load-4.settlement.json') == settled


def test_lease_guard_uses_monotonic_elapsed_when_wall_clock_stalls():
    limits = build_campaign()['limits']; mono = [0]
    b = WorkBudget(limits, 20000, first_wall=100, first_mono=0,
                   wall=lambda: 100, mono=lambda: mono[0])
    mono[0] = 19901
    with pytest.raises(NativeError): b.cleanup()
