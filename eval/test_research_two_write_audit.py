"""Synthetic receipt/database negative controls. Never uses Rhino or holdout."""
import hashlib
import json
import sqlite3
from contextlib import closing

import pytest

from plugin.rhino_listener.research_safety import ResearchSafetyError, canonical_hash
from tools import audit_r_research_two_write as module
from tools.r_research_two_write_smoke import SPEC


def put(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def make_db(path, tables):
    with closing(sqlite3.connect(path)) as db:
        for name, rows in tables.items():
            columns = list(rows[0])
            db.execute("CREATE TABLE "+name+" ("+", ".join(key+(" INTEGER" if type(rows[0][key]) is int else " TEXT")
                                                     for key in columns)+")")
            db.executemany("INSERT INTO "+name+" VALUES ("+",".join("?" for _ in columns)+")",
                           [tuple(row[key] for key in columns) for row in rows])
        db.commit()
    path.chmod(0o600)


def fixture(tmp_path, monkeypatch):
    root, batch, output, session = (tmp_path/name for name in ("source", "batch", "output", "session"))
    for path in (root, batch, output, session, session/"channel"):
        path.mkdir(mode=0o700)
    (root/"module.py").write_text("pass\n")
    inventory = {"module.py": hashlib.sha256((root/"module.py").read_bytes()).hexdigest()}
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "source_inventory", lambda _: inventory)
    approval = {"authorized_by": "repository_owner", "probe_spec_sha256": canonical_hash(SPEC), "approved": True,
                "authorization_basis": "explicit owner reply approving fixed two-write research safety probe"}
    active = "e"*64
    bootstrap = {"version": 2, "scope": SPEC["scope"], "initial_active_sha256": active,
                 "formal_quality_claim": False, "model_invocation_allowed": False}
    capture = {"case_id": SPEC["probe_id"], "session_dir": str(session), "on_rhino_main_thread": True,
               "capture_scope": "same_ui_callback_before_and_after_fixture_close", "close_seq": 2,
               "fixture_closed": True, "key_removed": True,
               **{key: active for key in ("initial_active_sha256", "before_close_active_sha256", "after_close_active_sha256")}}
    opened = {"status": "opened", "fixture": "empty", "case_id": SPEC["probe_id"], "session_dir": str(session),
              "initial_active_sha256": active}
    closed = {"status": "closed", "case_id": SPEC["probe_id"], "session_dir": str(session),
              "key_removed": True, "final_active_capture": capture}
    stopped = {"status": "stopped", "case_id": "RSDEV-END", "had_failure": False, "active_sha256_at_stop": active}
    for name, value in (("bootstrap.json", bootstrap), ("source-inventory.json", inventory), ("final-active-002.json", capture)):
        put(batch/name, value)
    for seq, action, case, kind, response in ((1, "open", SPEC["probe_id"], "empty", opened),
                                             (2, "close", SPEC["probe_id"], "none", closed),
                                             (3, "stop", "RSDEV-END", "none", stopped)):
        put(batch/("request-%03d.json" % seq), {"version": 2, "seq": seq, "action": action, "case_id": case, "fixture": kind})
        put(batch/("response-%03d.json" % seq), response)
    geometry = [[], [{"alias": "box-1", "min": [0., 0., 0.], "max": [347., 353., 359.]}],
                [{"alias": "box-1", "min": [7., -11., 13.], "max": [354., 342., 372.]}]]
    scenes = [{"revision": n+1, "scene_sha256": chr(97+n)*64,
               "summary": {"unit": "Millimeters", "document_key": "d"*64,
                           "object_count": len(objects), "aliases": [obj["alias"] for obj in objects]},
               "objects": objects, "selected_aliases": []} for n, objects in enumerate(geometry)]
    put(session/"initial.json", {"version": 1, "fixture": "empty_headless_mm", "scene": scenes[0],
                                 "active_document_content_sha256": active})
    for number, scene in enumerate(scenes, 1):
        nonce = str(number)*64
        put(session/("capture-"+nonce+".json"), {"version": 1, "nonce": nonce})
        put(session/("capture-response-"+nonce+".json"), {"version": 1, "nonce": nonce, "scene": scene})
    records = []
    for number, explicit in enumerate(SPEC["steps"], 1):
        request_id = "request-1234567890123456789"+str(number)
        args = module._geometry_args(explicit)
        key = hashlib.sha256(request_id.encode()).hexdigest()
        task_hash = hashlib.sha256(json.dumps(explicit, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        before, after = scenes[number-1], scenes[number]
        payload = {"version": 1, "request_id": request_id, "operation": explicit["op"], "arguments": args,
                   "scene_revision": before["revision"], "scene_sha256": before["scene_sha256"],
                   "document_key": "d"*64, "task_sha256": task_hash}
        execution = {"status": "done", "operation": explicit["op"], "ledger_state": "done", "result_sha256": "f"*64,
                     "before_scene_sha256": before["scene_sha256"], "after_scene_sha256": after["scene_sha256"],
                     "idempotency_key_sha256": hashlib.sha256(key.encode()).hexdigest()}
        ledger = {"idempotency_key": key, "expected_sha256": before["scene_sha256"], "expected_revision": before["revision"],
                  "document_key": "d"*64, "state": "done", "result_sha256": "f"*64,
                  "request_sha256": canonical_hash({"operation": explicit["op"], "arguments": args})}
        consent_args = dict(args)
        if explicit["op"] == "move_object": consent_args["object_id"] = consent_args.pop("alias")
        consent = {"request_id": request_id, "tool_name": explicit["op"], "status": "consumed", "task_sha256": task_hash,
                   "arguments_sha256": canonical_hash(consent_args), "scene_sha256": before["scene_sha256"],
                   "scene_revision": before["revision"]}
        events = [{"event_id": (number-1)*4+n, "request_id": request_id, "event_type": event,
                   "occurred_at": n, "reason_code": ""} for n, event in enumerate(
                       ("requested", "approved", "consumed", "signed_handoff_issued"), 1)]
        record = {"request_id": request_id, "operation": explicit["op"], "signed_arguments": args, "task_sha256": task_hash,
                  "document_key": "d"*64, "before_revision": before["revision"],
                  "before_scene_sha256": before["scene_sha256"], "after_scene_sha256": after["scene_sha256"],
                  "before_geometry": {"objects": before["objects"]}, "after_geometry": {"objects": after["objects"]},
                  "envelope_payload": payload, "execution": execution, "ledger_row": ledger,
                  "consent_request": consent, "consent_events": events}
        nonce = str(number+3)*64
        put(session/("execute-"+nonce+".json"), {"version": 1, "nonce": nonce, "request_id": request_id})
        put(session/("execute-response-"+nonce+".json"), execution)
        put(session/"channel"/(request_id+".json"), {"payload": payload, "signature": "a"*64})
        put(output/("step-%d.json" % number), record)
        records.append(record)
    ledgers = [r["ledger_row"] for r in records]
    make_db(session/"fixture.sqlite3", {"candidate_write": ledgers})
    make_db(output/"fixture.sqlite3", {"candidate_write": ledgers})
    make_db(output/"consent.sqlite3", {"consent_requests": [r["consent_request"] for r in records],
                                     "consent_events": [e for r in records for e in r["consent_events"]]})
    result = {"status": "two_write_research_safety_pass_not_model_quality", "probe_spec": SPEC,
              "probe_spec_sha256": canonical_hash(SPEC), "owner_approval": approval, "error": None,
              "cleanup_verified": True, "model_calls": 0, "formal_quality_claim": False, "c5_6_authorized": False,
              "no_model_or_tool_retries": True, "opened": opened, "closed": closed, "stopped": stopped,
              "source_inventory": inventory, "records": records}
    put(output/"result.json", result)
    put(output/"owner-approval.json", approval)
    return batch, output, session


def mutate(path, callback):
    value = json.loads(path.read_text())
    callback(value)
    put(path, value)


def test_synthetic_audit_is_path_free_and_not_c5_authorization(tmp_path, monkeypatch):
    batch, output, session = fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for directory in (batch, output, session, session/"channel") for p in directory.iterdir() if p.is_file()}
    value = module.audit(batch, output/"result.json")
    assert value["write_requests"] == value["ledger_rows_done"] == 2
    assert value["consent_events"] == 8 and not value["c5_6_authorized"] and not value["full_R_research_safety_gate_passed"]
    assert str(tmp_path) not in json.dumps(value)
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("tamper", ["live_ledger", "backup_ledger", "consent", "events", "execute", "replay",
                                    "envelope", "readback", "active", "key", "source", "owner", "extra_lifecycle"])
def test_independent_raw_evidence_tampering_is_rejected(tmp_path, monkeypatch, tamper):
    batch, output, session = fixture(tmp_path, monkeypatch)
    if tamper in {"live_ledger", "backup_ledger", "consent", "events"}:
        path = session/"fixture.sqlite3" if tamper == "live_ledger" else output/("fixture.sqlite3" if tamper == "backup_ledger" else "consent.sqlite3")
        sql = {"live_ledger": "UPDATE candidate_write SET state='uncertain'", "backup_ledger": "DELETE FROM candidate_write",
               "consent": "UPDATE consent_requests SET status='approved'", "events": "DELETE FROM consent_events WHERE event_id=8"}[tamper]
        with closing(sqlite3.connect(path)) as db: db.execute(sql); db.commit()
    elif tamper == "execute":
        mutate(session/("execute-response-"+"4"*64+".json"), lambda v: v.update(status="uncertain"))
    elif tamper == "replay":
        put(session/("execute-"+"6"*64+".json"), {"version": 1, "nonce": "6"*64, "request_id": "request-12345678901234567891"})
    elif tamper == "envelope":
        mutate(next((session/"channel").glob("*.json")), lambda v: v["payload"]["arguments"].update(width=999))
    elif tamper == "readback":
        mutate(session/("capture-response-"+"3"*64+".json"), lambda v: v["scene"]["objects"][0]["max"].__setitem__(0, 999))
    elif tamper == "active":
        mutate(batch/"final-active-002.json", lambda v: v.update(after_close_active_sha256="a"*64))
    elif tamper == "key": put(session/"channel"/"handoff.key", {"synthetic_test_only": True})
    elif tamper == "source": (tmp_path/"source"/"module.py").write_text("changed\n")
    elif tamper == "owner": mutate(output/"owner-approval.json", lambda v: v.update(authorized_by="codex"))
    elif tamper == "extra_lifecycle": put(batch/"request-004.json", {"version": 2})
    with pytest.raises(ResearchSafetyError): module.audit(batch, output/"result.json")
