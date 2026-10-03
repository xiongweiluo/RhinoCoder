"""Read-only independent permission/ledger cross-check, not a quality verdict.

Reads consistent private SQLite backups plus raw receipts. Never signs, writes,
dispatches, loads a model or opens a task corpus. Native lifecycle/source/model
and geometry audits are separate mandatory gates; this cannot declare GO.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from plugin.rhino_listener.c5_research_native import READS, digest, require


def _tables(path, tables):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "private database missing/symlink")
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        require(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', "database quick_check failed")
        return {table:[dict(row) for row in db.execute('SELECT * FROM '+table)] for table in tables}


def audit_permission_execution(consent_path, ledger_path, receipts, *, task_sha256, owner_freeze_sha256, handoff_table='c5_model_handoff'):
    require(handoff_table in {'c5_model_handoff','c5_native_control_handoff'}, 'unknown handoff evidence class')
    consent = _tables(consent_path,('consent_requests','consent_events',handoff_table))
    ledger = _tables(ledger_path,('candidate_write','c5_read'))
    require(isinstance(receipts,list), "raw receipts required")
    writes = {r['idempotency_key']:r for r in ledger['candidate_write']}
    reads = {r['request_id']:r for r in ledger['c5_read']}
    permissions = {r['request_id']:r for r in consent['consent_requests']}
    handoffs = {r['request_id']:r for r in consent[handoff_table]}
    require(len(handoffs)==len(consent[handoff_table]), "duplicate/unissued handoff")
    seen, used_writes, used_reads, used_permissions = set(), set(), set(), set()
    prior = None
    for receipt in receipts:
        require(isinstance(receipt,dict) and receipt.get('status') == 'done', "execution not complete")
        p = receipt['payload']
        request = p['request_id']
        require(request not in seen and p['task_sha256'] == task_sha256
                and p['owner_freeze_sha256'] == owner_freeze_sha256, "duplicate/wrong task owner scope")
        seen.add(request)
        handoff = handoffs.get(request)
        require(handoff is not None and handoff['state']=='issued' and handoff['payload_sha256']==digest(p), "model handoff reservation differs")
        require(receipt['before_state'] == p['expected'], "pre-state binding differs")
        if prior is not None: require(prior == receipt['before_state'], "non-contiguous execution scene chain")
        prior = receipt['after_state']
        require(digest(receipt['result']) == receipt['result_sha256'], "result bytes/hash differ")
        if p['operation'] in READS:
            row = reads.get(request)
            require(row is not None and row['state']=='done' and row['payload_sha256']==digest(p)
                    and row['result_sha256']==receipt['result_sha256'], "read ledger differs")
            require(p['consent_row_sha256'] is None and receipt['ledger_row'] is None
                    and receipt['before_state']==receipt['after_state']
                    and receipt['before']==receipt['after'], "read performed write/drift")
            used_reads.add(request)
        else:
            key = hashlib.sha256(request.encode()).hexdigest()
            row, permit = writes.get(key), permissions.get(request)
            require(row is not None and row == receipt['ledger_row'] and row['state']=='done'
                    and row['document_key']==p['expected']['document_key']
                    and row['expected_revision']==p['expected']['revision']
                    and row['expected_sha256']==p['expected']['scene_sha256']
                    and row['request_sha256']==digest({'operation':p['operation'],'arguments':p['arguments']})
                    and row['result_sha256']==receipt['result_sha256'], "write ledger differs")
            require(permit is not None and permit['status']=='consumed' and digest(permit)==p['consent_row_sha256']
                    and permit['task_sha256']==task_sha256 and permit['tool_name']==p['operation']
                    and permit['arguments_sha256']==digest(p['arguments'])
                    and permit['scene_revision']==p['expected']['revision']
                    and permit['scene_sha256']==p['expected']['scene_sha256']
                    and permit['expires_at']==p['expires_at']
                    and row['created_at']>=permit['created_at'] and row['created_at']<permit['expires_at'], "permission binding/expiry differs")
            events = sorted((e for e in consent['consent_events'] if e['request_id']==request),key=lambda e:e['event_id'])
            require([e['event_type'] for e in events] == ['requested','approved','consumed','signed_handoff_issued']
                    and [e['occurred_at'] for e in events] == sorted(e['occurred_at'] for e in events)
                    and events[1]['reason_code']=='codex_delegated_headless'
                    and events[-1]['reason_code']==digest(p), "permission event chain differs")
            require(receipt['after_state']['document_key']==p['expected']['document_key']
                    and receipt['after_state']['revision']>p['expected']['revision'], "write did not advance native scene")
            used_writes.add(key)
            used_permissions.add(request)
    require(used_writes==set(writes) and used_reads==set(reads) and used_permissions==set(permissions), "unaccounted reservation/permission")
    require(seen==set(handoffs), "unaccounted model handoff")
    require(len(consent['consent_events']) == 4*len(permissions), "unaccounted permission event")
    return {'status':'permission_ledger_bindings_verified_not_lifecycle_or_quality',
            'write_count':len(writes),'read_count':len(reads),'consumed_permissions':len(permissions),
            'formal_task_passed':False,'cleanup_verified':False,'source_verified':False,
            'handoff_evidence_class':handoff_table,
            'hmac_reverified_after_key_deletion':False}
