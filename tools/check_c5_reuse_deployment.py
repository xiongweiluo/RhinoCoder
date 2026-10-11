#!/usr/bin/env python3
"""Read-only CPU target preflight. Run this from a trusted source checkout.

The manifest and its hash must come from separately reviewed source material,
not from importing any Python module in the untrusted deployment root.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from training.c5_reuse_deployment import preflight, strict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--instance', required=True)
    parser.add_argument('--state-root', required=True, type=Path)
    args = parser.parse_args()
    try:
        # This input is review material, not a formal case/plan/key pathname.
        if args.manifest.resolve() != args.manifest or args.manifest.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('manifest_path')
        value = strict(args.manifest.read_bytes())
        result = preflight(args.root, value, args.manifest_sha256, args.instance, state_root=args.state_root)
    except (ValueError, OSError, KeyError, TypeError, SyntaxError):
        print(json.dumps({'status': 'cpu_deployment_preflight_rejected', 'execution_ready': False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
