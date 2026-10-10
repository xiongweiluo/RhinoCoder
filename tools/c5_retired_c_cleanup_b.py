#! python 3
"""New exact-approved manual safety closure only; NOT replay/repair or D.

Import is inert. Sticky admission precedes all live checks. Preserve atomic
drift/ledger; never call snapshot, dispatch, create a fixture or subscription.
"""
from pathlib import Path
import hashlib
import hmac
import importlib.util
import json
import os
import sqlite3
import stat
import sys
import threading
import time

ID = 'C5SAFE-HOSTASSURANCE-C-20261007-B'
C_ID = 'C5DEV-HOSTASSURANCE-20261007-C'
ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-state-20261007-C')
SOURCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-source-20261007-C')
SPEC = 'eval/c5/hostassurance-c-cleanup-spec-20261007-b.json'
FREEZE = 'eval/c5/hostassurance-c-cleanup-runtime-20261007-b.json'
DECISION = 'eval/c5/retired-c-manual-safety-closure-admission-proposal-v2.json'
ACCEPTANCE = 'eval/c5/retired-c-manual-safety-closure-owner-decision-v2.json'
DECISION_SHA = 'c103d9b97982411010119713dbc1a6bdb711e0ce7cd29b154ede6b8c19ae172f'
C_SHA = 'bbbbca84474d5cd397f2e011775cb17b50f6f4a7328c6cee339a4aedf13090d1'
C_RESULT_SHA = '6093aa3ae6e25f31ecaaad551c368a919d499ff2e6c8aa57d674910295b3c3a9'
ACTIVE_SHA = 'de8fa7924ad4cf7fbeffdbe982f0b559a77eca7a8cf1f24175df642404ec6cfa'
UNUSED = ('read-base', 'clarify-base', 'clarify-lora', 'unsupported-lora', 'unsupported-base')
EMPTY = {'groups': {}, 'objects': [], 'unit': 'Millimeters'}
SCOPE = 'retired C only; V2 exact empty fixture safety Dispose, seven specified keys and exact three delegates; preserve atomic drift and all ledger rows, no replay'


def require(ok, message):
    if not ok: raise RuntimeError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    require(path.is_absolute() and path.resolve() == path and path.is_file(), 'fixed regular file required')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()


def read(path):
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= 4194304, 'bounded fixed JSON required')
    def pairs(rows):
        value = {}
        for k, v in rows:
            require(k not in value, 'duplicate JSON key'); value[k] = v
        return value
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def authorize(spec, freeze, approval, decision, acceptance, script_sha):
    zero = ('model_calls', 'gpu_calls', 'holdout_calls', 'tool_dispatches', 'new_fixtures',
            'new_subscriptions', 'atomic_snapshot_calls', 'ledger_updates', 'key_file_contents_reads')
    require(spec['study_id'] == freeze['study_id'] == ID and spec['retired_study_id'] == C_ID
            and spec['retired_runtime_sha256'] == C_SHA
            and all(type(spec[k]) is int and spec[k] == 0 for k in zero)
            and spec['fixture_serial'] == 268435475 and spec['active_serial'] == 268435457
            and all(type(spec[k]) is int and spec[k] == v for k,v in {
                'fixture_closes_max':1,'specified_key_removes_max':7,'idle_exact_removes_max':2,'assemblyload_exact_removes_max':1}.items())
            and spec['claim_before_live_inspection'] is True and spec['replay_allowed'] is False
            and spec['historical_atomic_match_required_for_safety_Dispose'] is False
            and spec['research_product_atomic_guards_unchanged'] is True
            and spec['logical_budget_seconds'] == 180, 'exact V2 manual-only safety scope required')
    require(digest(decision) == DECISION_SHA and acceptance == {
            'decision_id': 'C5SAFE-CLOSURE-ADMISSION-20261007-V2', 'actor': 'repository_owner', 'accepted': True,
            'decision_spec_sha256': DECISION_SHA, 'scope': 'prepare_new_manual_safety_closure_only_not_execution',
            'actual_cleanup_execution_approved': False, 'approval_basis': 'Direct owner answer: 接受新安全判据，仅准备收尾B'}
            and type(acceptance['accepted']) is bool, 'owner V2 decision differs; not an execution grant')
    require(freeze['spec_sha256'] == digest(spec) and freeze['script_sha256'] == script_sha
            and freeze['decision_sha256'] == DECISION_SHA and freeze['acceptance_sha256'] == digest(acceptance),
            'new complete B source/decision freeze required')
    expected = {'study_id': ID, 'actor': 'repository_owner', 'approved': True,
                'spec_sha256': digest(spec), 'runtime_freeze_sha256': digest(freeze), 'scope': SCOPE}
    require(digest(approval) == digest(expected), 'separate exact B execution approval required')


