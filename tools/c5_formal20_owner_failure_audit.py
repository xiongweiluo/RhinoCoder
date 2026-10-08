#!/usr/bin/env python3
"""Frozen custodian TTY only: audit existing failed state, never decrypt/run.

Separate public audit package; original formal source and records unchanged.
Agent may invoke inspect-runtime (public files only), never audit.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import runpy
import stat
import sys
from pathlib import Path

ID = 'C5AUDIT-FORMAL20-V4-INCOMPLETE-20261009-A'
SOURCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-failure-audit-source-v1')
STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-failure-audit-state-v1')
ORIGINAL = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-source-v4')
EVIDENCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/formal20-state-v4')
SPEC_SHA = '1ce7dba2a75a853a6a2b8d81027235c442586f30718f05dc177f64a04b002fa7'
RUNTIME_SHA = '9f72a0491b49bbb5f21dd83e6c87bb16530218a375593e0308e69caee134f1a3'
CORE = 'c5_formal20_incomplete_audit.py'
ENTRY = 'c5_formal20_owner_failure_audit.py'


def require(ok):
    if not ok:
        raise RuntimeError('incomplete audit guard failed')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    require(path.is_file() and not path.is_symlink() and path.resolve() == path)
    value = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def public_json(path):
    require(path.is_file() and not path.is_symlink() and path.resolve() == path
            and 0 < path.stat().st_size <= 1048576)
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite metadata')))


def public_original():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
            and Path(__file__).resolve().parent == SOURCE)
    require(SOURCE.resolve() == SOURCE and ORIGINAL.resolve() == ORIGINAL)
    spec = public_json(ORIGINAL / 'eval/c5/rhino-formal20-spec-v4.json')
    freeze = public_json(ORIGINAL / 'eval/c5/rhino-formal20-runtime-freeze-v4.json')
    require(digest(spec) == SPEC_SHA and digest(freeze) == RUNTIME_SHA
            and freeze['spec_sha256'] == SPEC_SHA
            and digest(freeze['source_files']) == freeze['source_inventory_sha256'])
    require(file_sha(ORIGINAL / 'eval/c5/rhino-formal20-spec-v4.json') == freeze['spec_file_sha256'])
    require(all(file_sha(ORIGINAL / name) == sha for name, sha in freeze['source_files'].items()))
    require(all(file_sha(ORIGINAL / name) == sha for name, sha in freeze['fixed_public_files'].items()))
    return spec, freeze


def load_core(freeze):
    sys.path.insert(0, str(ORIGINAL))
    scope = runpy.run_path(str(SOURCE / CORE), run_name='c5_failure_audit_core')
    from plugin.rhino_listener.c5_research_provenance import SourceGuard
    guard = SourceGuard(ORIGINAL, freeze['source_files'], freeze['source_inventory_sha256'],
        project_prefixes=('agent', 'training', 'tools', 'plugin', 'data_pipeline'))
    guard()
    return scope['audit_pre_slot_failure'], guard


def environment():
    files = {}
    for name, module in tuple(sys.modules.items()):
        origin = getattr(module, '__file__', None)
        if not origin or str(origin).startswith('<'):
            continue
        path = Path(origin)
        if path.suffix == '.pyc':
            path = Path(importlib.util.source_from_cache(str(path)))
        path = path.resolve(strict=True)
        if path.is_relative_to(ORIGINAL) or path.is_relative_to(SOURCE):
            continue  # Separately frozen explicit project/audit bytes.
        files[str(path)] = file_sha(path)
    executable = Path(sys.executable).resolve(strict=True)
    files[str(executable)] = file_sha(executable)
    return {'python': sys.version, 'executable': str(executable),
            'readable_loaded_external_files': files,
            'kernel_and_unlisted_opaque_runtime_trusted_not_byte_proven': True}


def audit_owner(expected_sha):
    # This condition MUST precede any original evidence access.
    require(sys.stdin.isatty() and sys.stderr.isatty())
    spec, original = public_original()
    audit_freeze = public_json(SOURCE / 'review-runtime.json')
    require(digest(audit_freeze) == expected_sha and audit_freeze['audit_id'] == ID
            and audit_freeze['original_spec_sha256'] == SPEC_SHA
            and audit_freeze['original_runtime_sha256'] == RUNTIME_SHA
            and audit_freeze['source_files'].keys() == {CORE, ENTRY})
    def guard_bytes():
        require(digest(public_json(SOURCE / 'review-runtime.json')) == expected_sha
                and all(file_sha(SOURCE / n) == sha for n, sha in audit_freeze['source_files'].items()))
    guard_bytes()  # Before loading new audit code or existing private evidence.
    audit, guard_project = load_core(original)
    def guard():
        guard_bytes(); guard_project()
        require(environment() == audit_freeze['environment'])
    guard()
    require(not os.path.lexists(STATE) and STATE.parent.resolve() == STATE.parent)
    STATE.mkdir(mode=0o700)
    from plugin.rhino_listener.c5_research_channel import read_json, publish_json
    publish_json(STATE, 'owner-audit-admission.json', {'audit_id': ID,
        'review_runtime_sha256': expected_sha, 'actor': 'repository_owner',
        'original_runtime_sha256': RUNTIME_SHA, 'replay_allowed': False})
    summary = audit(lambda name: read_json(EVIDENCE, name), spec, original)
    guard()
    summary = {**summary, 'audit_id': ID, 'review_runtime_sha256': expected_sha}
    publish_json(STATE, 'owner-public-incomplete-audit-summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect-runtime', 'audit'))
    parser.add_argument('--freeze-sha256')
    args = parser.parse_args()
    try:
        if args.mode == 'inspect-runtime':
            _, original = public_original()
            load_core(original)
            result = {'audit_id': ID, 'environment': environment(), 'private_evidence_reads': 0}
        else:
            require(isinstance(args.freeze_sha256, str) and len(args.freeze_sha256) == 64)
            result = audit_owner(args.freeze_sha256)
        print(json.dumps(result, sort_keys=True)); return 0
    except Exception as exc:
        # Never print traceback, arbitrary exception message, task or path.
        print(json.dumps({'audit_id': ID, 'status': 'incomplete_audit_refused_no_automatic_retry',
            'error_type': type(exc).__name__, 'private_content_included': False,
            'replay_allowed': False}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
