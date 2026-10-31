"""Two declared fixed operations using the real atomic gate, before task seed.

No event subscription or external-ABA claim. The task uses its own quota
ledger; this bounded preparation ledger retains both fixed reservations.
"""
from .candidate_atomic_gate import AtomicGateError, RhinoAtomicGate, CONTROLLED_SNAPSHOT, rhino_scene_fingerprint
from .c5_research_channel import publish_json
from .c5_research_native import require


def check(session):
    import Rhino
    doc, directory = session.doc, session.directory
    atomic = RhinoAtomicGate(directory/'snapshot-protection.sqlite3', str(session.backend.serial),
                             session.scene_digest, create_ledger=True, state_contract=CONTROLLED_SNAPSHOT)
    baseline = atomic.snapshot()
    before = rhino_scene_fingerprint(doc, controlled_snapshot=True)
    keys = ['snapshot_fixed_add_00000001', 'snapshot_fixed_delete_00001']
    point = None
    def dispatch(operation, arguments):
        nonlocal point
        session.guard()
        if operation == 'fixed_add_point':
            point = doc.Objects.AddPoint(Rhino.Geometry.Point3d(0, 0, 0))
            require(str(point) != '00000000-0000-0000-0000-000000000000', 'fixed add failed')
        elif operation == 'fixed_delete_point':
            require(point is not None and doc.Objects.Delete(point, True), 'fixed delete failed')
        else:
            raise AssertionError('unapproved fixed operation')
        return {'operation':operation,'completed':True}
    states = [baseline]
    for index, operation in enumerate(('fixed_add_point','fixed_delete_point')):
        claim = {'operation':operation,'arguments':{},'before_state':states[-1],'key':keys[index]}
        publish_json(directory, 'snapshot-fixed-%d.claim.json'%index, claim)
        result = atomic.execute(keys[index], states[-1], operation, {}, dispatch)
        after = atomic.snapshot()
        require(after['revision'] > states[-1]['revision'], 'controlled write did not advance revision')
        publish_json(directory, 'snapshot-fixed-%d.result.json'%index,
                     {'result':result,'after_state':after,'ledger':atomic.inspect(keys[index])})
        states.append(after)
    after = rhino_scene_fingerprint(doc, controlled_snapshot=True)
    for field in ('document_settings_sha256','objects','layers_sha256'):
        require(before['components'][field] == after['components'][field], 'fixed content not restored')
    def forbidden_dispatch(operation, arguments):
        raise AssertionError('stale state reached dispatch')
    try:
        atomic.execute('snapshot_stale_check_000001', baseline, 'fixed_add_point', {}, forbidden_dispatch)
    except AtomicGateError as exc:
        require(exc.code == 'scene_changed', 'wrong stale revision rejection')
    else:
        raise AssertionError('stale controlled state was not rejected')
    publish_json(directory, 'snapshot-check.json', {'status':'passed', 'fixed_native_operations':2,
        'state_contract':CONTROLLED_SNAPSHOT, 'controlled_aba_rejected':True,'stale_dispatch_calls':0,
        'external_aba_detection':False, 'content_restored':True, 'states':states})
