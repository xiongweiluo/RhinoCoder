"""CPU-only diagnostics; no native host or evidence from any private study."""
import copy
import json
from pathlib import Path

import pytest

from plugin.rhino_listener import candidate_atomic_gate as atomic
from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener.lora_development_host import RhinoSession


def inputs():
    return (['Millimeters', 1e-6, .01, 101, 3], [('object-id', 'geometry-json', 'attributes-json')], [('layer-id', 'name')])


def test_component_record_preserves_original_full_identity_and_hides_geometry():
    document, items, layers = inputs()
    value = atomic.scene_fingerprint(document, items, layers)
    assert value['scene_sha256'] == atomic._hash(atomic._json({'document':document, 'objects':items, 'layers':layers}))
    text = json.dumps(value)
    assert all(raw not in text for raw in ('geometry-json','attributes-json','object-id','layer-id'))


@pytest.mark.parametrize('change', ['settings','process_serial','undo_serial','geometry','attributes','layers'])
def test_each_competing_fingerprint_component_is_distinguishable(change):
    original = inputs(); document, items, layers = copy.deepcopy(original)
    if change == 'settings': document[1] = 2e-6
    if change == 'process_serial': document[3] += 1
    if change == 'undo_serial': document[4] += 1
    if change == 'geometry': items[0] = (items[0][0], 'changed', items[0][2])
    if change == 'attributes': items[0] = (items[0][0], items[0][1], 'changed')
    if change == 'layers': layers.append(('new-layer','name'))
    before, after = atomic.scene_fingerprint(*original), atomic.scene_fingerprint(document, items, layers)
    assert before['scene_sha256'] != after['scene_sha256']
    fields = [k for k in before['components'] if before['components'][k] != after['components'][k]]
    expected = {'settings':'document_settings_sha256','process_serial':'process_next_object_serial',
                'undo_serial':'document_next_undo_serial','geometry':'objects','attributes':'objects','layers':'layers_sha256'}
    assert fields == [expected[change]]
    # This demonstrates competing mechanisms, not which one happened in Rhino.


def test_trace_uses_same_snapshot_once_and_stops_at_capacity(tmp_path, monkeypatch):
    tmp_path.chmod(0o700); calls = []
    value = atomic.scene_fingerprint(*inputs())
    monkeypatch.setattr(atomic, 'rhino_scene_fingerprint', lambda doc: calls.append(doc) or value)
    session = RhinoSession({}, 'a'*64, b'x'*32, directory=tmp_path, schemas={}, guard=lambda:None, fingerprint_limit=1)
    assert session.scene_digest() == value['scene_sha256'] and len(calls) == 1
    assert json.loads((tmp_path/'fingerprint-0001.json').read_text()) == {'sequence':1, **value}
    with pytest.raises(NativeError, match='capacity'):
        session.scene_digest()
    assert len(calls) == 1


def test_original_path_has_no_added_native_read_or_trace(tmp_path, monkeypatch):
    monkeypatch.setattr(atomic, 'rhino_scene_digest', lambda doc:'a'*64)
    monkeypatch.setattr(atomic, 'rhino_scene_fingerprint', lambda doc:pytest.fail('diagnostic disabled'))
    session = RhinoSession({}, 'b'*64, b'x'*32, directory=tmp_path, schemas={}, guard=lambda:None)
    assert session.scene_digest() == 'a'*64 and not list(tmp_path.iterdir())


def test_one_diagnostic_reuses_actual_preparation_and_cannot_inherit_two_probe_approval(tmp_path):
    from tools.build_lora_common_probe import build
    from training.lora_common_probe_runner import prepare
    from plugin.rhino_listener.lora_common_probe import admit, approval_record
    from plugin.rhino_listener.c5_research_channel import publish_json
    p = build(Path(__file__).resolve().parents[1], tmp_path/'bundle', fingerprint_diagnostic=True)
    ready = prepare(Path(p['source_root']), p)
    assert len(ready['cases']) == p['capacity']['slots'] == 1
    assert ready['cases'][0]['family_id'] == 'COMMON-D01'
    assert p['capacity']['model_step_requests_max'] == p['capacity']['generation_stages_max'] == 0
    assert p['capacity']['fingerprint_records_max'] == 5*p['capacity']['host_messages_max']
    s = Path(p['state_root']); assert not s.exists()
    s.mkdir(mode=0o700)
    wrong = approval_record(p); wrong['scope'] = 'two_new_public_scripted_native_probes_zero_models_no_final_test'
    publish_json(s, 'owner-approval.json', wrong)
    with pytest.raises(NativeError, match='approval'):
        admit(Path(p['source_root']), p)


def test_one_diagnostic_reuses_complete_synthetic_controller_path(tmp_path):
    from eval.test_lora_common_chain import WriteFixture
    from training.lora_common_probe_runner import controller
    from tools.build_lora_common_probe import build
    from plugin.rhino_listener.lora_development_host import DevelopmentHost
    from plugin.rhino_listener.c5_research_native import CORE
    p = build(Path(__file__).resolve().parents[1], tmp_path/'bundle', fingerprint_diagnostic=True)
    s = tmp_path/'synthetic'; s.mkdir(mode=0o700)
    for name in ('host','controller','journal','permission','fixtures'): (s/name).mkdir(mode=0o700)
    secret = b'x'*32
    def factory(view, runtime, key):
        directory = s/'fixtures'/view['slot_id']; directory.mkdir(mode=0o700)
        return WriteFixture(view, runtime, key, directory, None)
    host = DevelopmentHost(state=s/'host', runtime=digest(p), native_views=p['compiled']['views']['native'],
        schedule=p['compiled']['views']['schedule'], secret=secret, factory=factory, guard=lambda:None,
        cleanup_guard=lambda:None, operations=CORE, study=p['plan']['study_id'], messages_max=p['capacity']['host_messages_max'])
    # Complete synthetic path only. The native result remains a separate gate.
    run = controller(Path(p['source_root']),p,s,secret,host.handle,lambda:None,lambda:None)
    assert [r['outcome'] for r in run.run()] == ['success']
    assert len(run.results) == 1 and host.finish()['owned_fixture_remaining'] is False


def test_postrun_component_audit_distinguishes_counter_and_refuses_conflicting_evidence():
    import importlib.util
    path = Path(__file__).parent/'lora-development/common-probe-audit-procedure-20261027.py'
    spec = importlib.util.spec_from_file_location('probe_audit_cpu', path)
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    before = atomic.scene_fingerprint(*inputs())
    document, objects, layers = inputs(); document[3] += 1
    after = atomic.scene_fingerprint(document, objects, layers)
    records = [{'sequence':1, **before}, {'sequence':2, **after}]
    summary = audit.fingerprint_changes(records, before['scene_sha256'], after['scene_sha256'])
    assert summary['changed_components'] == ['process_next_object_serial']
    assert summary['changed_objects'] == [] and summary['change_origin_proven'] is False
    conflict = copy.deepcopy(records); conflict[1]['scene_sha256'] = conflict[0]['scene_sha256']
    with pytest.raises(AssertionError):
        audit.fingerprint_changes(conflict, before['scene_sha256'], after['scene_sha256'])
    with pytest.raises(KeyError):
        audit.fingerprint_changes(records[:1], before['scene_sha256'], after['scene_sha256'])
