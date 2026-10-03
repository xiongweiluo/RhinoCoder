#!/usr/bin/env python3
"""Audit original C5 final public export; no inference, claims or decryption."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.c5_execution import read_json, sha256_file, write_json  # noqa: E402
from training.c5_final_audit import audit_final_export, require  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--owner-ledger", type=Path, required=True)
    parser.add_argument("--formal-context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    freeze = read_json(ROOT/"eval/c5/c5-final-evaluation-freeze.json")
    for name, expected in freeze["implementation_sha256"].items():
        require(sha256_file(ROOT/name) == expected, "frozen implementation drift")
    registry_path = ROOT/"eval/c5/gpu-formal-registry-20261001.json"
    require(sha256_file(registry_path) == freeze["registry_sha256"], "registry file drift")
    result = audit_final_export(args.public_dir, freeze, read_json(args.formal_context),
                                args.owner_ledger, read_json(registry_path),
                                read_json(ROOT/"eval/c5/final-holdout-commitment.json"),
                                read_json(ROOT/"eval/c5/c5-engineering-readiness.json")["public_tool_schema_sha256"])
    write_json(args.output, result, exclusive=True)
    print("C5 public evidence audited; original run preserved; no rerun authorized.")


if __name__ == "__main__":
    main()
