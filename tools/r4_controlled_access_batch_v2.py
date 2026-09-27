#!/usr/bin/env python3
"""One-shot isolated R candidate runner; never the default product route.

Requires an existing Rhino UI-thread batch controller and a private SSH master.
Opens one empty disposable fixture, requests interactive operator opt-in, runs
the guarded candidate once, then closes/archives the fixture and stops the
controller. Failed or uncertain results remain failures, never retries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import r4_v6_formal_quality as core
from tools.r4_controlled_access_archive_v2 import _safe_bytes, archive_closed_case
from tools.r4_controlled_access_candidate_v2 import run as run_candidate
from tools.r4_controlled_access_optin_v2 import interactive_preflight_opt_in, request_stop
from tools.r4_v5_ssh_no_write_session import _private_publish, _private_publish_bytes, _private_read


def _expected_from_execution_receipts(session: Path) -> dict[str, int]:
    """Independent of the SQLite ledger; disagreement blocks archive success."""
    responses = sorted(session.glob("execute-response-*.json"))
    done = 0
    for path in responses:
        response = _private_read(path)
        if response.get("status") == "done" and response.get("ledger_state") == "done":
            done += 1
    return {"done": done} if done else {}


def _ledger_state(session: Path) -> dict[str, int]:
    with closing(sqlite3.connect((session / "fixture.sqlite3").as_uri() + "?mode=ro", uri=True)) as db:
        return dict(db.execute("SELECT state, COUNT(*) FROM candidate_write GROUP BY state"))


def _manifest(output: Path, source_files: tuple[str, ...]) -> None:
    files = {str(path.relative_to(output)): core.digest(path)
             for path in sorted(output.rglob("*")) if path.is_file()
             and path.name != "evidence-manifest.json"}
    _private_publish(output, "evidence-manifest.json", {
        "version": 2, "candidate": "r4_controlled_access_candidate_v2",
        "formal_quality_claim": False, "files": files,
        "source_sha256": {name: core.digest(core.ROOT / name) for name in source_files},
    })


SOURCE_FILES = (
    "agent/privacy.py",
    "tools/r4_candidate_ssh_master.sh",
    "tools/r4_controlled_access_archive_v2.py",
    "tools/r4_controlled_access_batch_v2.py",
    "tools/r4_controlled_access_candidate_v2.py",
    "tools/r4_controlled_access_optin_v2.py",
    "tools/r4_controlled_access_remote_guard_v2.py",
    "tools/r4_controlled_access_verify_candidate_v2.py",
    "tools/r4_v6_live_multistep.py",
    "tools/r4_v6_formal_quality.py",
    "tools/r4_v5_live_human_write.py",
    "tools/r4_v5_ssh_no_write_session.py",
    "tools/r4_v5_one_step_remote_probe.py",
    "plugin/rhino_listener/candidate_file_channel.py",
    "plugin/rhino_listener/candidate_readonly_idle_session.py",
    "plugin/rhino_listener/candidate_v6_live_session.py",
    "training/consent_candidate.py",
    "training/consent_handoff_v5_candidate.py",
    "training/controlled_v6_plan.py",
    "training/remote_result_v5_candidate.py",
    "training/tool_controller_candidate.py",
    "training/tool_schema_inventory.py",
)
V8_REPORT = core.ROOT / "docs/r4-evidence/v8-formal-run-20260926/report.json"
V8_REPORT_SHA256 = "f83de1b84a357f9983803fb00b3fed729b0f9361a394b39a023a212af36099c2"


def _verify_historical_baseline() -> None:
    if core.digest(V8_REPORT) != V8_REPORT_SHA256:
        raise RuntimeError("v8_original_report_digest_changed")
    report = json.loads(V8_REPORT.read_text(encoding="utf-8"))
    if (report.get("status") != "formal_quality_fail"
            or report.get("denominator") != 60
            or report.get("evaluated") != 60):
        raise RuntimeError("v8_original_formal_status_changed")
    cases = sorted(V8_REPORT.parent.glob("R8-*.json"))
    if len(cases) != 60 or sum(json.loads(path.read_text(encoding="utf-8")).get("passed") is True
                               for path in cases) != 59:
        raise RuntimeError("v8_original_case_result_changed")


def _reconcile_late_open(batch_dir: Path, case_id: str, *, seconds: float = 60) -> dict | None:
    """Resolve a published open request before using any later batch sequence.

    A Rhino UI stall can outlive the requester's 30-second wait.  Never send a
    stop as seq=1 in that case: the controller may still open the fixture.
    """
    response = batch_dir / "response-001.json"
    failure = batch_dir / "failure-001.json"
    deadline = time.monotonic() + seconds
    while True:
        if response.exists():
            opened = _private_read(response)
            if (opened.get("status") != "opened"
                    or opened.get("case_id") != case_id
                    or opened.get("fixture") != "empty"
                    or not isinstance(opened.get("session_dir"), str)):
                raise RuntimeError("candidate_late_open_receipt_invalid")
            return opened
        if failure.exists() or time.monotonic() >= deadline:
            return None
        time.sleep(0.1)


def _queue_unverified_cleanup(batch_dir: Path, case_id: str) -> None:
    """Leave ordered close/stop requests for a controller that resumes later.

    These requests do not prove cleanup.  The result remains a failure until
    a separate operator verifies the late responses and archived ledger.
    """
    for seq, action, fixture, target in (
            (2, "close", "none", case_id),
            (3, "stop", "none", "RCA2-END")):
        _private_publish(batch_dir, f"request-{seq:03d}.json", {
            "version": 1, "seq": seq, "action": action,
            "fixture": fixture, "case_id": target,
        })


def run_one(batch_dir: Path, output: Path, case_id: str, task: str,
            ssh_args: SimpleNamespace) -> dict:
    """Fail-closed one-shot candidate orchestration with best-effort cleanup."""
    if (not isinstance(task, str) or not task.strip()
            or len(task.encode("utf-8")) > 4096 or output.exists()):
        raise ValueError("invalid_task_or_existing_output")
    if not re.fullmatch(r"RCA2-[A-Z0-9-]{1,58}", case_id):
        raise ValueError("candidate_case_id_invalid")
    _verify_historical_baseline()
    os.mkdir(output, 0o700)
    _private_publish(output, "preflight.json", {
        "case_id": case_id, "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
        "model_manifest_sha256": core.MODEL_SHA,
        "host_key_sha256": core.HOST_KEY,
        "scope": "isolated_unsaved_headless_mm", "formal_quality_claim": False,
        "v8_original_formal_status": "formal_quality_fail",
        "v8_original_per_case_passed": 59,
        "v8_original_report_sha256": V8_REPORT_SHA256,
    })
    seq = 1
    session = None
    pending_opt_in = None
    lease = None
    receipt = None
    error = None
    close_receipt = None
    stopped = None
    archive = None
    open_attempted = False
    late_open_reconciled = False
    cleanup_queued_unverified = False
    try:
        preflight_args = SimpleNamespace(**vars(ssh_args), task=task,
                                         fixture_name="empty",
                                         delegated_headless_approval=True)
        pending_opt_in = interactive_preflight_opt_in(preflight_args)
        open_attempted = True
        opened = core._batch_request(batch_dir, seq, "open", case_id, "empty")
        seq += 1
        if (opened.get("case_id") != case_id or opened.get("fixture") != "empty"
                or not isinstance(opened.get("session_dir"), str)):
            raise RuntimeError("candidate_open_receipt_invalid")
        session = Path(opened["session_dir"])
        args = SimpleNamespace(**vars(ssh_args), session_dir=session, task=task,
                               fixture_name="empty", delegated_headless_approval=True)
        lease = pending_opt_in.bind(args)
        run_dir, receipt = run_candidate(args, lease)
        if run_dir is not None and receipt.get("status") != (
                "controlled_access_candidate_v2_completed_not_formal_quality"):
            raise RuntimeError("candidate_result_not_complete")
    except BaseException as exc:
        error = type(exc).__name__ + ":" + str(exc)
    finally:
        if open_attempted and session is None and not (batch_dir / "request-001.json").exists():
            # Publication failed before Rhino could see an open request.
            open_attempted = False
        if open_attempted and session is None:
            # Even a failed/expired call may have published request-001.
            # Advance the sequence before attempting *any* cleanup.
            seq = 2
            try:
                opened = _reconcile_late_open(batch_dir, case_id)
                if opened is not None:
                    session = Path(opened["session_dir"])
                    late_open_reconciled = True
                else:
                    _queue_unverified_cleanup(batch_dir, case_id)
                    cleanup_queued_unverified = True
                    error = (error + ";" if error else "") + (
                        "open_unresolved_cleanup_queued_unverified")
            except BaseException as exc:
                error = (error + ";" if error else "") + (
                    "open_reconciliation:" + type(exc).__name__ + ":" + str(exc))
        if lease is not None:
            try:
                lease.stop()
                _private_publish_bytes(output, "operator-grant.json",
                                       _safe_bytes(lease.control_dir / "grant.json"))
                _private_publish_bytes(output, "operator-stop.json",
                                       _safe_bytes(lease.control_dir / "stop.json"))
            except BaseException as exc:
                error = (error + ";" if error else "") + (
                    "opt_in_cleanup:" + type(exc).__name__ + ":" + str(exc))
        elif pending_opt_in is not None:
            try:
                pending_opt_in.stop()
                _private_publish_bytes(output, "operator-stop.json",
                                       _safe_bytes(pending_opt_in.control_dir / "stop.json"))
            except BaseException as exc:
                error = (error + ";" if error else "") + (
                    "preflight_opt_in_cleanup:" + type(exc).__name__ + ":" + str(exc))
        if session is not None:
            try:
                close_receipt = core._batch_request(batch_dir, seq, "close", case_id, "none")
                seq += 1
                _private_publish(output, "close-receipt.json", close_receipt)
                expected = _expected_from_execution_receipts(session)
                archive = archive_closed_case(session, output, case_id,
                                              close_receipt, expected_ledger=expected)
                _private_publish(output, "archive-receipt.json", archive)
            except BaseException as exc:
                error = (error + ";" if error else "") + (
                    "cleanup_or_archive:" + type(exc).__name__ + ":" + str(exc))
        if (not open_attempted and session is None) or close_receipt is not None:
            try:
                stopped = core._batch_request(batch_dir, seq, "stop", "RCA2-END", "none")
                _private_publish(output, "controller-receipt.json", stopped)
            except BaseException as exc:
                error = (error + ";" if error else "") + (
                    "controller_stop:" + type(exc).__name__ + ":" + str(exc))
        try:
            ledger = _ledger_state(session) if session is not None and close_receipt is not None else None
            expected = (_expected_from_execution_receipts(session)
                        if session is not None and close_receipt is not None else None)
        except BaseException as exc:
            ledger = expected = None
            error = (error + ";" if error else "") + (
                "ledger_audit:" + type(exc).__name__ + ":" + str(exc))
        for number in range(1, seq + 1):
            for stem in ("request", "response", "failure"):
                source = batch_dir / f"{stem}-{number:03d}.json"
                if source.exists():
                    try:
                        _private_publish_bytes(output, source.name, _safe_bytes(source))
                    except BaseException as exc:
                        error = (error + ";" if error else "") + (
                            "batch_audit:" + type(exc).__name__ + ":" + str(exc))
        passed = bool(
            error is None and lease is not None and receipt is not None
            and receipt.get("status") == "controlled_access_candidate_v2_completed_not_formal_quality"
            and receipt.get("active_document_unchanged") is True
            and type(receipt.get("step_count")) is int
            and receipt["step_count"] > 0
            and isinstance(receipt.get("steps"), list)
            and len(receipt.get("steps", [])) == receipt["step_count"]
            and all(row.get("readback_verified") is True for row in receipt.get("steps", []))
            and ledger == expected and archive is not None
            and archive.get("ledger") == expected
            and close_receipt is not None and close_receipt.get("key_removed") is True
            and stopped is not None and stopped.get("status") == "stopped")
        summary = {
            "status": "candidate_recorded_unverified" if passed else "candidate_fail",
            "formal_quality_claim": False, "case_id": case_id,
            "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
            "error": error, "ledger": ledger, "expected_ledger": expected,
            "fixture_closed": close_receipt is not None,
            "fixture_opened": session is not None,
            "key_removed": close_receipt.get("key_removed") if close_receipt else None,
            "controller_stopped": stopped is not None,
            "late_open_reconciled": late_open_reconciled,
            "cleanup_queued_unverified": cleanup_queued_unverified,
            "step_count": receipt.get("step_count") if receipt else None,
        }
        _private_publish(output, "summary.json", summary)
        _manifest(output, SOURCE_FILES)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    run = sub.add_parser("run")
    run.add_argument("--batch-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--case-id", required=True)
    run.add_argument("--task-file", type=Path, required=True,
                     help="0600 UTF-8 task in an owner-private directory; never put it in shell arguments")
    run.add_argument("--known-hosts", type=Path, required=True)
    run.add_argument("--control-socket", type=Path, required=True)
    stop = sub.add_parser("stop")
    stop.add_argument("--control-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "stop":
        request_stop(args.control_dir)
        print("STOP_REQUESTED: next guarded boundary will halt; completed writes are not undone")
        return
    core.require_remote_config()
    ssh = SimpleNamespace(
        host=core.HOST, port=core.PORT, user=core.USER,
        approved_manifest_sha256=core.MODEL_SHA,
        expected_host_key_sha256=core.HOST_KEY,
        known_hosts=args.known_hosts, control_socket=args.control_socket,
        collect_resource_metrics=True, formal_model_original_language=True,
        selector_json_prefix=True, v8_selector_prompt=True,
    )
    task = _safe_bytes(args.task_file).decode("utf-8")
    summary = run_one(args.batch_dir, args.output_dir, args.case_id, task, ssh)
    if summary["status"] != "candidate_recorded_unverified":
        print(json.dumps(summary, sort_keys=True, ensure_ascii=False))
        raise SystemExit(2)
    from tools.r4_controlled_access_verify_candidate_v2 import verify_archive

    try:
        verified = verify_archive(args.output_dir)
    except Exception as exc:
        print(json.dumps({"status": "candidate_evidence_fail",
                          "reason": type(exc).__name__ + ":" + str(exc),
                          "recorded": summary}, sort_keys=True, ensure_ascii=False))
        raise SystemExit(2) from None
    print(json.dumps(verified, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
