"""Independent raw SQLite/receipt controls, without native or model execution."""
import copy
import sqlite3
from contextlib import closing

import pytest

from eval.test_c5_research_permission import setup, observation, TASK
from plugin.rhino_listener.c5_research_native import NativeError
from training.c5_research_audit import audit_permission_execution
from training.tool_controller_candidate import task_sha256


def completed(tmp_path):
    backend,atomic,store,signer,gate = setup(tmp_path)
    receipts = []
    for op,args in (('create_box',{'width':2,'depth':3,'height':4}),('get_scene_summary',{})):
        receipts.append(gate.execute(signer.issue(observation(atomic,op,args),schemas=backend.schemas)))
    return atomic,store,receipts


def audit(atomic,store,receipts):
    return audit_permission_execution(store.path,atomic.path,receipts,task_sha256=task_sha256(TASK),owner_freeze_sha256='a'*64)


def test_complete_two_databases_readonly_and_not_full_quality(tmp_path):
    atomic,store,receipts = completed(tmp_path)
    result = audit(atomic,store,receipts)
    assert result['write_count'] == result['read_count'] == result['consumed_permissions'] == 1
    assert not result['formal_task_passed'] and not result['cleanup_verified'] and not result['source_verified']
    assert audit(atomic,store,receipts) == result


@pytest.mark.parametrize('change',['missing','duplicate','result','state','owner','ledger','read_mutation'])
def test_receipt_tampering_or_partial_records_rejected(tmp_path,change):
    atomic,store,receipts = completed(tmp_path)
    if change == 'missing': receipts.pop()
    if change == 'duplicate': receipts.append(copy.deepcopy(receipts[0]))
    if change == 'result': receipts[0]['result']['done'] = False
    if change == 'state': receipts[0]['before_state']['revision'] = 7
    if change == 'owner': receipts[0]['payload']['owner_freeze_sha256'] = 'd'*64
    if change == 'ledger': receipts[0]['ledger_row']['state'] = 'reserved'
    if change == 'read_mutation': receipts[1]['after']['objects'].append({'alias':'extra'})
    with pytest.raises(NativeError): audit(atomic,store,receipts)


def test_database_tampering_and_unknown_rows_rejected(tmp_path):
    atomic,store,receipts = completed(tmp_path)
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("UPDATE consent_requests SET arguments_sha256=?",('f'*64,))
        db.commit()
    with pytest.raises(NativeError): audit(atomic,store,receipts)


def test_symlink_database_rejected(tmp_path):
    atomic,store,receipts = completed(tmp_path)
    link = tmp_path/'linked.sqlite3'
    link.symlink_to(store.path)
    with pytest.raises(NativeError): audit_permission_execution(link,atomic.path,receipts,task_sha256=task_sha256(TASK),owner_freeze_sha256='a'*64)
