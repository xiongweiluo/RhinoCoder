"""Independent host journal replay; no producer/session import or host effects.

Requires external receipt SHA plus frozen study/source identities. Actual
private field evidence must only be replayed by the owner-side frozen entry.
This audit proves the limited record contract, NOT opaque-host code origins.
"""
from __future__ import annotations

import math

from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import digest, require

POLICY = 'c5-frozen-source-trusted-host-visible-continuity-v2'


def _raw_snapshot(value):
    require(isinstance(value, dict) and set(value) == {'process_identity', 'python_origins', 'assemblies',
        'native_images', 'active_sha256', 'active_serial', 'active_object_count', 'inspection_limits'}
        and value['active_object_count'] == 0 and type(value['active_object_count']) is int,
        'raw empty-document snapshot required')
    require(all(isinstance(value[k], list) for k in ('python_origins', 'assemblies', 'native_images', 'inspection_limits')),
        'raw snapshot inventories required')
    require(len({r['instance_id'] for r in value['assemblies']}) == len(value['assemblies'])
        and all(r['surface_sha256'] == digest({k: v for k, v in r.items() if k != 'surface_sha256'})
        for r in value['assemblies']), 'raw visible CLR instance/surface digest differs')
    require({'CLR', 'clr'} <= {r['module'] for r in value['python_origins']}, 'raw CLR bindings missing')


def audit_host_continuity(state, study_id, freeze_sha, source_sha, external_seal_sha):
    started = read_json(state, 'host-continuity.started.json')
    require(started == {'study_id': study_id, 'runtime_freeze_sha256': freeze_sha, 'replay_allowed': False},
        'independent permanent study claim differs')
    seal = read_json(state, 'host-continuity-seal.json')
    require(digest(seal) == external_seal_sha and seal['study_id'] == study_id and seal['policy_id'] == POLICY
        and seal['runtime_freeze_sha256'] == freeze_sha and seal['source_inventory_sha256'] == source_sha,
        'independent external seal/study/source differs')
    require(all(seal.get(k) is False for k in ('complete_handler_absence_proven', 'legacy_byte_closure_verified',
        'causal_origin_or_emitted_bytes_proven', 'execution_authority')), 'stronger assurance falsely claimed')
    count = seal['record_count']
    require(type(count) is int and 3 <= count <= 1040, 'raw host record population bound')
    require({p.name for p in state.glob('host-continuity-*.json')} ==
        {'host-continuity-%04d.json' % n for n in range(count)} | {'host-continuity-seal.json'},
        'missing/extra raw host record')
    head = digest({'study_id': study_id, 'runtime_freeze_sha256': freeze_sha,
        'policy_id': POLICY, 'source_inventory_sha256': source_sha})
    require(seal['genesis_sha256'] == head, 'raw host genesis differs')
    previous_time, baseline, kinds, failed, normal_count = -1, None, [], False, 0
    for n in range(count):
        row = read_json(state, 'host-continuity-%04d.json' % n)
        require(set(row) == {'schema_version', 'study_id', 'policy_id', 'runtime_freeze_sha256', 'sequence',
            'elapsed_seconds', 'previous_sha256', 'kind', 'payload', 'record_sha256'}
            and row['schema_version'] == 1 and row['sequence'] == n and row['study_id'] == study_id
            and row['policy_id'] == POLICY and row['runtime_freeze_sha256'] == freeze_sha
            and row['previous_sha256'] == head
            and row['record_sha256'] == digest({k: v for k, v in row.items() if k != 'record_sha256'}),
            'raw host chain differs')
        elapsed = row['elapsed_seconds']
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= previous_time,
            'raw host monotonic time differs')
        previous_time, head = elapsed, row['record_sha256']
        kind, p = row['kind'], row['payload']
        require(kind in {'subscribe_attempt', 'subscribed', 'baseline', 'checkpoint', 'cleanup_checkpoint',
            'detach_attempt', 'detached', 'failure'}, 'unknown host lifecycle record')
        kinds.append(kind)
        if kind == 'failure':
            failed = True
            continue
        if kind in {'baseline', 'checkpoint', 'cleanup_checkpoint'}:
            require(set(p) == ({'snapshot', 'events'} if kind == 'baseline' else
                {'snapshot', 'events', 'label', 'continuity_error_type', 'source_inventory_sha256'}),
                'raw host snapshot/checkpoint fields differ')
            value, events = p['snapshot'], p['events']
            _raw_snapshot(value)
            require(set(events) == {'events', 'errors', 'dropped'} and isinstance(events['events'], list)
                and isinstance(events['errors'], list) and type(events['dropped']) is int,
                'raw event/loss evidence shape differs')
            if kind == 'baseline':
                require(baseline is None and kinds[:3] == ['subscribe_attempt', 'subscribed', 'baseline']
                    and events['errors'] == [] and events['dropped'] == 0, 'baseline order/loss differs')
                baseline = value
            else:
                require(p['source_inventory_sha256'] == source_sha
                    and (baseline is not None or kind == 'cleanup_checkpoint'),
                    'dispatch checkpoint without frozen baseline/source')
                # Independently replay full raw inventory, not producer verdict.
                same = baseline is not None and value == baseline and events == {'events': [], 'errors': [], 'dropped': 0}
                require((p['continuity_error_type'] is None) == same, 'producer drift/error verdict differs from raw')
                if not same: failed = True
                if kind == 'checkpoint':
                    require('detach_attempt' not in kinds and normal_count < 512, 'dispatch checkpoint after detach/exhaustion')
                    normal_count += 1
        if kind == 'detached':
            require(p == {'exact_remove_call_completed': True, 'complete_handler_absence_proven': False},
                'detach observation is not full handler absence proof')
    require(head == seal['journal_head_sha256'] and kinds.count('subscribe_attempt') <= 1
        and kinds.count('subscribed') <= 1 and kinds.count('baseline') <= 1
        and kinds.count('detach_attempt') == 1 and kinds.count('detached') <= 1,
        'raw single-use lifecycle/head differs')
    complete = (not failed and baseline is not None and normal_count >= 1
        and kinds[:3] == ['subscribe_attempt', 'subscribed', 'baseline']
        and kinds[-3:] == ['detach_attempt', 'detached', 'cleanup_checkpoint'])
    require(type(seal['blocked']) is bool and seal['blocked'] == (not complete)
        and seal['exact_remove_call_completed'] == ('detached' in kinds), 'producer lifecycle settlement differs')
    return {'study_id': study_id, 'policy_id': POLICY, 'record_count': count,
        'status': 'limited_host_continuity_audit_verified' if complete else 'host_continuity_failed_or_incomplete_no_replay',
        'limited_visible_continuity_verified': complete, 'normal_checkpoint_count': normal_count,
        'raw_external_seal_sha256': external_seal_sha, 'legacy_byte_closure_verified': False,
        'complete_handler_absence_proven': False, 'causal_origin_or_emitted_bytes_proven': False,
        'execution_authority': False}


