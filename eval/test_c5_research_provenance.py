"""Synthetic source/import origin controls, no task or weight reads."""
import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugin.rhino_listener import c5_research_provenance as module
from plugin.rhino_listener.c5_research_native import NativeError, digest


def guard(tmp_path,monkeypatch):
    root=tmp_path/'source'
    root.mkdir()
    path=root/'frozen.py'
    path.write_text('VALUE = 1\n')
    files={'frozen.py':hashlib.sha256(path.read_bytes()).hexdigest()}
    monkeypatch.setattr(module.sys,'modules',{'training.frozen':SimpleNamespace(__file__=str(path))})
    return module.SourceGuard(root,files,digest(files)),path


def test_actual_import_source_and_inventory_hash(tmp_path,monkeypatch):
    value,path=guard(tmp_path,monkeypatch)
    assert value()==digest(value.files)
    path.write_text('VALUE = 2\n')
    with pytest.raises(NativeError): value()


@pytest.mark.parametrize('change',['foreign','unfrozen','namespace','symlink'])
def test_project_dependency_origin_drift_rejected(tmp_path,monkeypatch,change):
    value,path=guard(tmp_path,monkeypatch)
    if change=='foreign': module.sys.modules['training.frozen'].__file__=str(tmp_path/'foreign.py')
    if change=='unfrozen': module.sys.modules['training.other']=SimpleNamespace(__file__=str(value.root/'other.py'))
    if change=='namespace': module.sys.modules['agent']=SimpleNamespace(__path__=[str(tmp_path/'foreign')])
    if change=='symlink':
        original=value.root/'original.py'
        path.rename(original)
        path.symlink_to(original)
    with pytest.raises(NativeError): value()


def test_source_paths_never_accept_holdout_weights_or_traversal(tmp_path):
    for path in ('data/holdout.jsonl','weights/model.safetensors','../outside.py','a/../outside.py'):
        files={path:'a'*64}
        with pytest.raises(NativeError): module.SourceGuard(tmp_path,files,digest(files))
    ast.parse(Path(module.__file__).read_text(),feature_version=(3,9))
