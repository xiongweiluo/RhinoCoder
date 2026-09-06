#!/usr/bin/env python3
"""Run and audit the frozen A6 no-finetune comparison baseline."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.a6_baseline import (  # noqa: E402
    AUDIT_FILE,
    DEFAULT_GOLDEN,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REPORT,
    INFRA_ATTEMPTS_FILE,
    MANIFEST_FILE,
    OFFLINE_FILE,
    RESULTS_FILE,
    A6Error,
    analyze_golden_offline,
    audit_a6,
    audit_as_dict,
    finalize_manifest,
    normalize_live_checkpoints,
    prepare_run_manifest,
    render_report,
    run_live_benchmark,
    summarize_live_results,
    _read_jsonl,
    _write_json,
)
from agent.db import AuditDatabase, DEFAULT_AUDIT_DB  # noqa: E402


def _path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _offline(args: argparse.Namespace) -> int:
    output_dir = _path(args.output_dir)
    prepare_run_manifest(output_dir)
    analysis = analyze_golden_offline(_path(args.golden), output_dir / OFFLINE_FILE)
    replay = analysis["replay"]
    print(
        f"A6 offline replay: {'PASS' if replay['passed'] else 'FAIL'}; "
        f"traces={analysis['source']['traces']}, tasks={replay['unique_tasks']}, "
        f"tool_calls={replay['tool_calls']}"
    )
    return 0 if replay["passed"] else 1


def _prepare(args: argparse.Namespace) -> int:
    output_dir = _path(args.output_dir)
    manifest = prepare_run_manifest(output_dir)
    valid, infrastructure = normalize_live_checkpoints(output_dir)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    print(
        f"A6 checkpoints: valid={len(valid)}, infrastructure_attempts={len(infrastructure)}",
        file=sys.stderr,
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    summary = asyncio.run(
        run_live_benchmark(
            _path(args.output_dir),
            limit=args.limit,
            max_cost_usd=args.max_cost_usd,
            verbose=args.verbose,
        )
    )
    print(
        f"A6 live checkpoint: {summary['completed']}/{summary['expected']} complete; "
        f"new_runs={summary['new_runs']}"
    )
    return 0


def _sync_audit(args: argparse.Namespace) -> int:
    output_dir = _path(args.output_dir)
    records = [
        *_read_jsonl(output_dir / RESULTS_FILE),
        *_read_jsonl(output_dir / INFRA_ATTEMPTS_FILE),
    ]
    with AuditDatabase(_path(getattr(args, "database", DEFAULT_AUDIT_DB))) as database:
        summary = database.rebuild_route_decisions(records)
        audit = database.audit()
    print(
        json.dumps(
            {"route_rebuild": summary, "database_audit_passed": audit.passed},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0 if audit.passed else 1


def _audit(args: argparse.Namespace) -> int:
    output_dir = _path(args.output_dir)
    result = audit_a6(output_dir, _path(args.golden))
    _write_json(output_dir / AUDIT_FILE, audit_as_dict(result))
    finalize_manifest(output_dir, result)
    print(json.dumps(audit_as_dict(result), ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result.passed else 1


def _report(args: argparse.Namespace) -> int:
    output_dir = _path(args.output_dir)
    result = audit_a6(output_dir, _path(args.golden))
    _write_json(output_dir / AUDIT_FILE, audit_as_dict(result))
    manifest = finalize_manifest(output_dir, result)
    offline_path = output_dir / OFFLINE_FILE
    if not offline_path.is_file():
        raise A6Error("offline analysis is missing")
    offline = json.loads(offline_path.read_text(encoding="utf-8"))
    live = summarize_live_results(_read_jsonl(output_dir / RESULTS_FILE))
    infrastructure_attempts = _read_jsonl(output_dir / INFRA_ATTEMPTS_FILE)
    live["infrastructure_attempts"] = {
        "count": len(infrastructure_attempts),
        "by_scenario": {
            scenario: sum(
                1 for row in infrastructure_attempts
                if str(row.get("scenario") or row.get("mode") or "unknown") == scenario
            )
            for scenario in sorted(
                {str(row.get("scenario") or row.get("mode") or "unknown") for row in infrastructure_attempts}
            )
        },
        "error_codes": {
            code: sum(
                1 for row in infrastructure_attempts
                if str(row.get("infrastructure_error_code") or "unknown") == code
            )
            for code in sorted(
                {str(row.get("infrastructure_error_code") or "unknown") for row in infrastructure_attempts}
            )
        },
    }
    if DEFAULT_AUDIT_DB.is_file():
        with AuditDatabase(DEFAULT_AUDIT_DB) as database:
            database_audit = database.audit()
        live["sqlite_audit"] = {
            "passed": database_audit.passed,
            "route_decisions": database_audit.counts.get("route_decisions", 0),
            "sensitive_findings": len(database_audit.sensitive_field_findings),
        }
    report_path = _path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(manifest, live, offline, result), encoding="utf-8")
    print(f"Wrote A6 report to {report_path}")
    return 0 if result.passed else 1


def _all(args: argparse.Namespace) -> int:
    offline_code = _offline(args)
    if offline_code:
        return offline_code
    _run(args)
    sync_code = _sync_audit(args)
    if sync_code:
        return sync_code
    return _report(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    common.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", parents=[common], help="freeze the run contract")
    prepare.set_defaults(handler=_prepare)

    offline = subparsers.add_parser("offline", parents=[common], help="analyze all 300 golden traces")
    offline.set_defaults(handler=_offline)

    for name, handler in (("run", _run), ("all", _all)):
        command = subparsers.add_parser(name, parents=[common], help="run the live comparison matrix")
        command.add_argument("--limit", type=int, help="run at most N pending checkpoints")
        command.add_argument("--max-cost-usd", type=float, default=25.0)
        command.add_argument("--verbose", action="store_true")
        command.add_argument("--report", default=str(DEFAULT_REPORT))
        command.set_defaults(handler=handler)

    audit = subparsers.add_parser("audit", parents=[common], help="audit the complete A6 evidence")
    audit.set_defaults(handler=_audit)

    report = subparsers.add_parser("report", parents=[common], help="freeze the Markdown report")
    report.add_argument("--report", default=str(DEFAULT_REPORT))
    report.set_defaults(handler=_report)

    sync_audit = subparsers.add_parser(
        "sync-audit", parents=[common], help="restore A6 route lineage in the SQLite audit store"
    )
    sync_audit.add_argument("--database", default=str(DEFAULT_AUDIT_DB))
    sync_audit.set_defaults(handler=_sync_audit)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if getattr(args, "limit", None) is not None and args.limit < 1:
            raise A6Error("--limit must be positive")
        if getattr(args, "max_cost_usd", 1) <= 0:
            raise A6Error("--max-cost-usd must be positive")
        return int(args.handler(args))
    except (A6Error, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"A6 baseline error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
