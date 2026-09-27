#!/usr/bin/env python3
"""Owner-only C5 holdout audit and public commitment builder.

Run this command in a repository-owner-controlled environment.  Do not give
the plaintext path, encryption key, or command output directory to a training
or development agent.  Only the generated public commitment JSON is handed
back for registration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_tool_contract_candidate import TOKENIZER_SNAPSHOT  # noqa: E402
from training.c5_holdout import C5HoldoutError, build_public_commitment, sha256_file  # noqa: E402
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402


HISTORICAL_EXCLUSIONS = ROOT / "eval/c5/historical-exclusions.json"
DATASET_FREEZE = ROOT / "eval/c5/dataset-v2-freeze-manifest.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise C5HoldoutError(f"JSON root must be an object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise C5HoldoutError(f"{path}:{line_no}: row must be an object")
        rows.append(value)
    return rows


def _outside_repository(path: Path, label: str) -> None:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return
    raise C5HoldoutError(f"{label} must stay outside the repository")


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plaintext-holdout", type=Path, required=True)
    parser.add_argument("--encrypted-artifact", type=Path, required=True)
    parser.add_argument("--development", type=Path, action="append", required=True)
    parser.add_argument(
        "--tokenizer-snapshot",
        type=Path,
        default=TOKENIZER_SNAPSHOT,
        help="existing pinned local tokenizer snapshot; no download is attempted",
    )
    parser.add_argument("--encrypted-format", choices=("age-x25519", "aes-256-gcm"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        _outside_repository(args.plaintext_holdout, "plaintext holdout")
        _outside_repository(args.encrypted_artifact, "encrypted holdout artifact")
        _outside_repository(args.output, "public commitment staging output")
        if not args.tokenizer_snapshot.is_dir():
            raise C5HoldoutError("pinned tokenizer snapshot is unavailable; no download attempted")
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            args.tokenizer_snapshot, local_files_only=True
        )
        families = _load_jsonl(args.plaintext_holdout)
        if len(args.development) != 3:
            raise C5HoldoutError("exactly three frozen development split files are required")
        freeze = _load_json(DATASET_FREEZE)
        frozen_artifacts = {
            str(item.get("path") or ""): item for item in freeze.get("artifacts") or []
        }
        seen_names = set()
        development = []
        for path in args.development:
            name = path.name
            artifact = frozen_artifacts.get(name)
            if artifact is None or name in seen_names:
                raise C5HoldoutError("development inputs must be the three distinct frozen splits")
            if sha256_file(path) != artifact.get("sha256"):
                raise C5HoldoutError(f"development split hash drifted: {name}")
            rows = _load_jsonl(path)
            if len(rows) != int(artifact.get("families") or -1):
                raise C5HoldoutError(f"development split family count drifted: {name}")
            development.extend(rows)
            seen_names.add(name)
        if seen_names != {"train.jsonl", "validation.jsonl", "development.jsonl"}:
            raise C5HoldoutError("development inputs do not cover all three frozen splits")
        if len(development) != 440:
            raise C5HoldoutError("development comparison set must contain exactly 440 families")
        sealed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        commitment = build_public_commitment(
            families,
            development,
            tools=load_public_mcp_tools(),
            tokenizer=tokenizer,
            encrypted_artifact_path=args.encrypted_artifact,
            encrypted_format=args.encrypted_format,
            historical_exclusions=_load_json(HISTORICAL_EXCLUSIONS),
            historical_exclusions_sha256=sha256_file(HISTORICAL_EXCLUSIONS),
            development_dataset_freeze_sha256=sha256_file(DATASET_FREEZE),
            sealed_at=sealed_at,
        )
        _write_exclusive(args.output, commitment)
        result = {
            "status": "owner_commitment_ready_for_public_registration",
            "family_count": commitment["family_count"],
            "strata_counts": commitment["strata_counts"],
            "core_tool_family_counts": commitment["core_tool_family_counts"],
            "encrypted_artifact_sha256": commitment["encrypted_artifact"]["sha256"],
            "public_commitment_output": str(args.output),
            "development_agent_plaintext_access": False,
            "final_holdout_rows_read": 0,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (C5HoldoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C5 custodian error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
