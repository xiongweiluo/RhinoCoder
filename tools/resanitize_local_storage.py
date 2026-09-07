#!/usr/bin/env python3
"""Atomically reapply the current privacy sanitizer to local JSON storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.privacy import (  # noqa: E402
    cloud_sensitive_findings,
    configured_request_audit_path,
    minimize_for_cloud,
)
from agent.sanitizer import contains_sensitive_data, sanitize_structure  # noqa: E402


JSONL_PATHS = (
    ROOT / "data" / "golden_traces_v2.jsonl",
    ROOT / "data" / "feedback.jsonl",
    ROOT / "data" / "candidates.jsonl",
    ROOT / "data" / "ai_reviewed_candidates.jsonl",
    ROOT / "data" / "partial_traces.jsonl",
    ROOT / "data" / "error_traces.jsonl",
)


def _sanitize_model_request(row: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(row)
    sanitized["messages"] = minimize_for_cloud(row.get("messages") or [])
    sanitized["tools"] = minimize_for_cloud(row.get("tools") or [])
    findings = cloud_sensitive_findings(
        {"messages": sanitized["messages"], "tools": sanitized["tools"]}
    )
    if findings:
        raise ValueError(f"model request remains sensitive after minimization: {findings[:5]}")
    if "content_sha256" in sanitized:
        content = {
            "messages": sanitized.get("messages") or [],
            "tools": sanitized.get("tools") or [],
        }
        sanitized["content_sha256"] = hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
    return sanitized


def _atomic_write(path: Path, content: str) -> None:
    mode = path.stat().st_mode & 0o777
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def resanitize_jsonl(path: Path, *, apply: bool, model_requests: bool = False) -> int:
    if not path.is_file():
        return 0
    rows: list[dict[str, Any]] = []
    changed = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        if model_requests:
            request = {"messages": row.get("messages"), "tools": row.get("tools")}
            sanitized = _sanitize_model_request(row) if cloud_sensitive_findings(request) else row
        else:
            needs_sanitization = contains_sensitive_data(
                row,
                inspect_embedded_json=True,
            )
            sanitized = sanitize_structure(row) if needs_sanitization else row
        if model_requests:
            request = {
                "messages": sanitized.get("messages"),
                "tools": sanitized.get("tools"),
            }
            if cloud_sensitive_findings(request):
                raise ValueError(
                    f"{path}:{line_number}: model request remains sensitive after minimization"
                )
        elif contains_sensitive_data(sanitized, inspect_embedded_json=True):
            raise ValueError(f"{path}:{line_number}: sensitive data remains after sanitization")
        changed += sanitized != row
        rows.append(sanitized)
    if apply and changed:
        serialized = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
            for row in rows
        )
        _atomic_write(path, serialized)
    return changed


def resanitize_json(path: Path, *, apply: bool) -> int:
    if not path.is_file():
        return 0
    row = json.loads(path.read_text(encoding="utf-8"))
    sanitized = (
        sanitize_structure(row)
        if contains_sensitive_data(row, inspect_embedded_json=True)
        else row
    )
    if contains_sensitive_data(sanitized, inspect_embedded_json=True):
        raise ValueError(f"{path}: sensitive data remains after sanitization")
    changed = int(sanitized != row)
    if apply and changed:
        _atomic_write(
            path,
            json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist changes; default is dry-run")
    args = parser.parse_args()

    counts: dict[str, int] = {}
    for path in JSONL_PATHS:
        counts[str(path.relative_to(ROOT))] = resanitize_jsonl(path, apply=args.apply)
    request_path = configured_request_audit_path()
    counts[str(request_path.relative_to(ROOT))] = resanitize_jsonl(
        request_path,
        apply=args.apply,
        model_requests=True,
    )
    for path in sorted((ROOT / "data" / "traces").glob("*.json")):
        changed = resanitize_json(path, apply=args.apply)
        if changed:
            counts[str(path.relative_to(ROOT))] = changed

    print(json.dumps({"applied": args.apply, "changed": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
