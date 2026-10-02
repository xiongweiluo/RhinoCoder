#!/usr/bin/env python3
"""One fresh no-model/no-write lifecycle probe against research controller v2.

Only disposable empty headless fixture open/close/stop. Timeouts preserve
failure; cleanup requests are not closure proof. Never consumes a holdout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.r4_v5_ssh_no_write_session import _private_publish, _private_read  # noqa: E402
from plugin.rhino_listener.research_safety import (cleanup_plan, require, verify_final_active_capture,
                                     verify_loaded_sources)  # noqa: E402


def request(directory, seq, action, case_id, fixture, *, seconds=30):
    _private_publish(directory, "request-%03d.json" % seq, {
        "version": 2, "seq": seq, "action": action, "case_id": case_id, "fixture": fixture,
    })
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        failure = directory/("failure-%03d.json" % seq)
        if failure.exists():
            raise RuntimeError("research controller failure: "+json.dumps(_private_read(failure)))
        response = directory/("response-%03d.json" % seq)
        if response.exists():
            return _private_read(response)
        time.sleep(.1)
    raise TimeoutError("research response timeout: "+action)


def run_smoke(directory, output, case_id, *, send=request):
    require(re.fullmatch(r"RSDEV-[A-Z0-9-]{1,48}", case_id) is not None and not output.exists(),
            "fresh research case/output required")
    bootstrap = _private_read(directory/"bootstrap.json")
    inventory = _private_read(directory/"source-inventory.json")
    require(bootstrap.get("version") == 2 and bootstrap.get("model_invocation_allowed") is False
            and bootstrap.get("formal_quality_claim") is False, "not the no-model research controller")
    verify_loaded_sources(ROOT, inventory, tuple(sys.modules.values()))
    os.mkdir(output, 0o700)
    opened = closed = stopped = None
    error = None
    try:
        opened = send(directory, 1, "open", case_id, "empty")
        plan = cleanup_plan(open_published=True, case_id=case_id, opened=opened)
        require(plan["state"] == "known_fixture_ordered_cleanup_pending", "open identity unverified")
        require(opened.get("initial_active_sha256") == bootstrap["initial_active_sha256"], "initial digest mismatch")
        closed = send(directory, 2, "close", case_id, "none")
        require(closed.get("status") == "closed" and closed.get("session_dir") == opened["session_dir"]
                and closed.get("case_id") == case_id and closed.get("key_removed") is True, "close identity unverified")
        capture = _private_read(directory/"final-active-002.json")
        require(capture == closed.get("final_active_capture"), "capture/close receipt differ")
        verify_final_active_capture(capture, case_id=case_id, session_dir=opened["session_dir"],
                                    initial_sha256=bootstrap["initial_active_sha256"])
        stopped = send(directory, 3, "stop", "RSDEV-END", "none")
        require(stopped.get("status") == "stopped" and stopped.get("case_id") == "RSDEV-END"
                and stopped.get("had_failure") is False
                and stopped.get("active_sha256_at_stop") == bootstrap["initial_active_sha256"], "stop unverified")
    except BaseException as exc:
        error = type(exc).__name__+":"+str(exc)
    published = (directory/"request-001.json").exists()
    # A timeout may have a safely readable late open. It is not task success.
    if opened is None and (directory/"response-001.json").exists():
        try:
            opened = _private_read(directory/"response-001.json")
        except BaseException:
            pass
    plan = cleanup_plan(open_published=published, case_id=case_id, opened=opened, closed=closed)
    if error:
        # Queue only known-identity close/stop at their fixed sequence numbers;
        # never overwrite a published request or resend an execute/open.
        for action in plan["actions"]:
            seq = 2 if action == "close" else (3 if published else 1)
            target = case_id if action == "close" else "RSDEV-END"
            path = directory/("request-%03d.json" % seq)
            if not path.exists():
                _private_publish(directory, path.name, {
                    "version": 2, "seq": seq, "action": action, "fixture": "none", "case_id": target,
                })
    result = {
        "status": "research_lifecycle_smoke_pass_no_model_no_write" if not error else "research_lifecycle_failed_cleanup_unverified",
        "case_id": case_id, "error": error, "opened": opened, "closed": closed, "stopped": stopped,
        "cleanup_plan": plan, "cleanup_verified": error is None, "model_calls": 0, "write_requests": 0,
        "formal_quality_claim": False, "source_inventory": inventory,
    }
    _private_publish(output, "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()
    result = run_smoke(args.batch_dir, args.output_dir, args.case_id)
    print(json.dumps({k: result[k] for k in ("status", "case_id", "cleanup_verified", "model_calls", "write_requests")}))
    raise SystemExit(0 if result["cleanup_verified"] else 1)


if __name__ == "__main__":
    main()
