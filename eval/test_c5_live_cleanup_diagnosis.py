"""Synthetic readonly diagnosis orchestration; no real C directory or Rhino."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import c5_retired_c_live_diagnosis as diag


class Live:
    def __init__(self, bad=None):
        self.bad, self.calls = bad, []
    def call(self, name, value):
        self.calls.append(name)
        if self.bad == name+'_unknown':
            raise RuntimeError('synthetic unknown')
        return value
    def ui_thread(self): return self.call('ui', self.bad != 'ui_false')
    def active(self): return self.call('active', None if self.bad == 'active_absent' else SimpleNamespace(serial=268435457))
    def serial(self, doc): return self.call('serial', 999 if self.bad == 'serial' else doc.serial)
    def active_digest(self, doc): return self.call('active_digest', 'f'*64 if self.bad == 'active_digest' else diag.ACTIVE_SHA)
    def fixture(self): return self.call('registry', None if self.bad == 'fixture_absent' else SimpleNamespace(serial=268435475))
    def headless_unsaved(self, doc): return self.call('headless', self.bad != 'headless')
    def backend_doc_serial_matches(self): return self.call('backend_serial', self.bad != 'backend_serial')
    def readback(self): return self.call('geometry', {'groups': {}, 'objects': [], 'unit': 'Millimeters'})
    def scene_digest(self): return self.call('scene_digest', diag.HISTORICAL['scene_sha256'])


def cached():
    return {'backend_thread_matches': True, 'backend_closed': False, 'hub_fixture_matches_backend': True,
            'backend_serial_matches': True, 'atomic_document_key_matches_history': True}


def run(live, c=None, ledger=None):
    return diag.observe(live, cached() if c is None else c,
                        {'scene_rows': [diag.HISTORICAL]} if ledger is None else ledger, lambda: None)


def test_complete_synthetic_reads_are_not_cleanup_authority_or_atomic_snapshot():
    live = Live(); result = run(live)
    assert result['checks']['fixture_geometry_summary']['value']['empty'] is True
    assert result['checks']['current_scene_matches_history']['value'] is True
    assert live.calls.count('geometry') == live.calls.count('scene_digest') == 1
    assert live.calls.count('active_digest') == 2
    assert 'not_cleanup_authority' in result['live_read_stop_reason']
    json.dumps(result)  # No live document object can escape into evidence.


@pytest.mark.parametrize('bad', ['ui_false', 'ui_unknown', 'active_absent', 'active_unknown', 'serial',
                                'active_digest', 'active_digest_unknown', 'fixture_absent', 'registry_unknown',
                                'headless', 'backend_serial'])
def test_wrong_or_unknown_prerequisite_never_reads_geometry(bad):
    live = Live(bad); result = run(live)
    assert 'geometry' not in live.calls and 'scene_digest' not in live.calls
    assert result['live_read_stop_reason'] != 'bounded_read_sequence_finished_not_cleanup_authority'
    if bad.startswith('ui'):
        assert live.calls == ['ui']
    if bad.endswith('_unknown') and bad not in {'ui_unknown'}:
        assert any(v.get('status') == 'unknown_no_retry' for v in result['checks'].values())
    json.dumps(result)


@pytest.mark.parametrize('key,value', [('backend_thread_matches', False), ('backend_closed', True),
                                     ('hub_fixture_matches_backend', False), ('backend_serial_matches', False)])
def test_cached_owner_mismatch_never_serializes_fixture(key, value):
    c = cached(); c[key] = value; live = Live(); run(live, c)
    assert 'geometry' not in live.calls and 'scene_digest' not in live.calls


def test_geometry_unknown_stops_without_digest_or_second_try():
    live = Live('geometry_unknown'); result = run(live)
    assert live.calls.count('geometry') == 1 and 'scene_digest' not in live.calls
    assert result['checks']['fixture_geometry_summary']['status'] == 'unknown_no_retry'


def test_stored_revision_difference_is_observed_not_rewritten():
    value = {'scene_rows': [{**diag.HISTORICAL, 'revision': 1}]}; before = copy.deepcopy(value)
    result = run(Live(), ledger=value)
    assert result['checks']['stored_scene_matches_history']['value'] is False and value == before


def test_budget_failure_preserves_already_observed_fields_without_a_retry():
    calls, checks = [], {}
    def budget():
        calls.append(True)
        if len(calls) == 2: raise RuntimeError('synthetic budget')
    live = Live()
    with pytest.raises(RuntimeError):
        diag.observe(live, cached(), {'scene_rows': [diag.HISTORICAL]}, budget, checks=checks)
    assert checks['rhino_ui_thread_flag'] == {'status': 'observed', 'value': True}
    assert live.calls == ['ui']


@pytest.mark.parametrize('mutation', [None, 'old_grant', 'integer_approval', 'bad_script', 'model', 'snapshot', 'cleanup'])
def test_new_exact_readonly_grant_required(mutation):
    s = diag.read(Path(__file__).resolve().parents[1]/diag.SPEC)
    f = {'study_id': diag.ID, 'spec_sha256': diag.digest(s), 'script_sha256': 'a'*64,
         'retired_runtime_canonical_sha256': diag.C_SHA, 'retired_runtime_file_sha256': diag.C_FILE_SHA}
    a = {'study_id': diag.ID, 'actor': 'repository_owner', 'approved': True,
         'spec_sha256': diag.digest(s), 'runtime_freeze_sha256': diag.digest(f), 'scope': diag.SCOPE}
    script = 'a'*64
    if mutation == 'old_grant': a['study_id'] = 'C5SAFE-HOSTASSURANCE-C-20261007-A'
    elif mutation == 'integer_approval': a['approved'] = 1
    elif mutation == 'bad_script': script = 'b'*64
    elif mutation == 'model': s['model_calls'] = 1
    elif mutation == 'snapshot': s['atomic_snapshot_calls'] = 1
    elif mutation == 'cleanup': s['cleanup_authorized'] = True
    if mutation is None: diag.authorize(s, f, a, script)
    else:
        with pytest.raises(RuntimeError): diag.authorize(s, f, a, script)


def test_admission_is_durable_one_use_and_never_overwritten(tmp_path, monkeypatch):
    tmp_path.chmod(0o700); monkeypatch.setattr(diag, 'STATE', tmp_path)
    name = diag.ID+'.admission.claim.json'; diag.publish(name, {'synthetic': True})
    before = (tmp_path/name).read_bytes()
    with pytest.raises(FileExistsError): diag.publish(name, {'synthetic': False})
    assert (tmp_path/name).read_bytes() == before


def test_readonly_sqlite_does_not_update_scene_revision(tmp_path):
    import sqlite3
    p = tmp_path/'synthetic.sqlite3'; db = sqlite3.connect(p)
    db.executescript('CREATE TABLE candidate_scene(document_key TEXT,revision INTEGER,scene_sha256 TEXT); CREATE TABLE c5_read(request_id TEXT,payload_sha256 TEXT,state TEXT,result_sha256 TEXT); CREATE TABLE candidate_write(state TEXT);')
    db.execute('INSERT INTO candidate_scene VALUES(?,?,?)', ('a'*64, 1, 'b'*64)); db.commit(); db.close()
    before = p.read_bytes(); result = diag.ledger_readonly(p)
    assert result['scene_rows'][0]['revision'] == 1 and p.read_bytes() == before


def test_live_entry_import_is_inert_and_has_no_snapshot_or_mutation_calls():
    import ast
    source = Path(diag.__file__).read_text(); tree = ast.parse(source)
    assert 'Rhino' not in diag.__dict__ and 'torch' not in diag.__dict__
    forbidden = {'snapshot', 'dispatch', 'Dispose', 'unsubscribe', 'remove_private_key', 'InvokeOnUiThread'}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in forbidden for n in ast.walk(tree))
    assert not any(isinstance(n, ast.AugAssign) for n in ast.walk(tree))
