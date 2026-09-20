#!/usr/bin/env python3
"""Freeze, preflight, run, and audit the isolated C3 final evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.config import DEFAULT_CONFIG, ReadinessError  # noqa: E402
from eval.final_evaluation import (  # noqa: E402
    DEFAULT_C3_FREEZE_MANIFEST,
    DEFAULT_C3_LEDGER,
    DEFAULT_C3_RUNS,
    audit_c3_freeze,
    audit_completed_c3_run,
    c3_preflight,
    freeze_c3_evaluation,
    run_one_time_holdout,
)
from training.preregistration import (
    DEFAULT_C1_REPORT,
    DEFAULT_FREEZE_MANIFEST,
)  # noqa: E402


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    freeze = subparsers.add_parser(
        "freeze", help="freeze C2 artifacts and C3 protocol without reading holdout"
    )
    freeze.add_argument("--config", default=str(DEFAULT_CONFIG))
    freeze.add_argument("--c0-manifest", default=DEFAULT_FREEZE_MANIFEST)
    freeze.add_argument("--c1-report", default=DEFAULT_C1_REPORT)
    freeze.add_argument("--output", default=DEFAULT_C3_FREEZE_MANIFEST)

    freeze_audit = subparsers.add_parser(
        "freeze-audit", help="audit the immutable C3 freeze without holdout"
    )
    freeze_audit.add_argument("--manifest", default=DEFAULT_C3_FREEZE_MANIFEST)

    preflight = subparsers.add_parser(
        "preflight", help="prove readiness without opening holdout"
    )
    preflight.add_argument("--manifest", default=DEFAULT_C3_FREEZE_MANIFEST)
    preflight.add_argument("--ledger", default=DEFAULT_C3_LEDGER)

    run = subparsers.add_parser(
        "holdout-run", help="explicitly consume A5 holdout once for base/LoRA"
    )
    run.add_argument("--experiment-id", required=True)
    run.add_argument("--confirm-freeze-sha256", required=True)
    run.add_argument("--manifest", default=DEFAULT_C3_FREEZE_MANIFEST)
    run.add_argument("--ledger", default=DEFAULT_C3_LEDGER)
    run.add_argument("--runs-root", default=DEFAULT_C3_RUNS)
    run.add_argument("--resume-run-id")

    run_audit = subparsers.add_parser(
        "run-audit", help="audit a completed C3 run without reopening holdout"
    )
    run_audit.add_argument("--run-id", required=True)
    run_audit.add_argument("--manifest", default=DEFAULT_C3_FREEZE_MANIFEST)
    run_audit.add_argument("--ledger", default=DEFAULT_C3_LEDGER)
    run_audit.add_argument("--runs-root", default=DEFAULT_C3_RUNS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "freeze":
            result = freeze_c3_evaluation(
                args.config,
                output_path=args.output,
                c0_manifest_path=args.c0_manifest,
                c1_report_path=args.c1_report,
            )
        elif args.command == "freeze-audit":
            result = audit_c3_freeze(args.manifest)
        elif args.command == "preflight":
            result = c3_preflight(args.manifest, ledger_path=args.ledger)
        elif args.command == "holdout-run":
            result = run_one_time_holdout(
                experiment_id=args.experiment_id,
                confirm_freeze_sha256=args.confirm_freeze_sha256,
                manifest_path=args.manifest,
                ledger_path=args.ledger,
                runs_root=args.runs_root,
                resume_run_id=args.resume_run_id,
            )
        else:
            result = audit_completed_c3_run(
                args.run_id,
                manifest_path=args.manifest,
                ledger_path=args.ledger,
                runs_root=args.runs_root,
            )
        _print(result)
        return 0
    except (ReadinessError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C3 evaluation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
