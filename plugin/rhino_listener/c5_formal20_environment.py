"""Embedded Python/CLR loaded-origin inventory, no fixtures or model effects.

Run inside Rhino only for a separately authorized environment preflight.
Dynamic/non-file CLR code is rejected rather than claimed byte-frozen.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

from .c5_research_native import require


def verify_project_origins(root, files):
    """Check all loaded project origins, including __main__/private aliases."""
    root = Path(root)
    for module in tuple(sys.modules.values()):
        origin = getattr(module, '__file__', None)
        if not origin or str(origin).startswith('<'): continue
        path = Path(origin)
        if path.suffix == '.pyc': path = Path(importlib.util.source_from_cache(str(path)))
        if not path.is_absolute() or not path.is_relative_to(root): continue
        require(path.resolve() == path and path.is_file(), 'formal project module origin escape')
        name = path.relative_to(root).as_posix()
        require(name in files and hashlib.sha256(path.read_bytes()).hexdigest() == files[name],
            'formal unfrozen loaded project origin')


def loaded_external_files(root):
    import System
    root = Path(root)
    origins = set()
    for module in tuple(sys.modules.values()):
        origin = getattr(module, '__file__', None)
        if not origin or str(origin).startswith('<'): continue
        path = Path(origin)
        require(path.is_absolute(), 'formal embedded unresolved module origin')
        if path.suffix == '.pyc': path = Path(importlib.util.source_from_cache(str(path)))
        path = path.resolve(strict=True)
        if not path.is_relative_to(root): origins.add(path)
    for assembly in System.AppDomain.CurrentDomain.GetAssemblies():
        require(not assembly.IsDynamic and bool(assembly.Location), 'formal unverifiable CLR assembly')
        origins.add(Path(str(assembly.Location)).resolve(strict=True))
    origins.add(Path(sys.executable).resolve(strict=True))
    files = {}
    for path in sorted(origins):
        require(path.is_file(), 'formal embedded runtime origin not regular')
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
        files[str(path)] = h.hexdigest()
    require(files, 'formal empty embedded runtime inventory')
    return files
