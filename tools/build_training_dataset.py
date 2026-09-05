#!/usr/bin/env python3
"""Build, audit, and document the deterministic A5 training dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.collection_campaign import load_campaign  # noqa: E402
from data_pipeline.training_views import (  # noqa: E402
    DEFAULT_CAMPAIGN_MANIFEST,
    DEFAULT_OUTPUT,
    DEFAULT_SOURCE,
    TrainingDataError,
    audit_as_dict,
    audit_training_dataset,
    build_training_dataset,
    render_training_report,
)


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _add_dataset_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="golden Trace JSONL")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="dataset directory")


def _load_task_catalog(path: Path) -> dict[str, dict[str, Any]]:
    campaign = load_campaign(path)
    return {str(task["id"]): task for task in campaign.tasks}


def _print_audit(result: Any, *, as_json: bool) -> None:
    payload = audit_as_dict(result)
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return
    status = "PASS" if result.passed else "FAIL"
    print(
        f"A5 training dataset audit: {status}; "
        f"source_tasks={result.source_tasks}, samples={result.samples}, "
        f"artifacts={result.artifacts}, privacy_findings={result.privacy_findings}, "
        f"template_leaks={result.template_leaks}"
    )
    for finding in result.findings:
        print(f"- {finding}")


def _build(args: argparse.Namespace) -> int:
    source = _project_path(args.source)
    output_dir = _project_path(args.output_dir)
    campaign_path = _project_path(args.campaign_manifest)
    catalog = _load_task_catalog(campaign_path)
    manifest = build_training_dataset(
        source,
        output_dir,
        task_catalog=catalog,
        campaign_manifest_path=campaign_path,
    )
    audit = audit_training_dataset(output_dir, source)
    if args.json:
        print(
            json.dumps(
                {"manifest": manifest, "audit": audit_as_dict(audit)},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
    else:
        print(
            f"Built {manifest['stats']['total_samples']} samples from "
            f"{manifest['stats']['source_tasks']} golden tasks in {output_dir}"
        )
        _print_audit(audit, as_json=False)
    return 0 if audit.passed else 1


def _audit(args: argparse.Namespace) -> int:
    result = audit_training_dataset(_project_path(args.output_dir), _project_path(args.source))
    _print_audit(result, as_json=args.json)
    return 0 if result.passed else 1


def _report(args: argparse.Namespace) -> int:
    source = _project_path(args.source)
    output_dir = _project_path(args.output_dir)
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise TrainingDataError(f"manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = audit_training_dataset(output_dir, source)
    report_path = _project_path(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_training_report(manifest, audit), encoding="utf-8")
    print(f"Wrote A5 acceptance report to {report_path}")
    _print_audit(audit, as_json=False)
    return 0 if audit.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build and verify all four training views")
    _add_dataset_paths(build)
    build.add_argument(
        "--campaign-manifest",
        default=str(DEFAULT_CAMPAIGN_MANIFEST),
        help="campaign manifest that supplies authoritative task definitions",
    )
    build.add_argument("--json", action="store_true", help="emit machine-readable output")
    build.set_defaults(handler=_build)

    audit = subparsers.add_parser("audit", help="audit an existing export")
    _add_dataset_paths(audit)
    audit.add_argument("--json", action="store_true", help="emit machine-readable output")
    audit.set_defaults(handler=_audit)

    report = subparsers.add_parser("report", help="write a reproducible Markdown acceptance report")
    _add_dataset_paths(report)
    report.add_argument("--output", default="docs/training-data-pipeline.md", help="Markdown report path")
    report.set_defaults(handler=_report)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError, json.JSONDecodeError, TrainingDataError) as exc:
        print(f"A5 training dataset error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
