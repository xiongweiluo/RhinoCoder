#!/usr/bin/env python3
"""Owner terminal only: private CPU checks and an inert seal, never execution.

No arguments containing private paths. No task, answer, identity or private
path is printed. The owner supplies newly authored cases and an
independently encrypted/round-trip-verified copy. Never invoke on agent input.
"""
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class OwnerInputError(ValueError):
    pass


SAFE_ERRORS = {
    'empty_path': 'empty_path', 'path_has_outer_quote': 'path_has_outer_quote',
    'distinct paths required': 'input_paths_must_differ',
    'output already exists': 'output_directory_already_exists',
    'output parent missing': 'output_parent_missing',
    'encrypted size': 'encrypted_file_missing_symlink_empty_or_over_10_MiB',
    'encrypted format': 'encryption_format_must_be_age_x25519_or_aes_256_gcm',
    'binding not confirmed': 'current_file_binding_not_confirmed',
    'owner_private_input_must_be_outside_all_worktrees': 'private_path_inside_public_workspace',
    'cannot_verify_worktree_boundaries': 'worktree_boundary_check_failed',
    'missing_or_unbounded_input': 'input_file_missing_empty_or_over_size_limit',
    'invalid_json_input': 'invalid_json_or_encoding',
    'new numeric templates overlap': 'new_set_numeric_template_overlap',
    'new-set near-duplicate overlap': 'new_set_near_duplicate_overlap',
    'published historical fingerprint overlap': 'published_historical_fingerprint_overlap',
    'private channel package exceeds fixed byte budget': 'package_byte_budget_exceeded',
    'fixed stratum population differs': 'fixed_stratum_population_differs',
    'family/template/task reuse': 'family_template_or_task_reuse',
    'original twelve-tool coverage required': 'core_tool_coverage_differs',
    'seal time outside preparation window': 'seal_clock_outside_window',
    'current case and encryption binding required': 'current_binding_incomplete',
    'encrypted artifact commitment required': 'encrypted_commitment_invalid'
}


def private_path(label):
    value = getpass.getpass(label)
    if not value.strip(): raise OwnerInputError('empty_path')
    if value.startswith(("'", '"')) or value.endswith(("'", '"')):
        raise OwnerInputError('path_has_outer_quote')
    return Path(value).expanduser()


def failure_code(exc):
    # Never echo arbitrary exception messages or filenames from private I/O.
    if isinstance(exc, FileNotFoundError): return 'file_not_found'
    if isinstance(exc, FileExistsError): return 'output_directory_already_exists'
    if isinstance(exc, IsADirectoryError): return 'expected_file_got_directory'
    if isinstance(exc, PermissionError): return 'permission_denied'
    if isinstance(exc, (json.JSONDecodeError, UnicodeError)): return 'invalid_json_or_encoding'
    return SAFE_ERRORS.get(str(exc), 'unexpected_error_details_withheld')


