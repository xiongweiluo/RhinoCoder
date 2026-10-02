#!/usr/bin/env python3
"""Read-only audit of the owner-approved fixed synthetic two-write safety probe.

No fixture opening, signing, consent approval, model invocation or holdout access.
This audits retained raw receipts and databases, not just runner pass booleans.
The removed HMAC secret is never recovered: signature verification occurred at
execution; this audit cross-binds its retained payload, not a new HMAC proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.rhino_listener.research_safety import (SHA, canonical_hash, require,
    source_inventory, verify_exact_transition, verify_final_active_capture, verify_loaded_sources, verify_write_binding)  # noqa: E402
from plugin.rhino_listener.candidate_envelope_gate import _validate_payload  # noqa: E402
from tools.r4_v5_ssh_no_write_session import _private_directory, _private_read  # noqa: E402
from tools.r4_v6_live_multistep import _capture_value, _geometry_args, _initial  # noqa: E402
from tools.r_research_two_write_smoke import SPEC, verify_owner_approval  # noqa: E402


def database_rows(path, tables):
    _private_directory_checked(path.parent)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.getuid(), "unsafe database")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        require(tuple(db.execute("PRAGMA quick_check").fetchone()) == ("ok",), "database integrity failed")
        # Table names are internal constants, never supplied by the CLI.
        return {table: [dict(row) for row in db.execute("SELECT * FROM "+table+" ORDER BY rowid")]
                for table in tables}


def _private_directory_checked(path):
    fd = _private_directory(path)
    os.close(fd)


def audit(batch, result_path):
    result = _private_read(result_path, limit=512*1024)
    require(result.get("probe_spec") == SPEC and result.get("probe_spec_sha256") == canonical_hash(SPEC),
            "fixed probe differs")
    verify_owner_approval(result.get("owner_approval"))
    output = result_path.parent
    require(_private_read(output/"owner-approval.json") == result["owner_approval"], "owner receipt differs")
    require(result.get("status") == "two_write_research_safety_pass_not_model_quality"
            and result.get("error") is None and result.get("cleanup_verified") is True
            and result.get("model_calls") == 0 and result.get("formal_quality_claim") is False
            and result.get("c5_6_authorized") is False and result.get("no_model_or_tool_retries") is True,
            "failed or differently scoped probe")
    bootstrap = _private_read(batch/"bootstrap.json")
    inventory = _private_read(batch/"source-inventory.json")
    require(inventory == result["source_inventory"] and bool(inventory), "source inventory differs")
    require(inventory == source_inventory(ROOT), "source inventory incomplete or current checkout drifted")
    verify_loaded_sources(ROOT, inventory, [])
    require(bootstrap.get("version") == 2 and bootstrap.get("scope") == SPEC["scope"]
            and bootstrap.get("formal_quality_claim") is False and bootstrap.get("model_invocation_allowed") is False
            and not list(batch.glob("failure-*.json")), "controller scope/failure differs")
    require({p.name for p in batch.glob("request-*.json")} == {"request-%03d.json" % n for n in (1, 2, 3)}
            and {p.name for p in batch.glob("response-*.json")} == {"response-%03d.json" % n for n in (1, 2, 3)},
            "extra/missing lifecycle requests or responses")
    for seq, action, case, fixture in ((1, "open", SPEC["probe_id"], "empty"),
                                     (2, "close", SPEC["probe_id"], "none"), (3, "stop", "RSDEV-END", "none")):
        require(_private_read(batch/("request-%03d.json" % seq)) == {
            "version": 2, "seq": seq, "action": action, "case_id": case, "fixture": fixture},
            "lifecycle order/identity differs")
    opened, closed, stopped = (_private_read(batch/("response-%03d.json" % n)) for n in (1, 2, 3))
    require((opened, closed, stopped) == (result["opened"], result["closed"], result["stopped"]), "receipt/result differs")
    require(opened.get("status") == "opened" and opened.get("fixture") == "empty"
            and opened.get("case_id") == SPEC["probe_id"]
            and opened.get("initial_active_sha256") == bootstrap["initial_active_sha256"], "open unverified")
    require(closed.get("status") == "closed" and closed.get("case_id") == SPEC["probe_id"]
            and closed.get("session_dir") == opened["session_dir"] and closed.get("key_removed") is True,
            "close unverified")
    capture = _private_read(batch/"final-active-002.json")
    require(capture == closed["final_active_capture"] and capture.get("close_seq") == 2, "final capture differs")
    verify_final_active_capture(capture, case_id=SPEC["probe_id"], session_dir=opened["session_dir"],
                                initial_sha256=bootstrap["initial_active_sha256"])
    require(stopped.get("status") == "stopped" and stopped.get("case_id") == "RSDEV-END"
            and stopped.get("had_failure") is False
            and stopped.get("active_sha256_at_stop") == bootstrap["initial_active_sha256"], "stop unverified")
    session = Path(opened["session_dir"])
    require(session.is_absolute(), "session path not absolute")
    _private_directory_checked(session)
    require(not any((session/"channel"/name).exists() or (session/"channel"/name).is_symlink()
                    for name in ("handoff.key", "secret")), "handoff key retained")
    require(not list(session.glob("v6-plan-*")), "unexpected model plan")
    initial = _initial(session)
    require(_private_read(session/"initial.json")["active_document_content_sha256"] == bootstrap["initial_active_sha256"],
            "initial active digest differs")
    records = result.get("records")
    require(isinstance(records, list) and len(records) == 2, "two records required")
    ids = [row.get("request_id") for row in records]
    require(all(isinstance(r, str) for r in ids) and len(set(ids)) == 2, "duplicate write IDs")
    requests = [p for p in session.glob("execute-*.json") if not p.name.startswith("execute-response-")]
    responses = list(session.glob("execute-response-*.json"))
    require(len(requests) == len(responses) == 2, "extra/missing write attempts")
    executions = {}
    for path in requests:
        value = _private_read(path)
        nonce = path.stem.removeprefix("execute-")
        require(set(value) == {"version", "nonce", "request_id"} and type(value["version"]) is int
                and value["version"] == 1 and value["nonce"] == nonce and SHA.fullmatch(nonce)
                and value["request_id"] in ids and value["request_id"] not in executions, "write request invalid/replayed")
        executions[value["request_id"]] = _private_read(session/("execute-response-"+nonce+".json"))
    require({p.name for p in (session/"channel").glob("*.json")} == {request_id+".json" for request_id in ids},
            "extra/missing signed handoffs")
    live_rows = database_rows(session/"fixture.sqlite3", ("candidate_write",))["candidate_write"]
    backup_rows = database_rows(output/"fixture.sqlite3", ("candidate_write",))["candidate_write"]
    require(live_rows == backup_rows and len(live_rows) == 2, "ledger backup differs or extra write reservation")
    consent = database_rows(output/"consent.sqlite3", ("consent_requests", "consent_events"))
    require(len(consent["consent_requests"]) == 2 and len(consent["consent_events"]) == 8
            and {row["request_id"] for row in consent["consent_requests"]} == set(ids)
            and {row["request_id"] for row in consent["consent_events"]} == set(ids), "extra/missing consent records")
    captures = []
    for path in sorted(session.glob("capture-response-*.json")):
        value = _private_read(path)
        nonce = path.stem.removeprefix("capture-response-")
        require(set(value) == {"version", "nonce", "scene"} and type(value["version"]) is int
                and value["version"] == 1 and value["nonce"] == nonce and SHA.fullmatch(nonce), "capture identity differs")
        require(_private_read(session/("capture-"+nonce+".json")) == {"version": 1, "nonce": nonce}, "capture request differs")
        captures.append(_capture_value(value["scene"]))
    capture_requests = [p for p in session.glob("capture-*.json") if not p.name.startswith("capture-response-")]
    require(bool(captures) and len(captures) == len(capture_requests),
            "missing capture response")
    previous = initial.geometry_view()
    previous_digest = initial.state.scene_sha256
    previous_revision = initial.state.revision
    for number, (record, explicit) in enumerate(zip(records, SPEC["steps"]), 1):
        require(_private_read(output/("step-%d.json" % number), limit=128*1024) == record, "step/result differs")
        require(record["operation"] == explicit["op"] and record["signed_arguments"] == _geometry_args(explicit)
                and record["task_sha256"] == hashlib.sha256(json.dumps(explicit, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(), "executed task differs from approved spec")
        require(record["before_geometry"] == previous and record["before_scene_sha256"] == previous_digest
                and record["before_revision"] == previous_revision
                and record["document_key"] == initial.state.summary["document_key"], "inter-step scene chain differs")
        verify_exact_transition(record["operation"], record["signed_arguments"],
                                record["before_geometry"], record["after_geometry"])
        def matches(value, side):
            return (value.geometry_view() == record[side+"_geometry"]
                    and value.state.scene_sha256 == record[side+"_scene_sha256"]
                    and value.state.summary["document_key"] == record["document_key"]
                    and value.state.summary["unit"] == "Millimeters"
                    and (value.state.revision == record["before_revision"] if side == "before"
                         else value.state.revision > record["before_revision"]))
        require(any(matches(value, "before") for value in captures)
                and any(matches(value, "after") for value in captures), "geometry not bound to actual readback")
        request_id = record["request_id"]
        envelope = _private_read(session/"channel"/(request_id+".json"))
        require(set(envelope) == {"payload", "signature"} and SHA.fullmatch(str(envelope["signature"]))
                and envelope["payload"] == record["envelope_payload"]
                and executions[request_id] == record["execution"], "actual envelope/execution differs")
        _validate_payload(envelope["payload"])
        key = hashlib.sha256(request_id.encode()).hexdigest()
        ledger = next((row for row in live_rows if row["idempotency_key"] == key), None)
        request = next(row for row in consent["consent_requests"] if row["request_id"] == request_id)
        events = [row for row in consent["consent_events"] if row["request_id"] == request_id]
        require(ledger == record["ledger_row"] and request == record["consent_request"]
                and events == record["consent_events"], "self-reported ledger/consent differs from databases")
        verify_write_binding(record=record, execution=executions[request_id], ledger_row=ledger,
                             consent_request=request, consent_events=events, envelope_payload=envelope["payload"])
        previous, previous_digest = record["after_geometry"], record["after_scene_sha256"]
        previous_revision = min(value.state.revision for value in captures if matches(value, "after"))
    evidence = [batch/name for name in ("bootstrap.json", "source-inventory.json", "final-active-002.json")]
    evidence += [batch/("%s-%03d.json" % (kind, n)) for kind in ("request", "response") for n in (1, 2, 3)]
    evidence += [result_path, output/"owner-approval.json", output/"step-1.json", output/"step-2.json", session/"initial.json"]
    evidence += requests+responses+list(session.glob("capture-*.json"))+list((session/"channel").glob("*.json"))
    require(len({p.name for p in evidence}) == len(evidence), "ambiguous evidence names")
    return {
        "schema_version": 1, "probe_id": SPEC["probe_id"], "probe_spec_sha256": canonical_hash(SPEC),
        "status": "independently_verified_fixed_two_write_safety_only", "model_calls": 0, "write_requests": 2,
        "ledger_rows_done": 2, "consent_requests_consumed": 2, "consent_events": 8,
        "exact_geometry_and_scene_chain_verified": True, "fixture_closed": True,
        "actual_handoff_key_absent": True, "controller_stopped": True,
        "initial_before_after_stop_active_sha256": bootstrap["initial_active_sha256"],
        "raw_capture_scope": capture["capture_scope"], "source_files": len(inventory),
        "source_inventory_sha256": canonical_hash(inventory), "source_inventory": inventory,
        "private_evidence_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence},
        "ledger_rows_sha256": canonical_hash(live_rows), "consent_rows_and_events_sha256": canonical_hash(consent),
        "formal_quality_claim": False, "full_R_research_safety_gate_passed": False, "c5_6_authorized": False,
        "limitations": ["only fixed create_box/move_object, no model quality or twelve-tool proof",
                        "no remote model lineage or C5-6 execution freeze",
                        "HMAC checked at runtime, removed secret not recovered or reverified",
                        "owner approval metadata records external human authorization, does not create it"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = audit(args.batch_dir, args.result)
    with args.output.open("x") as destination:
        destination.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n")
    print(json.dumps({k: value[k] for k in ("status", "probe_id", "write_requests", "c5_6_authorized")}))


if __name__ == "__main__":
    main()
