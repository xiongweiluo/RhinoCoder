#!/usr/bin/env python3
"""Owner-approved fixed two-write safety probe; no model and no quality score.

This is deliberately not a twelve-tool C5 executor or formal task generator.
An external owner approval must bind the exact probe before any fixture opens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.rhino_listener.candidate_file_channel import load_private_secret, publish_signed_envelope  # noqa: E402
from plugin.rhino_listener.research_safety import (canonical_hash, cleanup_plan, require, verify_exact_transition,
    verify_final_active_capture, verify_loaded_sources, verify_write_binding)  # noqa: E402
from tools.r4_controlled_access_archive_v2 import _backup_ledger  # noqa: E402
from tools.r4_v5_ssh_no_write_session import _private_publish, _private_read  # noqa: E402
from tools.r4_v6_live_multistep import V6Scene, _execute, _initial  # noqa: E402
from tools.r_research_lifecycle_smoke import request  # noqa: E402
from training.consent_candidate import ConsentStore, DELEGATED_HEADLESS_SCOPE  # noqa: E402
from training.consent_handoff_v5_candidate import issue_signed_handoff  # noqa: E402
from training.explicit_step_gate_candidate import preflight  # noqa: E402
from training.tool_invocation_v5_candidate import CheckedInvocation  # noqa: E402
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402

SPEC = {
    "probe_id": "RSDEV-TWO-WRITE-20261002-A", "scope": "isolated_unsaved_headless_mm",
    "steps": [{"op": "create_box", "width": 347, "depth": 353, "height": 359},
              {"op": "move_object", "alias": "box-1", "dx": 7, "dy": -11, "dz": 13}],
    "max_write_requests": 2, "model_calls": 0, "formal_quality_claim": False,
}

# A was attempted once and failed after its first write. A fresh output path
# or corrected verifier does not authorize replay; a future probe requires
# its own versioned spec, ID and external owner approval.
RETIRED_PROBE_IDS = frozenset({"RSDEV-TWO-WRITE-20261002-A"})


def verify_owner_approval(approval, *, spec=None):
    spec = SPEC if spec is None else spec
    require(isinstance(approval, dict) and approval.get("authorized_by") == "repository_owner"
            and approval.get("probe_spec_sha256") == canonical_hash(spec)
            and approval.get("approved") is True
            and approval.get("authorization_basis") == "explicit owner reply approving fixed two-write research safety probe",
            "exact external owner approval missing; agent must not self-approve")


def write_steps(session, output, *, spec=None):
    spec = SPEC if spec is None else spec
    scene = V6Scene(session)
    require(not _initial(session).objects, "fixture not empty")
    tools = load_public_mcp_tools()
    consent = ConsentStore(output/"consent.sqlite3", tools)
    records = []
    for number, explicit in enumerate(spec["steps"], 1):
        before = scene.capture()
        task = json.dumps(explicit, sort_keys=True, separators=(",", ":"))
        expected = preflight(task, scene=scene, tools=tools)
        arguments = expected.arguments
        target = arguments.pop("object_id", None)
        checked = CheckedInvocation(expected.tool_name, arguments, target)
        link = consent.prepare(task, expected.tool_name, expected.arguments, scene=scene,
                               delegated_scope=DELEGATED_HEADLESS_SCOPE, ttl_seconds=300)
        try:
            require(consent.approve_delegated_headless(link) == "approved", "scoped approval rejected")
            envelope = issue_signed_handoff(task=task, checked=checked, link=link, scene=scene, consent=consent,
                                           tools=tools, secret=load_private_secret(session/"channel"))
            # No retry/reissue after publishing a consumed signed handoff.
            request_id = publish_signed_envelope(session/"channel", envelope)
            execution = _execute(session, request_id)
            require(execution.get("status") == "done", "execution uncertain; never retry")
            after = scene.capture()
            payload = envelope["payload"]
            verify_exact_transition(expected.tool_name, payload["arguments"], before.geometry_view(), after.geometry_view())
            with closing(sqlite3.connect((session/"fixture.sqlite3").as_uri()+"?mode=ro", uri=True)) as db:
                db.row_factory = sqlite3.Row
                key = hashlib.sha256(request_id.encode()).hexdigest()
                rows = db.execute("SELECT * FROM candidate_write WHERE idempotency_key=?", (key,)).fetchall()
                require(len(rows) == 1, "missing or duplicate write reservation")
                ledger_row = dict(rows[0])
            consent_row, _ = consent.inspect(link)
            record = {
                "request_id": request_id, "operation": expected.tool_name,
                "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
                "signed_arguments": payload["arguments"], "before_revision": before.state.revision,
                "document_key": before.state.summary["document_key"],
                "before_scene_sha256": before.state.scene_sha256, "after_scene_sha256": after.state.scene_sha256,
                "before_geometry": before.geometry_view(), "after_geometry": after.geometry_view(),
                "envelope_payload": payload, "execution": execution, "ledger_row": ledger_row,
                "consent_request": consent_row, "consent_events": consent.audit_events(request_id),
            }
            # Retain raw evidence before verification, including on failure.
            # A step file's presence is not a verified step/pass flag.
            _private_publish(output, "step-%d.json" % number, record)
            verify_write_binding(record=record, execution=execution, ledger_row=ledger_row,
                                 consent_request=consent_row, consent_events=record["consent_events"], envelope_payload=payload)
            records.append(record)
        finally:
            consent.abort_without_human(link)
    return records


def run(batch, output, approval, *, spec=None):
    spec = SPEC if spec is None else spec
    verify_owner_approval(approval, spec=spec)
    require(spec["probe_id"] not in RETIRED_PROBE_IDS, "probe ID retired after field attempt; no replay")
    if canonical_hash(spec) != canonical_hash(SPEC):
        # A future spec cannot use the shared engine as a backdoor around its
        # frozen entry/one-attempt admission. Only fixed B is implemented.
        from tools.r_research_two_write_v2 import begin_engine
        begin_engine(batch, output, approval, spec)
    require(not output.exists(), "fresh output required; safety probe cannot be rerun under same ID")
    bootstrap = _private_read(batch/"bootstrap.json")
    inventory = _private_read(batch/"source-inventory.json")
    require(bootstrap.get("version") == 2 and bootstrap.get("model_invocation_allowed") is False
            and bootstrap.get("formal_quality_claim") is False and bootstrap.get("scope") == spec["scope"],
            "unexpected controller")
    verify_loaded_sources(ROOT, inventory, tuple(sys.modules.values()))
    os.mkdir(output, 0o700)
    _private_publish(output, "owner-approval.json", approval)
    opened = closed = stopped = None
    records = []
    error = None
    cleanup_verified = False
    try:
        opened = request(batch, 1, "open", spec["probe_id"], "empty")
        require(cleanup_plan(open_published=True, case_id=spec["probe_id"], opened=opened)["actions"] == ["close", "stop"],
                "open identity unknown")
        require(opened.get("initial_active_sha256") == bootstrap["initial_active_sha256"], "initial active hash differs")
        records = write_steps(Path(opened["session_dir"]), output, spec=spec)
    except BaseException as exc:
        error = type(exc).__name__+":"+str(exc)
    finally:
        if opened is None and (batch/"response-001.json").exists():
            try: opened = _private_read(batch/"response-001.json")
            except BaseException: pass
        plan = cleanup_plan(open_published=(batch/"request-001.json").exists(), case_id=spec["probe_id"], opened=opened)
        if plan["actions"] == ["close", "stop"]:
            try:
                closed = request(batch, 2, "close", spec["probe_id"], "none")
                capture = _private_read(batch/"final-active-002.json")
                require(closed.get("status") == "closed" and closed.get("case_id") == spec["probe_id"]
                        and closed.get("key_removed") is True
                        and closed.get("session_dir") == opened["session_dir"] and capture == closed.get("final_active_capture"),
                        "closure identity differs")
                verify_final_active_capture(capture, case_id=spec["probe_id"], session_dir=opened["session_dir"],
                                            initial_sha256=bootstrap["initial_active_sha256"])
                stopped = request(batch, 3, "stop", "RSDEV-END", "none")
                require(stopped.get("status") == "stopped" and stopped.get("case_id") == "RSDEV-END"
                        and stopped.get("had_failure") is False
                        and stopped.get("active_sha256_at_stop") == bootstrap["initial_active_sha256"], "stop unverified")
                cleanup_verified = True
            except BaseException as exc:
                error = (error+";" if error else "")+"cleanup:"+type(exc).__name__+":"+str(exc)
                # Published close/stop are never reissued, and failure is never
                # converted to success by a late cleanup response.
                # Only known-identity open permits a fixed ordered stop. The
                # UI controller itself refuses stop until its fixture closes.
                if (batch/"request-002.json").exists() and not (batch/"request-003.json").exists():
                    _private_publish(batch, "request-003.json", {
                        "version": 2, "seq": 3, "action": "stop", "fixture": "none", "case_id": "RSDEV-END",
                    })
        else:
            error = (error+";" if error else "")+"fixture identity unknown; manual cleanup required"
    passed = error is None and len(records) == 2
    if passed:
        _backup_ledger(Path(opened["session_dir"])/"fixture.sqlite3", output/"fixture.sqlite3", expected={"done": 2})
    result = {
        "status": "two_write_research_safety_pass_not_model_quality" if passed else "two_write_research_safety_fail",
        "probe_spec": spec, "probe_spec_sha256": canonical_hash(spec), "owner_approval": approval,
        "records": records, "error": error, "opened": opened, "closed": closed, "stopped": stopped,
        "source_inventory": inventory, "model_calls": 0, "formal_quality_claim": False,
        "c5_6_authorized": False, "no_model_or_tool_retries": True,
        # Closure does not make a failed task pass; a task error does not erase
        # closure already checked against the exact UI-thread receipts.
        "cleanup_verified": cleanup_verified,
    }
    _private_publish(output, "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--owner-approval", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.batch_dir, args.output_dir, _private_read(args.owner_approval))
    print(json.dumps({k: result[k] for k in ("status", "error", "model_calls", "c5_6_authorized")}))
    raise SystemExit(0 if result["error"] is None else 1)


if __name__ == "__main__":
    main()
