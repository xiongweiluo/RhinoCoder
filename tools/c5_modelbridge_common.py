"""Fixed Mac development scope, never executes or claims on import."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_research_provenance import SourceGuard
from training.c5_model_transport import strict_json,LIMIT
from training.c5_modelbridge_runtime import file_sha

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/modelbridge-development-state-20261003-A')
ID='C5DEV-MODELBRIDGE-20261003-A'
SOCKET=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/ssh-24206.control')


def public(path):
    require(path.resolve()==path and path.is_file() and 0 < path.stat().st_size <= LIMIT,'fixed public path/size differs')
    return strict_json(path.read_bytes())


def mac_origins():
    """Read-only actual already-loaded non-project Python/module bytes.

    Call after importing all Mac client/auditor modules. Never enumerates data
    directories, environment variables, credentials or other repositories.
    """
    import importlib.util
    result={}
    for name,module in tuple(sys.modules.items()):
        origin=getattr(module,'__file__',None)
        if not origin or str(origin).startswith('<'):continue
        path=Path(origin)
        # PyTorch creates these in-memory operation namespaces with sentinel
        # __file__ strings; neither represents a loadable filesystem module.
        if name in {'torch.ops','torch.classes'} and str(path) in {'_ops.py','_classes.py'}:continue
        require(path.is_absolute(),'unresolved loaded module origin: '+name)
        if path.suffix=='.pyc':path=Path(importlib.util.source_from_cache(str(path)))
        try:path=path.resolve(strict=True)
        except FileNotFoundError as exc:raise RuntimeError('unresolved loaded module origin: '+name+' '+str(path)) from exc
        if path.is_relative_to(ROOT):continue
        result[str(path)]=file_sha(path)
    return {'python':sys.version,'file_sha256':result,'inventory_sha256':digest(result)}


def scope():
    spec=public(ROOT/'eval/c5/modelbridge-development-spec-20261003.json')
    freeze=public(ROOT/'eval/c5/modelbridge-runtime-freeze-20261003.json')
    require(spec['probe_id']==freeze['probe_id']==ID and spec['execution_ready'] is True
            and freeze['execution_ready'] is True and spec['mac_state_root']==str(STATE)
            and freeze['spec_sha256']==digest(spec),'new complete modelbridge freeze missing')
    require(file_sha(ROOT/'eval/c5/modelbridge-development-spec-20261003.json')==freeze['spec_file_sha256'],
            'actual development spec bytes differ')
    require(all(file_sha(ROOT/name)==sha for name,sha in freeze['fixed_public_files'].items()),
            'actual Mac fixed public configuration bytes differ')
    approval=read_json(STATE,'owner-approval.json')
    require(approval=={'probe_id':ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
                      'runtime_freeze_sha256':digest(freeze),
                      'approval_basis':'direct repository_owner approval of new modelbridge development spec and complete runtime freeze'},
            'new exact development owner approval missing/different')
    project=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],
                        project_prefixes=('agent','training','tools','plugin','data_pipeline'))
    def guard():
        project()
        actual=mac_origins()
        require(actual['python']==freeze['mac_environment']['python']
                and all(freeze['mac_environment']['file_sha256'].get(p)==sha for p,sha in actual['file_sha256'].items())
                and all(file_sha(Path(p))==sha for p,sha in freeze['mac_environment']['file_sha256'].items()),
                'actual Mac import/interpreter bytes differ')
    guard()
    require(len(spec['slot_order'])==8 and len(set(spec['slot_order']))==8
            and set(spec['slot_order'])==set(spec['task_plans'])==set(spec['slot_policies'])
            and all(len(p['steps'])==1 and p['route'] in {'base','lora'} for p in spec['task_plans'].values()),
            'fixed single-step eight-slot scope differs')
    return spec,freeze,approval,guard
