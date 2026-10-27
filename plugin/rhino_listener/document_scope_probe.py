"""Three disclosed fixture operations, only in the separately admitted probe.

Checks the real document event bridge and the existing atomic stale-state
rejection before the unchanged move/read task. No model or scoring override.
"""
from .candidate_atomic_gate import AtomicGateError, rhino_scene_fingerprint
from .c5_research_channel import publish_json
from .c5_research_native import require


def check(session, atomic):
    import Rhino
    directory, doc, clock = session.directory, session.doc, session.document_clock
    baseline = atomic.snapshot()
    before = rhino_scene_fingerprint(doc, document_clock=clock)
    serial_before = int(Rhino.DocObjects.RhinoObject.NextRuntimeSerialNumber)
    session.guard()
    publish_json(directory, 'scope-helper-create.claim.json', {'action': 'new_headless_document'})
    helper = Rhino.RhinoDoc.CreateHeadless(None)
    require(helper is not None, 'scope helper creation unknown')
    try:
        publish_json(directory, 'scope-helper-created.json', {'serial': int(helper.RuntimeSerialNumber)})
        session.guard()
        publish_json(directory, 'scope-helper-add.claim.json', {'action': 'AddPoint', 'point': [0, 0, 0]})
        added = helper.Objects.AddPoint(Rhino.Geometry.Point3d(0, 0, 0))
        require(str(added) != '00000000-0000-0000-0000-000000000000', 'scope helper add failed')
        unchanged = rhino_scene_fingerprint(doc, document_clock=clock)
        serial_after = int(Rhino.DocObjects.RhinoObject.NextRuntimeSerialNumber)
        require(before == unchanged and serial_after > serial_before, 'document scope isolation unverified')
        publish_json(directory, 'scope-helper-result.json', {'owned_fingerprint_unchanged': True,
            'process_serial_before': serial_before, 'process_serial_after': serial_after})
    finally:
        serial = int(helper.RuntimeSerialNumber)
        require(bool(helper.IsHeadless) and not helper.Path, 'scope helper identity differs')
        helper.Dispose()
        absent = Rhino.RhinoDoc.FromRuntimeSerialNumber(serial) is None
        publish_json(directory, 'scope-helper-close.json', {'fixture_registry_absent': absent})
        require(absent, 'scope helper cleanup unknown')
    session.guard()
    publish_json(directory, 'scope-owned-add.claim.json', {'action': 'AddPoint', 'point': [0, 0, 0]})
    point = doc.Objects.AddPoint(Rhino.Geometry.Point3d(0, 0, 0))
    require(str(point) != '00000000-0000-0000-0000-000000000000', 'owned ABA add failed')
    session.guard()
    publish_json(directory, 'scope-owned-delete.claim.json', {'action': 'Delete', 'target': 'new_scope_point'})
    require(doc.Objects.Delete(point, True), 'owned ABA delete failed')
    after = rhino_scene_fingerprint(doc, document_clock=clock)
    for field in ('document_settings_sha256', 'objects', 'layers_sha256'):
        require(before['components'][field] == after['components'][field], 'ABA content not restored')
    require(clock.snapshot() > before['components']['document_mutation_clock']['epoch'], 'ABA event bridge missing')
    def forbidden_dispatch(operation, arguments):
        raise AssertionError('stale state reached dispatch')
    try:
        atomic.execute('document_scope_stale_check_0001', baseline, 'move_object', {}, forbidden_dispatch)
    except AtomicGateError as exc:
        require(exc.code == 'scene_changed', 'wrong ABA rejection')
    else:
        raise AssertionError('ABA was not rejected')
    publish_json(directory, 'scope-check.json', {'status': 'passed', 'fixed_native_operations': 3,
        'other_document_did_not_change_identity': True, 'owned_add_delete_aba_rejected': True,
        'stale_dispatch_calls': 0, 'clock_counts': dict(clock.counts), 'epoch': clock.snapshot(),
        'native_scope': 'add_delete_and_cross_document_only_not_all_event_types'})
