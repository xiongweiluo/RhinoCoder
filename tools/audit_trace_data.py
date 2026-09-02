#!/usr/bin/env python3
"""审计本地黄金、Partial 与失败轨迹的准入和物理分流。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.sanitizer import contains_sensitive_data
from agent.trace_store import (
    AI_REVIEWED,
    AI_REVIEWED_FILE,
    CANDIDATE_FILE,
    ERROR_ANALYSIS,
    ERROR_ANALYSIS_FILE,
    GOLDEN_FILE,
    LEGACY_GOLDEN_FILE,
    PARTIAL,
    PARTIAL_FILE,
    validate_ai_review_candidate,
    validate_saved_golden_record,
)


@dataclass(slots=True)
class TraceDataAudit:
    counts: dict[str, int] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings


def _read_jsonl(path: Path, audit: TraceDataAudit, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        audit.counts[label] = 0
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            audit.findings.append(f"{path.name}:{line_no}: JSON 无效: {exc}")
            continue
        if not isinstance(row, dict):
            audit.findings.append(f"{path.name}:{line_no}: 必须是 JSON object")
            continue
        rows.append(row)
    audit.counts[label] = len(rows)
    return rows


def audit_trace_data() -> TraceDataAudit:
    audit = TraceDataAudit()
    golden_rows = _read_jsonl(GOLDEN_FILE, audit, "golden_v2")
    golden_task_keys = {
        (
            str((((row.get("metadata") or {}).get("task") or {}).get("campaign_id") or "")),
            str((((row.get("metadata") or {}).get("task") or {}).get("task_id") or "")),
        )
        for row in golden_rows
    }
    for index, row in enumerate(golden_rows, 1):
        for reason in validate_saved_golden_record(row):
            audit.findings.append(f"{GOLDEN_FILE.name}:{index}: {reason}")

    candidate_rows = _read_jsonl(AI_REVIEWED_FILE, audit, "ai_reviewed_candidate_history")
    active_candidates = 0
    for index, row in enumerate(candidate_rows, 1):
        if row.get("disposition") != AI_REVIEWED:
            audit.findings.append(f"{AI_REVIEWED_FILE.name}:{index}: disposition 应为 {AI_REVIEWED}")
        if contains_sensitive_data(row):
            audit.findings.append(f"{AI_REVIEWED_FILE.name}:{index}: 仍包含敏感字段")
        task = row.get("task") or {}
        task_key = (str(task.get("campaign_id") or ""), str(task.get("task_id") or ""))
        if task_key in golden_task_keys:
            continue
        active_candidates += 1
        gate = validate_ai_review_candidate(row)
        for reason in gate.reasons:
            audit.findings.append(f"{AI_REVIEWED_FILE.name}:{index}: {reason}")
    audit.counts["ai_reviewed_candidate"] = active_candidates

    separated = (
        (PARTIAL_FILE, "partial", PARTIAL),
        (ERROR_ANALYSIS_FILE, "error_analysis", ERROR_ANALYSIS),
        (CANDIDATE_FILE, "candidate", "candidate"),
    )
    for path, label, expected in separated:
        for index, row in enumerate(_read_jsonl(path, audit, label), 1):
            if row.get("disposition") != expected:
                audit.findings.append(f"{path.name}:{index}: disposition 应为 {expected}")
            if contains_sensitive_data(row):
                audit.findings.append(f"{path.name}:{index}: 仍包含敏感字段")

    legacy_rows = _read_jsonl(LEGACY_GOLDEN_FILE, audit, "legacy_excluded")
    if legacy_rows:
        audit.notices.append(
            f"{LEGACY_GOLDEN_FILE.name}: {len(legacy_rows)} 条旧格式记录已排除；新采集只写入 {GOLDEN_FILE.name}"
        )
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    audit = audit_trace_data()
    payload = {
        "passed": audit.passed,
        "counts": audit.counts,
        "notices": audit.notices,
        "findings": audit.findings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for label, count in audit.counts.items():
            print(f"  ✓ {label}: {count}")
        for notice in audit.notices:
            print(f"  ! {notice}")
        for finding in audit.findings:
            print(f"  ✗ {finding}")
        print("Trace data audit passed." if audit.passed else "Trace data audit failed.")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
