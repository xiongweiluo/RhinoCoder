"""Public synthetic integration: no model, Rhino, corpus, or former run reads."""
import copy
import json

import pytest

from eval.test_lora_development_controller import MemoryFixture
from eval.test_lora_development_wire import SECRET, RUNTIME, IDENTITY, TextTokenizer, fixed_response
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_gate import ResearchGate
from plugin.rhino_listener.c5_research_native import CORE, NativeError, digest
from plugin.rhino_listener.lora_development_host import DevelopmentHost
from training.c5_formal20_plan import _schemas
from training.c5_rhino_adapter import step_input
from training.lora_common_chain import CommonChain
from training.lora_common_probes import public_probes
from training.lora_comparison_plan import proposal, compile_cases, capacity
from training.lora_development_controller import DevelopmentController
from training.lora_development_scope import DevelopmentJournal


class WriteFixture(MemoryFixture):
    def __init__(self, plan, runtime, secret, directory, fault):
        super().__init__(plan, runtime, secret, directory, fault)
        self.gate = ResearchGate(self, self.atomic, secret, runtime,
            task_sha256=plan['task_sha256'], max_reads=plan['max_reads'], max_writes=plan['max_writes'])

    def dispatch(self, op, args):
        if op in {'get_scene_summary', 'get_bounding_box'} or self.fault == 'native_unknown':
            return super().dispatch(op, args)
        obj = self.scene['objects'][0]
        if op == 'move_object':
            for key in ('min', 'max', 'centroid'):
                obj[key] = [v + args['translate_' + axis] for v, axis in zip(obj[key], 'xyz')]
        elif op == 'set_object_layer': obj['layer'] = args['layer_name']
        elif op == 'set_object_color': obj['color'] = [args[k] for k in ('r', 'g', 'b')]
        else: raise AssertionError('unconfigured synthetic native operation')
        return {'synthetic_operation': op, 'object_id': 'box-1'}


def setup(tmp_path, fault=None):
    for name in ('journal', 'controller', 'host', 'permission'):
        (tmp_path / name).mkdir(mode=0o700)
    plan, cases = proposal(native_probe=True), public_probes()
    compiled = compile_cases(plan, cases)
    journal = DevelopmentJournal(tmp_path/'journal', plan, RUNTIME, compiled=compiled)
    sessions, calls = [], []
    def factory(view, runtime, secret):
        directory = tmp_path/view['slot_id']; directory.mkdir(mode=0o700)
        fixture = WriteFixture(view, runtime, secret, directory, fault)
        sessions.append(fixture); return fixture
    host = DevelopmentHost(state=tmp_path/'host', runtime=RUNTIME, native_views=compiled['views']['native'],
        schedule=compiled['views']['schedule'], secret=SECRET, factory=factory,
        operations=CORE, messages_max=capacity(plan)['host_messages_max'], study=plan['study_id'],
        guard=lambda: None, cleanup_guard=lambda: None)
    case_by_id = {c['family_id']: c for c in cases}
    def model(sent):
        calls.append(sent)
        if fault == 'model_unknown': raise TimeoutError('synthetic loss')
        case = case_by_id[compiled['views']['model'][sent['slot_id']]['family_id']]
        operation = case['expected_operations'][sent['step_index']]
        if fault == 'parse_failure': return fixed_response(sent, '```json\n{"tool":null}\n```')
        return fixed_response(sent, json.dumps({'tool': operation['name']}),
            json.dumps({k: operation[k] for k in ('name', 'arguments')}))
    controller = DevelopmentController(journal=journal, state=tmp_path/'controller', runtime=RUNTIME,
        secret=SECRET, schemas=_schemas(), tokenizer=TextTokenizer(), identities={'scripted_probe': IDENTITY},
        host=host.handle, model=model, guard=lambda: None, cleanup_guard=lambda: None,
        contract=CommonChain(plan, compiled, cases, tmp_path/'permission'))
    return controller, host, calls, sessions


