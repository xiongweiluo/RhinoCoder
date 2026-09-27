#!/usr/bin/env python3
"""Prepare and enforce C5 final-holdout public commitment and single-use gates."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.c5_holdout import (  # noqa: E402
    C5HoldoutError,
    claim_encrypted_artifact,
    gate_preflight,
    public_commitment_template,
    sha256_file,
    summarize_offline_results,
    validate_public_commitment,
)


PUBLIC_DIR = ROOT / "eval/c5"
HISTORICAL_EXCLUSIONS = PUBLIC_DIR / "historical-exclusions.json"
DATASET_FREEZE = PUBLIC_DIR / "dataset-v2-freeze-manifest.json"
DEFAULT_TEMPLATE = PUBLIC_DIR / "final-holdout-commitment-template.json"
DEFAULT_COMMITMENT = PUBLIC_DIR / "final-holdout-commitment.json"
DEFAULT_READINESS = PUBLIC_DIR / "final-holdout-gate-readiness.json"
DEFAULT_LEDGER = ROOT / "data/training/c5/final/holdout-consumption.jsonl"
DEFAULT_PERMIT = ROOT / "data/training/c5/final/decryption-permit.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise C5HoldoutError(f"required JSON file is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise C5HoldoutError(f"JSON root must be an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise C5HoldoutError(f"{path}:{line_no}: row must be an object")
        rows.append(value)
    return rows


def _write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    descriptor = os.open(path, flags, 0o600 if path.is_relative_to(ROOT / "data") else 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if exclusive:
            path.unlink(missing_ok=True)
        raise


def _expected_hashes() -> tuple[str, str]:
    if not HISTORICAL_EXCLUSIONS.is_file() or not DATASET_FREEZE.is_file():
        raise C5HoldoutError("C5-1b public freeze artifacts are missing")
    return sha256_file(HISTORICAL_EXCLUSIONS), sha256_file(DATASET_FREEZE)


def template_command(output: Path) -> dict[str, Any]:
    exclusions, dataset = _expected_hashes()
    value = public_commitment_template(
        expected_exclusion_sha256=exclusions,
        expected_dataset_freeze_sha256=dataset,
    )
    _write_json(output, value)
    return {
        "status": "owner_completion_required",
        "output": str(output),
        "plaintext_read": False,
        "final_holdout_rows_read": 0,
    }


def readiness_command(output: Path) -> dict[str, Any]:
    exclusions, dataset = _expected_hashes()
    implementation = (
        ROOT / "training/c5_holdout.py",
        ROOT / "tools/c5_holdout_gate.py",
        ROOT / "tools/c5_holdout_custodian.py",
        ROOT / "eval/test_c5_holdout_gate.py",
    )
    value = {
        "schema_version": "1.0",
        "status": "implementation_ready_owner_commitment_required",
        "historical_exclusions_sha256": exclusions,
        "development_dataset_freeze_sha256": dataset,
        "commitment_template_sha256": sha256_file(DEFAULT_TEMPLATE),
        "implementation_sha256": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in implementation
        },
        "owner_commitment_registered": DEFAULT_COMMITMENT.is_file(),
        "development_agent_plaintext_access": False,
        "final_holdout_rows_read": 0,
        "single_use_claim_executed": False,
        "training_authorized": False,
        "gpu_authorized": False,
    }
    _write_json(output, value)
    return value


def verify_command(path: Path) -> dict[str, Any]:
    exclusions, dataset = _expected_hashes()
    return validate_public_commitment(
        _read_json(path),
        expected_exclusion_sha256=exclusions,
        expected_dataset_freeze_sha256=dataset,
    )


def register_command(source: Path, output: Path) -> dict[str, Any]:
    value = _read_json(source)
    result = verify_command(source)
    if output.exists():
        raise C5HoldoutError("registered final-holdout commitment is immutable")
    _write_json(output, value, exclusive=True)
    if result["commitment_sha256"] != validate_public_commitment(
        _read_json(output),
        expected_exclusion_sha256=_expected_hashes()[0],
        expected_dataset_freeze_sha256=_expected_hashes()[1],
    )["commitment_sha256"]:
        raise C5HoldoutError("registered commitment changed during publication")
    return {
        **result,
        "status": "registered_unread_final_holdout_commitment",
        "output": str(output),
    }


def preflight_command(commitment_path: Path, ledger_path: Path) -> dict[str, Any]:
    exclusions, dataset = _expected_hashes()
    return gate_preflight(
        _read_json(commitment_path),
        ledger_path,
        expected_exclusion_sha256=exclusions,
        expected_dataset_freeze_sha256=dataset,
    )


def claim_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.permit_output.exists():
        raise C5HoldoutError("decryption permit output already exists")
    try:
        args.encrypted_artifact.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise C5HoldoutError("encrypted holdout artifact must stay outside the repository")
    exclusions, dataset = _expected_hashes()
    result = claim_encrypted_artifact(
        _read_json(args.commitment),
        args.encrypted_artifact,
        args.ledger,
        confirm_commitment_sha256=args.confirm_commitment_sha256,
        code_revision=args.code_revision,
        adapter_sha256=args.adapter_sha256,
        thresholds_sha256=args.thresholds_sha256,
        expected_exclusion_sha256=exclusions,
        expected_dataset_freeze_sha256=dataset,
    )
    permit = {
        "schema_version": "1.0",
        "run_id": result["run_id"],
        "decryption_permit": result.pop("decryption_permit"),
        "commitment_sha256": args.confirm_commitment_sha256,
    }
    _write_json(args.permit_output, permit, exclusive=True)
    return {**result, "permit_output": str(args.permit_output)}


def statistics_command(source: Path, output: Path | None) -> dict[str, Any]:
    result = summarize_offline_results(_read_jsonl(source))
    if output is not None:
        _write_json(output, result, exclusive=True)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser("template")
    template.add_argument("--output", type=Path, default=DEFAULT_TEMPLATE)

    readiness = commands.add_parser("readiness")
    readiness.add_argument("--output", type=Path, default=DEFAULT_READINESS)

    verify = commands.add_parser("verify-commitment")
    verify.add_argument("--commitment", type=Path, default=DEFAULT_COMMITMENT)

    register = commands.add_parser("register")
    register.add_argument("--input", type=Path, required=True)
    register.add_argument("--output", type=Path, default=DEFAULT_COMMITMENT)

    preflight = commands.add_parser("preflight")
    preflight.add_argument("--commitment", type=Path, default=DEFAULT_COMMITMENT)
    preflight.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)

    claim = commands.add_parser("claim")
    claim.add_argument("--commitment", type=Path, default=DEFAULT_COMMITMENT)
    claim.add_argument("--encrypted-artifact", type=Path, required=True)
    claim.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    claim.add_argument("--permit-output", type=Path, default=DEFAULT_PERMIT)
    claim.add_argument("--confirm-commitment-sha256", required=True)
    claim.add_argument("--code-revision", required=True)
    claim.add_argument("--adapter-sha256", required=True)
    claim.add_argument("--thresholds-sha256", required=True)

    statistics = commands.add_parser("statistics")
    statistics.add_argument("--input", type=Path, required=True)
    statistics.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "template":
            result = template_command(args.output)
        elif args.command == "readiness":
            result = readiness_command(args.output)
        elif args.command == "verify-commitment":
            result = verify_command(args.commitment)
        elif args.command == "register":
            result = register_command(args.input, args.output)
        elif args.command == "preflight":
            result = preflight_command(args.commitment, args.ledger)
        elif args.command == "claim":
            result = claim_command(args)
        else:
            result = statistics_command(args.input, args.output)
    except (C5HoldoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C5 holdout error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
