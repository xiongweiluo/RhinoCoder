#!/usr/bin/env python3
"""Create or audit the external C0 manifest, including evaluation-only P2 hashes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.config import (  # noqa: E402
    DEFAULT_CONFIG,
    ReadinessError,
    canonical_json,
    project_path,
    sha256_bytes,
    sha256_file,
)
from training.preregistration import (  # noqa: E402
    DEFAULT_FREEZE_MANIFEST,
    DEFAULT_PREREGISTRATION,
    _tracked_worktree_changes,
    audit_preregistration_freeze,
    build_freeze_payload,
)
from training.reporting import atomic_json  # noqa: E402


P2_EVALUATION_CONTRACT_FILES = (
    "eval/p2/freeze-manifest.json",
    "eval/p2/hard_tasks.jsonl",
    "eval/p2/fixtures.json",
    "eval/p2/statistics-protocol.json",
    "eval/p2/leakage-policy.json",
)


def _p2_contract() -> dict[str, Any]:
    files = {
        relative: sha256_file(project_path(relative))
        for relative in P2_EVALUATION_CONTRACT_FILES
    }
    return {
        "role": "evaluation_only_not_a_training_consumer",
        "files": files,
        "aggregate_sha256": sha256_bytes(canonical_json(files).encode("utf-8")),
    }


def build_complete_payload(
    config_path: str | Path = DEFAULT_CONFIG,
    preregistration_path: str | Path = DEFAULT_PREREGISTRATION,
) -> dict[str, Any]:
    payload = build_freeze_payload(config_path, preregistration_path)
    payload["evaluation_contracts"] = {"p2": _p2_contract()}
    return payload


def freeze(
    config_path: str | Path = DEFAULT_CONFIG,
    preregistration_path: str | Path = DEFAULT_PREREGISTRATION,
    output_path: str | Path = DEFAULT_FREEZE_MANIFEST,
) -> dict[str, Any]:
    if _tracked_worktree_changes():
        raise ReadinessError("C0 freeze requires a clean tracked worktree; commit reviewed changes first")
    target = project_path(output_path)
    if target.exists():
        raise ReadinessError(f"freeze manifest already exists and is immutable: {target}")
    payload = build_complete_payload(config_path, preregistration_path)
    payload["status"] = "frozen"
    atomic_json(target, payload)
    return {**payload, "freeze_manifest_sha256": sha256_file(target), "output": str(target)}


def audit(manifest_path: str | Path = DEFAULT_FREEZE_MANIFEST) -> dict[str, Any]:
    result = audit_preregistration_freeze(manifest_path)
    frozen = json.loads(project_path(manifest_path).read_text(encoding="utf-8"))
    if frozen.get("evaluation_contracts", {}).get("p2") != _p2_contract():
        raise ReadinessError("P2 evaluation contract hashes drifted after C0 freeze")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser("freeze")
    freeze_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    freeze_parser.add_argument("--preregistration", default=DEFAULT_PREREGISTRATION)
    freeze_parser.add_argument("--output", default=DEFAULT_FREEZE_MANIFEST)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--manifest", default=DEFAULT_FREEZE_MANIFEST)
    args = parser.parse_args()
    try:
        result = (
            freeze(args.config, args.preregistration, args.output)
            if args.command == "freeze"
            else audit(args.manifest)
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (ReadinessError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C0 freeze error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
