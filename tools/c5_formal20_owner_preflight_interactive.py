#!/usr/bin/env python3
"""Owner-terminal-only preflight. Private input paths are never echoed.

No noninteractive agent use, model/Rhino/network calls or consumption claims.
The owner supplies new20/original80 paths ONLY in the private terminal.
"""
from __future__ import annotations
import argparse
import getpass
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from tools.c5_rhino_formal20_owner_exclusion import preflight_paths, ExclusionPreflightError
from training.c5_formal20_plan import FormalPlanError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history-directory', type=Path, required=True)
    parser.add_argument('--development-root', type=Path, required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print(json.dumps({'status': 'owner_private_tty_required_no_inputs_read'}), file=sys.stderr); return 1
    try:
        extra = args.history_directory / 'extra-exclusion.jsonl'
        report = json.loads((args.history_directory / 'coverage-report.json').read_text())
        if (report['all_history_proven_complete'] is not False or report['manual_complete_r_inventory_review_required'] is not True
                or hashlib.sha256(extra.read_bytes()).hexdigest() != report['extra_exclusion_sha256']):
            raise ExclusionPreflightError('historical_export_identity_mismatch')
        # No task file is opened before these private owner-only prompts.
        candidate = Path(getpass.getpass('新20题 JSONL 绝对路径（不回显）：').strip())
        original80 = Path(getpass.getpass('原80家族 JSONL 绝对路径（不回显）：').strip())
        if not candidate.is_absolute() or not original80.is_absolute():
            raise ExclusionPreflightError('absolute_private_paths_required')
        _, result, _ = preflight_paths(candidate, original80,
            [args.development_root / n for n in ('train.jsonl', 'validation.jsonl', 'development.jsonl')], [extra])
    except (ExclusionPreflightError, FormalPlanError, OSError, ValueError, KeyError, TypeError, EOFError, KeyboardInterrupt) as exc:
        category = str(exc) if isinstance(exc, ExclusionPreflightError) else ('formal_case_schema_invalid'
            if isinstance(exc, FormalPlanError) else 'private_input_or_history_identity_invalid')
        print(json.dumps({'status': 'owner_private_preflight_failed', 'category': category}), file=sys.stderr); return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
