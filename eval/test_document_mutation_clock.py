"""CPU mechanism evidence only; no Rhino, model, old private data or grants."""
from pathlib import Path
from types import SimpleNamespace as NS
import threading

import pytest

from plugin.rhino_listener.candidate_atomic_gate import AtomicGateError, RhinoAtomicGate, scene_fingerprint
from plugin.rhino_listener.document_mutation_clock import DocumentMutationClock, EVENTS


def clock_fixture(**kwargs):
    callbacks, removed = {}, []
    def attach(name, callback): callbacks[name] = callback
    def detach(name, callback):
        assert callbacks.pop(name) is callback
        removed.append(name)
    clock = DocumentMutationClock(17, attach, detach, **kwargs)
    clock.start()
    return clock, callbacks, removed


def emit(callback, serial=17):
    callback(None, NS(Document=NS(RuntimeSerialNumber=serial)))


def fingerprint(clock, geometry='geometry', object_serial=21):
    return scene_fingerprint(['mm', 1e-6, .01, {'schema':'document_mutation_v1', 'epoch':clock.snapshot()}, 4],
                             [('id', geometry, 'attributes', object_serial)], [('layer', 'name')])


@pytest.mark.parametrize('event', EVENTS)
def test_each_owned_event_prevents_aba_but_other_document_does_not(tmp_path, event):
    clock, callbacks, removed = clock_fixture()
    gate = RhinoAtomicGate(tmp_path/'gate.db', 'owned-doc', lambda:fingerprint(clock)['scene_sha256'], create_ledger=True)
    expected = gate.snapshot()
    emit(callbacks[event], serial=99)
    assert gate.snapshot() == expected
    emit(callbacks[event]); emit(callbacks[event])
    # Identical serialized final content still rejects a stale authorization.
    with pytest.raises(AtomicGateError, match='scene_changed'):
        gate.execute('document_mutation_test_key_0001', expected, 'move_object', {},
                     lambda *a:pytest.fail('ABA dispatched'))
    assert gate.snapshot()['revision'] == 1 and clock.snapshot() == 2
    receipt = clock.close()
    assert receipt['removal_verified'] and not callbacks and set(removed) == set(EVENTS)
    with pytest.raises(AtomicGateError, match='unverified'): clock.snapshot()


def test_content_and_object_instance_remain_authoritative_without_an_event():
    clock, _, _ = clock_fixture()
    baseline = fingerprint(clock)['scene_sha256']
    assert fingerprint(clock, geometry='different')['scene_sha256'] != baseline
    assert fingerprint(clock, object_serial=22)['scene_sha256'] != baseline
    assert fingerprint(clock)['scene_sha256'] == baseline


def test_actual_fingerprint_uses_owned_clock_not_global_counter_and_rejects_midread_change(monkeypatch):
    import sys
    from plugin.rhino_listener.candidate_atomic_gate import rhino_scene_fingerprint
    clock, callbacks, _ = clock_fixture()
    geometry = NS(ToJSON=lambda options:'geometry')
    obj = NS(Id='owned-object', RuntimeSerialNumber=12, Geometry=geometry,
             Attributes=NS(ToJSON=lambda options:'attributes'))
    doc = NS(RuntimeSerialNumber=17, ModelUnitSystem='mm', ModelAbsoluteTolerance=1e-6,
             ModelAngleToleranceRadians=.01, NextUndoRecordSerialNumber=4, Layers=[],
             Objects=NS(GetObjectList=lambda settings:[obj]))
    class GlobalObjects:
        @property
        def NextRuntimeSerialNumber(self): pytest.fail('process-global counter read by scoped identity')
    monkeypatch.setitem(sys.modules, 'Rhino', NS(FileIO=NS(SerializationOptions=NS),
        DocObjects=NS(ObjectEnumeratorSettings=NS, RhinoObject=GlobalObjects())))
    value = rhino_scene_fingerprint(doc, document_clock=clock)
    emit(callbacks['AddRhinoObject'], serial=99)
    assert rhino_scene_fingerprint(doc, document_clock=clock) == value
    doc.RuntimeSerialNumber = 99
    with pytest.raises(AtomicGateError, match='wrong_document'): rhino_scene_fingerprint(doc, document_clock=clock)
    doc.RuntimeSerialNumber = 17
    def changing(options):
        emit(callbacks['ReplaceRhinoObject']); return 'geometry'
    geometry.ToJSON = changing
    with pytest.raises(AtomicGateError, match='during_fingerprint'): rhino_scene_fingerprint(doc, document_clock=clock)


