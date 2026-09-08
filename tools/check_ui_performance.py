#!/usr/bin/env python3
"""Enforce a small, dependency-free production bundle budget for the P1 demo UI."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "agent" / "ui" / "dist"
BUDGETS = {
    "javascript_gzip_bytes": 90 * 1024,
    "css_gzip_bytes": 20 * 1024,
    "total_gzip_bytes": 120 * 1024,
}


def audit_ui_bundle(dist: Path = DIST) -> dict[str, object]:
    findings: list[str] = []
    if not (dist / "index.html").is_file():
        return {"passed": False, "findings": ["UI dist/index.html 不存在；请先运行 npm build"]}

    javascript = sorted((dist / "assets").glob("*.js"))
    styles = sorted((dist / "assets").glob("*.css"))
    if not javascript:
        findings.append("UI 构建未产生 JavaScript bundle")
    if not styles:
        findings.append("UI 构建未产生 CSS bundle")

    javascript_gzip = sum(len(gzip.compress(path.read_bytes(), mtime=0)) for path in javascript)
    css_gzip = sum(len(gzip.compress(path.read_bytes(), mtime=0)) for path in styles)
    html_gzip = len(gzip.compress((dist / "index.html").read_bytes(), mtime=0))
    total_gzip = javascript_gzip + css_gzip + html_gzip
    measurements = {
        "javascript_gzip_bytes": javascript_gzip,
        "css_gzip_bytes": css_gzip,
        "html_gzip_bytes": html_gzip,
        "total_gzip_bytes": total_gzip,
        "javascript_files": len(javascript),
        "css_files": len(styles),
    }
    for key, budget in BUDGETS.items():
        actual = int(measurements[key])
        if actual > budget:
            findings.append(f"{key}={actual} 超过预算 {budget}")
    return {
        "passed": not findings,
        "measurements": measurements,
        "budgets": BUDGETS,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit_ui_bundle()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["passed"]:
        measurements = result["measurements"]
        print(
            "UI performance budget passed: "
            f"JS gzip={measurements['javascript_gzip_bytes']} B, "
            f"CSS gzip={measurements['css_gzip_bytes']} B, "
            f"total gzip={measurements['total_gzip_bytes']} B."
        )
    else:
        print("UI performance budget failed:")
        for finding in result["findings"]:
            print(f"  ✗ {finding}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
