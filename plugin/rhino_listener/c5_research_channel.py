"""Private one-use research I/O, Python 3.9 stdlib, no Rhino/model execution.

Claims belong in a fixed owner-verified state root, NOT a fresh output folder.
Changing output folders must never erase a claim or permit a consumed slot.
No recursive removal, broad cleanup, overwrite, recovery or replay helper.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import stat
from pathlib import Path

from .c5_research_native import canonical, digest, require

NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
LIMIT = 1024*1024


def private_directory(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, 'absolute non-symlink private directory required')
    fd = os.open(str(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700, 'private directory ownership/mode differs')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _name(name):
    require(isinstance(name,str) and NAME.fullmatch(name) and name not in {'.','..'}, 'single private filename required')
    return name


def _pairs(pairs):
    result = {}
    for key,value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def read_json(directory,name):
    root = private_directory(directory)
    try:
        fd = os.open(_name(name),os.O_RDONLY|os.O_NOFOLLOW,dir_fd=root)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and 0 < info.st_size <= LIMIT, 'private JSON ownership/mode/size differs')
            with os.fdopen(fd,'r',encoding='utf-8',closefd=False) as stream:
                raw = stream.read(LIMIT+1)
            require(len(raw.encode()) <= LIMIT, 'private JSON exceeds bound')
            return json.loads(raw,object_pairs_hook=_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        finally:
            os.close(fd)
    finally:
        os.close(root)


def publish_json(directory,name,value):
    raw = (canonical(value)+'\n').encode()
    require(len(raw) <= LIMIT, 'private JSON exceeds bound')
    root = private_directory(directory)
    temporary = None
    try:
        name = _name(name)
        temporary = 'publish-'+secrets.token_hex(16)+'.tmp'
        fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=root)
        try:
            with os.fdopen(fd,'wb',closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        # Hard-link promotion is atomic and cannot replace an existing name.
        # Consumers never observe a partially written request/response.
        os.link(temporary,name,src_dir_fd=root,dst_dir_fd=root,follow_symlinks=False)
        os.fsync(root)
    finally:
        if temporary is not None:
            try: os.unlink(temporary,dir_fd=root)
            except FileNotFoundError: pass
        os.close(root)


def claim_slot(state_root,slot_sha256,scope):
    """Permanent O_EXCL barrier before any model generation or fixture opening.

    The state root and scope/slot derivation must be in the approved frozen
    runner; caller-supplied fresh paths are not an authorized recovery mode.
    A crash even before subsequent work spends admission, never deletes this.
    """
    require(isinstance(slot_sha256,str) and SHA.fullmatch(slot_sha256), 'canonical slot hash required')
    require(isinstance(scope,dict) and set(scope)=={'stage','task_sha256','route','owner_freeze_sha256'}
            and scope['stage'] in {'development','formal'} and scope['route'] in {'base','lora','native_control'}
            and all(isinstance(scope[k],str) and SHA.fullmatch(scope[k]) for k in ('task_sha256','owner_freeze_sha256')), 'frozen slot scope differs')
    require(slot_sha256 == digest(scope), 'slot key must derive from frozen scope')
    publish_json(state_root,slot_sha256+'.claim.json',{'version':1,'slot_sha256':slot_sha256,'scope':scope,'replay_allowed':False})


def remove_private_key(directory,name):
    """Only the exact already-known key; no folder cleanup or key recreation."""
    root = private_directory(directory)
    try:
        name = _name(name)
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=root)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode)==0o600, 'private key ownership/mode differs')
        finally: os.close(fd)
        os.unlink(name,dir_fd=root)
        os.fsync(root)
        try:
            info = os.stat(name,dir_fd=root,follow_symlinks=False)
        except FileNotFoundError:
            return {'key_removed':True,'actual_absence_checked':True}
        raise ValueError('key still present after unlink')
    finally: os.close(root)