@pytest.mark.parametrize('fault', ['missing_document', 'thread', 'capacity'])
def test_unreadable_or_wrong_thread_or_overflow_event_poison(fault):
    clock, callbacks, _ = clock_fixture(event_limit=1)
    cb = callbacks['AddRhinoObject']
    if fault == 'missing_document': cb(None, NS())
    elif fault == 'thread':
        thread = threading.Thread(target=emit, args=(cb,)); thread.start(); thread.join()
    else: emit(cb); emit(cb)
    with pytest.raises(AtomicGateError, match='unverified'): clock.snapshot()
    assert clock.close()['removal_verified']


def test_partial_subscription_unwinds_exact_delegate_and_never_runs():
    callbacks, removed = {}, []
    def attach(name, callback):
        callbacks[name] = callback
        if name == EVENTS[2]: raise RuntimeError('partial attach')
    def detach(name, callback):
        assert callbacks.pop(name) is callback
        removed.append(name)
    clock = DocumentMutationClock(17, attach, detach)
    with pytest.raises(RuntimeError, match='partial attach'): clock.start()
    assert set(removed) == set(EVENTS[:3]) and not callbacks
    assert clock.close_result['removal_verified'] and clock.faults
    with pytest.raises(AtomicGateError): clock.snapshot()


def test_detach_failure_does_not_skip_remaining_handlers_or_claim_cleanup():
    clock, callbacks, removed = clock_fixture()
    original = clock.detach
    def detach(name, callback):
        if name == EVENTS[-1]: raise RuntimeError('removal failed')
        original(name, callback)
    clock.detach = detach
    receipt = clock.close()
    assert not receipt['removal_verified'] and len(removed) == len(EVENTS)-1
    with pytest.raises(AtomicGateError): clock.snapshot()


def test_host_disposal_failure_still_detaches_and_records(tmp_path):
    from plugin.rhino_listener.lora_development_host import RhinoSession
    tmp_path.chmod(0o700)
    clock, callbacks, _ = clock_fixture()
    session = RhinoSession({}, 'a'*64, b'x'*32, directory=tmp_path, schemas={}, guard=lambda:None,
                           document_scope_probe=True, fingerprint_limit=10)
    session.document_clock = clock
    def fail():
        assert not callbacks  # detach before disposed Document event args expire
        raise RuntimeError('dispose failed')
    session._close_document = fail
    with pytest.raises(RuntimeError, match='dispose failed'): session.close()
    assert not callbacks and (tmp_path/'document-clock-close.json').is_file()


def test_actual_scoped_preparation_rejects_old_approval_and_has_zero_model_capacity(tmp_path):
    from tools.build_lora_common_probe import build
    from training.lora_common_probe_runner import prepare
    from plugin.rhino_listener.lora_common_probe import approval_record, admit
    from plugin.rhino_listener.c5_research_channel import publish_json
    package = build(Path(__file__).resolve().parents[1], tmp_path/'bundle', document_scope_probe=True)
    root = Path(package['source_root']); ready = prepare(root, package)
    assert [c['family_id'] for c in ready['cases']] == ['COMMON-S01']
    cap = package['capacity']
    assert cap['model_step_requests_max'] == cap['generation_stages_max'] == 0
    assert cap['isolated_documents_max'] == 2 and cap['additional_fixture_operations_max'] == 3
    state = Path(package['state_root']); assert not state.exists()
    state.mkdir(mode=0o700)
    wrong = approval_record(package); wrong['scope'] = 'one_move_fingerprint_diagnostic_zero_models_no_final_test'
    publish_json(state, 'owner-approval.json', wrong)
    with pytest.raises(Exception, match='approval'): admit(root, package)


