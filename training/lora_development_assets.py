"""Read-only verification of explicitly bound model paths, including HF blobs."""
from pathlib import Path
import stat

from plugin.rhino_listener.c5_research_native import require
from tools.audit_lora_development_environment import sha


def path_identity(path, *, follow=True):
    value = Path(path).stat() if follow else Path(path).lstat()
    # Reads may update atime; that is not a change to content or its binding.
    return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def verify_model_paths(assets, bindings):
    expected = {}
    for root_key, names_key in [('snapshot_dir', 'base_files'), ('adapter_root', 'adapter_files')]:
        root = Path(assets[root_key])
        require(root.is_absolute() and root.resolve() == root, 'model root alias differs')
        expected.update({str(root / name): value for name, value in assets[names_key].items()})
    require(type(bindings) is dict and set(bindings) == set(expected), 'complete model path bindings required')
    files, identities = {}, {}
    for name, expected_sha in expected.items():
        binding = bindings[name]
        require(type(binding) is dict and set(binding) == {'resolved_path', 'sha256'}
                and binding['sha256'] == expected_sha, 'model binding digest differs')
        logical, target = Path(name), Path(binding['resolved_path'])
        require(target.is_absolute() and target.resolve() == target and logical.resolve() == target
                and stat.S_ISREG(target.stat().st_mode), 'model target differs from approved binding')
        before = (path_identity(logical, follow=False), path_identity(target))
        require(sha(target) == expected_sha, 'fixed model bytes differ')
        require(before == (path_identity(logical, follow=False), path_identity(target))
                and logical.resolve() == target, 'model binding changed during verification')
        identities[name] = (str(target), before)
        files[name] = files[str(target)] = expected_sha

    def check():
        for name, (target, before) in identities.items():
            require(Path(name).resolve() == Path(target) and Path(target).resolve() == Path(target)
                    and before == (path_identity(name, follow=False), path_identity(target)),
                    'verified model path binding drift')
    return files, check
