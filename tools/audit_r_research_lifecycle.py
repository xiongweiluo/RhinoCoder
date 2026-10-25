#!/usr/bin/env python3
"""Audit only a no-model/no-write research lifecycle; publish path-free proof.

Never runs Rhino, opens a fixture, grants consent, or reads evaluation tasks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.r4_v5_ssh_no_write_session import _private_read  # noqa: E402
from plugin.rhino_listener.research_safety import (canonical_hash, require, verify_final_active_capture,
                                                  verify_loaded_sources)  # noqa: E402


def audit(batch, result_path):
    result = _private_read(result_path)
    case_id = result["case_id"]
    bootstrap = _private_read(batch/"bootstrap.json")
    inventory = _private_read(batch/"source-inventory.json")
    require(inventory == result["source_inventory"], "result/source inventory differs")
    verify_loaded_sources(ROOT, inventory, [])
    require(bootstrap["version"] == 2 and bootstrap["formal_quality_claim"] is False
            and bootstrap["model_invocation_allowed"] is False, "bootstrap scope changed")
    require(result["status"] == "research_lifecycle_smoke_pass_no_model_no_write"
            and result["error"] is None and result["cleanup_verified"] is True
            and result["model_calls"] == 0 and result["write_requests"] == 0
            and not list(batch.glob("failure-*.json")), "failed/mutating lifecycle cannot pass")
    for seq, action, expected_case, fixture in ((1, "open", case_id, "empty"),
                                               (2, "close", case_id, "none"),
                                               (3, "stop", "RSDEV-END", "none")):
        require(_private_read(batch/("request-%03d.json" % seq)) == {
            "version": 2, "seq": seq, "action": action, "fixture": fixture, "case_id": expected_case,
        }, "request identity/order differs")
    opened, closed, stopped = (_private_read(batch/("response-%03d.json" % seq)) for seq in (1, 2, 3))
    require((opened, closed, stopped) == (result["opened"], result["closed"], result["stopped"]), "receipt/result differs")
    require(opened["status"] == "opened" and opened["fixture"] == "empty" and opened["case_id"] == case_id
            and opened["initial_active_sha256"] == bootstrap["initial_active_sha256"], "open identity differs")
    require(closed["status"] == "closed" and closed["case_id"] == case_id and closed["key_removed"] is True
            and closed["session_dir"] == opened["session_dir"], "close identity differs")
    capture = _private_read(batch/"final-active-002.json")
    require(capture == closed["final_active_capture"], "final capture differs")
    verify_final_active_capture(capture, case_id=case_id, session_dir=opened["session_dir"],
                                initial_sha256=bootstrap["initial_active_sha256"])
    require(stopped["status"] == "stopped" and stopped["case_id"] == "RSDEV-END" and stopped["had_failure"] is False
            and stopped["active_sha256_at_stop"] == bootstrap["initial_active_sha256"], "controller stop unverified")
    session = Path(opened["session_dir"])
    require(not any((session/"channel"/name).exists() for name in ("handoff.key", "secret")), "key still exists")
    require(not list(session.glob("execute-*.json")) and not list(session.glob("v6-plan-*")), "unexpected model/write artifacts")
    with closing(sqlite3.connect((session/"fixture.sqlite3").as_uri()+"?mode=ro", uri=True)) as db:
        require(db.execute("PRAGMA quick_check").fetchone() == ("ok",), "ledger integrity failed")
        require(db.execute("SELECT COUNT(*) FROM candidate_write").fetchone() == (0,), "unexpected write ledger row")
    files = ["bootstrap.json", "source-inventory.json", "final-active-002.json"]
    files += ["%s-%03d.json" % (kind, seq) for kind in ("request", "response") for seq in (1, 2, 3)]
    return {
        "schema_version": 1, "case_id": case_id, "status": "independently_verified_lifecycle_only",
        "initial_before_after_stop_active_sha256": bootstrap["initial_active_sha256"],
        "raw_capture_scope": capture["capture_scope"], "close_seq": 2,
        "fixture_closed": True, "actual_handoff_key_absent": True, "controller_stopped": True,
        "model_calls": 0, "write_requests": 0, "ledger_rows": 0,
        "source_files": len(inventory), "source_inventory_sha256": canonical_hash(inventory),
        "source_inventory": inventory,
        "private_evidence_sha256": {name: hashlib.sha256((batch/name).read_bytes()).hexdigest() for name in files},
        "private_result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "formal_quality_claim": False, "full_R_research_safety_gate_passed": False,
        "c5_6_authorized": False, "limitations": ["no write/consent/geometry field verification", "no remote model lineage", "not C5 twelve-tool executor"],
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
    print(json.dumps({k: value[k] for k in ("status", "case_id", "source_files", "full_R_research_safety_gate_passed")}))


if __name__ == "__main__":
    main()
