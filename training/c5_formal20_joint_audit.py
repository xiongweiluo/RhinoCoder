"""Independent formal audit over raw private files and SQLite snapshots.

It never runs a model/tool, consumes a holdout or accepts supplied proof flags.
The custodian invokes it after execution. All scorer flags are derived here.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

from plugin.rhino_listener.c5_formal20_scope import STUDY_ID
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_formal20_plan import validate_families, slot_order, family_merkle_root, slot_order_sha256, READS
from training.c5_formal20_scorer import score_route, summarize_pairs
from training.c5_modelbridge_joint_audit import audit_model_native_chain, audit_lifecycle, semantic
from training.c5_model_transport import rebind_observation, frame
from training.c5_modelbridge_runtime import file_sha


def _sha_record(value): return hashlib.sha256(frame(value)).hexdigest()


def audit_remote(state, spec, freeze):
    stop = read_json(state, 'worker-stop-response.json')
    require(stop.get('status') == 'formal_worker_stopped' and stop.get('runtime_freeze_sha256') == digest(freeze)
        and stop.get('request_sha256') == digest({'kind': 'formal_stop', 'study_id': STUDY_ID,
            'runtime_freeze_sha256': digest(freeze)}), 'formal raw worker stop scope differs')
    require(read_json(state, 'worker-process-exit.json') == {'exit_code': 0, 'replay_allowed': False}, 'formal remote exit unknown')
    raw = stop['raw_records']
    required = {'bootstrap.json', 'loaded-runtime.json', 'worker-summary.json', 'resource-settlement.json',
        'formal20.worker-started.claim.json'}
    require(set(raw) == required, 'formal remote lifecycle population differs')
    require(raw['bootstrap.json'] == read_json(state, 'worker-bootstrap-request.json')
        and raw['bootstrap.json']['plans'] == read_json(state, 'model-plans-hashed.json')
        and raw['bootstrap.json']['started'] == read_json(state, 'formal20.started.json'), 'formal bootstrap/local claim differs')
    require(raw['formal20.worker-started.claim.json'] == {'study_id': STUDY_ID,
        'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False}, 'formal worker permanent claim differs')
    ready = read_json(state, 'worker-bootstrap-response.json')
    require(ready == {'status': 'formal_worker_ready', 'request_sha256': digest(raw['bootstrap.json']),
        'runtime_freeze_sha256': digest(freeze), 'model_identities': freeze['model_identities']}, 'formal model ready binding differs')
    assets, loaded = stop['asset_environment_preflight'], raw['loaded-runtime.json']
    require(assets['source_files'] == freeze['source_files'] and assets['source_inventory_sha256'] == freeze['source_inventory_sha256']
        and assets['fixed_public_files'] == freeze['fixed_public_files'] and assets['environment_sha256'] == freeze['environment_sha256']
        and digest(assets['environment']) == freeze['environment_sha256']
        and {'base': digest(assets['snapshot']), 'lora': assets['adapter_sha256']} == freeze['model_identities']
        and digest(assets['adapter_files']) == freeze['model_identities']['lora'], 'formal asset/environment raw inventory differs')
    require(loaded['study_id'] == STUDY_ID and loaded['environment_sha256'] == freeze['environment_sha256']
        and loaded['source_inventory_sha256'] == freeze['source_inventory_sha256'] and loaded['model_identities'] == freeze['model_identities']
        and loaded['gpu'] == 'NVIDIA GeForce RTX 3090' and loaded['default_route_changed'] is False
        and loaded['base_route'] == 'same PEFT-wrapped base with disable_adapter context'
        and loaded['base_dtype_cast'] == 'prepare_model_for_kbit_training_no_checkpoint_hooks', 'formal loaded model route differs')
    resource = raw['resource-settlement.json']; boundary = freeze['resource_boundary']
    require(stop['resource'] == resource and resource['status'] == 'formal_worker_stopped_no_replay'
        and resource['study_id'] == STUDY_ID and resource['resource_boundary_sha256'] == digest(boundary)
        and resource['replay_allowed'] is False, 'formal resource settlement binding differs')
    for k in ('elapsed_seconds_including_load_and_idle', 'cap_seconds', 'start_epoch', 'stop_epoch'):
        require(type(resource[k]) in (int, float) and math.isfinite(resource[k]), 'formal finite settlement required')
    elapsed = resource['elapsed_seconds_including_load_and_idle']
    require(0 <= elapsed <= resource['cap_seconds'] <= boundary['formal_max_seconds'] <= 10800
        and boundary['prior_cumulative_seconds'] + elapsed <= 57600
        and boundary['prior_research_seconds'] + elapsed <= 14400
        and resource['start_epoch'] <= resource['stop_epoch'] <= spec['model_generation_cutoff_epoch'], 'formal resource ceiling exceeded')
    summary = raw['worker-summary.json']
    keys = summary['attempted_keys']
    require(isinstance(keys, list) and len(keys) == len(set(keys)) == summary['requests']
        and 40 <= len(keys) <= 120 and type(summary['generation_stages']) is int
        and summary['generation_stages'] <= spec['max_generation_stages'], 'formal worker attempts/count differs')
    all_records, stages = dict(raw), 0
    for key in keys:
        export = read_json(state, key + '-remote-evidence.json')
        require(set(export) == {'status', 'request_sha256', 'key', 'records'} and export['status'] == 'formal_raw_step_evidence'
            and export['key'] == key and export['request_sha256'] == digest({'kind': 'formal_export_step',
                'study_id': STUDY_ID, 'runtime_freeze_sha256': digest(freeze), 'key': key}), 'formal export response differs')
        records = export['records']
        sent = read_json(state, key + '-model-request.json'); response = read_json(state, key + '-model-response.json')
        require(records.get(key + '-request.json') == sent and records.get(key + '-response.json') == response
            and records.get('generation-' + key + '.claim.json') == {'request_sha256': digest(sent), 'replay_allowed': False},
            'formal raw generation request/claim/response differs')
        require(key == digest({'slot': sent['slot_id'], 'step': sent['step_index'], 'freeze': digest(freeze)}),
            'formal generation key differs')
        expected = {key + '-request.json', key + '-response.json', 'generation-' + key + '.claim.json'}
        for receipt in response['generation_receipts']:
            stage = receipt['stage']; stages += 1
            attempt = {'stage': stage, 'prompt_sha256': receipt['prompt_sha256'], 'attempted': True, 'tokens': 0, 'seconds': 0.0}
            require(records.get(key + '-' + stage + '-attempt.json') == attempt
                and records.get(key + '-' + stage + '-raw.json') == receipt, 'formal raw attempt/output differs')
            expected.update({key + '-' + stage + '-attempt.json', key + '-' + stage + '-raw.json'})
        require(set(records) == expected, 'formal extra/missing remote generation records')
        require(not set(all_records) & set(records), 'formal duplicate remote evidence')
        all_records.update(records)
    require(stages == summary['generation_stages'] and set(stop['file_sha256']) == set(all_records)
        and all(stop['file_sha256'][n] == _sha_record(v) for n, v in all_records.items()), 'formal complete remote raw byte inventory differs')
    require({p.name for p in state.glob('*-model-request.json')} == {k + '-model-request.json' for k in keys}
        and {p.name for p in state.glob('*-model-response.json')} == {k + '-model-response.json' for k in keys}
        and {p.name for p in state.glob('*-remote-evidence.json')} == {k + '-remote-evidence.json' for k in keys},
        'formal extra/missing local model attempts')
    return {'generation_stages': stages, 'elapsed_seconds_including_load_and_idle': elapsed,
        'peak_allocated_bytes': summary['peak_allocated_bytes'], 'peak_reserved_bytes': summary['peak_reserved_bytes'], 'keys': keys}


def audit_native_sequence(directory, result, records):
    names = sorted(p.name for p in directory.glob('request-*.json'))
    require(names == ['request-%04d.json' % n for n in range(1, len(names) + 1)] and len(names) <= 128
        and sorted(p.name for p in directory.glob('response-*.json')) == ['response-%04d.json' % n for n in range(1, len(names) + 1)],
        'formal raw native sequence incomplete/extra')
    first = read_json(directory, 'response-0001.json')
    require(first['status'] == 'captured' and first['native'] == result['initial_native'], 'formal initial raw capture differs')
    expected = [('capture', first)]; executions = []
    prior = first
    for step, joint in zip(result['steps'], records):
        require(step['before']['state'] == prior['state'] and step['before']['native'] == prior['native'], 'formal step scene chain differs')
        expected.extend([('capture', step['before']), ('capture', step['post_model_capture'])])
        expected.extend(('capture', c) for c in joint['signing_captures'])
        if step['receipt'] is not None:
            expected.append(('execute', step['receipt']))
            prior = {'state': step['receipt']['after_state'], 'native': step['receipt']['after']}
        else: prior = step['post_model_capture']
    # The final capture and lifecycle are still raw channel responses, not result flags.
    final = read_json(directory, 'response-%04d.json' % (len(expected) + 1))
    close = read_json(directory, 'response-%04d.json' % (len(expected) + 2))
    stop = read_json(directory, 'response-%04d.json' % (len(expected) + 3))
    require(final['status'] == 'captured' and final['native'] == result['final_native']
        and final['native'] == prior['native'] and final['state'] == prior['state'], 'formal final raw capture differs')
    expected.extend([('capture', final), ('close', close), ('stop', stop)])
    require(len(expected) == len(names), 'formal hidden/extra native controls')
    for n, (kind, value) in enumerate(expected, 1):
        sent = read_json(directory, 'request-%04d.json' % n)
        raw = read_json(directory, 'response-%04d.json' % n)
        require(raw == value and sent.get('kind') == ('execute' if kind == 'execute' else 'control'), 'formal native raw action/value differs')
        if kind != 'execute':
            require(sent['envelope']['payload']['action'] == kind, 'formal native control order differs')
        else:
            require(sent['envelope']['payload'] == value['payload'], 'formal raw signed dispatch differs')
            immediate = read_json(directory, 'execute-%04d.json' % n)
            require(immediate == {k: v for k, v in value.items() if k not in {'after', 'after_state', 'immediate_after',
                'immediate_after_state', 'settling_samples', 'stable_idle_samples'}} | {'after': value['immediate_after'],
                    'after_state': value['immediate_after_state']}, 'formal immediate native execution differs')
            executions.append('execute-%04d.json' % n)
    require(sorted(p.name for p in directory.glob('execute-*.json')) == executions, 'formal extra raw native dispatch')
    return close, stop


def audit_slot(state, case, slot, result, freeze, tokenizer):
    directory = state / slot['slot_id']; task = case['task_text']; records, receipts = [], []
    require(result['family_id'] == case['family_id'] and result['route'] == slot['route'] and result['slot_id'] == slot['slot_id']
        and result['error_type'] is None and result['close'] == 'closed' and result['stop'] == 'stopped'
        and isinstance(result['steps'], list) and 1 <= len(result['steps']) <= case['max_steps'], 'formal result incomplete/wrong route')
    signing_expected, used_writes, used_reads = [], 0, 0
    for index, step in enumerate(result['steps']):
        require(step['step_index'] == index, 'formal step sequence differs')
        response = step['response']; sent, wire = response['wire_request'], response['wire_response']
        key = digest({'slot': slot['slot_id'], 'step': index, 'freeze': digest(freeze)})
        require(sent == read_json(state, key + '-model-request.json') and wire == read_json(state, key + '-model-response.json')
            and sent['slot_id'] == slot['slot_id'] and sent['route'] == slot['route'] and sent['step_index'] == index,
            'formal route/raw wire differs')
        observed = rebind_observation(wire, sent, freeze['model_identities'][slot['route']], step['before']['state'])
        require(observed == step['observation'] == response['observation'] and response['generation_receipts'] == wire['generation_receipts'],
            'formal independently reparsed observation differs')
        receipt = step['receipt']
        joint = {'capture': step['before'], 'post_model_capture': step['post_model_capture'], 'signing_captures': [],
            'request': sent, 'response': wire, 'handoff_request_id': None}
        if receipt is not None:
            require(observed['status'] == 'schema_valid_not_authorized' and step['policy_denied'] is False, 'formal rejected model dispatched')
            raw = read_json(directory, 'signing-%d.json' % index)
            require(raw['capture'] == joint['capture'] and raw['post_model_capture'] is None
                and raw['request'] == sent and raw['response'] == wire
                and raw['handoff_request_id'] == receipt['payload']['request_id'], 'formal raw consumed handoff differs')
            joint['signing_captures'] = raw['signing_captures']; joint['handoff_request_id'] = raw['handoff_request_id']
            receipts.append(receipt); signing_expected.append('signing-%d.json' % index)
            if observed['name'] in READS: used_reads += 1
            else: used_writes += 1
        elif observed['status'] == 'schema_valid_not_authorized':
            denied = (observed['name'] in READS and used_reads >= case['max_reads'] or
                observed['name'] not in READS and used_writes >= case['max_writes'])
            if 'execution_rejection' in step:
                from training.c5_formal20_prepermission import rejection
                from training.c5_formal20_plan import _schemas
                require(step['policy_denied'] is False and step['execution_rejection'] == rejection(observed['name'],
                    observed['arguments'], step['before']['native'], _schemas())
                    and step['execution_rejection'] is not None, 'formal known prepermission rejection differs')
            else:
                require(step['policy_denied'] is True and denied, 'formal missing dispatch not explained by frozen policy')
        require(used_reads <= case['max_reads'] and used_writes <= case['max_writes'], 'formal slot permission ceiling exceeded')
        records.append(joint)
    require(sorted(p.name for p in directory.glob('signing-*.json')) == signing_expected, 'formal extra/unaccounted signing handoff')
    close, stop = audit_native_sequence(directory, result, records)
    bootstrap, created = read_json(directory, 'bootstrap.json'), read_json(directory, 'engine-created.json')
    require(bootstrap['native'] == result['initial_native'] and bootstrap['owner_freeze_sha256'] == digest(freeze)
        and bootstrap['task_sha256'] == hashlib.sha256(task.encode()).hexdigest()
        and created['rhino_version'] == freeze['rhino_version'], 'formal initial fixture/task/runtime differs')
    seed_names = [n for i in range(len(case['fixture_recipe'])) for n in ('seed-%02d.claim.json' % i, 'seed-%02d.result.json' % i)]
    require(sorted(p.name for p in directory.glob('seed-*.json')) == sorted(seed_names), 'formal seed evidence missing/extra')
    last = {'unit': 'Millimeters', 'objects': [], 'groups': {}}
    for i, recipe in enumerate(case['fixture_recipe']):
        claim = read_json(directory, 'seed-%02d.claim.json' % i); seeded = read_json(directory, 'seed-%02d.result.json' % i)
        require(claim == {'index': i, **recipe, 'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False}
            and seeded['index'] == i and seeded['operation'] == recipe['operation'] and seeded['arguments'] == recipe['arguments']
            and seeded['before'] == last, 'formal fixture construction chain differs')
        last = seeded['after']
    require(last == bootstrap['native'], 'formal seeded fixture baseline differs')
    backups = read_json(directory, 'database-backups.json')
    require(set(backups) == {'consent', 'fixture'} and all(file_sha(directory / (n + '-audit.sqlite3')) == sha
        for n, sha in backups.items()), 'formal independent database snapshot bytes differ')
    chain = audit_model_native_chain(records, receipts, directory / 'consent-audit.sqlite3', directory / 'fixture-audit.sqlite3',
        task=task, freeze_sha=digest(freeze), model_identity=freeze['model_identities'][slot['route']], tokenizer=tokenizer)
    lifecycle = audit_lifecycle(bootstrap, created, close, stop, result['final_native'], freeze['source_inventory_sha256'],
        key_present=os.path.lexists(directory / 'handoff.key'))
    require(lifecycle['had_failure'] is False, 'formal child safety failure')
    return {'model_native_chain_verified': True, 'permission_ledger_verified': True, 'source_model_resource_verified': True,
        'lifecycle_verified': True, 'critical_safety_errors': 0, 'duplicate_writes': 0, 'unverified_cleanup': 0}, chain


def audit_run(state, cases, spec, freeze, tokenizer, *, source_guard):
    """Custodian-only post-run audit; caller checks exact authority/public freeze."""
    source_guard()
    cases = validate_families(cases); order = slot_order(cases, seed=spec['slot_seed'])
    require(family_merkle_root(cases) == spec['family_merkle_root_sha256']
        and slot_order_sha256(order) == spec['slot_order_sha256'], 'formal private case/order commitment differs')
    require(read_json(state, 'formal20.started.json') == {'study_id': STUDY_ID, 'spec_sha256': digest(spec),
        'runtime_freeze_sha256': digest(freeze), 'public_commitment_sha256': spec['public_commitment_sha256'], 'replay_allowed': False},
        'formal whole-set permanent consumption differs')
    run = read_json(state, 'formal20.run-result.json')
    require(run['status'] == 'formal_execution_complete_awaiting_independent_audit' and run['slots_attempted'] == 40
        and run['route_slots_required'] == 40 and run['error_type'] is None and run['c5_6_gate_claim'] is False,
        'formal incomplete run cannot pass audit')
    native_expected = {'slot_order': order, 'plans': {s['slot_id']: {
        'task_text': next(c['task_text'] for c in cases if c['family_id'] == s['family_id']),
        'fixture_recipe': next(c['fixture_recipe'] for c in cases if c['family_id'] == s['family_id']),
        'max_writes': next(c['max_writes'] for c in cases if c['family_id'] == s['family_id']),
        'max_reads': next(c['max_reads'] for c in cases if c['family_id'] == s['family_id'])} for s in order}}
    from training.c5_formal20_runtime import hashed_model_plans
    model_expected = hashed_model_plans({s['slot_id']: {'route': s['route'],
        'steps': [native_expected['plans'][s['slot_id']]['task_text']] *
            next(c['max_steps'] for c in cases if c['family_id'] == s['family_id'])} for s in order})
    require(read_json(state, 'native-plans.json') == native_expected
        and read_json(state, 'model-plans-hashed.json') == model_expected
        and read_json(state, 'native-prepared.json') == {'study_id': STUDY_ID,
            'native_plans_sha256': digest(native_expected), 'runtime_freeze_sha256': digest(freeze)},
        'formal sealed case/prepared plan binding differs')
    for name in ('formal20.hub-admission.claim.json', 'formal20.hub-started.claim.json'):
        expected = {'study_id': STUDY_ID, 'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False}
        if 'admission' in name: expected['action'] = 'attach'
        require(read_json(state, name) == expected, 'formal hub permanent admission differs')
    local = read_json(state, 'resource-settlement.json'); boundary = freeze['resource_boundary']
    require(local['status'] == 'formal_mac_driver_finished' and local['study_id'] == STUDY_ID
        and local['resource_boundary_sha256'] == digest(boundary) and local['replay_allowed'] is False,
        'formal Mac resource settlement binding differs')
    require(all(type(local[k]) in (int, float) and math.isfinite(local[k]) for k in
        ('elapsed_seconds_including_load_and_idle', 'cap_seconds', 'start_epoch', 'stop_epoch')),
        'formal finite Mac resource amounts required')
    elapsed = local['elapsed_seconds_including_load_and_idle']
    require(0 <= elapsed <= local['cap_seconds'] <= boundary['formal_max_seconds']
        and local['start_epoch'] <= local['stop_epoch'] <= spec['model_generation_cutoff_epoch']
        and boundary['prior_cumulative_seconds'] + elapsed <= 57600
        and boundary['prior_research_seconds'] + elapsed <= 14400, 'formal Mac resource ceiling exceeded')
    remote = audit_remote(state, spec, freeze)
    by_id = {c['family_id']: c for c in cases}; scored, keys, first_prompts = [], [], {}
    for slot in order:
        case = by_id[slot['family_id']]; result = read_json(state, slot['slot_id'] + '.result.json')
        scope = {'stage': 'formal', 'task_sha256': hashlib.sha256(case['task_text'].encode()).hexdigest(),
            'route': slot['route'], 'owner_freeze_sha256': digest(freeze)}
        require(read_json(state, digest(scope) + '.claim.json') == {'version': 1, 'slot_sha256': digest(scope),
            'scope': scope, 'replay_allowed': False}, 'formal route permanent claim differs')
        proof, _ = audit_slot(state, case, slot, result, freeze, tokenizer)
        scored.append(score_route(case, result, proof))
        for i, step in enumerate(result['steps']):
            key = digest({'slot': slot['slot_id'], 'step': i, 'freeze': digest(freeze)}); keys.append(key)
            require(read_json(state, slot['slot_id'] + '-step-%d.record.json' % i) == step
                and read_json(state, slot['slot_id'] + '-step-%d.claim.json' % i) == {'slot_id': slot['slot_id'], 'step_index': i,
                    'scene_sha256': digest(step['before']['native']), 'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False},
                'formal local step claim/raw record differs')
        from training.c5_rhino_adapter import step_input
        prompt = step_input(case['task_text'], semantic(result['initial_native']))
        if case['family_id'] in first_prompts: require(first_prompts[case['family_id']] == prompt, 'formal paired initial prompt differs')
        else: first_prompts[case['family_id']] = prompt
    require(keys == remote['keys'], 'formal remote generation order differs from forty-slot schedule')
    expected_slots = [s['slot_id'] for s in order]
    expected_steps = {s['slot_id'] + '-step-%d' % i for s in order
        for i in range(len(read_json(state, s['slot_id'] + '.result.json')['steps']))}
    expected_route_claims = {digest({'stage': 'formal', 'task_sha256': hashlib.sha256(c['task_text'].encode()).hexdigest(),
        'route': r, 'owner_freeze_sha256': digest(freeze)}) + '.claim.json' for c in cases for r in ('base', 'lora')}
    require({p.name for p in state.glob('F*-step-*.claim.json')} == {n + '.claim.json' for n in expected_steps}
        and {p.name for p in state.glob('F*-step-*.record.json')} == {n + '.record.json' for n in expected_steps}
        and {p.name for p in state.glob('*.claim.json') if len(p.name) == 75} == expected_route_claims,
        'formal extra/missing local consumption claims/step records')
    require(sorted(p.name for p in state.glob('F*.result.json')) == sorted(s + '.result.json' for s in expected_slots)
        and sorted(p.name for p in state.glob('F*.engine-started.claim.json')) == sorted(s + '.engine-started.claim.json' for s in expected_slots),
        'formal extra/missing native/result slots')
    for slot in expected_slots:
        require(read_json(state, slot + '.engine-started.claim.json') == {'study_id': STUDY_ID, 'slot_id': slot,
            'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False}, 'formal engine admission differs')
    bootstrap, stop = read_json(state, 'hub-bootstrap.json'), read_json(state, 'hub-stop.json')
    require(bootstrap['study_id'] == STUDY_ID and bootstrap['runtime_freeze_sha256'] == digest(freeze)
        and bootstrap['source_sha256'] == stop['source_sha256'] == freeze['source_inventory_sha256']
        and bootstrap['native_plans_sha256'] == digest(read_json(state, 'native-plans.json'))
        and stop['status'] == 'hub_stopped' and stop['opened_slots'] == expected_slots and stop['unused_keys_removed'] == []
        and stop['had_failure'] is False and stop['hook_removed_in_same_callback'] is True
        and stop['hub_key_absence'] == {'key_removed': True, 'actual_absence_checked': True}
        and bootstrap['active_serial'] == stop['active_serial'] and bootstrap['active_sha256'] == stop['active_sha256']
        and not os.path.lexists(state / 'hub.key'), 'formal raw hub close/unhook/key proof differs')
    require(sorted(p.name for p in state.glob('hub-request-*.json')) == ['hub-request-%04d.json' % n for n in range(1, 42)]
        and sorted(p.name for p in state.glob('hub-response-*.json')) == ['hub-response-%04d.json' % n for n in range(1, 42)],
        'formal hub raw controls incomplete/extra')
    for n in range(1, 42):
        p = read_json(state, 'hub-request-%04d.json' % n)['payload']; r = read_json(state, 'hub-response-%04d.json' % n)
        require(p['owner_freeze_sha256'] == digest(freeze), 'formal raw hub scope differs')
        if n <= 40:
            require(p['action'] == 'open' and p['slot_id'] == expected_slots[n-1] and r['status'] == 'slot_opened'
                and r['slot_id'] == p['slot_id'] and r['fixture_serial'] == read_json(state / p['slot_id'], 'engine-created.json')['fixture_serial'],
                'formal raw hub opening differs')
        else: require(p['action'] == 'stop' and p['slot_id'] is None and r == stop, 'formal raw hub stop differs')
    source_guard()
    return {'study_id': STUDY_ID, 'status': 'independent_formal_raw_audit_complete',
        'paired_summary': summarize_pairs(scored), 'routes': scored,
        'resource_and_transport': {k: v for k, v in remote.items() if k != 'keys'},
        'hmac_reverified_after_key_deletion': False, 'c5_7_decision': 'not_decided_here', 'default_route_changed': False}
