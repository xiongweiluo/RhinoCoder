#! python 3
"""New approved-development ScriptEditor entry. Never reuse native12/R B."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/modelbridge-development-state-20261003-A')
ID='C5DEV-MODELBRIDGE-20261003-A'


def start():
    import Rhino
    for name,module in tuple(sys.modules.items()):
        if (name.startswith(('rhino_research_','rhino_c5_')) or 'candidate_' in name) and getattr(module,'_SESSION',None) is not None:
            raise RuntimeError('another live research session; never reuse')
    namespace='rhino_c5_'+uuid.uuid4().hex
    loader=importlib.util.spec_from_file_location(namespace,ROOT/'plugin/rhino_listener/__init__.py',
                 submodule_search_locations=[str(ROOT/'plugin/rhino_listener')])
    package=importlib.util.module_from_spec(loader)
    sys.modules[namespace]=package;loader.loader.exec_module(package)
    native=importlib.import_module(namespace+'.c5_research_native')
    channel=importlib.import_module(namespace+'.c5_research_channel')
    provenance=importlib.import_module(namespace+'.c5_research_provenance')
    hub_module=importlib.import_module(namespace+'.c5_modelbridge_hub')
    import json
    def public(path):
        native.require(path.resolve()==path and 0 < path.stat().st_size <= 1024*1024,'frozen public path/size differs')
        def pairs(items):
            result={}
            for k,v in items:
                native.require(k not in result,'duplicate frozen JSON key');result[k]=v
            return result
        return json.loads(path.read_text(),object_pairs_hook=pairs,
                          parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite public JSON')))
    spec=public(ROOT/'eval/c5/modelbridge-development-spec-20261003.json')
    freeze=public(ROOT/'eval/c5/modelbridge-runtime-freeze-20261003.json')
    native.require(spec['probe_id']==freeze['probe_id']==ID and spec['execution_ready'] is True
                   and freeze['execution_ready'] is True and freeze['spec_sha256']==native.digest(spec)
                   and spec['mac_state_root']==str(STATE),'new complete development freeze required')
    approval=channel.read_json(STATE,'owner-approval.json')
    native.require(approval=={'probe_id':ID,'actor':'repository_owner','approved':True,
                    'spec_sha256':native.digest(spec),'runtime_freeze_sha256':native.digest(freeze),
                    'approval_basis':'direct repository_owner approval of new modelbridge development spec and complete runtime freeze'},
                    'new exact owner approval missing/different')
    source=provenance.SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],project_prefixes=(namespace,))
    source()
    import hashlib
    native.require(hashlib.sha256((ROOT/'eval/c5/modelbridge-development-spec-20261003.json').read_bytes()).hexdigest()
                   ==freeze['spec_file_sha256'],'actual spec file bytes differ')
    native.require(sys.version_info[:2]==(3,9) and str(Rhino.RhinoApp.Version)==freeze['rhino_version'],
                   'actual embedded Python/Rhino build differs')
    prepared=channel.read_json(STATE,'prepared.json')
    native.require(prepared['runtime_freeze_sha256']==native.digest(freeze),'prepared scope differs')
    active=Rhino.RhinoDoc.ActiveDoc
    native.require(Rhino.RhinoApp.IsOnMainThread and active is not None and not native._all_objects(active),
                   'usable blank active document required; never clear user geometry')
    channel.publish_json(STATE,ID+'.hub-started.claim.json',{'probe_id':ID,
                         'runtime_freeze_sha256':native.digest(freeze),'replay_allowed':False})
    schemas=public(ROOT/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    hub=hub_module.DevelopmentHub(STATE,spec,freeze,schemas,source,active)
    package._SESSION=hub  # Retain actual owner before fallible attach.
    tick=hub._callback
    def callback(sender,event):
        tick(sender,event)
        if hub.stopped:package._SESSION=None
    hub._callback=callback;hub.attach()
    print('C5_MODELBRIDGE_NEW_APPROVED_HUB '+str(STATE))


if __name__=='__main__':start()
