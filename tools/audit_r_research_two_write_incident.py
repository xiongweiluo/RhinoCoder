#!/usr/bin/env python3
"""Post-hoc read-only audit of failed, retired two-write attempt A.

Reconstructs only its first synthetic write from raw receipts. Never executes,
retries, changes the original result, or upgrades the failed two-write gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.rhino_listener.research_safety import (canonical_hash, require, verify_exact_transition,
    verify_final_active_capture, verify_write_binding)  # noqa: E402
from tools.audit_r_research_two_write import database_rows  # noqa: E402
from tools.r4_v5_ssh_no_write_session import _private_read  # noqa: E402
from tools.r4_v6_live_multistep import _capture_value, _geometry_args, _initial  # noqa: E402
from tools.r_research_two_write_smoke import SPEC, verify_owner_approval  # noqa: E402

FROZEN_REVISION = "ae74b0e13591d69c4b01fca528b50fa6d4465bf8"


def verify_frozen_inventory(inventory):
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", FROZEN_REVISION, "--",
        "agent", "training", "tools", "plugin", "mcp_server", "requirements-lock.txt"], cwd=ROOT).decode().splitlines()
    expected = {}
    for name in names:
        if name.endswith(".py") or name == "requirements-lock.txt":
            raw = subprocess.check_output(["git", "show", FROZEN_REVISION+":"+name], cwd=ROOT)
            expected[name] = hashlib.sha256(raw).hexdigest()
    require(inventory == expected and bool(expected), "field source manifest differs from frozen original Git revision")


def audit(archive):
    batch, client, fixture = (archive/name for name in ("batch", "client", "fixture"))
    result = _private_read(client/"result.json", limit=512*1024)
    require(result.get("status") == "two_write_research_safety_fail"
            and result.get("error") == "ResearchSafetyError:pre-scene chain differs"
            and result.get("cleanup_verified") is False and result.get("records") == []
            and result.get("model_calls") == 0 and result.get("formal_quality_claim") is False
            and result.get("c5_6_authorized") is False and result.get("no_model_or_tool_retries") is True,
            "original failed attempt was changed or unexpected")
    require(result.get("probe_spec") == SPEC and SPEC["probe_id"] == "RSDEV-TWO-WRITE-20261002-A"
            and result.get("probe_spec_sha256") == canonical_hash(SPEC), "retired spec differs")
    verify_owner_approval(result["owner_approval"])
    require(_private_read(client/"owner-approval.json") == result["owner_approval"], "owner receipt differs")
    inventory = _private_read(batch/"source-inventory.json")
    require(inventory == result["source_inventory"], "manifest/result differs")
    verify_frozen_inventory(inventory)
    bootstrap = _private_read(batch/"bootstrap.json")
    require(bootstrap.get("version") == 2 and bootstrap.get("scope") == SPEC["scope"]
            and bootstrap.get("model_invocation_allowed") is False and bootstrap.get("formal_quality_claim") is False,
            "bootstrap scope differs")
    require({p.name for p in batch.glob("request-*.json")} == {"request-%03d.json" % n for n in (1, 2, 3)}
            and {p.name for p in batch.glob("response-*.json")} == {"response-%03d.json" % n for n in (1, 2, 3)},
            "extra/missing lifecycle request or response")
    for n, action, case, kind in ((1, "open", SPEC["probe_id"], "empty"),
                                (2, "close", SPEC["probe_id"], "none"), (3, "stop", "RSDEV-END", "none")):
        require(_private_read(batch/("request-%03d.json" % n)) == {
            "version": 2, "seq": n, "action": action, "case_id": case, "fixture": kind}, "lifecycle order/identity differs")
    opened, closed, stopped = (_private_read(batch/("response-%03d.json" % n)) for n in (1, 2, 3))
    require((opened, closed, stopped) == (result["opened"], result["closed"], result["stopped"]), "result/receipts differ")
    require(opened.get("status") == "opened" and opened.get("case_id") == SPEC["probe_id"]
            and opened.get("fixture") == "empty" and opened.get("initial_active_sha256") == bootstrap["initial_active_sha256"],
            "open identity differs")
    require(closed.get("status") == "closed" and closed.get("case_id") == SPEC["probe_id"]
            and closed.get("key_removed") is True and closed.get("session_dir") == opened["session_dir"], "close unverified")
    capture = _private_read(batch/"final-active-002.json")
    require(capture == closed["final_active_capture"] and capture.get("close_seq") == 2, "final capture differs")
    verify_final_active_capture(capture, case_id=SPEC["probe_id"], session_dir=opened["session_dir"],
                                initial_sha256=bootstrap["initial_active_sha256"])
    require(stopped.get("status") == "stopped" and stopped.get("case_id") == "RSDEV-END"
            and stopped.get("had_failure") is False
            and stopped.get("active_sha256_at_stop") == bootstrap["initial_active_sha256"], "stop unverified")
    original_session = Path(opened["session_dir"])
    require(original_session.is_absolute() and original_session.is_dir(), "original closed fixture directory unavailable")
    for directory in (original_session/"channel", fixture/"channel"):
        require(not any((directory/name).exists() or (directory/name).is_symlink()
                        for name in ("handoff.key", "secret")), "key remains")
    require(not list(original_session.glob("v6-plan-*")), "unexpected model plan")
    # An archive must not conceal a second attempt or rejected/replayed request.
    for directory, original in ((fixture, original_session), (fixture/"channel", original_session/"channel")):
        names = {p.name for p in directory.glob("*.json")}
        actual = {p.name for p in original.glob("*.json") if p.name == "initial.json"
                  or p.name.startswith(("capture-", "execute-")) or original.name == "channel"}
        require(names == actual and all((directory/name).read_bytes() == (original/name).read_bytes() for name in names),
                "archive differs from original requests/readbacks/handoffs")
    requests = [p for p in fixture.glob("execute-*.json") if not p.name.startswith("execute-response-")]
    require(len(requests) == len(list(fixture.glob("execute-response-*.json"))) == 1, "not exactly one write attempt")
    request = _private_read(requests[0])
    nonce = requests[0].stem.removeprefix("execute-")
    require(request == {"version": 1, "nonce": nonce, "request_id": request.get("request_id")}, "execute identity differs")
    execution = _private_read(fixture/("execute-response-"+nonce+".json"))
    envelopes = list((fixture/"channel").glob("*.json"))
    require(len(envelopes) == 1 and envelopes[0].name == request["request_id"]+".json", "handoff count differs")
    envelope = _private_read(envelopes[0])
    payload = envelope["payload"]
    explicit = SPEC["steps"][0]
    require(payload.get("version") == 1 and payload.get("operation") == "create_box"
            and payload.get("request_id") == request["request_id"] and payload.get("arguments") == _geometry_args(explicit)
            and payload.get("scene_revision") == 0
            and payload.get("task_sha256") == hashlib.sha256(json.dumps(explicit, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest(), "first approved task differs")
    initial = _initial(fixture)
    require(initial.state.revision == 0 and initial.state.scene_sha256 == payload["scene_sha256"]
            and initial.state.summary["document_key"] == payload["document_key"]
            and _private_read(fixture/"initial.json")["active_document_content_sha256"] == bootstrap["initial_active_sha256"],
            "initial scene differs")
    snapshots = []
    for path in fixture.glob("capture-response-*.json"):
        value = _private_read(path)
        capture_nonce = path.stem.removeprefix("capture-response-")
        require(value.get("version") == 1 and value.get("nonce") == capture_nonce
                and _private_read(fixture/("capture-"+capture_nonce+".json")) == {"version": 1, "nonce": capture_nonce},
                "capture identity differs")
        snapshots.append(_capture_value(value["scene"]))
    before = [v for v in snapshots if v.state.scene_sha256 == payload["scene_sha256"]]
    after = [v for v in snapshots if v.state.scene_sha256 == execution.get("after_scene_sha256")]
    require(bool(before) and bool(after) and all(v.state == initial.state and v.geometry_view() == initial.geometry_view()
                                               for v in before), "before capture differs")
    require(all(v.state.revision == 1 and v.state.summary["document_key"] == payload["document_key"]
                and v.state.summary["unit"] == "Millimeters" and v.geometry_view() == after[0].geometry_view()
                for v in after), "after capture differs")
    ledgers = database_rows(fixture/"fixture.sqlite3", ("candidate_write",))["candidate_write"]
    live_ledgers = database_rows(original_session/"fixture.sqlite3", ("candidate_write",))["candidate_write"]
    consent = database_rows(client/"consent.sqlite3", ("consent_requests", "consent_events"))
    require(len(ledgers) == 1 and live_ledgers == ledgers and len(consent["consent_requests"]) == 1
            and len(consent["consent_events"]) == 4, "extra/missing ledger or consent")
    record = {"request_id": request["request_id"], "operation": "create_box", "signed_arguments": payload["arguments"],
              "task_sha256": payload["task_sha256"], "document_key": payload["document_key"], "before_revision": 0,
              "before_scene_sha256": payload["scene_sha256"], "after_scene_sha256": execution["after_scene_sha256"]}
    verify_exact_transition("create_box", payload["arguments"], initial.geometry_view(), after[0].geometry_view())
    # Corrected post-hoc verifier allows legitimate zero; this is diagnostic
    # evidence only. The original runtime result remains failed and immutable.
    verify_write_binding(record=record, execution=execution, ledger_row=ledgers[0], envelope_payload=payload,
                         consent_request=consent["consent_requests"][0], consent_events=consent["consent_events"])
    original_checker = subprocess.check_output(["git", "show", FROZEN_REVISION+":plugin/rhino_listener/research_safety.py"], cwd=ROOT)
    require(b'record["before_revision"] >= 1' in original_checker, "original defect not present in frozen checker")
    evidence = [p for directory in (batch, client, fixture, fixture/"channel") for p in directory.iterdir() if p.is_file()]
    return {"schema_version": 1, "probe_id": SPEC["probe_id"], "probe_spec_sha256": canonical_hash(SPEC),
        "status": "failed_attempt_preserved_posthoc_first_write_and_cleanup_verified", "original_status": result["status"],
        "original_error": result["error"], "original_cleanup_verified_flag": False,
        "runtime_source_revision": FROZEN_REVISION, "runtime_source_files": len(inventory),
        "runtime_source_inventory_sha256": canonical_hash(inventory), "runtime_source_inventory": inventory,
        "diagnosis": "original verifier wrongly required before_revision >= 1; all actual pre-scene revisions equal valid zero",
        "posthoc_binding_and_box_bounds_verified": True, "actual_before_revision": 0, "actual_after_revision": 1,
        "write_attempts": 1, "ledger_rows_done": 1, "consumed_consents": 1, "consent_events": 4,
        "second_write_attempts": 0, "model_calls": 0, "owner_approval_bound": True,
        "fixture_closed_verified": True, "actual_handoff_key_absent_at_audit": True, "controller_stopped_verified": True,
        "initial_before_after_stop_active_sha256": bootstrap["initial_active_sha256"], "raw_capture_scope": capture["capture_scope"],
        "private_evidence_sha256": {p.relative_to(archive).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence},
        "formal_quality_claim": False, "two_write_gate_passed": False, "full_R_research_safety_gate_passed": False,
        "c5_6_authorized": False, "retired_no_replay": True,
        "limitations": ["only first fixed synthetic create_box; move never attempted", "no model quality or twelve-tool proof",
                        "HMAC verified at runtime only; removed secret not recovered", "post-hoc diagnostics do not promote attempt A to PASS"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = audit(args.archive)
    with args.output.open("x") as destination:
        destination.write(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k: value[k] for k in ("status", "write_attempts", "second_write_attempts", "two_write_gate_passed")}))


if __name__ == "__main__":
    main()
