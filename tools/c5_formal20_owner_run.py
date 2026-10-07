#!/usr/bin/env python3
"""Custodian-side formal driver and post-run auditor. No task read in preflight.

Run is disabled until complete public spec/runtime plus exact new owner grant.
The age package/key paths are supplied ONLY in the custodian's private terminal.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from plugin.rhino_listener.c5_formal20_scope import MAC_STATE
from plugin.rhino_listener.c5_research_channel import read_json, publish_json, private_directory
from plugin.rhino_listener.c5_research_native import require
from training.c5_formal20_field_scope import scope, public
from training.c5_formal20_runner import FormalRunner
from training.c5_formal20_adapters import ModelAdapter, NativeAdapter
from training.c5_formal20_runtime import FormalBudget
from training.c5_formal20_joint_audit import audit_run
from training.c5_modelbridge_runtime import file_sha
from training.c5_model_transport import strict_json
from tools.c5_formal20_public_preflight import preflight as public_commitment_preflight
from tools.c5_formal20_freeze_preflight import report as preparation_report

COMMITMENT = ROOT / 'eval/c5/rhino-formal20-public-commitment-v1.json'


def commitment(spec):
    value = public(COMMITMENT)
    verified = public_commitment_preflight(COMMITMENT)
    require(verified['public_commitment_sha256'] == spec['public_commitment_sha256']
        and value['family_merkle_root_sha256'] == spec['family_merkle_root_sha256']
        and value['slot_order_sha256'] == spec['slot_order_sha256'], 'formal public commitment/spec differs')
    return value


def sealed_loader(sealed, identity, commitment_value, freeze, *, state=MAC_STATE, repository_root=None):
    """Closure only; actual package/key checks and decryption occur after started."""
    def load():
        from tools.c5_rhino_formal20_owner_exclusion import _require_owner_private_path, _worktrees
        require((state / 'formal20.started.json').is_file(), 'formal consumption missing before private input')
        roots = _worktrees() if repository_root is None else _worktrees(repository_root=repository_root)
        for path in (sealed, identity):
            _require_owner_private_path(path, roots)
            require(path.is_absolute() and path.resolve() == path and path.is_file(), 'formal private input type invalid')
            fd = private_directory(path.parent); os.close(fd)
            require((path.stat().st_mode & 0o777) == 0o600, 'formal private input mode must be 0600')
        require(sealed != identity and commitment_value['encrypted_artifact']['format'] == 'age-x25519'
            and sealed.stat().st_size == commitment_value['encrypted_artifact']['bytes']
            and file_sha(sealed) == commitment_value['encrypted_artifact']['sha256'], 'formal encrypted artifact differs')
        executable = Path(freeze['decryption_executable'])
        require(executable.is_absolute() and file_sha(executable) == freeze['decryption_executable_sha256'],
            'formal frozen age executable differs')
        # Paths stay private and exceptions never expose stderr or decrypted text.
        result = subprocess.run([str(executable), '--decrypt', '--identity', str(identity), str(sealed)],
            capture_output=True, timeout=30, check=False)
        require(result.returncode == 0 and 0 < len(result.stdout) <= 8 * 1024 * 1024, 'formal decryption failed/bound exceeded')
        from training.c5_formal20_plan import validate_families
        cases = validate_families([strict_json(line) for line in result.stdout.splitlines() if line.strip()])
        publish_json(state, 'private-cases.json', cases)
        return cases
    return load


def run(sealed, identity):
    spec, freeze, approval, guard = scope()
    public_value = commitment(spec)
    require(isinstance(freeze.get('decryption_executable'), str)
        and isinstance(freeze.get('decryption_executable_sha256'), str)
        and public_value['encrypted_artifact']['format'] == 'age-x25519', 'frozen age loader required before admission')
    budget = FormalBudget(freeze['resource_boundary'])
    runner = FormalRunner(state=MAC_STATE, spec=spec, freeze=freeze, approval=approval,
        model=ModelAdapter(MAC_STATE, spec, freeze, guard=guard),
        native=NativeAdapter(MAC_STATE, spec, freeze, guard=guard), source_guard=guard, budget_guard=budget.check)
    value = runner.run(sealed_loader(sealed, identity, public_value, freeze))
    budget.settle(MAC_STATE, 'formal_mac_driver_finished')
    return value


def audit():
    # Authority is still checked, but expiry never forbids a read-only audit.
    spec, freeze, _, guard = scope(check_time=False)
    commitment(spec)
    run_result = read_json(MAC_STATE, 'formal20.run-result.json')
    require(run_result['status'] == 'formal_execution_complete_awaiting_independent_audit', 'incomplete formal run retained for diagnosis')
    from training.c5_execution import load_pinned_tokenizer, load_config
    directory = Path(freeze['tokenizer_dir'])
    require(directory.is_absolute() and directory.resolve() == directory and all(file_sha(directory / n) == sha
        for n, sha in freeze['tokenizer_file_sha256'].items()), 'formal audit tokenizer drift')
    tokenizer = load_pinned_tokenizer(directory, config=load_config())
    guard()
    value = audit_run(MAC_STATE, read_json(MAC_STATE, 'private-cases.json'), spec, freeze, tokenizer, source_guard=guard)
    publish_json(MAC_STATE, 'independent-audit.json', value)
    # Public terminal/report has aggregate statistics only, never per-family text.
    return {'status': value['status'], 'paired_summary': value['paired_summary'],
        'resource_and_transport': value['resource_and_transport']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'progress', 'run', 'audit'))
    parser.add_argument('--sealed-package', type=Path)
    parser.add_argument('--identity-file', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'preflight':
            require(args.sealed_package is None and args.identity_file is None, 'public preflight accepts no private inputs')
            value = preparation_report()
        elif args.mode == 'progress':
            require(args.sealed_package is None and args.identity_file is None, 'progress accepts no private inputs')
            from training.c5_formal20_public_progress import read_public_progress
            value=read_public_progress(MAC_STATE)
        elif args.mode == 'run':
            require(args.sealed_package is not None and args.identity_file is not None, 'owner terminal sealed inputs required')
            value = run(args.sealed_package, args.identity_file)
        else:
            require(args.sealed_package is None and args.identity_file is None, 'audit uses already consumed private state only')
            value = audit()
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({'status': 'formal20_field_entry_stopped_without_retry', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