def publish(name, value):
    require(name in {ID+'.admission.claim.json', ID+'.effects.claim.json', ID+'.result.json', ID+'.failure.json'},
            'fixed B evidence filename required')
    fdroot = os.open(str(STATE), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fdroot)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'private C state ownership/mode differs')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fdroot)
        with os.fdopen(fd, 'wb') as stream:
            stream.write((canonical(value)+'\n').encode()); stream.flush(); os.fsync(stream.fileno())
        os.fsync(fdroot)
    finally: os.close(fdroot)


def ledger(path):
    require(path.resolve() == path and path.is_file(), 'fixed existing ledger required')
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
    try:
        db.row_factory = sqlite3.Row; db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        return {'scene': [dict(r) for r in db.execute('SELECT document_key,revision,scene_sha256 FROM candidate_scene')],
                'read': [dict(r) for r in db.execute('SELECT * FROM c5_read')],
                'write': [dict(r) for r in db.execute('SELECT * FROM candidate_write')]}
    finally: db.close()


def validate_safety_binding(created, payload, rows, observed):
    """Pure manual Dispose admission, never authorizes a model/tool write."""
    require(created['fixture_serial'] == 268435475 and created['active_serial'] == 268435457
            and created['runtime_freeze_sha256'] == C_SHA and payload['owner_freeze_sha256'] == C_SHA
            and payload['operation'] == 'get_scene_summary' and payload['arguments'] == {}, 'original exact fixture/read scope differs')
    require(len(rows['scene']) == 1 and rows['scene'][0]['document_key'] == payload['expected']['document_key']
            and type(rows['scene'][0]['revision']) is int and rows['scene'][0]['revision'] >= 0
            and len(rows['read']) == 1 and not rows['write']
            and rows['read'][0]['request_id'] == payload['request_id'] and rows['read'][0]['state'] == 'done'
            and rows['read'][0]['payload_sha256'] == digest(payload)
            and rows['read'][0]['result_sha256'] == digest(EMPTY), 'historical single readonly ledger or document key differs')
    require(all(observed[k] is True for k in ('ui_thread', 'backend_thread', 'active_serial', 'active_content',
            'fixture_registry', 'fixture_serial', 'headless_unsaved', 'owner_document'))
            and observed['backend_closed'] is False and observed['native'] == EMPTY,
            'exact current empty disposable fixture/active/owner not verified')
    return {'historical_expected': payload['expected'], 'stored_scene': rows['scene'][0],
            'historical_atomic_matches_stored': rows['scene'][0] == payload['expected'],
            'safety_Dispose_only_not_write_authority': True}


