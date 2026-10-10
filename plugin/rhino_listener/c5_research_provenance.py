"""Strict source/import byte guard; no runtime start, weights or task access.

The full manifest, entry script, installed dependency/environment and model
assets must still be frozen/approved by the lifecycle runner. This guard does
not invent that manifest or turn a source label into owner approval.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import sys
from pathlib import Path, PurePosixPath

from .c5_research_native import digest, require

PREFIXES = ('plugin','training','agent','tools')


class SourceGuard:
    def __init__(self, root, files, expected_inventory_sha256, *, project_prefixes=PREFIXES):
        self.root = Path(root)
        require(self.root.is_absolute() and self.root.resolve()==self.root, 'canonical source root required')
        require(isinstance(files,dict) and 0 < len(files) <= 512
                and digest(files)==expected_inventory_sha256, 'approved source inventory differs')
        self.files = dict(files)
        self.expected = expected_inventory_sha256
        require(isinstance(project_prefixes,(tuple,list)) and 0 < len(project_prefixes) <= 8
                and all(isinstance(p,str) and p.isidentifier() for p in project_prefixes), 'frozen private namespace required')
        self.prefixes = tuple(project_prefixes)
        for name, sha in files.items():
            p = PurePosixPath(name)
            require(isinstance(name,str) and not p.is_absolute() and p.as_posix()==name
                    and all(part not in {'.','..'} for part in p.parts)
                    and (name.endswith('.py') or name in {'eval/c5/rhino-runtime-schema-v1.json',
                         'eval/c5/native12-development-spec-20261003.json'})
                    and isinstance(sha,str) and len(sha)==64 and all(c in '0123456789abcdef' for c in sha),
                    'source inventory path/hash differs')

    def _file(self, name):
        path = self.root/name
        require(path.resolve()==path and path.is_relative_to(self.root), 'symlink/source escape rejected')
        fd = os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 2*1024*1024, 'source file type/size differs')
            sha = hashlib.sha256()
            with os.fdopen(fd,'rb',closefd=False) as stream:
                for chunk in iter(lambda:stream.read(65536),b''): sha.update(chunk)
            return sha.hexdigest()
        finally: os.close(fd)

    def __call__(self):
        for name,sha in self.files.items():
            require(self._file(name)==sha, 'actual source bytes drift: '+name)
        for name,module in list(sys.modules.items()):
            if name.split('.')[0] not in self.prefixes: continue
            origin = getattr(module,'__file__',None)
            # Namespace packages must not silently add foreign search roots.
            if origin is None:
                paths = getattr(module,'__path__',())
                require(paths and all(Path(p).resolve().is_relative_to(self.root) for p in paths), 'foreign namespace module: '+name)
                continue
            origin = Path(origin)
            if origin.suffix=='.pyc': origin = Path(importlib.util.source_from_cache(str(origin)))
            require(origin.is_absolute() and origin.resolve()==origin and origin.is_relative_to(self.root), 'foreign loaded project module: '+name)
            relative = origin.relative_to(self.root).as_posix()
            require(relative in self.files and self._file(relative)==self.files[relative], 'unfrozen loaded dependency: '+name)
        return self.expected
