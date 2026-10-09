#!/usr/bin/env python3
"""Run the network-free C5-2 contract/data engineering gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.c5_engineering import (  # noqa: E402
    C5EngineeringError,
    DEFAULT_CONFIG,
    audit_engineering_gate,
)


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--tokenizer-snapshot", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit_engineering_gate(
            args.dataset_dir,
            args.tokenizer_snapshot,
            config_path=args.config,
        )
    except (C5EngineeringError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C5 engineering gate failed: {exc}", file=sys.stderr)
        return 1
    if args.output:
        _atomic_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
