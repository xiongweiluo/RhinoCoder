"""Independent raw observer replay, no CLR/Rhino/model/private-task access.

The externally captured seal digest is required. A hash chain alone cannot
protect against wholesale rewriting of both a journal and its local seal.
"""
from __future__ import annotations

import math

from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_host_observer import PROBE_ID, validate_snapshot


def audit_observer(state, expected_freeze_sha, external_seal_sha):
    seal=read_json(state,'observer-seal.json')
    require(digest(seal)==external_seal_sha and seal['probe_id']==PROBE_ID
        and seal['runtime_freeze_sha256']==expected_freeze_sha
        and seal['execution_admission_granted'] is False
        and seal['code_bytes_or_causal_origin_proven'] is False, 'observer external seal/identity differs')
    count=seal['record_count']
    require(type(count) is int and 1<=count<=128, 'bounded observer record count required')
    expected={'observer-%04d.json'%i for i in range(count)}
    require({p.name for p in state.glob('observer-*.json') if p.name!='observer-seal.json'}==expected,
        'extra or missing observer journal records')
    claim=read_json(state,'observer.started.json')
    require(claim['probe_id']==PROBE_ID and claim['runtime_freeze_sha256']==expected_freeze_sha
        and claim['replay_allowed'] is False, 'permanent observer admission identity differs')
    head=digest({'probe_id':PROBE_ID,'runtime_freeze_sha256':expected_freeze_sha})
    snapshots, event_batches, kinds, actions, failures = {}, {}, [], [], []
    last_elapsed=-1
    for index in range(count):
        record=read_json(state,'observer-%04d.json'%index)
        require(set(record)=={'schema_version','probe_id','runtime_freeze_sha256','sequence',
            'elapsed_seconds','previous_sha256','kind','payload','record_sha256'}, 'observer journal shape differs')
        claimed=record['record_sha256']
        body={k:v for k,v in record.items() if k!='record_sha256'}
        require(type(record['elapsed_seconds']) in (int,float) and math.isfinite(record['elapsed_seconds'])
            and digest(body)==claimed and record['previous_sha256']==head
            and record['sequence']==index and record['probe_id']==PROBE_ID
            and record['runtime_freeze_sha256']==expected_freeze_sha
            and record['elapsed_seconds']>=last_elapsed, 'observer raw journal chain differs')
        head,last_elapsed=claimed,record['elapsed_seconds']
        kind,payload=record['kind'],record['payload'];kinds.append(kind)
        if kind=='snapshot':
            require(payload['phase'] not in snapshots, 'duplicate snapshot phase')
            snapshots[payload['phase']]=validate_snapshot(payload['value'])
            rows=snapshots[payload['phase']]['assemblies']
            require(len({r['instance_id'] for r in rows})==len(rows), 'duplicate actual CLR instance identity')
            require(all(digest({k:v for k,v in r.items() if k!='surface_sha256'})==r['surface_sha256']
                for r in rows), 'raw CLR surface fingerprint differs')
        elif kind=='events':
            require(payload['phase'] not in event_batches and payload['dropped']==0 and payload['errors']==[],
                'missing/duplicated/error observer events')
            event_batches[payload['phase']]=payload['events']
        elif kind=='canary_action': actions.append(payload['action'])
        elif kind=='failure': failures.append(payload['error_type'])
    require(head==seal['journal_head_sha256'] and kinds[0]=='begin' and kinds[-1]=='finished',
        'observer journal not fully sealed')
    limits={str(item) for snap in snapshots.values() for item in snap['inspection_limits']}
    capability=False
    if not failures:
        require(kinds==['begin','subscribe_attempt','subscribed','snapshot','events','canary_action',
            'snapshot','events','canary_action','snapshot','events','detach_attempt','detached',
            'canary_action','snapshot','events','finished'], 'observer raw lifecycle order differs')
        require(set(snapshots)==set(event_batches)=={'baseline','subscribed_empty','subscribed_with_type','after_detach_sentinel'},
            'complete observer lifecycle snapshots/events missing')
        require(actions==['create_subscribed_empty_assembly','add_one_empty_type_no_method_invocation',
            'create_detached_empty_assembly'] and kinds.count('subscribed')==kinds.count('detached')==1,
            'observer actions/subscription lifecycle differs')
        def canary(phase,role):
            rows=[r for r in snapshots[phase]['assemblies'] if r.get('probe_canary_role')==role]
            require(len(rows)==1, 'observer canary identity ambiguous')
            return rows[0]
        before=canary('subscribed_empty','subscribed');after=canary('subscribed_with_type','subscribed')
        require(before['instance_id']==after['instance_id'] and before['dynamic'] is True
            and after['dynamic'] is True and before['surface_sha256']!=after['surface_sha256']
            and before['visible_type_count']==0 and after['visible_type_count']==1,
            'same-instance structure change not independently detected')
        require(before['visible_types']==[] and len(after['visible_types'])==1
            and after['visible_types'][0]['name']=='C5ObserverEmptyType', 'actual canary type surface differs')
        identity=before['instance_id']
        recorded=[e for batch in event_batches.values() for e in batch if e['instance_id']==identity]
        require(len(recorded)==1 and recorded[0]['event']=='AssemblyLoad', 'subscribed canary event not unique')
        detached=canary('after_detach_sentinel','detached')['instance_id']
        require(not any(e['instance_id']==detached for batch in event_batches.values() for e in batch),
            'detached callback still active')
        origin=snapshots['baseline']
        require(all((s['process_identity'],s['active_sha256'],s['active_serial'],s['active_object_count'])==
            (origin['process_identity'],origin['active_sha256'],origin['active_serial'],0) for s in snapshots.values()),
            'actual process/document continuity differs')
        capability=True
    return {'probe_id':PROBE_ID,'status':'observer_capability_raw_audit_verified_with_limits' if capability
        else 'observer_incomplete_or_failed_no_replay','capability_control_verified':capability,
        'reflection_limits':sorted(limits),'journal_head_sha256':head,'seal_sha256':external_seal_sha,
        'clean_host_baseline_verified':False,'complete_event_coverage_proven':False,
        'code_bytes_or_causal_origin_proven':False,'legacy_byte_closure_verified':False,
        'formal_execution_ready':False,'model_calls':0,'holdout_rows_read':0,'fixtures_created':0}