def test_same_controller_complete_writes_new_scene_prompt_and_permission_audit(tmp_path):
    controller, host, calls, sessions = setup(tmp_path)
    rows = controller.run()
    if any(r['outcome'] != 'success' for r in rows):
        pytest.fail(str([read_json(tmp_path/'controller', r['identity']['slot_id']+'.evidence.json') for r in rows]))
    assert len(rows) == 2 and len(calls) == 5
    assert all(s.closed for s in sessions) and host.finish()['owned_fixture_remaining'] is False
    assert not (tmp_path/'journal'/'selection.json').exists()
    for call in calls:
        assert controller.wire.user_step(call) == step_input(call['task'], call['scene'])
        assert all(k not in call for k in ('expected_operations', 'fixture_recipe', 'final_assertions', 'progress'))
    for previous, current in zip(calls, calls[1:]):
        if current['slot_id'] == previous['slot_id']:
            assert current['binding']['revision'] > previous['binding']['revision']
            assert current['predecessor']['after_state'] == current['binding']
            assert current['scene'] != previous['scene']
    for row in rows:
        evidence = read_json(tmp_path/'controller', row['identity']['slot_id']+'.evidence.json')
        assert evidence['slot_elapsed_seconds_including_cleanup'] > 0
        assert evidence['execution']['native_effect'] == 'verified_writes'


@pytest.mark.parametrize('fault', ['native_unknown', 'model_unknown', 'close_unknown', 'ledger_forgery'])
def test_uncertainty_never_consumes_next_probe_and_does_not_mask_failure(tmp_path, fault):
    controller, host, calls, sessions = setup(tmp_path, fault)
    rows = controller.run()
    assert len(rows) == 1 and rows[0]['outcome'] == 'engineering_failure' and not rows[0]['may_advance']
    assert len(sessions) == 1 and sessions[0].closed == (fault != 'close_unknown')


def test_strict_quality_failure_continues_without_permission_or_parser_relaxation(tmp_path):
    controller, host, calls, sessions = setup(tmp_path, 'parse_failure')
    rows = controller.run()
    assert len(rows) == 2 and all(r['outcome'] == 'task_failure' and r['may_advance'] for r in rows)
    assert len(calls) == 2 and all(s.closed for s in sessions)


def test_public_preparation_capacity_no_test_cases_and_no_grant():
    plan = proposal(); bounds = capacity(plan)
    assert bounds['families'] == 40 and bounds['slots'] == 80
    assert bounds['generation_stages_max'] == 288 and bounds['host_messages_max'] == 2416
    assert bounds['worst_window_seconds'] == 35280
    assert not plan['execution_authorized'] and 'cases' not in plan
    assert compile_cases(proposal(native_probe=True), public_probes())['study_id'] != plan['study_id']


def test_compiled_task_injection_and_quota_drift_rejected(tmp_path):
    from training.lora_comparison_plan import validate_compiled
    plan, cases = proposal(native_probe=True), public_probes()
    compiled = compile_cases(plan, cases)
    injected = copy.deepcopy(compiled)
    injected['views']['model']['common-000']['expected_operations'] = []
    with pytest.raises(NativeError): validate_compiled(plan, injected)
    injected = copy.deepcopy(compiled)
    injected['views']['native']['common-000']['max_writes'] = 20
    with pytest.raises(NativeError): validate_compiled(plan, injected)
    compiled['cases_sha256'] = 'f'*64
    with pytest.raises(NativeError): CommonChain(plan, compiled, cases, tmp_path)


def test_stratified_interval_extremes_are_nonzero_width_and_incomplete_denied():
    from training.lora_comparison_statistics import clopper_pearson, paired_interval
    from training.lora_comparison_plan import STRATA
    assert clopper_pearson(0, 40, .05)[1] == pytest.approx(1-.025**(1/40))
    assert clopper_pearson(40, 40, .05)[0] == pytest.approx(.025**(1/40))
    counts = {layer: {'both': n, 'base_only': 0, 'lora_only': 0, 'neither': 0} for layer, n in STRATA.items()}
    report = paired_interval(counts, STRATA)
    assert report['delta_lora_minus_base'] == 0 and report['interval'][0] < 0 < report['interval'][1]
    counts['core_tool']['both'] -= 1
    with pytest.raises(NativeError): paired_interval(counts, STRATA)