def audit_request_checkpoint_bindings(state, slot_order, freeze_sha):
    """Bind every raw signed hub/native request to the anchored source check.

    Owner-side only for private formal execution evidence. No network/host
    operation. The whole chain must be audited separately against receipt.
    """
    count=0
    for directory,prefix,check_prefix in [(state,'hub-request-','hub-host-check-')] + [
        (state/slot,'request-','host-check-') for slot in slot_order]:
        requests=sorted(directory.glob(prefix+'*.json'))
        require({p.name for p in directory.glob(check_prefix+'*.json')} == {
            check_prefix+p.name[len(prefix):] for p in requests}, 'missing/extra per-request host checkpoint binding')
        for path in requests:
            sent=read_json(directory,path.name)
            check=read_json(directory,check_prefix+path.name[len(prefix):])
            require(set(check)=={'request_sha256','host_record_sha256','host_sequence','runtime_freeze_sha256'}
                and check['request_sha256']==digest(sent) and check['runtime_freeze_sha256']==freeze_sha
                and type(check['host_sequence']) is int and 0<=check['host_sequence']<1040,
                'raw request/freeze host-check binding differs')
            row=read_json(state,'host-continuity-%04d.json'%check['host_sequence'])
            require(row['record_sha256']==check['host_record_sha256']
                and row['runtime_freeze_sha256']==freeze_sha, 'raw host checkpoint anchor differs')
            envelope=sent.get('envelope',sent)
            cleanup=sent.get('kind','control')=='control' and envelope['payload'].get('action') in {'close','stop'}
            require(row['kind']==('cleanup_checkpoint' if cleanup else 'checkpoint')
                and row['payload']['continuity_error_type'] is None, 'request bypassed successful correct host guard')
            count+=1
    return {'raw_requests_bound_to_anchored_checkpoints':count,'execution_authority':False}
