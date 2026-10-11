"""Read-only complete public CPU deployment preflight, without target imports.

This byte closure covers the fixed CPU entrypoints, local Python imports,
package initializers and literal public JSON/Markdown file dependencies. The
stdlib/interpreter/OS are explicitly trusted and not a live runtime freeze.
No dynamic imports, third-party imports or arbitrary entrypoints are admitted.
"""
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

ENTRYPOINTS = ('training/c5_reuse_joint.py', 'training/c5_reuse_joint_audit.py',
               'training/c5_reuse_deployment.py', 'tools/check_c5_formal20_reuse_draft.py',
               'tools/audit_c5_final_decision.py', 'tools/check_c5_reuse_deployment.py')
STDLIB = frozenset(('argparse', 'ast', 'fcntl', 'hashlib', 'hmac', 'json', 'os', 'pathlib',
                   're', 'selectors', 'sqlite3', 'stat', 'sys', 'threading', 'time',
                   '__future__', 'dataclasses', 'typing'))
MAX_FILE = 2 * 1024 * 1024


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw):
    require(type(raw) is bytes and len(raw) <= MAX_FILE, 'deployment_json_size')
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'deployment_duplicate_key')
            result[k] = v
        return result
    def constant(_):
        raise ValueError('deployment_nonfinite')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def relative(name):
    require(type(name) is str and bool(re.fullmatch(r'[a-zA-Z0-9_./-]+', name)), 'deployment_name')
    p = PurePosixPath(name)
    if name == 'requirements-training.txt':
        return p.parts
    require(not p.is_absolute() and '..' not in p.parts and str(p) == name
            and p.parts[0] in ('training', 'tools', 'eval', 'docs'), 'deployment_path')
    require((p.suffix == '.py' and p.parts[0] in ('training', 'tools'))
            or (p.suffix == '.json' and name.startswith('eval/c5/'))
            or (p.suffix == '.json' and name.startswith('training/configs/'))
            or (p.suffix == '.md' and p.parts[0] == 'docs'), 'deployment_public_type')
    return p.parts


def read_file(root, name):
    parts = relative(name)
    root = Path(root)
    require(root.is_absolute() and root.resolve() == root, 'deployment_root')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(leaf)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                    and not before.st_mode & 0o022 and before.st_uid == os.getuid()
                    and 0 <= before.st_size <= MAX_FILE, 'deployment_file')
            raw = os.pread(leaf, before.st_size + 1, 0)
            after = os.fstat(leaf)
            named = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')
            require(all(getattr(before, k) == getattr(after, k) == getattr(named, k) for k in fields)
                    and len(raw) == before.st_size, 'deployment_read_race')
            return raw
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def dependencies(name, raw):
    if not name.endswith('.py'):
        return set()
    tree = ast.parse(raw, filename=name)
    found = set()
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            require(node.level == 0, 'deployment_relative_import')
            modules = [node.module]
            if node.module in ('training', 'tools'):
                require(all(a.name != '*' for a in node.names), 'deployment_star_import')
                modules.extend(node.module + '.' + a.name for a in node.names)
        for module in modules:
            require(type(module) is str, 'deployment_import')
            top = module.split('.')[0]
            if top in ('training', 'tools'):
                if module not in ('training', 'tools'):
                    found.add(module.replace('.', '/') + '.py')
                if top == 'training':
                    found.add(top + '/__init__.py')
            else:
                require(top in STDLIB, 'deployment_unfrozen_import')
        if isinstance(node, ast.Call):
            func = node.func
            require(not (isinstance(func, ast.Name) and func.id in ('__import__', 'eval', 'exec'))
                    and not (isinstance(func, ast.Attribute) and func.attr in ('import_module', 'load_module')),
                    'deployment_dynamic_code')
        if isinstance(node, ast.Constant) and type(node.value) is str:
            value = node.value
            if re.fullmatch(r'(eval/c5/[^\s]+\.json|training/configs/[^\s]+\.json|docs/[^\s]+\.md|(?:training|tools)/[^\s]+\.py|requirements-training\.txt)', value):
                relative(value)
                found.add(value)
    return found


def closure(root):
    """Derive dependencies from actual bytes, including verifier dependencies."""
    pending = set(ENTRYPOINTS)
    files = {}
    while pending:
        name = min(pending)
        pending.remove(name)
        if name in files:
            continue
        raw = read_file(root, name)
        files[name] = digest(raw)
        pending.update(dependencies(name, raw) - files.keys())
        require(len(files) <= 128, 'deployment_closure_capacity')
    return dict(sorted(files.items()))


def identity(instance):
    require(type(instance) is str and re.fullmatch(r'cpu-[a-z0-9-]{1,48}', instance), 'deployment_instance')
    return {'protocol': 'c5-reuse-cpu-synthetic-v1',
            'study_id': 'c5-rhino-paired-20-reuse-v1-synthetic-engineering',
            'instance_id': instance, 'execution_kind': 'cpu_synthetic_not_execution_authority'}