def main():
    spec, freeze = read(ROOT/SPEC), read(ROOT/FREEZE)
    authorize(spec, freeze, read(STATE/'manual-c-cleanup-b-owner-approval.json'), read(ROOT/DECISION),
              read(ROOT/ACCEPTANCE), file_sha(Path(__file__).resolve()))
    require(file_sha(ROOT/SPEC) == freeze['spec_file_sha256'], 'new spec bytes differ')
    publish(ID+'.admission.claim.json', {'study_id': ID, 'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False})
    started = time.monotonic(); progress = {'study_id': ID, 'retired_study_id': C_ID,
            'runtime_freeze_sha256': digest(freeze), 'accepted_decision_sha256': DECISION_SHA,
            'field_remains_failure': True, 'complete_handler_absence_proven': False}
    def budget(): require(time.monotonic()-started < 180, 'logical B budget reached; not CLR preemption')
    try:
        progress['phase'] = 'frozen_files_and_retired_evidence'
        oldpath = SOURCE/'eval/c5/hostassurance-development-runtime-freeze-20261007-c.json'
        require(file_sha(oldpath) == freeze['retired_runtime_file_sha256'] and digest(read(oldpath)) == C_SHA, 'complete original C runtime differs')
        for n, sha in freeze['fixed_development_evidence'].items():
            budget(); require(file_sha(STATE/n) == sha, 'fixed retired development evidence differs')
        for n, sha in freeze['new_source_files'].items():
            budget(); require(file_sha(ROOT/n) == sha, 'new standalone B code closure differs')
        require(file_sha(STATE/'result.json') == C_RESULT_SHA, 'original C failure changed')
        helper_path = ROOT/'tools/c5_hostassurance_retired_c_cleanup.py'
        helper_spec = importlib.util.spec_from_file_location('_c5_retired_A_pure_validation_only', str(helper_path))
        helper = importlib.util.module_from_spec(helper_spec); helper_spec.loader.exec_module(helper)
        import Rhino
        matches = [(n, m, m._SESSION) for n, m in tuple(sys.modules.items())
                   if n.startswith('rhino_c5_') and getattr(m, '_SESSION', None) is not None
                   and getattr(m._SESSION, 'state', None) == STATE and m._SESSION.spec.get('probe_id') == C_ID]
        require(len(matches) == 1, 'unique retained original C owner required')
        name, package, hub = matches[0]; prefix = name+'.plugin.rhino_listener.'
        native, channel = sys.modules[prefix+'c5_research_native'], sys.modules[prefix+'c5_research_channel']
        old_scope = sys.modules[prefix+'c5_hostassurance_development_scope_c']
        _, oldfreeze, _, _, guard = old_scope.scope(SOURCE, private_prefixes=(name,), check_time=False)
        guard(); require(digest(oldfreeze) == C_SHA, 'original C source/readable-host scope differs')
        child = hub.child; q = STATE/'read-lora'
        require(child is not None and child.directory == q and child.pending is None and child.seq == 10
                and child.attached and not child.stopped and not child.close_attempted
                and hub.fixture is child.gate.backend.doc and hub.opened == ['write-base', 'write-lora', 'read-lora']
                and hub.attached and not hub.stopped and hub.seq == 4 and not hub.assurance.finished,
                'retained owner/pending/delegates differ; never guess')
        require({p.name for p in q.glob('request-*.json')} == {'request-%04d.json' % n for n in range(1,10)}
                and {p.name for p in q.glob('response-*.json')} == {'response-%04d.json' % n for n in range(1,10)}
                and not (STATE/'hub-request-0004.json').exists(), 'extra/missing requests forbid B cleanup')
        for slot in UNUSED:
            require(not (STATE/(slot+'.engine-started.claim.json')).exists() and not (STATE/slot/'engine-created.json').exists(), 'future slot may have opened')
        before = ledger(q/'fixture.sqlite3'); progress['ledger_before'] = before
        require(digest(before) == freeze['ledger_logical_rows_sha256'], 'prepared ledger rows changed before B')
        require(len(before['read']) == 1, 'one completed historical read required')
        request = read(q/'request-0009.json'); response = read(q/'response-0009.json'); created = read(q/'engine-created.json')
        payload = helper.validate_retired(read(STATE/'result.json'), created, request, response, len(before['write']), before['read'][0])
        gate_module = sys.modules[prefix+'c5_research_gate']
        require(hmac.compare_digest(request['envelope']['signature'], gate_module.signature(child.gate.secret, payload)), 'historical HMAC differs; no replay')
        progress['historical_HMAC_verified_without_replay'] = True
        progress['phase'] = 'actual_current_empty_fixture_safety_predicate'
        backend = child.gate.backend
        require(Rhino.RhinoApp.IsOnMainThread and threading.get_ident() == backend.thread, 'safe UI/backend thread required')
        active = Rhino.RhinoDoc.ActiveDoc; require(active is not None and int(active.RuntimeSerialNumber) == 268435457, 'known active document required')
        registered = Rhino.RhinoDoc.FromRuntimeSerialNumber(268435475)
        observed = {'ui_thread': bool(Rhino.RhinoApp.IsOnMainThread), 'backend_thread': threading.get_ident() == backend.thread,
                    'active_serial': int(active.RuntimeSerialNumber) == 268435457,
                    'active_content': native.active_content_digest(active) == ACTIVE_SHA,
                    'fixture_registry': registered is not None, 'fixture_serial': backend.serial == 268435475,
                    'headless_unsaved': bool(backend.doc.IsHeadless) and not backend.doc.Path,
                    'owner_document': hub.fixture is backend.doc and int(backend.doc.RuntimeSerialNumber) == 268435475,
                    'backend_closed': backend.closed}
        require(all(v is True for k,v in observed.items() if k != 'backend_closed') and observed['backend_closed'] is False, 'known disposable empty fixture scope differs')
        observed['native'] = backend.readback()
        progress['current_empty_fixture_safety_observation'] = observed
        progress['atomic_drift_retained'] = validate_safety_binding(created, payload, before, observed)
        for directory, key in [(q, 'handoff.key')]+[(STATE/s, 'handoff.key') for s in UNUSED]+[(STATE, 'hub.key')]:
            info = os.lstat(directory/key)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600, 'specified residual key metadata differs')
        require(ledger(q/'fixture.sqlite3') == before, 'ledger drift during B admission')
        budget(); publish(ID+'.effects.claim.json', {'study_id': ID, 'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False})
        progress['phase'] = 'exact_idle_detach_and_single_fixture_close'
        child.blocked = hub.blocked = True
        Rhino.RhinoApp.Idle -= child._callback; child.attached = False; progress['child_idle_exact_remove_call_completed'] = True
        Rhino.RhinoApp.Idle -= hub._callback; hub.attached = False; progress['hub_idle_exact_remove_call_completed'] = True
        budget(); child.close_attempted = True; progress['fixture_close_attempted'] = True
        progress['close_capture'] = backend.close()
        require(progress['close_capture']['fixture_registry_absent'] is True, 'single actual registry closure unknown')
        progress['phase'] = 'seven_scoped_key_file_removes'
        progress['key_absence'] = {}
        for directory, key in [(q, 'handoff.key')]+[(STATE/s, 'handoff.key') for s in UNUSED]+[(STATE, 'hub.key')]:
            budget(); progress['key_absence'][str((directory/key).relative_to(STATE))] = channel.remove_private_key(directory, key)
        require(len(progress['key_absence']) == 7 and all(v == {'key_removed': True, 'actual_absence_checked': True}
                for v in progress['key_absence'].values()), 'seven key file absences not verified')
        child.stopped = hub.stopped = True; progress['phase'] = 'existing_observer_exact_detach_and_seal'
        budget(); receipt = hub.assurance.finish(); progress['host_receipt'] = receipt
        channel.publish_json(STATE, 'host-continuity-terminal-receipt.json', receipt)
        require(hub.assurance.detached and receipt['record_count'] >= 55, 'original observer exact detach unknown')
        progress['phase'] = 'ledger_original_failure_and_active_preservation'
        progress['ledger_after'] = ledger(q/'fixture.sqlite3')
        require(progress['ledger_after'] == before and file_sha(STATE/'result.json') == C_RESULT_SHA
                and native.active_content_digest(Rhino.RhinoDoc.ActiveDoc) == ACTIVE_SHA, 'logical ledger/original failure/active changed')
        package._SESSION = None
        progress.update(status='retired_C_manual_safety_closed_not_experiment_PASS', ledger_logical_rows_preserved=True,
                        original_result_sha256=C_RESULT_SHA, fixture_registry_absent=True, whole_host_zero_effects_proven=False,
                        memory_or_external_key_copy_erasure_proven=False, model_calls=0, gpu_calls=0, holdout_calls=0,
                        tool_dispatches=0, new_subscriptions=0, atomic_snapshot_calls=0, ledger_updates=0, execution_authority=False)
        publish(ID+'.result.json', progress)
    except BaseException as exc:
        progress.update(status='manual_B_failed_retired_no_retry', error_type=type(exc).__name__, execution_authority=False)
        publish(ID+'.failure.json', progress)
        raise
    print('C5_MANUAL_B_HOST_EXTERNAL_RECEIPT '+canonical(receipt))
    print('C5_RETIRED_C_MANUAL_B_SAFETY_RESULT '+canonical(progress))


if __name__ == '__main__': main()
