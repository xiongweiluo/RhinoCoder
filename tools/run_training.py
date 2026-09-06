#!/usr/bin/env python3
"""Audit, smoke-test, launch, resume and evaluate the locked LoRA experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.cluster import (  # noqa: E402
    inventory_cluster,
    load_cluster_config,
    placeholder_paths,
    validate_cluster_config,
)
from training.config import (  # noqa: E402
    DEFAULT_CONFIG,
    ReadinessError,
    audit_readiness,
    load_config,
    project_path,
)
from training.data import audit_official_tokenizer  # noqa: E402
from training.reporting import atomic_json  # noqa: E402
from training.runtime import evaluate_adapter, train, write_report  # noqa: E402
from training.smoke import run_cpu_smoke  # noqa: E402


DEFAULT_CLUSTER_TEMPLATE = "training/school_gpu.example.json"


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _audit(args: argparse.Namespace) -> int:
    result = audit_readiness(args.config, require_data=not args.no_data)
    _print(result.to_dict())
    return 0 if result.passed else 1


def _smoke(args: argparse.Namespace) -> int:
    result = run_cpu_smoke(args.config, args.output_dir)
    _print(result)
    return 0 if result["passed"] else 1


def _tokenizer_audit(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = audit_official_tokenizer(
        config,
        cache_dir=args.cache_dir,
        local_files_only=args.local_files_only,
    )
    if args.output:
        atomic_json(project_path(args.output), result)
    _print(result)
    return 0 if result["passed"] else 1


def _train(args: argparse.Namespace) -> int:
    _print(train(args.config, resume=args.resume))
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    _print(evaluate_adapter(args.adapter, args.config))
    return 0


def _report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    run_dir = args.run_dir or config["checkpoint"]["root"]
    target = write_report(run_dir, args.output, args.config)
    print(f"Wrote experiment report to {target}")
    return 0


def _cluster_template_audit(args: argparse.Namespace) -> int:
    config = load_cluster_config(args.cluster_config)
    findings = validate_cluster_config(config, allow_placeholders=True)
    payload = {
        "passed": not findings,
        "status": config.get("status"),
        "placeholders": placeholder_paths(config),
        "findings": findings,
    }
    _print(payload)
    return 0 if not findings else 1


def _cluster_check(args: argparse.Namespace) -> int:
    result = inventory_cluster(args.cluster_config)
    if args.output:
        atomic_json(project_path(args.output), result)
    _print(result)
    commands = result["commands"]
    required_ok = all(
        commands[name].get("available") and commands[name].get("returncode") == 0
        for name in ("nvidia_smi", "scheduler", "storage")
    )
    return 0 if required_ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="validate the immutable B1/B2 contract and A5 inputs")
    audit.add_argument("--config", default=str(DEFAULT_CONFIG))
    audit.add_argument("--no-data", action="store_true", help="audit static contract before local data restore")
    audit.set_defaults(handler=_audit)

    smoke = subparsers.add_parser("smoke", help="run a network-free two-step CPU adapter smoke and resume")
    smoke.add_argument("--config", default=str(DEFAULT_CONFIG))
    smoke.add_argument("--output-dir", default="data/training/smoke")
    smoke.set_defaults(handler=_smoke)

    tokenizer = subparsers.add_parser(
        "tokenizer-audit",
        help="verify all train/validation samples with the pinned upstream tokenizer",
    )
    tokenizer.add_argument("--config", default=str(DEFAULT_CONFIG))
    tokenizer.add_argument("--cache-dir", default="data/training/tokenizer-cache")
    tokenizer.add_argument("--output", default="data/training/tokenizer-audit.json")
    tokenizer.add_argument("--local-files-only", action="store_true")
    tokenizer.set_defaults(handler=_tokenizer_audit)

    train_parser = subparsers.add_parser("train", help="launch the locked QLoRA job on CUDA")
    train_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    train_parser.add_argument("--resume", default="auto", help="auto, none, or a checkpoint inside the run dir")
    train_parser.set_defaults(handler=_train)

    evaluate = subparsers.add_parser("evaluate", help="evaluate an adapter on validation only")
    evaluate.add_argument("--config", default=str(DEFAULT_CONFIG))
    evaluate.add_argument("--adapter", required=True)
    evaluate.set_defaults(handler=_evaluate)

    report = subparsers.add_parser("report", help="render one run's immutable experiment report")
    report.add_argument("--config", default=str(DEFAULT_CONFIG))
    report.add_argument("--run-dir")
    report.add_argument("--output", default="data/training/runs/latest-report.md")
    report.set_defaults(handler=_report)

    template = subparsers.add_parser(
        "cluster-template-audit", help="validate the pre-access school GPU checklist template"
    )
    template.add_argument("--cluster-config", default=DEFAULT_CLUSTER_TEMPLATE)
    template.set_defaults(handler=_cluster_template_audit)

    cluster = subparsers.add_parser(
        "cluster-check", help="after access is granted, inventory CUDA, GPU, Slurm and storage"
    )
    cluster.add_argument("--cluster-config", default="training/school_gpu.local.json")
    cluster.add_argument("--output", default="data/training/cluster-inventory.json")
    cluster.set_defaults(handler=_cluster_check)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (ReadinessError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"training readiness error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
