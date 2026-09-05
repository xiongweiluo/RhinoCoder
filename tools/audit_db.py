#!/usr/bin/env python3
"""Create, import, audit, query, and export the RhinoCoder SQLite audit store."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.db import (  # noqa: E402
    DEFAULT_AUDIT_DB,
    AuditDatabase,
    import_golden_dataset,
)


def _write_or_print(payload: object, output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        print(text, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    output.chmod(0o600)
    print(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_AUDIT_DB)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Apply all schema migrations")

    import_parser = subparsers.add_parser(
        "import-golden", help="Idempotently import the local golden JSONL dataset"
    )
    import_parser.add_argument("--root", type=Path, default=ROOT)
    import_parser.add_argument("--golden", type=Path)
    import_parser.add_argument("--expected-count", type=int, default=300)
    import_parser.add_argument("--output", type=Path)

    audit_parser = subparsers.add_parser(
        "audit", help="Run integrity, foreign-key, privacy, and lineage checks"
    )
    audit_parser.add_argument("--output", type=Path)

    lineage_parser = subparsers.add_parser(
        "lineage", help="Export all normalized records for one run_id"
    )
    lineage_parser.add_argument("run_id")
    lineage_parser.add_argument("--output", type=Path)

    summary_parser = subparsers.add_parser(
        "summary", help="Export model, tag, failure, and table summaries"
    )
    summary_parser.add_argument("--output", type=Path)

    args = parser.parse_args()
    with AuditDatabase(args.database) as database:
        if args.command == "init":
            _write_or_print(
                {"database": str(database.path), "schema_version": database.schema_version},
                None,
            )
            return 0
        if args.command == "import-golden":
            summary = import_golden_dataset(
                database,
                root=args.root,
                golden_path=args.golden,
                expected_count=args.expected_count,
            )
            _write_or_print(asdict(summary), args.output)
            return 0
        if args.command == "audit":
            result = database.audit()
            _write_or_print(asdict(result), args.output)
            return 0 if result.passed else 1
        if args.command == "lineage":
            _write_or_print(database.get_run_lineage(args.run_id), args.output)
            return 0
        if args.command == "summary":
            _write_or_print(database.summary(), args.output)
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
