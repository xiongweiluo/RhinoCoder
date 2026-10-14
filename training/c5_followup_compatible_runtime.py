"""C5 development runtime preflight and accounting; no GPU load on import.

Fixed worker entry supplies the approved root/freeze/owner record. These
helpers never inspect a final run, holdout artifact, training state or corpus.
Actual installed files, not version strings alone, fingerprint dependencies.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import math
import os
import platform
import stat
import subprocess
import sys
import time
from pathlib import Path

from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_followup_profile import PREFIX,PYTHON,GPU_CACHE
NATIVE=Path(PREFIX)
PACKAGE_PREFIX=Path("/data/conda-envs/rhinocoder")


def file_sha(path):
    path = Path(path)
    require(path.resolve()==path and path.is_file(),'non-symlink regular asset required')
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode),'regular asset required')
        value = hashlib.sha256()
        with os.fdopen(fd,'rb',closefd=False) as stream:
            for block in iter(lambda:stream.read(1024*1024),b''): value.update(block)
        return value.hexdigest()
    finally: os.close(fd)


def installed_environment(prefix):
    """Read all distribution-owned non-cache bytes, including shared libraries.

    All paths must stay in the dedicated environment; unknown distributions
    without file metadata or unregistered subsequently loaded modules fail.
    No torch import, CUDA initialization, installation or network fallback.
    """
    prefix = Path(prefix)
    require(prefix.is_absolute() and prefix.resolve()==prefix and prefix==PACKAGE_PREFIX and Path(sys.prefix).resolve()==NATIVE,
            'dedicated environment root differs')
    inventory,packages,missing_metadata_files = {},{},[]
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get('Name','').lower().replace('_','-')
        require(name and name not in packages and dist.files,'unknown/duplicate environment distribution')
        files = {}
        for item in dist.files:
            if str(item).endswith(('.pyc','.pyo')) or '__pycache__' in Path(str(item)).parts: continue
            path = Path(dist.locate_file(item)).absolute()
            # wheel ../../bin entries normalize lexically, never follow symlinks.
            path = Path(os.path.normpath(path))
            # The provider's pip metadata was built by Python 3.13 but this
            # dedicated interpreter is 3.11: a stale, non-loadable pip3.13
            # launcher is the sole observed missing RECORD entry. Retain the
            # anomaly in the frozen report rather than inventing its bytes.
            if name=='pip' and str(item)=='../../../bin/pip3.13' and not path.exists():
                missing_metadata_files.append('pip:'+str(item))
                continue
            require(path.is_relative_to(prefix) and path.resolve()==path,'environment asset path escapes/symlink')
            key = path.relative_to(prefix).as_posix()
            actual = file_sha(path)
            require(key not in inventory or inventory[key]==actual,'overlapping inconsistent package file')
            inventory[key] = actual; files[key] = actual
        require(files,'empty distribution source inventory')
        packages[name] = {'version':dist.version,'file_count':len(files),'inventory_sha256':digest(files)}
    executable = Path(sys.executable).resolve(strict=True)
    require(executable==Path(PYTHON),'foreign compatible Python executable')
    require(missing_metadata_files==['pip:../../../bin/pip3.13'],
            'unexpected missing package metadata file')
    report = {'python':sys.version,'executable_sha256':file_sha(executable),
              'platform':platform.platform(),'packages':packages,'inventory_sha256':digest(inventory),
              'distribution_file_count':len(inventory),'missing_metadata_files':missing_metadata_files}
    return report,inventory


def _file_identity(path):
    value = Path(path).lstat()
    require(stat.S_ISREG(value.st_mode), 'loaded dependency is not a regular file')
    return tuple(getattr(value,key) for key in ('st_dev','st_ino','st_mode','st_nlink',
                 'st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns'))


def verify_loaded_environment(prefix,inventory,*,modules=None):
    """Check each distinct loaded origin's bytes once in THIS invocation.

    Native extensions can publish many module aliases for one large file.
    Every origin is still validated, and every invocation hashes the full
    distinct file set. Metadata checks before/after hashing, at each alias,
    and at the end reject concurrent drift. No cross-checkpoint digest cache.
    modules is a CPU verification hook; the actual loader uses sys.modules.
    """
    prefix = Path(prefix)
    verified = {}
    for module in (tuple(sys.modules.values()) if modules is None else tuple(modules)):
        origin = getattr(module,'__file__',None)
        if not origin: continue
        path = Path(origin)
        if path.suffix=='.pyc':
            import importlib.util
            path = Path(importlib.util.source_from_cache(str(path)))
        if 'site-packages' not in path.parts: continue
        require(path.is_absolute() and path.resolve()==path and path.is_relative_to(prefix),
                'foreign installed module origin')
        key = path.relative_to(prefix).as_posix()
        require(key in inventory, 'unregistered/drifted loaded dependency')
        identity = _file_identity(path)
        if path in verified:
            require(identity==verified[path], 'loaded dependency changed during verification')
            continue
        actual = file_sha(path)
        require(identity==_file_identity(path), 'loaded dependency changed during verification')
        require(actual==inventory[key], 'unregistered/drifted loaded dependency')
        verified[path] = identity
    require(all(_file_identity(path)==identity for path,identity in verified.items()),
            'loaded dependency changed during verification')


def runtime_preflight(prefix):
    env,inventory = installed_environment(prefix)
    # Standard-library Python/lib-dynload bytes are not wheel-owned.
    stdlib = NATIVE/'lib'/('python%d.%d'%sys.version_info[:2])
    files = {}
    for p in sorted(stdlib.rglob('*')):
        if 'site-packages' in p.parts or '__pycache__' in p.parts or not p.is_file(): continue
        if p.suffix in {'.py','.so'}: files[p.relative_to(NATIVE).as_posix()] = file_sha(p)
    require(files,'standard library inventory missing')
    native = {p.relative_to(NATIVE).as_posix():file_sha(p) for p in sorted((NATIVE/'lib').glob('libpython*.a'))
              if p.is_file() and not p.is_symlink()}
    require(native,'actual libpython binary missing')
    gpu = subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version',
                                  '--format=csv,noheader'],text=True,timeout=15).strip()
    # Changing free-memory/utilization is an observation, not a frozen hash.
    require(len(gpu.splitlines())==1,'single GPU required')
    fields = [x.strip() for x in gpu.split(',')]
    require(len(fields)==5 and fields[0]=='NVIDIA GeForce RTX 3090' and fields[1]=='24576 MiB','approved RTX3090 24GB differs')
    native_files=native_inventory()
    links={p.relative_to(NATIVE).as_posix():os.readlink(p) for p in sorted(NATIVE.rglob('*')) if p.is_symlink()}
    linked=native_linked_libraries()
    report = {**env,'native_symlinks':links,'native_linked_libraries':linked,'pycache_prefix':GPU_CACHE,'compatible_prefix':str(NATIVE),'compatible_runtime_files':native_files,'compatible_runtime_inventory_sha256':digest(native_files),'stdlib_file_count':len(files),'stdlib_inventory_sha256':digest(files),
              'libpython_files':native,'gpu_name':fields[0],'gpu_total_memory':fields[1],'driver_version':fields[4]}
    return {'environment':report,'environment_sha256':digest(report),'gpu_observation':gpu,
            'model_loaded':False,'holdout_rows_read':0,'gpu_generation_calls':0},inventory


def native_inventory():
    require(sys.pycache_prefix==GPU_CACHE and not os.path.lexists(GPU_CACHE),'followup_no_unfrozen_bytecode_cache')
    require(Path(sys.prefix).resolve()==NATIVE and Path(sys.executable).resolve()==Path(PYTHON),'followup_native_interpreter')
    files={}
    for p in sorted(NATIVE.rglob('*')):
        if '__pycache__' in p.parts or p.suffix in ('.pyc','.pyo') or not p.is_file() or p.is_symlink():continue
        files[p.relative_to(NATIVE).as_posix()]=file_sha(p)
    require(bool(files) and 'bin/python3.11' in files and 'lib/python3.11/site-packages/c5_frozen_model_packages.pth' in files,'followup_native_inventory')
    return files

def verify_native(plan):
    expected=plan['environment']['gpu']
    require(native_inventory()==expected['compatible_runtime_files']
        and {p.relative_to(NATIVE).as_posix():os.readlink(p) for p in sorted(NATIVE.rglob('*')) if p.is_symlink()}==expected['native_symlinks']
        and native_linked_libraries()==expected['native_linked_libraries'],'followup_compatible_runtime_drift')


def native_linked_libraries():
    result={}
    binaries=[Path(PYTHON)]+sorted((NATIVE/'lib/python3.11/lib-dynload').glob('*.so'))
    for binary in binaries:
        p=subprocess.run(['/usr/bin/ldd',str(binary)],capture_output=True,text=True,check=True,timeout=10)
        for line in p.stdout.splitlines():
            words=line.split()
            require('not found' not in line,'followup_native_unresolved_library')
            target=words[2] if len(words)>=3 and words[1]==' =>' else (words[2] if len(words)>=3 and words[1]=='=>' else words[0] if words else '')
            if target.startswith('/'):
                path=Path(target).resolve(strict=True);result[str(path)]=file_sha(path)
    return result
