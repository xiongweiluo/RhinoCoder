#! python 3
"""Separately approved one-use READONLY diagnosis; never a cleanup retry.

No effects on import. No subscription, model, tool, close, key access or
atomic.snapshot(): the latter can UPDATE candidate_scene. Only the fixed
retired C document may be read, after UI-thread/owner/active safety checks.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import threading
import time

ID = 'C5DIAG-HOSTASSURANCE-C-20261007-A'
C_ID = 'C5DEV-HOSTASSURANCE-20261007-C'
STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-state-20261007-C')
SOURCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-source-20261007-C')
ROOT = Path(__file__).resolve().parents[1]
SPEC = 'eval/c5/hostassurance-c-live-diagnosis-spec-20261007-a.json'
FREEZE = 'eval/c5/hostassurance-c-live-diagnosis-runtime-20261007-a.json'
OLD_FREEZE = 'eval/c5/hostassurance-development-runtime-freeze-20261007-c.json'
C_SHA = 'bbbbca84474d5cd397f2e011775cb17b50f6f4a7328c6cee339a4aedf13090d1'
C_FILE_SHA = 'dc9a6708843bba203181c56a6f16d0210e90bc506d3226e5a7b10be023bc3a9a'
C_RESULT_SHA = '6093aa3ae6e25f31ecaaad551c368a919d499ff2e6c8aa57d674910295b3c3a9'
ACTIVE_SHA = 'de8fa7924ad4cf7fbeffdbe982f0b559a77eca7a8cf1f24175df642404ec6cfa'
SCOPE = 'retired C only; decomposed readonly live checks, no snapshot transaction, cleanup, key access, subscription, model or holdout'
HISTORICAL = {'document_key': 'd4847d190fd28470173a34f6aab7b963ed961caf2efb029a8d47a70ffec1227c',
              'revision': 0, 'scene_sha256': '1a22822c3e897798767fa78730a0cdd8b41ac40feb18f6b7b8ed590604dae72b'}
ZERO = ('model_calls', 'gpu_calls', 'holdout_calls', 'tool_dispatches', 'fixture_creates', 'fixture_closes',
        'key_reads', 'key_removes', 'new_subscriptions', 'delegate_removes', 'atomic_snapshot_calls', 'ledger_updates')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    require(path.is_absolute() and path.resolve() == path and path.is_file(), 'fixed regular file required')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= 4194304, 'bounded fixed JSON required')
    def pairs(rows):
        value = {}
        for k, v in rows:
            require(k not in value, 'duplicate JSON field')
            value[k] = v
        return value
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def authorize(spec, freeze, approval, script_sha):
    require(spec['study_id'] == freeze['study_id'] == ID and spec['retired_study_id'] == C_ID
            and spec['retired_runtime_sha256'] == C_SHA and spec['historical_expected_state'] == HISTORICAL
            and spec['fixture_serial'] == 268435475 and spec['active_serial'] == 268435457
            and spec['active_content_sha256'] == ACTIVE_SHA and spec['logical_budget_seconds'] == 180
            and all(type(spec[k]) is int and spec[k] == 0 for k in ZERO)
            and spec['claim_before_Rhino_import_or_live_inspection'] is True
            and spec['replay_allowed'] is False and spec['cleanup_authorized'] is False
            and spec['no_UI_thread_marshalling_or_callbacks'] is True, 'exact readonly diagnosis scope required')
    require(freeze['spec_sha256'] == digest(spec) and freeze['script_sha256'] == script_sha
            and freeze['retired_runtime_canonical_sha256'] == C_SHA
            and freeze['retired_runtime_file_sha256'] == C_FILE_SHA, 'complete diagnosis freeze differs')
    expected = {'study_id': ID, 'actor': 'repository_owner', 'approved': True,
                'spec_sha256': digest(spec), 'runtime_freeze_sha256': digest(freeze), 'scope': SCOPE}
    require(digest(approval) == digest(expected), 'new direct exact diagnosis approval required')


def publish(name, value):
    """Fixed evidence-only durable O_EXCL: existing name can never be replaced."""
    require(name in {ID+'.admission.claim.json', ID+'.result.json', ID+'.failure.json'}, 'fixed diagnostic evidence name required')
    root = os.open(str(STATE), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(root)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'private state ownership/mode differs')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
        with os.fdopen(fd, 'wb') as stream:
            stream.write((canonical(value)+'\n').encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(root)
    finally:
        os.close(root)


def ledger_readonly(path):
    require(path.resolve() == path and path.is_file(), 'fixed existing ledger required')
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        return {'scene_rows': [dict(r) for r in db.execute('SELECT document_key,revision,scene_sha256 FROM candidate_scene')],
                'read_rows': [dict(r) for r in db.execute('SELECT request_id,payload_sha256,state,result_sha256 FROM c5_read')],
                'write_rows': [dict(r) for r in db.execute('SELECT * FROM candidate_write')]}
    finally:
        db.close()


def observe(live, cached, ledger, budget, *, checks=None):
    """Pure injectable orchestration; each allowed read once, no fallback/retry."""
    checks = {} if checks is None else checks
    def sample(name, fn):
        budget()
        try:
            value = fn()
            checks[name] = {'status': 'observed', 'value': value}
            return value
        except BaseException as exc:
            checks[name] = {'status': 'unknown_no_retry', 'error_type': type(exc).__name__}
            return None
    checks['cached_owner'] = cached
    checks['stored_scene_matches_history'] = {'status': 'observed', 'value': ledger['scene_rows'] == [HISTORICAL]}
    if sample('rhino_ui_thread_flag', live.ui_thread) is not True or cached['backend_thread_matches'] is not True:
        return {'checks': checks, 'live_read_stop_reason': 'not_safe_UI_owner_thread_no_document_reads'}
    active = sample('active_document_present', live.active)
    # Do not serialize a different user document. Keep objects only in memory.
    if checks['active_document_present']['status'] == 'unknown_no_retry':
        return {'checks': checks, 'live_read_stop_reason': 'active_lookup_unknown'}
    if active is None:
        checks['active_document_present'] = {'status': 'observed', 'value': False}
        return {'checks': checks, 'live_read_stop_reason': 'active_absent_or_unknown'}
    checks['active_document_present'] = {'status': 'observed', 'value': True}
    if sample('active_serial_matches', lambda: live.serial(active) == 268435457) is not True:
        return {'checks': checks, 'live_read_stop_reason': 'active_identity_differs_no_geometry_reads'}
    before = sample('active_content_sha256_before', lambda: live.active_digest(active))
    if before is None:
        return {'checks': checks, 'live_read_stop_reason': 'active_digest_unknown'}
    checks['active_content_matches'] = {'status': 'observed', 'value': before == ACTIVE_SHA}
    if before != ACTIVE_SHA:
        return {'checks': checks, 'live_read_stop_reason': 'active_content_differs_no_fixture_geometry_reads'}
    fixture = sample('fixture_registry_present', live.fixture)
    if checks['fixture_registry_present']['status'] == 'unknown_no_retry':
        return {'checks': checks, 'live_read_stop_reason': 'registry_lookup_unknown'}
    if fixture is None:
        checks['fixture_registry_present'] = {'status': 'observed', 'value': False}
        return {'checks': checks, 'live_read_stop_reason': 'fixture_absent_or_unknown'}
    checks['fixture_registry_present'] = {'status': 'observed', 'value': True}
    if sample('fixture_serial_matches', lambda: live.serial(fixture) == 268435475) is not True:
        return {'checks': checks, 'live_read_stop_reason': 'fixture_identity_differs'}
    if sample('fixture_headless_unsaved', lambda: live.headless_unsaved(fixture)) is not True:
        return {'checks': checks, 'live_read_stop_reason': 'fixture_not_known_headless_unsaved'}
    if cached['backend_closed'] is not False or cached['hub_fixture_matches_backend'] is not True or cached['backend_serial_matches'] is not True:
        return {'checks': checks, 'live_read_stop_reason': 'cached_fixture_owner_state_differs'}
    if sample('backend_document_serial_matches', live.backend_doc_serial_matches) is not True:
        return {'checks': checks, 'live_read_stop_reason': 'backend_document_identity_differs'}
    def geometry_summary():
        value = live.readback()
        return {'empty': value == {'groups': {}, 'objects': [], 'unit': 'Millimeters'},
                'object_count': len(value['objects']), 'group_count': len(value['groups']), 'sha256': digest(value)}
    if sample('fixture_geometry_summary', geometry_summary) is None:
        return {'checks': checks, 'live_read_stop_reason': 'geometry_read_unknown_no_further_reads'}
    current_sha = sample('current_frozen_scene_digest', live.scene_digest)
    if current_sha is None:
        return {'checks': checks, 'live_read_stop_reason': 'scene_digest_unknown_no_further_reads'}
    checks['current_scene_matches_history'] = {'status': 'observed', 'value': current_sha == HISTORICAL['scene_sha256']}
    checks['current_scene_matches_stored'] = {'status': 'observed', 'value': len(ledger['scene_rows']) == 1
                                            and current_sha == ledger['scene_rows'][0]['scene_sha256']}
    after = sample('active_content_sha256_after', lambda: live.active_digest(active))
    if after is not None:
        checks['active_content_before_after_same'] = {'status': 'observed', 'value': before == after == ACTIVE_SHA}
    return {'checks': checks, 'live_read_stop_reason': 'bounded_read_sequence_finished_not_cleanup_authority'}


def main():
    spec, freeze = read(ROOT/SPEC), read(ROOT/FREEZE)
    approval = read(STATE/'hostassurance-c-live-diag-owner-approval.json')
    authorize(spec, freeze, approval, file_sha(Path(__file__).resolve()))
    require(file_sha(ROOT/SPEC) == freeze['spec_file_sha256'], 'exact new spec bytes differ')
    # Sticky admission precedes Rhino import, source/ledger and all live reads.
    publish(ID+'.admission.claim.json', {'study_id': ID, 'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False})
    started = time.monotonic()
    progress = {'study_id': ID, 'runtime_freeze_sha256': digest(freeze), 'cleanup_authorized': False}
    def budget():
        require(time.monotonic()-started < 180, 'logical diagnosis budget reached; not CLR preemption')
    try:
        progress['phase'] = 'verify_original_frozen_source_and_readable_host'
        old = read(SOURCE/OLD_FREEZE)
        require(file_sha(SOURCE/OLD_FREEZE) == C_FILE_SHA and digest(old) == C_SHA,
                'complete original C runtime changed')
        for name, sha in old['source_files'].items():
            budget()
            require(file_sha(SOURCE/name) == sha, 'original source bytes differ')
        for name, sha in old['frozen_observed_host_files'].items():
            budget()
            require(file_sha(Path(name)) == sha, 'known readable host bytes differ')
        progress['phase'] = 'verify_retired_failure_and_historical_binding'
        require(file_sha(STATE/'result.json') == C_RESULT_SHA, 'original C failure changed')
        require(file_sha(STATE/'manual-c-cleanup-attempt-observed.json') == freeze['cleanup_A_observation_sha256'],
                'retired cleanup A observation changed')
        p = read(STATE/'read-lora/request-0009.json')['envelope']['payload']
        require(p['expected'] == HISTORICAL and p['owner_freeze_sha256'] == C_SHA
                and p['operation'] == 'get_scene_summary', 'historical development request differs')
        progress['phase'] = 'inspect_unique_retained_cached_owner'
        matches = [(n, m, m._SESSION) for n, m in tuple(sys.modules.items())
                   if n.startswith('rhino_c5_') and getattr(m, '_SESSION', None) is not None
                   and getattr(m._SESSION, 'state', None) == STATE and m._SESSION.spec.get('probe_id') == C_ID]
        require(len(matches) == 1, 'unique retained original C owner required')
        name, package, hub = matches[0]
        child = hub.child
        require(child is not None and child.directory == STATE/'read-lora' and child.pending is None,
                'known idle retained child required; no pending operation diagnosis')
        backend, atomic = child.gate.backend, child.gate.atomic
        namespace = name+'.plugin.rhino_listener.'
        native = sys.modules[namespace+'c5_research_native']
        atomic_module = sys.modules[namespace+'candidate_atomic_gate']
        require(Path(native.__file__) == SOURCE/'plugin/rhino_listener/c5_research_native.py'
                and Path(atomic_module.__file__) == SOURCE/'plugin/rhino_listener/candidate_atomic_gate.py'
                and file_sha(Path(native.__file__)) == old['source_files']['plugin/rhino_listener/c5_research_native.py']
                and file_sha(Path(atomic_module.__file__)) == old['source_files']['plugin/rhino_listener/candidate_atomic_gate.py'],
                'retained readonly helper file identities differ')
        cached = {'backend_thread_matches': threading.get_ident() == backend.thread,
                  'backend_closed': backend.closed, 'backend_serial_matches': backend.serial == 268435475,
                  'hub_fixture_matches_backend': hub.fixture is backend.doc,
                  'atomic_document_key_matches_history': atomic.document_key == HISTORICAL['document_key'],
                  'child_idle_attached_flag': child.attached, 'hub_idle_attached_flag': hub.attached,
                  'observer_finished_flag': hub.assurance.finished}
        ledger_path = STATE/'read-lora/fixture.sqlite3'
        progress['phase'] = 'readonly_ledger_before'
        before = ledger_readonly(ledger_path)
        progress['phase'] = 'actual_host_version_then_decomposed_reads'
        import Rhino
        require(sys.version_info[:2] == (3, 9) and str(Rhino.RhinoApp.Version) == '8.21.25188.17002', 'actual host version differs')
        class LiveReads:
            def ui_thread(self):
                value = Rhino.RhinoApp.IsOnMainThread
                require(type(value) is bool, 'actual UI flag is not a boolean')
                return value
            def active(self): return Rhino.RhinoDoc.ActiveDoc
            def serial(self, doc): return int(doc.RuntimeSerialNumber)
            def active_digest(self, doc): return native.active_content_digest(doc)
            def fixture(self): return Rhino.RhinoDoc.FromRuntimeSerialNumber(268435475)
            def headless_unsaved(self, doc): return bool(doc.IsHeadless) and not doc.Path
            def backend_doc_serial_matches(self): return int(backend.doc.RuntimeSerialNumber) == 268435475
            def readback(self): return backend.readback()
            def scene_digest(self): return atomic_module.rhino_scene_digest(backend.doc)
        progress['checks'] = {}
        progress.update(observe(LiveReads(), cached, before, budget, checks=progress['checks']))
        budget()
        progress['phase'] = 'readonly_ledger_after_and_preservation'
        after = ledger_readonly(ledger_path)
        progress.update(status='readonly_diagnosis_observed_not_cleanup',
                        ledger_logical_rows_before_after_same=before == after,
                        stored_scene_rows=before['scene_rows'], historical_expected_state=HISTORICAL,
                        original_result_sha256_after=file_sha(STATE/'result.json'),
                        whole_host_zero_effects_proven=False, execution_authority=False,
                        **{k: 0 for k in ZERO})
        require(before == after and progress['original_result_sha256_after'] == C_RESULT_SHA,
                'ledger logical rows or original result changed during diagnosis; preserve uncertainty')
        publish(ID+'.result.json', progress)
    except BaseException as exc:
        progress.update(status='diagnosis_failed_retired_no_retry', error_type=type(exc).__name__, execution_authority=False)
        publish(ID+'.failure.json', progress)
        raise
    print('C5_RETIRED_C_READONLY_DIAGNOSIS '+canonical(progress))


if __name__ == '__main__':
    main()