@pytest.mark.parametrize('fault', ['foreign_document', 'changed_after_state', 'wrong_step', 'wrong_observation'])
def test_write_success_does_not_license_foreign_or_forged_next_scene(tmp_path, fault):
    controller, host, calls, sessions = setup(tmp_path)
    controller.run()
    sent, next_sent = calls[0], copy.deepcopy(calls[1])
    evidence = read_json(tmp_path/'controller', sent['slot_id']+'.evidence.json')
    observed = evidence['steps'][0]['observation']
    if fault == 'foreign_document': next_sent['binding']['document_key'] = 'f'*64
    if fault == 'changed_after_state': next_sent['binding']['revision'] += 1
    if fault == 'wrong_step': next_sent['predecessor']['step_index'] += 1
    if fault == 'wrong_observation': next_sent['predecessor']['observation_sha256'] = 'f'*64
    with pytest.raises(NativeError):
        checked = controller.wire.validate_request(next_sent, controller.journal.views['model'], RUNTIME)
        controller.wire.check_predecessor(checked, sent, observed)


def test_repeated_read_is_new_claimed_step_but_same_request_cannot_reissue(tmp_path):
    from eval.test_c5_research_permission import setup as permission_setup, observation
    backend, atomic, store, signer, gate = permission_setup(tmp_path, max_writes=0)
    observed = observation(atomic, 'get_scene_summary', {})
    first = signer.issue(observed, schemas=backend.schemas, step_request_sha256='a'*64)
    gate.execute(first)
    second = signer.issue(observed, schemas=backend.schemas, step_request_sha256='b'*64)
    gate.execute(second)
    assert first['payload']['request_id'] != second['payload']['request_id']
    # Independently reconstructed signer still cannot replay that same claim.
    from training.c5_research_permission import ResearchSigner
    reloaded = ResearchSigner(store, signer.scene, b'x'*32, 'a'*64, signer.task,
        max_writes=0, max_reads=2, clock=lambda: 100)
    with pytest.raises(NativeError):
        reloaded.issue(observed, schemas=backend.schemas, step_request_sha256='b'*64)


def test_actual_probe_preparation_and_runner_reuse_controller_without_grant(tmp_path):
    from pathlib import Path
    from tools.build_lora_common_probe import build
    from training.lora_common_probe_runner import prepare, controller as make_controller
    from plugin.rhino_listener.lora_common_probe import admit
    package = build(Path(__file__).resolve().parents[1], tmp_path/'bundle')
    root = Path(package['source_root'])
    prepared = prepare(root, package)
    assert len(prepared['cases']) == 2 and not Path(package['state_root']).exists()
    with pytest.raises((NativeError, FileNotFoundError)): admit(root, package)
    state = tmp_path/'synthetic'; state.mkdir(mode=0o700)
    for name in ('host', 'controller', 'journal', 'permission', 'fixtures'): (state/name).mkdir(mode=0o700)
    def factory(view, runtime, secret):
        directory = state/'fixtures'/view['slot_id']; directory.mkdir(mode=0o700)
        return WriteFixture(view, runtime, secret, directory, None)
    host = DevelopmentHost(state=state/'host', runtime=digest(package), native_views=prepared['views']['native'],
        schedule=prepared['views']['schedule'], secret=SECRET, factory=factory,
        operations=CORE, messages_max=prepared['capacity']['host_messages_max'], study=package['plan']['study_id'],
        guard=lambda: None, cleanup_guard=lambda: None)
    runner = make_controller(root, package, state, SECRET, host.handle, lambda: None, lambda: None)
    assert all(r['outcome'] == 'success' for r in runner.run())
    assert host.finish()['owned_fixture_remaining'] is False


@pytest.mark.parametrize('route', ['base', 'current_lora'])
def test_same_peer_parser_and_original_prompt_for_both_weight_routes(tmp_path, route):
    import hashlib
    from contextlib import nullcontext
    from training import lora_common_wire as wire
    from training.lora_development_peer import DevelopmentPeer
    from training.lora_comparison_plan import FINAL_STUDY
    from plugin.rhino_listener.lora_development_channel import PROTOCOL
    from training.lora_development_cases import fixture_design
    # One public unit fixture, not a generated final family population.
    task = '读取一次完整场景摘要。'
    views = {'unit-0': {'study_id': FINAL_STUDY, 'route': route, 'system': 'original', 'task': task, 'max_steps': 1}}
    sent = {'protocol': PROTOCOL, 'study_id': FINAL_STUDY, 'runtime_sha256': RUNTIME, 'slot_id': 'unit-0',
        'route': route, 'system': 'original', 'task': task, 'step_index': 0, 'scene': fixture_design()[1],
        'binding': {'document_key': 'd'*64, 'revision': 0, 'scene_sha256': 'e'*64},
        'predecessor': None, 'host_evidence_sha256': 'f'*64}
    prompts = []
    def generate(prompt, stage):
        prompts.append(prompt)
        raw = '{"tool":"get_scene_summary"}' if stage == 'selector' else '{"name":"get_scene_summary","arguments":{}}'
        return {'raw': raw, 'tokens': 8, 'seconds': .01,
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
            'output_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    peer = DevelopmentPeer(state=tmp_path, runtime=RUNTIME, views=views, identities={route: IDENTITY},
        tokenizer=TextTokenizer(), generate=generate, route_context=lambda _: nullcontext(), guard=lambda: None, wire=wire)
    returned = peer.infer(sent)
    assert returned['observation']['status'] == 'schema_valid_not_authorized'
    assert len(prompts) == 2 and wire.user_step(sent) == step_input(task, sent['scene'])
    with pytest.raises((NativeError, FileExistsError)): peer.infer(sent)


