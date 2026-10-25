"""Real-file alias/tamper/race checks; no model imports or GPU calls."""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from training import c5_followup_compatible_runtime as check
from plugin.rhino_listener.c5_research_native import NativeError

def setup(tmp_path):
    root=tmp_path/'site-packages';root.mkdir();p=root/'native.so';q=root/'module.py'
    p.write_bytes(b'original compiled bytes');q.write_bytes(b'original Python bytes')
    pins={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (p,q)}
    return root,p,q,pins

def module(path):return SimpleNamespace(__file__=str(path))

def test_aliases_hash_each_distinct_origin_once_and_rehash_next_guard(tmp_path,monkeypatch):
    root,p,q,pins=setup(tmp_path);calls=[];original=check.file_sha
    def counted(path):calls.append(path);return original(path)
    monkeypatch.setattr(check,'file_sha',counted)
    mods=[module(p) for _ in range(32)]+[module(q),SimpleNamespace()]
    check.verify_loaded_environment(root,pins,modules=mods);assert calls==[p,q]
    check.verify_loaded_environment(root,pins,modules=mods);assert calls==[p,q,p,q]

@pytest.mark.parametrize('mode',('changed_bytes','unknown_origin','foreign_origin','symlink_origin'))
def test_unique_byte_and_origin_checks_stay_closed(tmp_path,mode):
    root,p,q,pins=setup(tmp_path);target=p
    if mode=='changed_bytes':
        old=p.stat();p.write_bytes(b'altered compiled bytes!');os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns))
    elif mode=='unknown_origin':target=root/'unknown.so';target.write_bytes(b'unknown')
    elif mode=='foreign_origin':target=tmp_path/'other/site-packages/outside.py';target.parent.mkdir(parents=True);target.write_bytes(b'outside')
    else:target=root/'alias.so';target.symlink_to(p)
    with pytest.raises(NativeError):check.verify_loaded_environment(root,pins,modules=[module(target)])


def test_mutation_during_hash_is_rejected_even_if_old_digest_returned(tmp_path,monkeypatch):
    root,p,q,pins=setup(tmp_path);original=check.file_sha
    def raced(path):
        value=original(path);old=p.stat();p.write_bytes(b'changed during hashing!');os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns));return value
    monkeypatch.setattr(check,'file_sha',raced)
    with pytest.raises(NativeError,match='changed during verification'):
        check.verify_loaded_environment(root,pins,modules=[module(p)])

@pytest.mark.parametrize('next_origin',('alias','other_file'))
def test_mutation_between_aliases_or_before_end_is_rejected(tmp_path,next_origin):
    root,p,q,pins=setup(tmp_path)
    class MutatingOrigin:
        @property
        def __file__(self):
            old=p.stat();p.write_bytes(b'changed after first hash');os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns))
            return str(p if next_origin=='alias' else q)
    with pytest.raises(NativeError,match='changed during verification'):
        check.verify_loaded_environment(root,pins,modules=[module(p),MutatingOrigin()])


def test_cached_bytecode_origins_are_checked_against_source(tmp_path):
    root,p,q,pins=setup(tmp_path);cached=q.parent/'__pycache__'/'module.cpython-311.pyc'
    check.verify_loaded_environment(root,pins,modules=[module(cached),module(q)])