def manifest(source, instance, destination):
    """Review material only. Does not copy, mkdir or execute any target file."""
    source, destination = Path(source), Path(destination)
    identity(instance)
    require(destination.is_absolute() and destination.resolve() == destination
            and not destination.exists() and not destination.is_symlink()
            and destination.name == instance + '-source'
            and destination != source and source not in destination.parents, 'deployment_destination_unavailable')
    files = closure(source)
    return {'kind': 'cpu_public_deployment_manifest_not_execution_freeze', 'scope': identity(instance),
            'destination': str(destination), 'entrypoints': list(ENTRYPOINTS), 'files': files,
            'trust_boundary': 'interpreter_stdlib_os_opaque_not_byte_frozen', 'execution_ready': False}


def preflight(root, value, expected_manifest_sha256, instance, *, state_root):
    """Independent source/manifest anchor, exact target inventory and no state.

    Caller retains expected_manifest_sha256 outside the target before staging.
    A self-consistent manifest copied alongside altered files is insufficient.
    """
    require(type(value) is dict and set(value) == {'kind', 'scope', 'destination', 'entrypoints',
            'files', 'trust_boundary', 'execution_ready'}, 'deployment_manifest_schema')
    require(digest(canonical(value)) == expected_manifest_sha256, 'deployment_manifest_anchor')
    root, state_root = Path(root), Path(state_root)
    require(value['kind'] == 'cpu_public_deployment_manifest_not_execution_freeze'
            and canonical(value['scope']) == canonical(identity(instance)) and value['destination'] == str(root)
            and value['entrypoints'] == list(ENTRYPOINTS) and value['execution_ready'] is False
            and value['trust_boundary'] == 'interpreter_stdlib_os_opaque_not_byte_frozen', 'deployment_identity')
    require(root.is_absolute() and root.resolve() == root and root.is_dir()
            and root.name == instance + '-source', 'deployment_root')
    st = root.lstat()
    require(st.st_uid == os.getuid() and not st.st_mode & 0o022, 'deployment_root_mode')
    require(state_root.is_absolute() and state_root.resolve() == state_root
            and not state_root.exists() and not state_root.is_symlink()
            and state_root != root and root not in state_root.parents
            and state_root not in root.parents, 'deployment_state_not_fresh')
    require(state_root.name == instance + '-state', 'deployment_state_identity')
    require(type(value['files']) is dict and 0 < len(value['files']) <= 128, 'deployment_manifest_files')
    expected_dirs = {''}
    for name, expected in value['files'].items():
        parts = relative(name)
        expected_dirs.update('/'.join(parts[:i]) for i in range(1, len(parts)))
        require(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected)
                and digest(read_file(root, name)) == expected, 'deployment_byte_drift')
    # Walk only the chosen deployment fixture; never inventory the workspace.
    actual_files, actual_dirs = set(), {''}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            st = path.lstat()
            require(not stat.S_ISLNK(st.st_mode) and st.st_uid == os.getuid()
                    and not st.st_mode & 0o022, 'deployment_inventory_type')
            rel = path.relative_to(root).as_posix()
            if name in dirs:
                actual_dirs.add(rel)
            else:
                require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'deployment_inventory_type')
                actual_files.add(rel)
    require(actual_files == set(value['files']) and actual_dirs == expected_dirs, 'deployment_extra_or_missing')
    require(closure(root) == value['files'], 'deployment_transitive_closure')
    return {'status': 'cpu_actual_deployment_root_bytes_verified_not_live_freeze',
            'manifest_sha256': expected_manifest_sha256, 'files_verified': len(actual_files),
            'state_absent': True, 'target_code_executed': False, 'execution_ready': False}


def stage_cpu_public(source, value, expected_manifest_sha256, instance, *, state_root):
    """O_EXCL staging into a new local CPU directory, never a live deployment.

    No overwrite, repair, cleanup or retry on partial failure. Output remains
    reviewable and incomplete. No file from the staged root is executed.
    """
    require(type(value) is dict and digest(canonical(value)) == expected_manifest_sha256,
            'deployment_manifest_anchor')
    destination = Path(value['destination'])
    require(manifest(source, instance, destination) == value, 'deployment_source_drift')
    state_root = Path(state_root)
    require(state_root.is_absolute() and state_root.resolve() == state_root
            and state_root.name == instance + '-state' and not state_root.exists()
            and not state_root.is_symlink() and state_root != destination
            and destination not in state_root.parents and state_root not in destination.parents,
            'deployment_state_not_fresh')
    destination.mkdir(mode=0o700)
    directories = {destination}
    for name, expected in value['files'].items():
        raw = read_file(source, name)
        require(digest(raw) == expected, 'deployment_source_drift')
        target = destination / name
        # All parents are underneath the newly created, owned CPU directory.
        for parent in reversed(target.parents):
            if parent == destination or destination not in parent.parents:
                continue
            if parent not in directories:
                parent.mkdir(mode=0o700)
                directories.add(parent)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            offset = 0
            while offset < len(raw):
                n = os.write(fd, raw[offset:])
                require(n > 0, 'deployment_write')
                offset += n
            os.fsync(fd)
        finally:
            os.close(fd)
    for directory in directories:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return preflight(destination, value, expected_manifest_sha256, instance, state_root=state_root)
