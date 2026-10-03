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
from plugin.rhino_listener.c5_research_channel import publish_json


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
    require(prefix.is_absolute() and prefix.resolve()==prefix and Path(sys.prefix).resolve()==prefix,
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
    require(executable.is_relative_to(prefix),'foreign Python executable')
    require(missing_metadata_files==['pip:../../../bin/pip3.13'],
            'unexpected missing package metadata file')
    report = {'python':sys.version,'executable_sha256':file_sha(executable),
              'platform':platform.platform(),'packages':packages,'inventory_sha256':digest(inventory),
              'distribution_file_count':len(inventory),'missing_metadata_files':missing_metadata_files}
    return report,inventory


def verify_loaded_environment(prefix,inventory):
    """Reject loaded foreign/unregistered Python and native extension origins.

    Project modules are independently covered by the project SourceGuard;
    standard-library files are separately fingerprinted by runtime preflight.
    """
    prefix = Path(prefix)
    for module in tuple(sys.modules.values()):
        origin = getattr(module,'__file__',None)
        if not origin: continue  # built-ins have no file.
        path = Path(origin)
        if path.suffix=='.pyc':
            import importlib.util
            path = Path(importlib.util.source_from_cache(str(path)))
        if 'site-packages' not in path.parts: continue
        require(path.is_absolute() and path.resolve()==path and path.is_relative_to(prefix),
                'foreign installed module origin')
        key = path.relative_to(prefix).as_posix()
        require(key in inventory and file_sha(path)==inventory[key],'unregistered/drifted loaded dependency')


def runtime_preflight(prefix):
    env,inventory = installed_environment(prefix)
    # Standard-library Python/lib-dynload bytes are not wheel-owned.
    stdlib = Path(prefix)/'lib'/('python%d.%d'%sys.version_info[:2])
    files = {}
    for p in sorted(stdlib.rglob('*')):
        if 'site-packages' in p.parts or '__pycache__' in p.parts or not p.is_file(): continue
        if p.suffix in {'.py','.so'}: files[p.relative_to(prefix).as_posix()] = file_sha(p)
    require(files,'standard library inventory missing')
    native = {p.relative_to(prefix).as_posix():file_sha(p) for p in sorted((Path(prefix)/'lib').glob('libpython*.so*'))
              if p.is_file() and not p.is_symlink()}
    require(native,'actual libpython binary missing')
    gpu = subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version',
                                  '--format=csv,noheader'],text=True,timeout=15).strip()
    # Changing free-memory/utilization is an observation, not a frozen hash.
    require(len(gpu.splitlines())==1,'single GPU required')
    fields = [x.strip() for x in gpu.split(',')]
    require(len(fields)==5 and fields[0]=='NVIDIA GeForce RTX 3090' and fields[1]=='24576 MiB','approved RTX3090 24GB differs')
    report = {**env,'stdlib_file_count':len(files),'stdlib_inventory_sha256':digest(files),
              'libpython_files':native,'gpu_name':fields[0],'gpu_total_memory':fields[1],'driver_version':fields[4]}
    return {'environment':report,'environment_sha256':digest(report),'gpu_observation':gpu,
            'model_loaded':False,'holdout_rows_read':0,'gpu_generation_calls':0},inventory


class Budget:
    """Wall-clock/GPU reservation includes loading and idle, not only kernels.

    A persistent state must be exclusively claimed before construction by
    the approved lifecycle. Both UTC cutoff and monotonic cap apply; output
    settlement does not permit reopening an exhausted/uncertain run.
    """
    def __init__(self,boundary,*,wall=time.time,mono=time.monotonic):
        required = {'owner_confirmed','provider_expiry_epoch','hard_stop_epoch','export_reserve_seconds',
                    'development_max_seconds','prior_cumulative_seconds','original_cumulative_max_seconds'}
        require(isinstance(boundary,dict) and set(boundary)==required and boundary['owner_confirmed'] is True,
                'new exact owner resource boundary missing')
        require(all(type(boundary[k]) in (int,float) and math.isfinite(boundary[k]) and boundary[k] >= 0
                    for k in required-{'owner_confirmed'}),'finite resource amounts required')
        require(boundary['export_reserve_seconds'] >= 900
                and 0 < boundary['development_max_seconds'] <= 3600
                and boundary['original_cumulative_max_seconds']==16*3600
                and boundary['hard_stop_epoch'] <= boundary['provider_expiry_epoch'],'approved resource limits differ')
        self.wall,self.mono,self.boundary = wall,mono,dict(boundary)
        self.start_mono,self.start_wall = mono(),wall()
        self.cap = min(boundary['development_max_seconds'],16*3600-boundary['prior_cumulative_seconds'],
                       boundary['hard_stop_epoch']-self.start_wall-boundary['export_reserve_seconds'])
        require(self.cap > 0,'hard stop/export reserve or cumulative budget exhausted')
        self.check()

    def check(self):
        elapsed = self.mono()-self.start_mono
        require(elapsed >= 0 and elapsed < self.cap
                and self.wall() < self.boundary['hard_stop_epoch']-self.boundary['export_reserve_seconds'],
                'modelbridge budget stop; no retry')
        return self.cap-elapsed

    def settle(self,state,status):
        elapsed = self.mono()-self.start_mono
        require(elapsed >= 0 and math.isfinite(elapsed),'invalid monotonic settlement')
        value = {'status':status,'elapsed_seconds_including_load_and_idle':elapsed,'cap_seconds':self.cap,
                 'start_epoch':self.start_wall,'stop_epoch':self.wall(),'resource_boundary_sha256':digest(self.boundary),
                 'replay_allowed':False,'formal_holdout_calls':0}
        publish_json(state,'resource-settlement.json',value)
        return value
