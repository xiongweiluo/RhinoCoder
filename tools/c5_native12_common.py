"""Fixed native-only development spec/freeze/owner scope; no execution on import."""
from __future__ import annotations

import json
from pathlib import Path

from plugin.rhino_listener.c5_research_native import CORE, digest, require, validate_native_arguments
from plugin.rhino_listener.c5_research_channel import read_json

ROOT = Path(__file__).resolve().parents[1]
ID = 'C5DEV-NATIVE12-20261003-A'
STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/native12-development-state')
OUTPUT = STATE/(ID+'-output')
TASK = 'C5独立未保存headless毫米夹具原生十二工具开发控制；不运行模型，不变更用户文档。'
SPEC_PATH = ROOT/'eval/c5/native12-development-spec-20261003.json'
FREEZE_PATH = ROOT/'eval/c5/native12-runtime-freeze-20261003.json'
APPROVAL_BASIS = 'explicit repository_owner reply approving fixed C5 native twelve-tool development spec and source freeze'


def read_public(path):
    require(path.resolve()==path and path.stat().st_size <= 1024*1024, 'fixed public file path/size differs')
    def pairs(values):
        result = {}
        for key,value in values:
            require(key not in result, 'duplicate frozen JSON key')
            result[key]=value
        return result
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite frozen JSON')))


def fixed_scope():
    spec,freeze = read_public(SPEC_PATH),read_public(FREEZE_PATH)
    schemas=read_public(ROOT/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    require(spec['probe_id']==ID and spec['fixed_state_root']==str(STATE)
            and freeze['probe_id']==ID and freeze['spec_sha256']==digest(spec)
            and freeze['source_inventory_sha256']==digest(freeze['source_files'])
            and freeze['complete_native_probe_runtime'] is True
            and spec['model_calls']==spec['gpu_calls']==spec['formal_holdout_calls']==0
            and spec['signed_write_requests_max']==10 and spec['signed_read_requests_max']==2,
            'fixed native-only spec/freeze differs')
    require(len(spec['steps'])==12 and {s['name'] for s in spec['steps']}==CORE, 'full twelve-tool scope differs')
    for step in spec['steps']: validate_native_arguments(step['name'],step['arguments'],schemas)
    approval=read_json(STATE,'owner-approval.json')
    require(approval.get('approved') is True and approval=={'probe_id':ID,'actor':'repository_owner','approved':True,
                       'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
                       'approval_basis':APPROVAL_BASIS}, 'exact direct human approval evidence missing/differs')
    return spec,freeze,schemas,approval
