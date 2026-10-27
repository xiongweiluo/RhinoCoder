#!/usr/bin/env python3
"""Owner terminal only: private CPU checks and an inert seal, never execution.

No arguments containing private paths. No task, answer, identity or private
path is printed. The owner supplies newly authored cases, exclusions and an
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


def main():
    check = sys.argv[1:] == ['--check']
    if sys.argv[1:] and not check:
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
    from training.lora_final_custody import seal
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
        roots=_worktrees(repository_root=Path('/Users/xiongweiluo/RhinoCoder'))
        paths={key:Path(getpass.getpass(label)).expanduser() for key,label in (
            ('cases','私有40家族JSON数组路径（不回显）：'),
            ('exclusions','私有排除清单JSON路径（不回显）：'),
            ('attestation','本人核查确认JSON路径（不回显）：'),
            ('encrypted','已加密且往返核实的题目文件路径（不回显）：'),
            ('output','新的私有封存输出目录（不回显）：'))}
        for path in paths.values(): _require_owner_private_path(path,roots+[ROOT])
        if len({p.resolve() for p in paths.values()}) != len(paths): raise ValueError('distinct paths required')
        encrypted=paths['encrypted']
        if encrypted.is_symlink() or not encrypted.is_file() or not 0 < encrypted.stat().st_size <= 10*1024**2: raise ValueError('encrypted size')
        format_=getpass.getpass('加密格式 age-x25519 或 aes-256-gcm（不回显）：')
        cases=_json(paths['cases'])
        package,receipt=seal(spec,cases,_json(paths['exclusions']),
            {'format':format_,'bytes':encrypted.stat().st_size,'sha256':hashlib.sha256(encrypted.read_bytes()).hexdigest()},
            _json(paths['attestation']))
        paths['output'].mkdir(mode=0o700)  # Never replace or consume an earlier seal.
        for name,value in [('runtime-package.json',package),('scorer-cases.json',cases),('owner-receipt.json',receipt)]:
            publish_json(paths['output'],name,value)
        print(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except Exception:
        # Private exceptions may include task text, IDs or paths. Keep them local
        # and unprinted; failed partial output is retained, never made a grant.
        print('seal_failed_no_authority_created; owner privately inspect inputs; do not send private files')
        return 2


if __name__=='__main__': raise SystemExit(main())
