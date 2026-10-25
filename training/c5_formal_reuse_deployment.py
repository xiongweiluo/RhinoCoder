"""Independent public population/byte verification; no imports or run effects."""
import hashlib
import os
import json
import stat
from pathlib import Path
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE

def verify(root,spec,runtime):
    root=Path(root);require(root.is_absolute() and root.resolve()==root and root.is_dir(),
        'formal_reuse_deployment_root')
    pins=runtime['source_files'];names=set(pins)|{FREEZE_FILE}
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    directories={str(p) for n in names for p in Path(n).parents if str(p)!='.'}
    actual_directories={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()}
    require(actual==names and actual_directories==directories and all(not p.is_symlink()
        and (stat.S_ISREG(p.lstat().st_mode) or stat.S_ISDIR(p.lstat().st_mode)) for p in root.rglob('*')),
        'formal_reuse_deployment_closed_population')
    require(all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in pins.items()),
        'formal_reuse_deployment_bytes')
    from training.c5_reuse_evidence import strict
    require(strict((root/FREEZE_FILE).read_bytes(),limit=2097152)==runtime and strict((root/SPEC_FILE).read_bytes())==spec
        and runtime['spec_sha256']==digest(spec),'formal_reuse_deployment_spec_runtime_binding')
    return {'complete_public_population_bytes_verified':True,'files':len(names),
        'spec_sha256':digest(spec),'runtime_sha256':digest(runtime),'execution_authority':False,
        'model_or_rhino_calls':0,'private_formal_reads':0}

def stage_local(root,payload,*,state_root,archive_root=None):
    root,state=Path(root),Path(state_root)
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(state),
        'formal_reuse_stage_requires_unconsumed_candidate')
    require(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in payload),
        'formal_reuse_public_payload_path')
    if not root.exists():root.mkdir(mode=0o700)
    existing={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    require(existing<=set(payload) and all(not p.is_symlink() for p in root.rglob('*')),
        'formal_reuse_stage_unknown_public_population')
    changed={n:(root/n).read_bytes() for n in existing if (root/n).read_bytes()!=payload[n]}
    if changed:
        require(archive_root is not None,'formal_reuse_changed_public_candidate_requires_archive')
        archive_root=Path(archive_root)
        require(archive_root.is_absolute() and archive_root.resolve()==archive_root
            and archive_root!=root and root not in archive_root.parents and archive_root not in root.parents,
            'formal_reuse_public_archive_path')
        identity=hashlib.sha256(json.dumps({n:hashlib.sha256(raw).hexdigest() for n,raw in sorted(changed.items())},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        archive=archive_root/identity;archive.mkdir(mode=0o700,parents=True,exist_ok=True)
        for n,raw in changed.items():
            p=archive/n;p.parent.mkdir(parents=True,exist_ok=True)
            if p.exists():require(p.read_bytes()==raw,'formal_reuse_public_archive_collision')
            else:
                with p.open('xb') as stream:stream.write(raw)
                p.chmod(0o600)
    for n,raw in payload.items():
        require(not os.path.lexists(state),'formal_reuse_no_update_after_state_or_grant')
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists():
            if p.read_bytes()==raw:continue
            require(n in changed,'formal_reuse_candidate_changed_during_staging')
            temp=p.with_name(p.name+'.candidate-tmp')
            with temp.open('xb') as stream:stream.write(raw)
            temp.chmod(0o600);os.replace(temp,p);continue
        with p.open('xb') as stream:stream.write(raw)
        p.chmod(0o600)
    return root