def test_new_export_capacity_uses_plan_but_cannot_expand_old_package(tmp_path):
    import io
    from plugin.rhino_listener.c5_research_channel import publish_json
    from plugin.rhino_listener.lora_development_runtime import common_configuration
    from training.lora_development_export import export_gpu, verify_archive, file_limit
    plan = proposal(); cfg = common_configuration(plan)
    package = {'kind': plan['study_id'], 'comparison_plan': plan, 'limits': cfg}
    assert file_limit(package) == 1216 and file_limit({}) == 1024
    publish_json(tmp_path, 'gpu-settlement.json', {'package_sha256': digest(package), 'status': 'gpu_stopped'})
    peer = tmp_path/'load-0'/'peer'; peer.mkdir(parents=True)
    # Tiny synthetic files, not task generation, model output or a real run.
    for i in range(1100): (peer/('%04d.json'%i)).write_text('{}')
    stream = io.BytesIO(); export_gpu(tmp_path, package, stream)
    archive = tmp_path/'synthetic.tar'; archive.write_bytes(stream.getvalue())
    assert verify_archive(archive, package)['files'] == 1101
    with pytest.raises(NativeError): verify_archive(archive, {})


def test_storage_reserve_stops_new_work_but_preserves_cleanup_space(tmp_path):
    from plugin.rhino_listener.lora_development_runtime import common_configuration
    from training.lora_comparison_storage import check_evidence_budget
    cfg = common_configuration(proposal())
    assert cfg['evidence_work_bytes_max'] + cfg['gpu_archive_reserve_bytes'] + cfg['evidence_cleanup_reserve_bytes'] == cfg['evidence_total_bytes_max']
    cfg.update(evidence_work_bytes_max=3, evidence_total_bytes_max=8)
    (tmp_path/'synthetic.json').write_bytes(b'123456')
    with pytest.raises(NativeError): check_evidence_budget(tmp_path, cfg)
    assert check_evidence_budget(tmp_path, cfg, cleanup=True)['bytes'] == 6
    (tmp_path/'alias').symlink_to(tmp_path/'synthetic.json')
    with pytest.raises(NativeError): check_evidence_budget(tmp_path, cfg, cleanup=True)


def test_final_worker_requires_complete_bound_views_before_loading():
    from training.lora_development_gpu_entry import peer_contract
    from plugin.rhino_listener.lora_development_runtime import common_configuration
    plan = proposal()
    inert = {'kind': plan['study_id'], 'comparison_plan': plan, 'limits': common_configuration(plan)}
    # Metadata proposal cannot masquerade as a ready private execution package.
    with pytest.raises(KeyError): peer_contract(inert)


def test_live_storage_guard_tolerates_atomic_publication_without_claiming_identity(tmp_path, monkeypatch):
    import os
    from plugin.rhino_listener.lora_development_runtime import common_configuration
    from training.lora_comparison_storage import check_evidence_budget
    cfg = common_configuration(proposal())
    (tmp_path/'published.json').write_text('{}')
    os.link(tmp_path/'published.json', tmp_path/'publish-temporary.tmp')
    monkeypatch.setattr(os, 'walk', lambda *args, **kwargs: iter([(str(tmp_path), [],
        ['published.json', 'publish-temporary.tmp', 'already-removed.tmp'])]))
    report = check_evidence_budget(tmp_path, cfg)
    assert report['bytes'] == 4 and report['files'] == 2 and not report['private_contents_read']