def main():
    check = sys.argv[1:] == ['--check']
    check_cases_only = sys.argv[1:] == ['--check-cases']
    check_seal_only = sys.argv[1:] == ['--check-seal']
    if sys.argv[1:] and not (check or check_cases_only or check_seal_only):
        print('only_public_check_or_interactive_owner_mode_supported'); return 2
    # Before prompting or opening any data. This is a workflow barrier, not an
    # OS security boundary against an agent that disregards its instructions.
    if not check and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        print('owner_interactive_terminal_required'); return 2
    from training.lora_development_local_tokenizer import SITE
    if SITE not in sys.path: sys.path.append(SITE)  # -S: explicit CPU dependency closure, no site hooks.
    from tools.c5_rhino_formal20_owner_exclusion import _json, _worktrees, _require_owner_private_path
    from plugin.rhino_listener.c5_research_channel import publish_json
    from plugin.rhino_listener.lora_development_admission import source_guard
    from training.lora_final_custody import seal_owner_confirmed
    stage, input_kind, output_created = 'public_source_check', None, False
    try:
        spec=json.loads((ROOT/'lora-final-spec.json').read_text())
        source_guard(ROOT,spec['source_files'])
        from training.lora_final_preparation import validate_spec
        validate_spec(spec)
        if check:
            from plugin.rhino_listener.c5_research_native import digest
            print(json.dumps({'status':'passed','spec_sha256':digest(spec),'private_inputs_read':False,
                'model_calls':0,'rhino_calls':0,'execution_authorized':False})); return 0
        # Repo location is public; used only to enumerate ALL managed worktrees.
        stage = 'worktree_boundary_check'
        roots=_worktrees(repository_root=Path('/Users/xiongweiluo/RhinoCoder'))
        if check_cases_only:
            stage, input_kind = 'input_path', 'cases'
            path=private_path('私有40家族JSON数组路径（不回显）：')
            _require_owner_private_path(path,roots+[ROOT])
            from training.lora_final_case_check import check_cases
            stage = 'case_structure_check'
            report=check_cases(spec,_json(path))
            print(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2))
            return 0 if not report['errors'] else 2
        paths = {}
        for key,label in (
            ('cases','私有40家族JSON数组路径（不回显，不加引号）：'),
            ('encrypted','已加密且往返核实的题目文件路径（不回显，不加引号）：'),
            ('output','尚不存在的私有封存输出目录（不回显，不加引号）：')):
            stage, input_kind = 'input_path', key
            paths[key] = private_path(label)
            stage = 'private_path_boundary_check'
            _require_owner_private_path(paths[key],roots+[ROOT])
        stage, input_kind = 'path_relationship_check', None
        if len({p.resolve() for p in paths.values()}) != len(paths): raise ValueError('distinct paths required')
        stage, input_kind = 'output_directory_check', 'output'
        if paths['output'].exists() or paths['output'].is_symlink(): raise OwnerInputError('output already exists')
        if not paths['output'].parent.is_dir(): raise OwnerInputError('output parent missing')
        stage, input_kind = 'encrypted_file_check', 'encrypted'
        encrypted=paths['encrypted']
        if encrypted.is_symlink() or not encrypted.is_file() or not 0 < encrypted.stat().st_size <= 10*1024**2: raise ValueError('encrypted size')
        stage = 'encrypted_format_check'
        format_=getpass.getpass('加密格式 age-x25519 或 aes-256-gcm（不回显）：')
        if format_ not in {'age-x25519','aes-256-gcm'}: raise OwnerInputError('encrypted format')
        stage, input_kind = 'read_cases_json', 'cases'
        cases=_json(paths['cases'])
        # Prior review comes from the owner's recorded instruction, not a new file.
        # Only bind that review to these exact bytes and the newly prepared encryption.
        stage, input_kind = 'current_file_binding', None
        confirmed = getpass.getpass('已记录查重与核查确认。确认本次文件是该已核查版本、密文已往返核对且密钥/明文未交给代理、题目未经模型或正式运行消费；输入 SEAL（不回显）：')
        if confirmed != 'SEAL': raise ValueError('binding not confirmed')
        from datetime import datetime, timezone
        from plugin.rhino_listener.lora_final_admission import BINDING_FLAGS
        binding = dict(actor='repository_owner', sealed_at_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                       owner_confirmation=spec['custody_policy']['owner_confirmation'], **{k:True for k in BINDING_FLAGS})
        stage, input_kind = 'encrypted_hash', 'encrypted'
        encrypted_record = {'format':format_,'bytes':encrypted.stat().st_size,'sha256':hashlib.sha256(encrypted.read_bytes()).hexdigest()}
        stage, input_kind = 'custody_validation', None
        package,receipt=seal_owner_confirmed(spec,cases,encrypted_record,binding)
        if check_seal_only:
            print(json.dumps({'status':'seal_preflight_passed_not_sealed','sealed':False,
                'files_written':0,'execution_authorized':False,'model_calls':0,'rhino_calls':0}))
            return 0
        stage, input_kind = 'create_output_directory', 'output'
        paths['output'].mkdir(mode=0o700)  # Never replace or consume an earlier seal.
        output_created = True
        stage = 'publish_sealed_files'
        for name,value in [('runtime-package.json',package),('scorer-cases.json',cases),('owner-receipt.json',receipt)]:
            publish_json(paths['output'],name,value)
        print(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'seal_preflight_failed' if check_seal_only else 'owner_check_or_seal_failed',
            'stage':stage, 'input':input_kind, 'code':failure_code(exc),
            'sealed':False, 'execution_authorized':False,
            'output_may_be_partial':output_created, 'model_calls':0, 'rhino_calls':0}))
        return 2


if __name__=='__main__': raise SystemExit(main())
