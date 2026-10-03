#!/usr/bin/env python3
"""Verify only an owner-provided *public* C5-6 commitment; no claim or run."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.c5_formal20_commitment import (
    FormalCommitmentValidationError, validate_public_commitment,
)
from training.c5_holdout import sha256_file


def _strict_public(path: Path):
    if not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise FormalCommitmentValidationError("bounded_public_commitment_required")
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value:
                raise FormalCommitmentValidationError("duplicate_public_key")
            value[key] = child
        return value
    return json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          FormalCommitmentValidationError("nonfinite_public_value")))


def preflight(path: Path):
    original80 = json.loads((ROOT / "eval/c5/final-holdout-commitment.json").read_text(encoding="utf-8"))
    return validate_public_commitment(
        _strict_public(path),
        expected_development_freeze_sha256=sha256_file(ROOT / "eval/c5/dataset-v2-freeze-manifest.json"),
        expected_historical_exclusions_sha256=sha256_file(ROOT / "eval/c5/historical-exclusions.json"),
        expected_original80_commitment_file_sha256=sha256_file(ROOT / "eval/c5/final-holdout-commitment.json"),
        expected_original80_merkle_root_sha256=original80["fingerprints"]["family_merkle_root_sha256"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commitment", type=Path, required=True,
                        help="path to path-free public JSON ONLY; never pass task plaintext")
    args = parser.parse_args()
    try:
        result = preflight(args.commitment)
    except (FormalCommitmentValidationError, OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        category = str(exc) if isinstance(exc, FormalCommitmentValidationError) else "invalid_public_commitment"
        print(json.dumps({"status": "public_formal20_preflight_failed", "category": category}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
