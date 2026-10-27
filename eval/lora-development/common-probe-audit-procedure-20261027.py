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


def main():
    if not __debug__:
        raise RuntimeError('Assertions are required; do not use -O.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostic', action='store_true', help='Review only the separately approved single-slot diagnostic')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    package_name = 'common-state-diagnostic-package-20261027.json' if args.diagnostic else 'common-native-probe-package-20261027.json'
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
    from training.lora_common_chain import CommonChain
    from training.lora_common_wire import reparse_response, check_predecessor, user_step
    from training.c5_rhino_adapter import step_input
    from training.c5_modelbridge_joint_audit import semantic
    from training.c5_formal20_plan import validate_fixture_readback
    from training.c5_formal20_scorer import score_route, AUDIT_KEYS
    from training.c5_research_audit import _tables, audit_permission_tables
    runtime = digest(package)
    assert runtime == ('931aad6fc68afc1752c089ce6c6291e8808321d712c07f422c009a5edaef36cf' if args.diagnostic else
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
    definitions = diagnostic_probes() if args.diagnostic else public_probes()
    cases = {c['family_id']: c for c in definitions}
    contract = CommonChain(package['plan'], package['compiled'], definitions, s/'permission')
    exchanges = {}
    requests = sorted((s/'host').glob('host-*.request.json'))
    assert len(requests) <= package['capacity']['host_messages_max']
    for seq, path in enumerate(requests, 1):
        assert path.name == 'host-%04d.request.json'%seq
        req, res = read(path), read(s/'host'/('host-%04d.response.json'%seq))
        assert req == read(s/'controller'/('controller-host-%04d.request.json'%seq)) == read(s/'host'/('request-%04d.json'%seq))
        assert res == read(s/'controller'/('controller-host-%04d.response.json'%seq)) == read(s/'host'/('response-%04d.json'%seq))
        p, rp = req['payload'], res['payload']
        assert p['sequence'] == rp['sequence'] == seq and p['runtime_sha256'] == rp['runtime_sha256'] == runtime
        assert rp['slot_id'] == p['slot_id'] and rp['request_sha256'] == digest(p['request'])
        exchanges.setdefault(p['slot_id'], []).append((p['request'], rp['value'], res, seq))
    summaries, native_writes, native_reads, steps_total, seeds = [], 0, 0, 0, 0
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
            assert case['family_id'] == ('COMMON-D01' if args.diagnostic else 'COMMON-P01') and row['outcome'] == 'engineering_failure'
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
        summaries.append({'slot_id':slot,'family_id':cell['family_id'],'outcome':row['outcome'],
            'steps':len(receipts),'writes':audit['write_count'],'reads':audit['read_count'],
            'seconds_including_cleanup':e['slot_elapsed_seconds_including_cleanup'],
            'evidence_sha256':digest(e),'original_score_recomputed':e['error_type'] is None,'cleanup_verified':True,
            'actual_scene_and_successor_input_verified':e['error_type'] is None,
            'continuity_failure':continuity_failure,'fingerprint_review':fingerprint_review,
            'execution_status_preserved':e['execution'],'permission_and_native_sqlite_verified':True})
    if args.diagnostic:
        assert native_writes == 1 and native_reads in (0,1) and steps_total == 1+native_reads and seeds == 7
    else:
        assert (native_writes,native_reads,steps_total,seeds) == (3,1,4,14)
    assert len(list((s/'controller').glob('*.model.json'))) == steps_total
    assert inventory(state) == inventory(backup) == (original,raw_bytes)
    report = {'date':'2026-10-27','package_sha256':runtime,'source_inventory_sha256':digest(package['source_files']),
        'executed_ci_commit':'d46dc568d4563255db2a7b3097667b5e81a08c3c' if args.diagnostic else '056978e5a209f96987e7c0d76436aa999e95f3e6',
        'ci_run_id':40446893205 if args.diagnostic else 40442746428,
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
