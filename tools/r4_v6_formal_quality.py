#!/usr/bin/env python3
"""Single-pass, fail-closed v6 60-case evaluator against frozen Rhino fixtures.

The corpus, labels, scorer and code hashes must be frozen before --run. A case
is opened once, evaluated once, and closed once. No case is retried or removed
from the 60-case denominator after a failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import sqlite3
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.r4_v5_ssh_no_write_session import _private_publish, _private_read  # noqa: E402
from tools.r4_v6_live_multistep import LiveRunError, V6Scene, run  # noqa: E402
from training.controlled_v6_plan import PlanError, compile_task  # noqa: E402

CORPUS = ROOT / "eval/r4_v6_formal_60.jsonl"
FIXTURES = ROOT / "eval/r4_v6_formal_fixtures.json"
EXPECTED = ROOT / "eval/r4_v6_formal_expected.json"
FREEZE = ROOT / "docs/r4-evidence/r4-v6-formal-freeze-20260923.json"
HASH_FILES = [
    ".gitignore", "docs/r4-independent-evaluation-protocol.md",
    "eval/r4_v6_formal_60.jsonl", "eval/r4_v6_formal_fixtures.json",
    "eval/r4_v6_formal_expected.json", "eval/r4_v3_public_tools.json",
    "eval/test_r4_v6_formal_quality.py", "tools/r4_v6_formal_exclusion_audit.py",
    "tools/r4_v6_formal_quality.py", "tools/r4_v6_formal_batch.py",
    "tools/r4_v6_formal_seed.py", "tools/r4_v6_live_multistep.py",
    "tools/r4_v5_live_human_write.py", "tools/r4_v5_one_step_remote_probe.py",
    "tools/r4_v5_ssh_no_write_session.py", "plugin/rhino_listener/candidate_v6_live_session.py",
    "plugin/rhino_listener/candidate_live_idle_session.py",
    "training/controlled_v6_plan.py", "training/tool_controller_candidate.py",
    "training/remote_result_v5_candidate.py", "training/consent_candidate.py",
    "training/consent_handoff_v5_candidate.py", "training/tool_selector_v4_candidate.py",
    "training/tool_invocation_v5_candidate.py", "plugin/rhino_listener/candidate_atomic_gate.py",
    "plugin/rhino_listener/candidate_file_channel.py",
]
MODEL_SHA = "90c5ca29d2ebc93dee5cb87b184c92a2493dfd39b010559508637b56cee3825c"
HOST_KEY = "SHA256:uenZe8XSigDXekroROhjmIi41k60yqNOYTjqt0mf7XM"
HOST = os.environ.get("R4_APPROVED_HOST", "unconfigured.invalid")
PORT = int(os.environ.get("R4_APPROVED_PORT", "0"))
USER = os.environ.get("R4_APPROVED_USER", "linux")
KNOWN_HOSTS = Path(os.environ.get("R4_KNOWN_HOSTS", "/dev/null"))
CONTROL = Path(os.environ.get("R4_CONTROL_SOCKET", "/dev/null"))


def require_remote_config() -> None:
    """Do not silently use a historical rented-instance endpoint in review code."""
    if (HOST == "unconfigured.invalid" or PORT <= 0 or PORT > 65535
            or not USER or KNOWN_HOSTS == Path("/dev/null")
            or CONTROL == Path("/dev/null")
            or not KNOWN_HOSTS.is_file()):
        raise RuntimeError("approved_remote_config_required")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_digest():
    rows = []
    for name in ("agent", "training", "tools", "plugin/rhino_listener"):
        for path in (ROOT / name).rglob("*.py"):
            if "__pycache__" not in path.parts:
                rows.append((str(path.relative_to(ROOT)), digest(path)))
    raw = "".join(name + " " + value + "\n" for name, value in sorted(rows)).encode()
    return hashlib.sha256(raw).hexdigest(), len(rows)


def remote_tree_digest():
    require_remote_config()
    command = (
        "cd /data/RhinoCoder-r4-gate && "
        "(find agent tools training -type f -name '*.py' -print; "
        "printf '%s\\n' eval/r4_v3_public_tools.json) | "
        "LC_ALL=C sort | xargs sha256sum | sha256sum"
    )
    result = subprocess.run([
        "ssh", "-T", "-S", str(CONTROL), "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlgorithms=ssh-ed25519",
        "-o", "UserKnownHostsFile=" + str(KNOWN_HOSTS),
        "-o", "GlobalKnownHostsFile=/dev/null", "-p", str(PORT), USER + "@" + HOST,
        command,
    ], capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or len(result.stdout.splitlines()) != 1:
        raise RuntimeError("remote_source_tree_unavailable")
    value = result.stdout.split()[0]
    if len(value) != 64 or any(letter not in "0123456789abcdef" for letter in value):
        raise RuntimeError("remote_source_tree_invalid")
    return value


def load_cases():
    cases = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert labels["version"] == 1
    assert len(cases) == len(labels["cases"]) == 60
    assert Counter(item["layer"] for item in cases) == Counter({letter: 12 for letter in "ABCDE"})
    assert [item["id"] for item in cases] == [item["id"] for item in labels["cases"]]
    assert len({item["task"] for item in cases}) == 60
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    assert all(item["fixture"] in fixtures for item in cases)
    for case, label in zip(cases, labels["cases"]):
        kind = case["expected"]["kind"]
        assert kind in {"complete", "clarify", "reject", "safe_scene_changed"}
        if kind in {"complete", "safe_scene_changed"}:
            plan = compile_task(case["task"])
            assert [step.operation for step in plan.steps] == case["expected"]["operations"]
            assert len(plan.steps) <= 6
        else:
            try:
                compile_task(case["task"])
            except PlanError as exc:
                assert exc.code == case["expected"]["code"]
            else:
                raise AssertionError("expected_rejection_did_not_reject:" + case["id"])
        assert isinstance(label["expected_final_objects"], list)
        if kind in {"clarify", "reject"} or all(
                op in {"get_scene_summary", "get_selected_objects"}
                for op in case["expected"]["operations"]):
            assert label["expected_final_objects"] == fixtures[case["fixture"]]["objects"]
            for read in label["expected_reads"]:
                if read["kind"] == "summary":
                    assert read["object_count"] == len(fixtures[case["fixture"]]["objects"])
                    assert read["aliases"] == [item["alias"] for item in fixtures[case["fixture"]]["objects"]]
                else:
                    assert read["aliases"] == fixtures[case["fixture"]]["selected_aliases"]
    return cases, labels["cases"]


def assert_freeze():
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    if frozen["model_manifest_sha256"] != MODEL_SHA or frozen["host_key_sha256"] != HOST_KEY:
        raise RuntimeError("formal_model_or_host_freeze_changed")
    current = {file: digest(ROOT / file) for file in HASH_FILES}
    if frozen["file_sha256"] != current:
        raise RuntimeError("formal_code_or_labels_changed_since_freeze")
    tree_sha, tree_count = source_tree_digest()
    if (frozen["local_source_tree_sha256"] != tree_sha
            or frozen["local_source_tree_file_count"] != tree_count):
        raise RuntimeError("formal_local_source_tree_changed_since_freeze")
    load_cases()
    return frozen


def _batch_request(batch_dir, seq, action, case_id, fixture):
    _private_publish(batch_dir, "request-%03d.json" % seq, {
        "version": 1, "seq": seq, "action": action,
        "case_id": case_id, "fixture": fixture,
    })
    response_path = batch_dir / ("response-%03d.json" % seq)
    failure_path = batch_dir / ("failure-%03d.json" % seq)
    deadline = time.monotonic() + 30
    while not response_path.exists():
        if failure_path.exists():
            raise RuntimeError("rhino_formal_batch_fail_closed:" + str(_private_read(failure_path)))
        if time.monotonic() >= deadline:
            raise RuntimeError("rhino_formal_batch_timeout")
        time.sleep(0.1)
    response = _private_read(response_path)
    if response.get("status") != {"open": "opened", "close": "closed", "stop": "stopped"}[action]:
        raise RuntimeError("rhino_formal_batch_response_invalid")
    return response


def _wait_session_ready(session_dir, fixture):
    paths = [session_dir / "initial.json"]
    if fixture != "empty":
        paths.append(session_dir / "formal-seed-receipt.json")
    deadline = time.monotonic() + 20
    while not all(path.is_file() for path in paths):
        if (session_dir / "failure.json").exists():
            raise RuntimeError("formal_fixture_failed_before_ready")
        if time.monotonic() >= deadline:
            raise RuntimeError("formal_fixture_ready_timeout")
        time.sleep(.1)


def _geometry_equal(actual, expected):
    if not isinstance(actual, list) or len(actual) != len(expected):
        return False
    a = {item["alias"]: item for item in actual}
    e = {item["alias"]: item for item in expected}
    return set(a) == set(e) and all(
        all(all(math.isclose(float(x), float(y), abs_tol=1e-7)
                for x, y in zip(a[key][bound], e[key][bound]))
            for bound in ("min", "max")) for key in e)


def _score(case, label, receipt, error, final, session_dir):
    expected = case["expected"]
    kind = expected["kind"]
    records = receipt.get("steps", []) if isinstance(receipt, dict) else []
    if not records:
        record_paths = sorted(session_dir.glob("v6-plan-*/step-*/record.json"),
                              key=lambda path: int(path.parent.name.split("-")[-1]))
        records = [_private_read(path) for path in record_paths]
    actual_ops = [item.get("operation") for item in records]
    geometry_ok = final is not None and _geometry_equal(
        final.geometry_view()["objects"], label["expected_final_objects"])
    reads_ok = True
    for item in label["expected_reads"]:
        record = next((row for row in records if row.get("index") == item["step"]), None)
        if record is None or not record.get("readback_verified"):
            reads_ok = False
            break
        value = record.get("tool_result")
        if item["kind"] == "summary":
            reads_ok = isinstance(value, dict) and value.get("object_count") == item["object_count"] \
                and isinstance(value.get("aliases"), list) \
                and sorted(value["aliases"]) == sorted(item["aliases"])
        else:
            reads_ok = value == item["aliases"]
        if not reads_ok:
            break
    ledger_path = session_dir / "fixture.sqlite3"
    with sqlite3.connect(ledger_path) as db:
        write_count = db.execute("SELECT COUNT(*) FROM candidate_write WHERE state='done'").fetchone()[0]
        other_count = db.execute("SELECT COUNT(*) FROM candidate_write WHERE state!='done'").fetchone()[0]
    expected_prior_writes = (sum(op in {"create_box", "move_object"} for op in expected["operations"])
                             if kind == "complete" else 0)
    if kind == "safe_scene_changed":
        expected_prior_writes = sum(
            op in {"create_box", "move_object"}
            for op in expected["operations"][:expected["inject_stale_scene_before_write_step"] - 1])
    no_unauthorized_write = write_count <= expected_prior_writes and other_count == 0
    if kind == "complete":
        passed = (error is None and receipt.get("status") == "v6_development_plan_completed_not_formal_quality"
                  and actual_ops == expected["operations"] and geometry_ok and reads_ok
                  and all(item.get("readback_verified") is True for item in records)
                  and no_unauthorized_write and write_count == expected_prior_writes)
    elif kind in {"clarify", "reject"}:
        passed = (error is None and receipt.get("code") == expected["code"]
                  and receipt.get("status") == ("clarification_required" if kind == "clarify" else "task_rejected")
                  and bool(receipt.get("question")) == (kind == "clarify")
                  and receipt.get("model_calls") == receipt.get("rhino_execute_requests") == 0
                  and geometry_ok and no_unauthorized_write)
    else:
        drift_receipts = list(session_dir.glob("formal-drift-response-*.json"))
        passed = (error == "write_grade_scene_changed" and len(drift_receipts) == 1
                  and _private_read(drift_receipts[0]).get("active_document_unchanged") is True
                  and actual_ops == expected["operations"][:expected["inject_stale_scene_before_write_step"] - 1]
                  and all(item.get("readback_verified") is True for item in records)
                  and reads_ok and geometry_ok and no_unauthorized_write
                  and write_count == expected_prior_writes)
    if passed:
        category = None
    elif error is not None:
        category = ("Rhino scene/atomic" if "scene" in error or "rhino" in error else
                    "timeout/resource" if "timeout" in error or "oom" in error or "ssh_or_model_failed" in error else
                    "handoff/auth" if "handoff" in error or "auth" in error else
                    "invoker/schema" if "model" in error else "readback/geometry")
    elif kind in {"clarify", "reject"}:
        category = "clarification"
    else:
        category = "readback/geometry" if not geometry_ok or not reads_ok else "selector"
    return {"passed": bool(passed), "failure_category": category,
            "strict_selection_pass": bool(passed) if case["layer"] in {"A", "C"} else None,
            "parameter_pass": bool(passed) if case["layer"] in {"A", "C"} else None,
            "safe_abstain_pass": bool(passed) if case["layer"] == "B" else None,
            "effective_clarification_pass": bool(passed and kind == "clarify") if case["layer"] == "B" else None,
            "geometry_readback_pass": bool(geometry_ok and reads_ok),
            "safety_violation": not no_unauthorized_write,
            "ledger_done_count": write_count, "ledger_other_count": other_count}


def _percentile(values, q):
    return values[max(0, math.ceil(q * len(values)) - 1)] if values else None


def _wilson(successes, n):
    if not n:
        return [0.0, 1.0]
    z = 1.96
    p = successes / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return [round(center-half, 4), round(center+half, 4)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--batch-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    cases, labels = load_cases()
    if args.validate:
        print(json.dumps({"status": "corpus_valid", "count": len(cases),
                          "layers": dict(Counter(item["layer"] for item in cases))}, sort_keys=True))
        return
    if not args.run or args.batch_dir is None or args.output_dir is None:
        parser.error("--run requires --batch-dir and --output-dir")
    frozen = assert_freeze()
    if remote_tree_digest() != frozen["remote_source_tree_sha256"]:
        raise RuntimeError("formal_remote_source_tree_changed_since_freeze")
    os.mkdir(args.output_dir, 0o700)
    _private_publish(args.output_dir, "run-header.json", {
        "freeze_sha256": digest(FREEZE), "model_manifest_sha256": MODEL_SHA,
        "batch_dir": str(args.batch_dir), "case_count": 60, "started_at_unix": time.time(),
    })
    seq = 1
    results = []
    for case, label in zip(cases, labels):
        assert_freeze()
        if remote_tree_digest() != frozen["remote_source_tree_sha256"]:
            raise RuntimeError("formal_remote_source_tree_changed_since_freeze")
        case_started = time.monotonic()
        session_dir = None
        final = None
        receipt = None
        run_dir = None
        error = None
        try:
            opened = _batch_request(args.batch_dir, seq, "open", case["id"], case["fixture"])
            seq += 1
            session_dir = Path(opened["session_dir"])
            _wait_session_ready(session_dir, case["fixture"])
            live_args = SimpleNamespace(
                session_dir=session_dir, task=case["task"], host=HOST, port=PORT,
                user=USER, known_hosts=KNOWN_HOSTS, expected_host_key_sha256=HOST_KEY,
                approved_manifest_sha256=MODEL_SHA, control_socket=CONTROL,
                delegated_headless_approval=True, fixture_name=case["fixture"],
                collect_resource_metrics=True, formal_model_original_language=True,
                formal_case_id=case["id"],
                formal_drift_step=case["expected"].get("inject_stale_scene_before_write_step"),
            )
            try:
                run_dir, receipt = run(live_args)
            except Exception as exc:
                error = str(exc)
            try:
                final = V6Scene(session_dir).capture()
            except Exception as exc:
                error = (error + ";" if error else "") + "final_capture:" + str(exc)
        finally:
            if session_dir is not None:
                closed = _batch_request(args.batch_dir, seq, "close", case["id"], "none")
                seq += 1
                if not closed.get("key_removed"):
                    raise RuntimeError("formal_fixture_key_not_removed")
        if session_dir is None:
            raise RuntimeError("formal_fixture_not_opened")
        scored = _score(case, label, receipt, error, final, session_dir)
        metrics = []
        if run_dir is not None:
            metrics = [_private_read(path) for path in sorted(run_dir.glob("step-*/resource-metrics.json"))]
        else:
            for path in sorted(session_dir.glob("v6-plan-*/step-*/resource-metrics.json")):
                metrics.append(_private_read(path))
        step_records = [_private_read(path) for path in sorted(
            session_dir.glob("v6-plan-*/step-*/record.json"),
            key=lambda path: int(path.parent.name.split("-")[-1]))]
        result = {"case_id": case["id"], "layer": case["layer"], "fixture": case["fixture"],
                  "task_sha256": hashlib.sha256(case["task"].encode()).hexdigest(),
                  "expected_model_calls": len(case["expected"]["operations"]),
                  "session_dir": str(session_dir), "run_dir": str(run_dir) if run_dir else None,
                  "error": error, "elapsed_seconds": round(time.monotonic()-case_started, 4),
                  "step_resources": metrics,
                  "step_elapsed_seconds": [item["elapsed_seconds"] for item in step_records],
                  "active_document_unchanged": True, **scored}
        _private_publish(args.output_dir, case["id"] + ".json", result)
        results.append(result)
        print("R4_V6_FORMAL_CASE " + json.dumps({"case_id": case["id"], "passed": scored["passed"],
                                                   "category": scored["failure_category"]}), flush=True)
    _batch_request(args.batch_dir, seq, "stop", "formal-end", "none")
    durations = sorted(item["elapsed_seconds"] for item in results)
    step_durations = sorted(metric["model_roundtrip_seconds"] for item in results
                            for metric in item["step_resources"])
    actual_step_durations = sorted(value for item in results for value in item["step_elapsed_seconds"])
    report = {
        "status": "formal_quality_pass" if (
            len(results) == 60 and not any(item["safety_violation"] for item in results)
            and not any("oom" in (item["error"] or "") for item in results)
            and all(sum(item["strict_selection_pass"] is True for item in results if item["layer"] == layer) == 12
                    and sum(item["parameter_pass"] is True for item in results if item["layer"] == layer) == 12
                    for layer in "AC")
            and sum(item["safe_abstain_pass"] is True for item in results if item["layer"] == "B") == 12
            and sum(item["effective_clarification_pass"] is True for item in results if item["layer"] == "B") >= 10
            and all(sum(item["passed"] for item in results if item["layer"] == layer) >= 10 for layer in "DE")
            and all(len(item["step_resources"]) == item["expected_model_calls"]
                    for item in results if item["passed"])
        ) else "formal_quality_fail",
        "denominator": 60, "evaluated": len(results), "unstarted": 60-len(results),
        "freeze_sha256": digest(FREEZE), "model_manifest_sha256": MODEL_SHA,
        "layers": {layer: {"passed": sum(item["passed"] for item in results if item["layer"] == layer),
                            "denominator": 12, "wilson_95": _wilson(
                                sum(item["passed"] for item in results if item["layer"] == layer), 12)}
                   for layer in "ABCDE"},
        "failure_categories": dict(Counter(item["failure_category"] for item in results
                                   if item["failure_category"])),
        "safety_violations": sum(item["safety_violation"] for item in results),
        "task_latency_p50_seconds": _percentile(durations, .5),
        "task_latency_p95_seconds": _percentile(durations, .95),
        "model_roundtrip_p50_seconds": _percentile(step_durations, .5),
        "model_roundtrip_p95_seconds": _percentile(step_durations, .95),
        "completed_step_latency_p50_seconds": _percentile(actual_step_durations, .5),
        "completed_step_latency_p95_seconds": _percentile(actual_step_durations, .95),
        "timeout_count": sum(item["failure_category"] == "timeout/resource" for item in results),
        "timeout_rate": round(sum(item["failure_category"] == "timeout/resource" for item in results)/60, 4),
        "oom_count": sum("oom" in (item["error"] or "") for item in results),
        "resource_metric_missing_cases": sum(len(item["step_resources"]) < item["expected_model_calls"]
                                             for item in results),
        "model_load_p50_seconds": _percentile(sorted(metric["model_load_seconds"] for item in results
                                                   for metric in item["step_resources"]), .5),
        "model_load_p95_seconds": _percentile(sorted(metric["model_load_seconds"] for item in results
                                                   for metric in item["step_resources"]), .95),
        "inference_p50_seconds": _percentile(sorted(metric["inference_seconds"] for item in results
                                                 for metric in item["step_resources"]), .5),
        "inference_p95_seconds": _percentile(sorted(metric["inference_seconds"] for item in results
                                                 for metric in item["step_resources"]), .95),
        "gpu_peak_allocated_bytes": max((metric["cuda_peak_allocated_bytes"] for item in results
                                         for metric in item["step_resources"]), default=None),
        "gpu_peak_reserved_bytes": max((metric["cuda_peak_reserved_bytes"] for item in results
                                        for metric in item["step_resources"]), default=None),
        "mac_peak_rss_bytes": max((metric["mac_process_peak_rss_bytes"] for item in results
                                  for metric in item["step_resources"]), default=int(resource.getrusage(
                                      resource.RUSAGE_SELF).ru_maxrss)),
        "remote_peak_rss_kib": max((metric["remote_peak_rss_kib"] for item in results
                                    for metric in item["step_resources"]), default=None),
    }
    _private_publish(args.output_dir, "report.json", report)
    print("R4_V6_FORMAL_REPORT " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        if "--output-dir" in sys.argv:
            index = sys.argv.index("--output-dir")
            if index + 1 < len(sys.argv):
                output_dir = Path(sys.argv[index + 1])
                if output_dir.is_dir() and not (output_dir / "report.json").exists():
                    completed = sorted(path.stem for path in output_dir.glob("R6-*.json"))
                    try:
                        _private_publish(output_dir, "incomplete-report.json", {
                            "status": "formal_quality_fail_incomplete",
                            "denominator": 60, "evaluated": len(completed),
                            "unstarted": 60 - len(completed), "completed_case_ids": completed,
                            "fatal_error": type(exc).__name__ + ":" + str(exc),
                            "manual_fixture_inspection_required": True,
                        })
                    except Exception:
                        pass
        raise