@pytest.mark.parametrize('events_delivered', [True, False])
def test_actual_native_scope_check_control_flow_and_missing_events_fail_closed(tmp_path, monkeypatch, events_delivered):
    import sys
    from plugin.rhino_listener import document_scope_probe as probe
    clock, callbacks, _ = clock_fixture()
    registry, serial = {}, [100]
    class Doc:
        IsHeadless = True
        Path = ''
        def __init__(self, ident):
            self.RuntimeSerialNumber = ident; self.Objects = self
            self.objects = []; registry[ident] = self
        def AddPoint(self, point):
            serial[0] += 1; self.objects.append(serial[0])
            if events_delivered: emit(callbacks['AddRhinoObject'], self.RuntimeSerialNumber)
            return serial[0]
        def Delete(self, point, quiet):
            self.objects.remove(point)
            if events_delivered: emit(callbacks['DeleteRhinoObject'], self.RuntimeSerialNumber)
            return True
        def Dispose(self): del registry[self.RuntimeSerialNumber]
    class ObjectType:
        @property
        def NextRuntimeSerialNumber(self): return serial[0]
    rhino = NS(RhinoDoc=NS(CreateHeadless=lambda _:Doc(99), FromRuntimeSerialNumber=registry.get),
               DocObjects=NS(RhinoObject=ObjectType()), Geometry=NS(Point3d=lambda *xyz:xyz))
    monkeypatch.setitem(sys.modules, 'Rhino', rhino)
    monkeypatch.setattr(probe, 'rhino_scene_fingerprint', lambda doc, document_clock:fingerprint(clock))
    tmp_path.chmod(0o700)
    session = NS(doc=Doc(17), directory=tmp_path, document_clock=clock, guard=lambda:None)
    atomic = RhinoAtomicGate(tmp_path/'gate.db', 'owned-doc', lambda:fingerprint(clock)['scene_sha256'], create_ledger=True)
    if events_delivered:
        probe.check(session, atomic)
        assert (tmp_path/'scope-check.json').is_file()
    else:
        with pytest.raises(Exception, match='ABA event bridge missing'): probe.check(session, atomic)
        assert not (tmp_path/'scope-check.json').exists()
    assert set(registry) == {17} and session.doc.objects == []


def test_scoped_package_uses_same_complete_controller_as_prior_probes(tmp_path):
    from eval.test_lora_common_chain import WriteFixture
    from training.lora_common_probe_runner import controller
    from tools.build_lora_common_probe import build
    from plugin.rhino_listener.lora_development_host import DevelopmentHost
    from plugin.rhino_listener.c5_research_native import CORE, digest
    package = build(Path(__file__).resolve().parents[1], tmp_path/'bundle', document_scope_probe=True)
    state = tmp_path/'synthetic'; state.mkdir(mode=0o700)
    for name in ('host','controller','journal','permission','fixtures'): (state/name).mkdir(mode=0o700)
    def factory(view, runtime, key):
        directory = state/'fixtures'/view['slot_id']; directory.mkdir(mode=0o700)
        return WriteFixture(view, runtime, key, directory, None)
    secret = b'x'*32
    host = DevelopmentHost(state=state/'host', runtime=digest(package), native_views=package['compiled']['views']['native'],
        schedule=package['compiled']['views']['schedule'], secret=secret, factory=factory, guard=lambda:None,
        cleanup_guard=lambda:None, operations=CORE, study=package['plan']['study_id'], messages_max=package['capacity']['host_messages_max'])
    run = controller(Path(package['source_root']), package, state, secret, host.handle, lambda:None, lambda:None)
    assert [r['outcome'] for r in run.run()] == ['success']
    assert host.finish()['owned_fixture_remaining'] is False


def test_scope_audit_never_promotes_missing_or_failed_cleanup(tmp_path):
    import importlib.util
    import copy
    path = Path(__file__).parent/'lora-development/common-probe-audit-procedure-20261027.py'
    spec = importlib.util.spec_from_file_location('scope_audit_cpu', path)
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    clock, callbacks, _ = clock_fixture()
    emit(callbacks['AddRhinoObject']); emit(callbacks['DeleteRhinoObject'])
    value = fingerprint(clock); (tmp_path/'fingerprint-0001.json').touch()
    evidence = {
        'scope-check.json': {'status':'passed','fixed_native_operations':3,'other_document_did_not_change_identity':True,
            'owned_add_delete_aba_rejected':True,'stale_dispatch_calls':0,'epoch':2,'clock_counts':dict(clock.counts)},
        'created.json':{'serial':17}, 'scope-helper-created.json':{'serial':99},
        'scope-helper-result.json':{'owned_fingerprint_unchanged':True,'process_serial_before':10,'process_serial_after':11},
        'scope-helper-close.json':{'fixture_registry_absent':True},
        'scope-helper-add.claim.json':{'action':'AddPoint','point':[0,0,0]},
        'scope-owned-add.claim.json':{'action':'AddPoint','point':[0,0,0]},
        'scope-owned-delete.claim.json':{'action':'Delete','target':'new_scope_point'},
        'document-clock-close.json':clock.close(), 'fingerprint-0001.json':{'sequence':1,**value}}
    def run(rows):
        return audit.review_document_scope(tmp_path, lambda p:rows[p.name],
            [{'state':{'scene_sha256':value['scene_sha256']}}], [],
            {'document_events_max':256,'fingerprint_records_max':237}, EVENTS)
    assert run(evidence)['scope_checks_verified']
    missing = dict(evidence); del missing['scope-helper-close.json']
    with pytest.raises(KeyError): run(missing)
    broken = copy.deepcopy(evidence); broken['document-clock-close.json']['removal_verified'] = False
    with pytest.raises(AssertionError): run(broken)
