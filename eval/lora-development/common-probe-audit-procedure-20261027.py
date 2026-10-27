"""Post-run CPU review of the exact approved public probe package only.

No model, Rhino, network, old evidence, authority writer, retry or new task.
Audit SQLite/WAL copies; keep the stopped original and one bounded backup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


def fingerprint_changes(records, before_sha, after_sha):
    """Explain recorded components, without inferring who caused a change."""
    by_hash = {}
    for sequence, record in enumerate(records, 1):
        assert record['sequence'] == sequence
        components = record['components']; sha = record['scene_sha256']
        assert set(components) == {'document_settings_sha256', 'process_next_object_serial',
                                  'document_next_undo_serial', 'layers_sha256', 'objects'}
        assert sha not in by_hash or by_hash[sha] == components
        by_hash[sha] = components
    before, after = by_hash[before_sha], by_hash[after_sha]
    changed = [k for k in before if before[k] != after[k]]
    objects = []
    for identity in sorted(set(before['objects']) | set(after['objects'])):
        a, b = before['objects'].get(identity), after['objects'].get(identity)
        if a != b:
            objects.append({'identity_sha256': identity,
                            'fields': ['membership'] if a is None or b is None else [k for k in a if a[k] != b[k]]})
    return {'changed_components': changed, 'changed_objects': objects,
            'process_serial_before': before['process_next_object_serial'],
            'process_serial_after': after['process_next_object_serial'],
            'document_undo_before': before['document_next_undo_serial'],
            'document_undo_after': after['document_next_undo_serial'],
            'change_origin_proven': False}



def review_document_scope(fixture, read, captures, receipts, capacity, events):
    """Strict positive-path review; missing/partial evidence refuses verification.

    A startup/cleanup failure retains its raw failure record and is reported as
    incomplete; this function cannot turn missing evidence into success.
    """
    proof = read(fixture/'scope-check.json')
    assert proof['status'] == 'passed' and proof['fixed_native_operations'] == 3
    assert proof['other_document_did_not_change_identity'] and proof['owned_add_delete_aba_rejected']
    assert proof['stale_dispatch_calls'] == 0
    assert read(fixture/'scope-helper-created.json')['serial'] != read(fixture/'created.json')['serial']
    helper = read(fixture/'scope-helper-result.json')
    assert helper['owned_fingerprint_unchanged'] and helper['process_serial_after'] > helper['process_serial_before']
    assert read(fixture/'scope-helper-close.json')['fixture_registry_absent'] is True
    for name, expected in (
        ('scope-helper-add.claim.json', {'action':'AddPoint','point':[0,0,0]}),
        ('scope-owned-add.claim.json', {'action':'AddPoint','point':[0,0,0]}),
        ('scope-owned-delete.claim.json', {'action':'Delete','target':'new_scope_point'})):
        assert read(fixture/name) == expected
    closed = read(fixture/'document-clock-close.json')
    assert closed['removal_verified'] and not closed['faults'] and closed['exact_delegates_removed'] == sorted(events)
    assert set(closed['counts']) == set(events) and closed['epoch'] == sum(closed['counts'].values())
    assert 0 < proof['epoch'] <= closed['epoch'] <= capacity['document_events_max']
    assert proof['clock_counts']['AddRhinoObject'] >= 1 and proof['clock_counts']['DeleteRhinoObject'] >= 1
    files = sorted(fixture.glob('fingerprint-*.json'))
    assert 0 < len(files) <= capacity['fingerprint_records_max']
    hashes, previous_epoch = {}, -1
    for index, path in enumerate(files, 1):
        record = read(path); comp = record['components']; sha = record['scene_sha256']
        assert path.name == 'fingerprint-%04d.json'%index and record['sequence'] == index
        assert set(comp) == {'document_settings_sha256','document_mutation_clock','document_next_undo_serial','layers_sha256','objects'}
        epoch = comp['document_mutation_clock']
        assert epoch['schema'] == 'document_mutation_v1' and previous_epoch <= epoch['epoch'] <= closed['epoch']
        previous_epoch = epoch['epoch']
        assert sha not in hashes or hashes[sha] == comp
        hashes[sha] = comp
    required = {v['state']['scene_sha256'] for v in captures}
    required.update(r[k]['scene_sha256'] for r in receipts for k in ('before_state','after_state'))
    assert required <= set(hashes)
    return {'scope_checks_verified':True,'cleanup_verified':True,'fingerprint_records':len(files),
            'all_captured_and_receipt_states_covered':True,'event_counts':closed['counts'],
            'historical_counter_origin_proven':False,'all_native_event_types_validated':False}


def review_document_scope_open_stop(fixture, read, evidence, history, events):
    """Audit the observed missing-event stop without passing the candidate.

    Preserve the controller's not_verified/effect_known=false classifications.
    The verified source fails at this point only after the three fixed setup
    operations and content-restoration assertions returned. No task was sent.
    """
    assert [req['action'] for req,_,_,_ in history] == ['open','close','stop']
    failed, closed, stopped = [value for _,value,_,_ in history]
    assert failed['status'] == 'host_failure_no_retry' and failed['action'] == 'open'
    assert failed['effect_state'] == 'unknown' and failed['cleanup_verified'] is False
    assert failed['failure']['stage'] == 'host_open' and failed['failure']['message'] == 'ABA event bridge missing'
    assert [(f['stage'],f['message']) for f in evidence['failures']] == [
        ('fixture_open','host effect unknown; stop batch'), ('evidence_verification','fixture lifecycle differs')]
    assert evidence['steps'] == [] and evidence['initial_native'] is None and evidence['final_native'] is None
    assert evidence['score'] is None and evidence['close'] == closed and evidence['stop'] == stopped
    assert evidence['execution'] == {'evidence_integrity':'not_verified','fixture_cleanup':'verified',
        'model_request':'not_sent','native_effect':'none','resume_eligible':False}
    created, helper = read(fixture/'created.json'), read(fixture/'scope-helper-created.json')
    assert created['serial'] != helper['serial'] and closed['fixture_serial'] == created['serial']
    assert closed['status'] == 'closed' and closed['fixture_registry_absent'] is True
    assert closed['readback_error'] is None and not closed['existing_document_content_read']
    assert closed['fixture_before_close_native'] == {'groups':{},'objects':[],'unit':'Millimeters'}
    assert stopped['status'] == 'stopped' and stopped['host_blocked'] is True and stopped['fixture_registry_absent']
    assert stopped['ledger'] == {'candidate_write':[],'c5_read':[]}
    assert read(fixture/'scope-helper-close.json')['fixture_registry_absent'] is True
    isolated = read(fixture/'scope-helper-result.json')
    assert isolated['owned_fingerprint_unchanged'] is True and isolated['process_serial_after'] > isolated['process_serial_before']
    for name, expected in (
        ('scope-helper-create.claim.json', {'action':'new_headless_document'}),
        ('scope-helper-add.claim.json', {'action':'AddPoint','point':[0,0,0]}),
        ('scope-owned-add.claim.json', {'action':'AddPoint','point':[0,0,0]}),
        ('scope-owned-delete.claim.json', {'action':'Delete','target':'new_scope_point'})):
        assert read(fixture/name) == expected
    clock = read(fixture/'document-clock-close.json')
    assert clock['removal_verified'] and not clock['faults'] and clock['exact_delegates_removed'] == sorted(events)
    assert clock['epoch'] == 0 and clock['counts'] == dict.fromkeys(events, 0)
    assert not (fixture/'scope-check.json').exists() and not list(fixture.glob('seed-*.json'))
    files = sorted(fixture.glob('fingerprint-*.json'))
    assert [p.name for p in files] == ['fingerprint-0001.json']
    first = read(files[0]); assert first['sequence'] == 1
    assert first['components']['document_mutation_clock'] == {'schema':'document_mutation_v1','epoch':0}
    assert first['components']['objects'] == {}
    return {'native_candidate_accepted':False,'partial_failure_and_cleanup_audited':True,
        'cross_document_identity_check':True,'local_event_counter_advanced':False,
        'stale_authorization_rejection_reached':False,'task_started':False,
        'event_counts':clock['counts'],'process_serial_before':isolated['process_serial_before'],
        'process_serial_after':isolated['process_serial_after'],'fixed_operations_reached':3,
        'operation_count_basis':'verified failure location after guarded native calls; not model-write ledger',
        'original_execution_classification_preserved':True}



def review_controlled_snapshot(fixture, read, captures, receipts, capacity, fixed_ledger):
    """Positive-path audit. Partial/missing evidence never becomes a pass."""
    proof = read(fixture/'snapshot-check.json')
    assert proof['status'] == 'passed' and proof['fixed_native_operations'] == 2
    assert proof['state_contract'] == 'controlled_snapshot_v1' and proof['controlled_aba_rejected']
    assert proof['stale_dispatch_calls'] == 0 and proof['external_aba_detection'] is False and proof['content_restored']
    states = proof['states']; assert len(states) == 3
    assert len({r['document_key'] for r in states}) == 1
    assert states[0]['revision'] < states[1]['revision'] < states[2]['revision']
    writes = fixed_ledger['candidate_write']; assert len(writes) == 2
    by_key = {r['idempotency_key']: r for r in writes}; assert len(by_key) == 2
    for index, operation in enumerate(('fixed_add_point','fixed_delete_point')):
        claim = read(fixture/('snapshot-fixed-%d.claim.json'%index))
        result = read(fixture/('snapshot-fixed-%d.result.json'%index))
        assert claim['operation'] == operation and claim['arguments'] == {} and claim['before_state'] == states[index]
        row = by_key[claim['key']]
        assert row == result['ledger'] and row['state'] == 'done'
        assert row['document_key'] == states[index]['document_key']
        assert row['expected_revision'] == states[index]['revision'] and row['expected_sha256'] == states[index]['scene_sha256']
        expected_result = {'operation':operation,'completed':True}
        digest = lambda v: hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        assert row['request_sha256'] == digest({'operation':operation,'arguments':{}})
        assert result['result'] == expected_result and row['result_sha256'] == digest(expected_result)
        assert result['after_state'] == states[index+1]
    assert len(fixed_ledger['candidate_scene']) == 1
    final = fixed_ledger['candidate_scene'][0]
    assert {k:final[k] for k in states[-1]} == states[-1]
    hashes, count = review_controlled_fingerprints(fixture,read,captures,receipts,capacity,
        extra_hashes=[s['scene_sha256'] for s in states])
    before, after = [hashes[states[i]['scene_sha256']] for i in (0,2)]
    assert all(before[f] == after[f] for f in ('document_settings_sha256','objects','layers_sha256'))
    assert not list(fixture.glob('scope-*.json')) and not (fixture/'document-clock-close.json').exists()
    return {'controlled_aba_and_fixed_ledger_verified':True,'fixed_operations':2,
            'external_aba_detection':False,'fingerprint_records':count,
            'task_and_fixed_ledgers_separate':True,'model_quality_evidence':False}


def review_controlled_fingerprints(fixture,read,captures,receipts,capacity,*,extra_hashes=()):
    files = sorted(fixture.glob('fingerprint-*.json'))
    assert 0 < len(files) <= capacity['fingerprint_records_max']
    hashes = {}
    for index, path in enumerate(files, 1):
        record = read(path); comp = record['components']; sha = record['scene_sha256']
        assert record['sequence'] == index and path.name == 'fingerprint-%04d.json'%index
        assert set(comp) == {'document_settings_sha256','state_contract','document_next_undo_serial','layers_sha256','objects'}
        assert comp['state_contract'] == {'schema':'controlled_snapshot_v1','external_aba_detection':False}
        assert sha not in hashes or hashes[sha] == comp
        hashes[sha] = comp
    required = set(extra_hashes) | {v['state']['scene_sha256'] for v in captures}
    required.update(r[k]['scene_sha256'] for r in receipts for k in ('before_state','after_state'))
    assert required <= set(hashes)
    return hashes, len(files)


def main():
    if not __debug__:
        raise RuntimeError('Assertions are required; do not use -O.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--diagnostic', action='store_true', help='Review only the separately approved single-slot diagnostic')
    modes.add_argument('--document-scope', action='store_true', help='Review only the separately approved document-scope probe')
    modes.add_argument('--continuity', action='store_true', help='Review only the separately approved move-read-only probe')
    modes.add_argument('--snapshot', action='store_true', help='Review only the separately approved controlled-snapshot probe')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    package_name = ('common-controlled-continuity-package-20261027.json' if args.continuity else 'common-controlled-snapshot-package-20261027.json' if args.snapshot else 'common-document-scope-package-20261027.json' if args.document_scope else
                    'common-state-diagnostic-package-20261027.json' if args.diagnostic else 'common-native-probe-package-20261027.json')
    package = json.loads((root/'eval/lora-development'/package_name).read_text())
    source, state = Path(package['source_root']), Path(package['state_root'])
    sys.path.insert(0, str(source))
    from plugin.rhino_listener.c5_research_native import digest
    from plugin.rhino_listener.lora_development_admission import source_guard
    from plugin.rhino_listener.lora_common_probe import approval_record
    from training.lora_development_export import read_stable
    from training.lora_common_probe_runner import ScriptedTokenizer, IDENTITY
    from training.lora_common_probes import public_probes
    if args.diagnostic:
        from training.lora_common_probes import diagnostic_probes
    if args.document_scope:
        from training.lora_common_probes import document_scope_probes
        from plugin.rhino_listener.document_mutation_clock import EVENTS
    if args.continuity:
        from training.lora_common_probes import controlled_continuity_probes
    if args.snapshot:
        from training.lora_common_probes import controlled_snapshot_probes
    from training.lora_common_chain import CommonChain
    from training.lora_common_wire import reparse_response, check_predecessor, user_step
    from training.c5_rhino_adapter import step_input
    from training.c5_modelbridge_joint_audit import semantic
    from training.c5_formal20_plan import validate_fixture_readback
    from training.c5_formal20_scorer import score_route, AUDIT_KEYS
    from training.c5_research_audit import _tables, audit_permission_tables
    runtime = digest(package)
    assert runtime == (json.loads((root/'eval/lora-development/common-controlled-continuity-preparation-20261027.json').read_text())['package_sha256'] if args.continuity else json.loads((root/'eval/lora-development/common-controlled-snapshot-preparation-20261027.json').read_text())['package_sha256'] if args.snapshot else '25296784f4305a1045249774f0305c0c98a2f294b2e1b2f891c3137371135583' if args.document_scope else
                       '931aad6fc68afc1752c089ce6c6291e8808321d712c07f422c009a5edaef36cf' if args.diagnostic else
                       '85ba112e4aa98073760f0a73e0d10c35d1e94015bc0c57c70326ccf5382f5ebb')
    source_guard(source, package['source_files'])
    read = lambda p: json.loads(read_stable(p))
    result = read(state/'probe-result.json')
    assert result['package_sha256'] == runtime and result['model_loads'] == 0
    assert result['model_quality_evidence'] is False
    assert result['host']['status'] == 'host_stopped' and result['host']['exact_delegate_remove_returned']
    assert result['key_removal']['actual_absence_checked'] and not os.path.lexists(state/'host-secret.json')
    assert read(state/'owner-approval.json') == approval_record(package)
    assert read(state/'host/host-settlement.json') == result['host']
    assert read(state/'host/host-ready.json')['entry_return_release_observed'] is True

    def inventory(directory):
        records, total = {}, 0
        for p in sorted(directory.rglob('*')):
            info = p.lstat()
            assert not stat.S_ISLNK(info.st_mode) and info.st_uid == os.getuid()
            if p.is_dir():
                continue
            raw = read_stable(p); total += len(raw)
            assert len(records) < package['capacity']['evidence_files_max'] and total <= 1024**3
            records[p.relative_to(directory).as_posix()] = hashlib.sha256(raw).hexdigest()
        return records, total
    original, raw_bytes = inventory(state)
    backup = state.parent/'evidence-backup'
    if not backup.exists():
        backup.mkdir(mode=0o700)
        for name, sha in original.items():
            target = backup/name; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            raw = read_stable(state/name); assert hashlib.sha256(raw).hexdigest() == sha
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(raw)
    assert inventory(backup) == (original, raw_bytes)
    s = backup
    rows, views = result['rows'], package['compiled']['views']
    assert not result['failures'] and len(rows) == package['capacity']['slots']
    assert [r['identity']['slot_id'] for r in rows] == [c['slot_id'] for c in views['schedule']]
    assert not (s/'journal/selection.json').exists()
    definitions = controlled_continuity_probes() if args.continuity else controlled_snapshot_probes() if args.snapshot else document_scope_probes() if args.document_scope else diagnostic_probes() if args.diagnostic else public_probes()
    cases = {c['family_id']: c for c in definitions}
    contract = CommonChain(package['plan'], package['compiled'], definitions, s/'permission')
    snapshot_timeout = (args.snapshot and len(rows) == 1 and
        [(f['stage'],f['message']) for f in read(s/'controller'/(rows[0]['identity']['slot_id']+'.evidence.json'))['failures']]
        == [('fixture_open','host reply timeout')])
    exchanges = {}
    requests = sorted((s/'host').glob('host-*.request.json'))
    assert len(requests) <= package['capacity']['host_messages_max']
    for seq, path in enumerate(requests, 1):
        assert path.name == 'host-%04d.request.json'%seq
        req, res = read(path), read(s/'host'/('host-%04d.response.json'%seq))
        assert req == read(s/'controller'/('controller-host-%04d.request.json'%seq)) == read(s/'host'/('request-%04d.json'%seq))
        assert res == read(s/'host'/('response-%04d.json'%seq))
        if snapshot_timeout and seq == 1:
            assert not (s/'controller'/('controller-host-%04d.response.json'%seq)).exists()
        else:
            assert res == read(s/'controller'/('controller-host-%04d.response.json'%seq))
        p, rp = req['payload'], res['payload']
        assert p['sequence'] == rp['sequence'] == seq and p['runtime_sha256'] == rp['runtime_sha256'] == runtime
        assert rp['slot_id'] == p['slot_id'] and rp['request_sha256'] == digest(p['request'])
        exchanges.setdefault(p['slot_id'], []).append((p['request'], rp['value'], res, seq))
    summaries, native_writes, native_reads, steps_total, seeds = [], 0, 0, 0, 0
    scope_open_stop = False
    proof = {k: 0 if k in {'critical_safety_errors','duplicate_writes','unverified_cleanup'} else True for k in AUDIT_KEYS}
    for row, cell in zip(rows, views['schedule']):
        slot = cell['slot_id']; case = cases[cell['family_id']]; history = exchanges[slot]
        e = read(s/'controller'/(slot+'.evidence.json'))
        assert digest(e) == row['evidence_sha256'] and e['cell'] == cell
        assert e['provider_kind'] == 'scripted_probe' and e['slot_elapsed_seconds_including_cleanup'] > 0
        key = digest(row['identity'])
        assert read(s/'journal'/(key+'.result.json')) == row
        assert read(s/'journal'/(key+'.claim.json')) == {'identity': row['identity'], 'replay_allowed': False}
        fixture = s/'fixtures'/slot; created = read(fixture/'created.json')
        assert created['runtime_sha256'] == runtime and created['headless'] and not created['existing_document_content_read']
        if snapshot_timeout:
            assert [req['action'] for req,_,_,_ in history] == ['open','close','stop']
            assert history[0][1] == {'status':'opened','fixture_serial':created['serial']}
            assert e['error_type'] == 'TimeoutError' and e['steps'] == [] and e['score'] is None
            assert e['initial_native'] is None and e['final_native'] is None
            assert row['outcome'] == 'engineering_failure' and row['effect_known'] is True and row['stop_requested'] is True
            assert e['execution'] == {'evidence_integrity':'verified','fixture_cleanup':'verified',
                'model_request':'not_sent','native_effect':'none','resume_eligible':True}
            assert e['close'] == history[1][1] and e['stop'] == history[2][1]
            assert e['close']['status'] == 'closed' and e['close']['fixture_serial'] == created['serial']
            assert e['close']['fixture_registry_absent'] and e['close']['readback_error'] is None
            assert not e['close']['existing_document_content_read']
            assert e['stop'] == {'status':'stopped','ledger':{'candidate_write':[],'c5_read':[]},
                'fixture_registry_absent':True,'host_blocked':False}
            validate_fixture_readback(case,e['close']['fixture_before_close_native'])
            assert not list((s/'controller').glob('*.model.json')) and not list((s/'journal').glob('*.step-*'))
            assert len(list(fixture.glob('seed-*.claim.json'))) == len(case['fixture_recipe'])
            assert len(list(fixture.glob('seed-*.result.json'))) == len(case['fixture_recipe'])
            for i,seed in enumerate(case['fixture_recipe']):
                assert read(fixture/('seed-%02d.claim.json'%i)) == seed
                assert 'result' in read(fixture/('seed-%02d.result.json'%i)); seeds += 1
            with tempfile.TemporaryDirectory(prefix='common-snapshot-timeout-audit-') as td:
                td=Path(td).resolve()
                for directory,pattern in [(fixture,'*.sqlite3*'),(s/'permission',slot+'.consent.sqlite3*')]:
                    for path in directory.glob(pattern): (td/path.name).write_bytes(read_stable(path))
                task_tables=_tables(td/'fixture.sqlite3',('candidate_write','c5_read','candidate_scene'))
                assert task_tables == {'candidate_write':[],'c5_read':[],'candidate_scene':[]}
                assert _tables(td/(slot+'.consent.sqlite3'),('consent_requests','consent_events','c5_model_handoff')) == {
                    'consent_requests':[],'consent_events':[],'c5_model_handoff':[]}
                fixed=_tables(td/'snapshot-protection.sqlite3',('candidate_write','candidate_scene'))
            scope_review=review_controlled_snapshot(fixture,read,[],[],package['capacity'],fixed)
            observed_mtimes={n:(state/n).stat().st_mtime for n in (
                'host/host-ready.json','host/request-0001.json','host/request-0002.json',
                'fixtures/'+slot+'/created.json','host/host-0001.response.json','host/shutdown.request.json')}
            assert observed_mtimes['host/request-0002.json'] < observed_mtimes['fixtures/'+slot+'/created.json'] < observed_mtimes['host/host-0001.response.json'] < observed_mtimes['host/shutdown.request.json']
            summaries.append({'slot_id':slot,'family_id':cell['family_id'],'outcome':row['outcome'],
                'steps':0,'writes':0,'reads':0,'seconds_including_cleanup':e['slot_elapsed_seconds_including_cleanup'],
                'evidence_sha256':digest(e),'original_score_recomputed':False,'cleanup_verified':True,
                'actual_scene_and_successor_input_verified':False,'execution_status_preserved':e['execution'],
                'permission_and_native_sqlite_verified':False,'empty_task_and_consent_tables_verified':True,
                'state_contract_review':scope_review,'late_open_response_not_received_by_controller':True,
                'original_file_mtimes_observed':observed_mtimes,'mtime_is_observational_not_a_native_event_clock':True})
            continue
        if args.document_scope and history[0][1].get('status') == 'host_failure_no_retry':
            partial = review_document_scope_open_stop(fixture, read, e, history, EVENTS)
            assert row['outcome'] == 'engineering_failure' and row['effect_known'] is False
            assert not list((s/'controller').glob('*.model.json'))
            # CommonChain.start creates empty consent tables before open.
            # Existence is not a permission issue; nonempty rows would be.
            permission_files = list((s/'permission').iterdir())
            assert {p.name for p in permission_files} <= {
                slot+'.consent.sqlite3',slot+'.consent.sqlite3-wal',slot+'.consent.sqlite3-shm'}
            assert not list((s/'journal').glob('*.step-*'))
            # Read a disposable SQLite/WAL copy; the stopped original/backup
            # stay byte-identical. ResearchGate was not constructed at failure.
            with tempfile.TemporaryDirectory(prefix='common-scope-stop-audit-') as td:
                import sqlite3
                from contextlib import closing
                td = Path(td).resolve()
                for path in fixture.glob('fixture.sqlite3*'): (td/path.name).write_bytes(read_stable(path))
                for path in permission_files: (td/path.name).write_bytes(read_stable(path))
                consent = _tables(td/(slot+'.consent.sqlite3'), ('consent_requests','consent_events','c5_model_handoff'))
                assert consent == {'consent_requests':[],'consent_events':[],'c5_model_handoff':[]}
                with closing(sqlite3.connect(td/'fixture.sqlite3')) as db:
                    assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
                    assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'candidate_scene','candidate_write'}
                    assert db.execute('SELECT COUNT(*) FROM candidate_write').fetchone()[0] == 0
                    scene = db.execute('SELECT revision,scene_sha256 FROM candidate_scene').fetchall()
                    assert scene == [(0,read(fixture/'fingerprint-0001.json')['scene_sha256'])]
            summaries.append({'slot_id':slot,'family_id':cell['family_id'],'outcome':row['outcome'],
                'steps':0,'writes':0,'reads':0,'seconds_including_cleanup':e['slot_elapsed_seconds_including_cleanup'],
                'evidence_sha256':digest(e),'original_score_recomputed':False,'cleanup_verified':True,
                'actual_scene_and_successor_input_verified':False,'execution_status_preserved':e['execution'],
                'permission_and_native_sqlite_verified':False,'empty_atomic_write_table_verified':True,
                'empty_consent_tables_verified':True,
                'document_scope_review':partial})
            scope_open_stop = True
            continue
        assert history[0][0]['action'] == 'open' and history[0][1]['fixture_serial'] == created['serial']
        assert len(list(fixture.glob('seed-*.claim.json'))) == len(case['fixture_recipe'])
        assert len(list(fixture.glob('seed-*.result.json'))) == len(case['fixture_recipe'])
        for i, seed in enumerate(case['fixture_recipe']):
            assert read(fixture/('seed-%02d.claim.json'%i)) == seed
            assert 'result' in read(fixture/('seed-%02d.result.json'%i)); seeds += 1
        captures = [v for req,v,_,_ in history if req['action'] == 'capture']
        assert e['initial_native'] == captures[0]['native']
        validate_fixture_readback(case, e['initial_native'])
        receipts, previous, previous_sent, previous_obs = [], None, None, None
        assert len(e['steps']) <= case['max_steps']
        for index, step in enumerate(e['steps']):
            saved = read(s/'controller'/(slot+'-step-%d.model.json'%index))
            sent, response = saved['request'], saved['response']
            obs = reparse_response(response, sent, model_views=views['model'], runtime=runtime,
                                   identity=IDENTITY, tokenizer=ScriptedTokenizer())
            assert obs == step['observation'] and sent['step_index'] == index and not step['policy_denied']
            check_predecessor(sent, previous_sent, previous_obs)
            assert user_step(sent) == step_input(sent['task'], sent['scene'])
            capture = [(v,env) for req,v,env,_ in history if req['action'] == 'capture'
                       and digest({'capture':env, 'previous':previous}) == sent['host_evidence_sha256']]
            assert len(capture) == 1
            current, _ = capture[0]
            assert sent['scene'] == semantic(current['native']) and sent['binding'] == current['state']
            if previous is not None:
                prior = previous['envelope']['payload']['value']
                assert prior['after_state'] == current['state'] and prior['after'] == current['native']
            receipt = step['receipt']; assert receipt is not None
            matched = [(i, req, env, seq) for i,(req,v,env,seq) in enumerate(history)
                       if req['action'] == 'execute' and v == receipt]
            assert len(matched) == 1
            pos, req, env, seq = matched[0]
            assert history[pos-1][0]['action'] == 'capture'
            contract.audit_receipt(receipt, req['envelope'], obs, history[pos-1][1])
            receipts.append(receipt)
            previous = {'step_index':index,'observation':obs,'envelope':env,'request':req,'sequence':seq}
            previous_sent, previous_obs = sent, obs
            assert read(s/'journal'/(key+'.step-%d.result.json'%index))['evidence_sha256'] == digest(step)
            steps_total += 1
        assert len([req for req,_,_,_ in history if req['action'] == 'execute']) == len(receipts)
        assert [r['action'] for r,_,_,_ in history][-2:] == ['close','stop']
        assert history[-2][1] == e['close'] and history[-1][1] == e['stop']
        assert e['close']['fixture_registry_absent'] and e['stop']['fixture_registry_absent'] and not e['stop']['host_blocked']
        assert e['close']['fixture_serial'] == created['serial']
        assert e['close']['fixture_before_close_native'] == captures[-1]['native']
        # SQLite may maintain SHM metadata even in read-only mode: use disposable
        # DB/WAL copies, not the original or the retained backup.
        with tempfile.TemporaryDirectory(prefix='common-probe-audit-') as td:
            td = Path(td).resolve()
            for pattern, directory in [('fixture.sqlite3*', fixture), (slot+'.consent.sqlite3*', s/'permission')]:
                for path in directory.glob(pattern):
                    (td/path.name).write_bytes(read_stable(path))
            ledger = _tables(td/'fixture.sqlite3', ('candidate_write','c5_read'))
            consent = _tables(td/(slot+'.consent.sqlite3'), ('consent_requests','consent_events','c5_model_handoff'))
            if args.snapshot:
                for path in fixture.glob('snapshot-protection.sqlite3*'):
                    (td/path.name).write_bytes(read_stable(path))
                fixed_ledger = _tables(td/'snapshot-protection.sqlite3', ('candidate_write','candidate_scene'))
        assert ledger == e['stop']['ledger']
        audit = audit_permission_tables(consent, ledger, receipts,
            task_sha256=hashlib.sha256(case['task_text'].encode()).hexdigest(), owner_freeze_sha256=runtime)
        native_writes += audit['write_count']; native_reads += audit['read_count']
        continuity_failure = None
        if e['error_type'] is None:
            assert not e['failures'] and e['final_native'] == captures[-1]['native']
            score = score_route(case, {'family_id':cell['family_id'],'slot_id':slot,'route':'lora','steps':e['steps'],
                'initial_native':e['initial_native'],'final_native':e['final_native'],'close':'closed','stop':'stopped'}, proof)
            assert score == e['score'] and row['outcome'] == ('success' if score['outcome_correct'] else 'task_failure')
        else:
            # Preserve this actual failure; do not score the incomplete task as
            # success just because the first write and cleanup are verified.
            assert case['family_id'] == ('COMMON-B02' if args.continuity else 'COMMON-B01' if args.snapshot else 'COMMON-S01' if args.document_scope else 'COMMON-D01' if args.diagnostic else 'COMMON-P01') and row['outcome'] == 'engineering_failure'
            assert e['score'] is None and len(e['steps']) == 1 and e['final_native'] is None
            assert [(f['stage'],f['message']) for f in e['failures']] == [('step_preflight','noncontiguous native execution')]
            last = receipts[-1]; current = captures[-1]
            assert current['native'] == e['close']['fixture_before_close_native']
            if not args.diagnostic:
                assert last['after'] == current['native']
            assert last['after_state']['document_key'] == current['state']['document_key']
            assert last['after_state']['revision'] != current['state']['revision']
            assert last['after_state']['scene_sha256'] != current['state']['scene_sha256']
            continuity_failure = {'stage':'step_preflight','message':'noncontiguous native execution',
                'changed_binding_fields':['revision','scene_sha256'],'same_document':True,
                'same_semantic_and_native_readback':last['after'] == current['native'],'failed_before_next_scripted_request':True,
                'receipt_revision':last['after_state']['revision'],'next_capture_revision':current['state']['revision'],
                'which_full_digest_component_changed':'unknown; old package records only aggregate digest',
                'unknown_native_effect_not_relabelled_as_success':True}
        fingerprint_review = None
        if args.diagnostic:
            files = sorted(fixture.glob('fingerprint-*.json'))
            assert 0 < len(files) <= package['capacity']['fingerprint_records_max']
            assert [f.name for f in files] == ['fingerprint-%04d.json'%i for i in range(1,len(files)+1)]
            records = [read(f) for f in files]
            covered = {r['scene_sha256'] for r in records}
            required = {v['state']['scene_sha256'] for v in captures}
            required.update(r[k]['scene_sha256'] for r in receipts for k in ('before_state','after_state'))
            assert required <= covered
            after_write = receipts[0]['after_state']['scene_sha256']
            first_execution = next(i for i,(req,_,_,_) in enumerate(history) if req['action'] == 'execute')
            successor = next(v for req,v,_,_ in history[first_execution+1:] if req['action'] == 'capture')
            fingerprint_review = {'records':len(records),'all_captured_and_receipt_states_covered':True,
                **fingerprint_changes(records,after_write,successor['state']['scene_sha256'])}
            if continuity_failure is not None:
                continuity_failure['which_full_digest_component_changed'] = fingerprint_review['changed_components']
        scope_review = None
        if args.document_scope:
            scope_review = review_document_scope(fixture, read, captures, receipts, package['capacity'], EVENTS)
        if args.snapshot:
            scope_review = review_controlled_snapshot(fixture, read, captures, receipts, package['capacity'], fixed_ledger)
        if args.continuity:
            assert not list(fixture.glob('snapshot-*')) and not list(fixture.glob('scope-*'))
            assert not (fixture/'document-clock-close.json').exists()
            _, count = review_controlled_fingerprints(fixture,read,captures,receipts,package['capacity'])
            scope_review = {'fingerprint_records':count,'fixed_operations_repeated':0,
                'all_captured_and_receipt_states_covered':True,'external_aba_detection':False}
        summaries.append({'slot_id':slot,'family_id':cell['family_id'],'outcome':row['outcome'],
            'steps':len(receipts),'writes':audit['write_count'],'reads':audit['read_count'],
            'seconds_including_cleanup':e['slot_elapsed_seconds_including_cleanup'],
            'evidence_sha256':digest(e),'original_score_recomputed':e['error_type'] is None,'cleanup_verified':True,
            'actual_scene_and_successor_input_verified':e['error_type'] is None,
            'continuity_failure':continuity_failure,'fingerprint_review':fingerprint_review,
            'execution_status_preserved':e['execution'],'permission_and_native_sqlite_verified':True,
            **({'state_contract_review':scope_review} if args.snapshot or args.continuity else {'document_scope_review':scope_review} if args.document_scope else {})})
    if snapshot_timeout:
        assert (native_writes,native_reads,steps_total,seeds) == (0,0,0,7)
    elif scope_open_stop:
        assert (native_writes,native_reads,steps_total,seeds) == (0,0,0,0)
    elif args.diagnostic or args.document_scope or args.snapshot or args.continuity:
        assert native_writes == 1 and native_reads in (0,1) and steps_total == 1+native_reads and seeds == 7
    else:
        assert (native_writes,native_reads,steps_total,seeds) == (3,1,4,14)
    assert len(list((s/'controller').glob('*.model.json'))) == steps_total
    assert inventory(state) == inventory(backup) == (original,raw_bytes)
    prestart = None
    if args.document_scope or args.snapshot or args.continuity:
        prestart_name = 'common-controlled-continuity-prestart-20261027.json' if args.continuity else 'common-controlled-snapshot-prestart-20261027.json' if args.snapshot else 'common-document-scope-prestart-20261027.json'
        prestart = read(root/'eval/lora-development'/prestart_name)
        assert prestart['package_sha256'] == runtime and prestart['all_five_ci_successful'] is True
    report = {'date':'2026-10-27','package_sha256':runtime,'source_inventory_sha256':digest(package['source_files']),
        'executed_ci_commit':prestart['source_commit'] if prestart else 'd46dc568d4563255db2a7b3097667b5e81a08c3c' if args.diagnostic else '056978e5a209f96987e7c0d76436aa999e95f3e6',
        'ci_run_id':prestart['ci_run_id'] if prestart else 40446893205 if args.diagnostic else 40442746428,
        **({'additional_fixed_fixture_operations':3, 'isolated_documents':2,
            'native_candidate_accepted':not scope_open_stop and all(r['outcome']=='success' for r in rows),
            'audit_scope':'incomplete_native_check_failure_and_cleanup' if scope_open_stop else 'complete_probe',
            'positive_path_auditor_initial_rejection_retained':
                ["KeyError: fixture_serial; host open failed before the successful-open record",
                 "Early-stop audit initially assumed permission directory absent; actual CommonChain.start creates empty tables before open. Replaced by copy-based emptiness verification, never by accepting permission rows."] if scope_open_stop else None}
           if args.document_scope else {}),
        **({'additional_fixed_fixture_operations':2,'isolated_documents':1,
            'state_contract':'controlled_snapshot_v1','external_aba_detection':False,
            'native_candidate_accepted':all(r['outcome']=='success' for r in rows),
            'audit_scope':'late_open_timeout_fixed_checks_and_cleanup_only' if snapshot_timeout else 'complete_probe',
            'fixed_controlled_history_check_passed':True, 'move_read_validated':native_writes==native_reads==1 and all(r['outcome']=='success' for r in rows)}
           if args.snapshot else {}),
        **({'additional_fixed_fixture_operations':0,'isolated_documents':1,
            'state_contract':'controlled_snapshot_v1','external_aba_detection':False,
            'native_candidate_accepted':all(r['outcome']=='success' for r in rows),
            'audit_scope':'move_read_only_prior_fixed_check_not_repeated',
            'move_read_validated':native_writes==native_reads==1 and all(r['outcome']=='success' for r in rows)}
           if args.continuity else {}),
        'rows':summaries,'native_writes':native_writes,'native_reads':native_reads,'fixture_seed_operations':seeds,
        'host_messages':len(requests),'elapsed_seconds':result['elapsed_seconds'],'evidence_files':len(original),
        'evidence_bytes':raw_bytes,'retained_backup_copies':1,'evidence_inventory_sha256':digest(original),
        'source_verified':True,'original_and_backup_unchanged':True,'host_callback_removed':True,
        'host_secret_absence_verified':True,'host_settlement':result['host'],'model_loads':0,'gpu_calls':0,
        'historical_development_loads_retained':5,'model_quality_evidence':False,'training':False,
        'final_test_created_or_executed':False,'phase_one_complete':False,'additional_resource_actions':0,
        'actual_paid_lease_amount':None,'hmac_reverified_after_key_deletion':False,
        'whole_host_byte_closure_proven':False,
        'limitations':['scripted public mechanism only; no weight comparison or historical attribution',
            'only the reported native operations exercised; other tools rely on prior component/CPU evidence',
            'placeholder token counts do not validate real model context or latency',
            'HMAC verified live; deleted secret not recreated for post-run verification']}
    with args.output.open('x') as out:
        out.write(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('rows','native_writes','native_reads','host_messages','elapsed_seconds','evidence_files','evidence_bytes')}))


if __name__ == '__main__':
    main()
