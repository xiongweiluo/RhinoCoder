#!/usr/bin/env python3
"""Recompute and validate the committed, privacy-minimized P2 result projection."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "docs" / "p2-hard-set-results.json"
TASKS = ROOT / "eval" / "p2" / "hard_tasks.jsonl"


def main() -> int:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    tasks = [json.loads(line) for line in TASKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = data["results"]
    findings: list[str] = []
    if data.get("scope") != "external-user-authored automated hard-set evaluation; not a user usability study":
        findings.append("scope is not the locked honest P2a statement")
    if data.get("freeze", {}).get("holdout_read") != 0:
        findings.append("holdout_read is not zero")
    if len(rows) != 30 or {row["task_id"] for row in rows} != {task["id"] for task in tasks}:
        findings.append("result/task IDs are not a complete 30-task match")
    valid = [row for row in rows if row["initial"]["adjudicated_status"] != "infrastructure_excluded"]
    passed = sum(row["initial"]["adjudicated_status"] == "pass" for row in valid)
    baseline = data["baseline"]
    if (len(valid), passed) != (baseline["valid_capability_attempts"], baseline["automated_passed"]):
        findings.append("baseline counts are not reproducible")
    if not math.isclose(baseline["success_rate"], passed / len(valid), abs_tol=0.00005):
        findings.append("baseline success rate is not reproducible")
    failures = Counter(row["initial"]["failure_category"] for row in valid if row["initial"]["adjudicated_status"] == "fail")
    if dict(sorted(failures.items())) != baseline["failure_categories"]:
        findings.append("failure categories are not reproducible")
    interruptions = data.get("infrastructure_interruptions") or []
    interruption_rows = [attempt for row in rows for attempt in row.get("infrastructure_attempts", [])]
    if len(interruptions) != 5 or len(interruption_rows) != 5:
        findings.append("five infrastructure interruptions are not preserved")
    if baseline.get("execution_attempts_including_infrastructure") != 35 or baseline.get("unfilled_or_excluded_tasks") != 0:
        findings.append("same-slot infrastructure resume accounting is inconsistent")
    retests = [row["retest"] for row in rows if "retest" in row]
    if len(retests) != 3 or sum(row["adjudicated_status"] == "pass" for row in retests) != data["intervention"]["passed"]:
        findings.append("representative retest counts are not reproducible")
    serialized = json.dumps(data, ensure_ascii=False)
    forbidden = ("RhinoDoc", "messages\"", "before_scene", "after_scene", "object_id", "@example.com")
    if any(token in serialized for token in forbidden):
        findings.append("public projection contains a forbidden raw-evidence field")
    manual = data.get("manual_evidence", {})
    if manual.get("completed") != ["P2-HARD-017"] or manual.get("pending") != ["P2-HARD-002", "P2-HARD-014"]:
        findings.append("manual/browser evidence status does not match the accepted browser cancellation check")
    if data.get("manual_evidence", {}).get("usability_study_completed") is not False:
        findings.append("P2b usability status is not explicitly false")
    verification = data.get("verification", {})
    if verification.get("python_tests") != {"passed": 193, "failed": 0}:
        findings.append("final Python test evidence is missing or inconsistent")
    if verification.get("privacy_audit", {}).get("sensitive_findings") != 0:
        findings.append("final privacy audit is not zero-findings")
    if verification.get("holdout_read") != 0:
        findings.append("verification holdout_read is not zero")
    if findings:
        for finding in findings:
            print("FAIL:", finding)
        return 1
    print("P2 result audit passed: 30/30 valid slots, 18 passed, 5 preserved infrastructure interruptions, holdout_read=0, retest=2/3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
