#!/usr/bin/env python3
"""Execute one authorized C5 development/formal segment, without holdout access."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

from training.c5_execution import execute  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("overfit", "system", "formal"), required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--resume-step", type=int)
    parser.add_argument("--stop-after-step", type=int)
    args = parser.parse_args()
    if args.stop_after_step is not None and (args.phase != "overfit" or args.stop_after_step != 1):
        parser.error("only the frozen overfit step-1 independent resume boundary may pause")
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("passed") or not result.get("completed") else 2
    except Exception as exc:
        print(f"C5 execution stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
