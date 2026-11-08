#!/usr/bin/env python3
"""Prepare public probe bytes and an empty future state path; never grant/run."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def build(root, destination, *, fingerprint_diagnostic=False, document_scope_probe=False, controlled_snapshot_probe=False, controlled_continuity_probe=False):
    from tools.build_lora_development_package import source_manifest
    from plugin.rhino_listener.c5_research_native import digest, require
    from training.lora_common_probes import public_probes, diagnostic_probes, document_scope_probes, controlled_snapshot_probes, controlled_continuity_probes
    from training.lora_comparison_plan import proposal, compile_cases, capacity
    root, destination = Path(root).resolve(), Path(destination).resolve()
    require(not destination.exists(), 'new preparation directory only; never overwrite evidence')
    files = source_manifest(root)
    for path in (root/'tools').glob('*lora_common*.py'):
        files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = proposal(native_probe=True, fingerprint_diagnostic=fingerprint_diagnostic, document_scope_probe=document_scope_probe, controlled_snapshot_probe=controlled_snapshot_probe, controlled_continuity_probe=controlled_continuity_probe)
    cases = controlled_continuity_probes() if controlled_continuity_probe else controlled_snapshot_probes() if controlled_snapshot_probe else document_scope_probes() if document_scope_probe else diagnostic_probes() if fingerprint_diagnostic else public_probes()
    package = {'kind': 'public_common_controlled_continuity_probe_v1' if controlled_continuity_probe else 'public_common_controlled_snapshot_probe_v1' if controlled_snapshot_probe else 'public_common_document_scope_probe_v1' if document_scope_probe else
                           'public_common_state_diagnostic_v1' if fingerprint_diagnostic else 'public_common_native_probe_v1',
        'source_files': dict(sorted(files.items())),
        'source_root': str(destination/'source'), 'state_root': str(destination/'state'),
        'python': str(Path('/opt/anaconda3/bin/python3.13').resolve()),
        'lease_end_epoch': int(datetime.fromisoformat('2026-10-30T20:00:00+01:00').timestamp()),
        'plan': plan, 'compiled': compile_cases(plan, cases), 'capacity': capacity(plan),
        'model_loads': 0, 'execution_authorized': False}
    destination.mkdir(mode=0o700)
    source = destination/'source'; source.mkdir(mode=0o700)
    for name, expected in files.items():
        raw = (root/name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'source changed during copy')
        target = source/name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (source/'common-probe-package.json').write_text(json.dumps(package, indent=2, sort_keys=True)+'\n')
    # No state, owner record, host key, native callback or process created.
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--fingerprint-diagnostic', action='store_true')
    parser.add_argument('--document-scope-probe', action='store_true')
    parser.add_argument('--controlled-snapshot-probe', action='store_true')
    parser.add_argument('--controlled-continuity-probe', action='store_true')
    args = parser.parse_args()
    from plugin.rhino_listener.c5_research_native import digest
    package = build(ROOT, args.destination, fingerprint_diagnostic=args.fingerprint_diagnostic, document_scope_probe=args.document_scope_probe, controlled_snapshot_probe=args.controlled_snapshot_probe, controlled_continuity_probe=args.controlled_continuity_probe)
    print(json.dumps({'package_sha256': digest(package), 'source_root': package['source_root'],
                      'model_loads': 0, 'state_created': False, 'execution_authorized': False}))
