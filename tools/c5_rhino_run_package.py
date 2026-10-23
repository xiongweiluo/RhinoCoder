#! python 3
"""Install once per approved package; no owner/chat readiness relay.

The waiting delegate is removed BEFORE actual arm/baseline. It is reattached
only after that attempt's terminal receipt and observer detachment. It cannot
load a model or expose tasks. A reused or ambiguous arm claim pauses.
"""
import json
import runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def install():
    import Rhino
    import sys,types,uuid,importlib
    prefix='rhino_package_'+uuid.uuid4().hex
    for name,path in ((prefix,ROOT),(prefix+'.plugin',ROOT/'plugin'),
                      (prefix+'.plugin.rhino_listener',ROOT/'plugin/rhino_listener')):
        module=types.ModuleType(name);module.__path__=[str(path)];sys.modules[name]=module
    def load(name):return importlib.import_module(prefix+'.plugin.rhino_listener.'+name)
    protocol=load('c5_formal_reuse_scope');channel=load('c5_research_channel');native=load('c5_research_native')
    MAC_STATE,SPEC_FILE,FREEZE_FILE,MAC_SOURCE,authority=(protocol.MAC_STATE,protocol.SPEC_FILE,
        protocol.FREEZE_FILE,protocol.MAC_SOURCE,protocol.authority)
    read_json,publish_json=channel.read_json,channel.publish_json
    digest,require=native.digest,native.require
    SourceGuard=load('c5_formal_reuse_source_guard').SourceGuard
    spec=json.loads((ROOT/SPEC_FILE).read_bytes());freeze=json.loads((ROOT/FREEZE_FILE).read_bytes())
    grant=read_json(MAC_STATE,'owner-approval.json');authority(spec,freeze,grant)
    require(ROOT==MAC_SOURCE and 'run_package' in spec,'run_package_rhino_fixed_entry')
    source=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],project_prefixes=(prefix,))
    source();waiting=[False]
    def attach():
        require(not waiting[0],'run_package_duplicate_wait_delegate')
        Rhino.RhinoApp.Idle+=tick;waiting[0]=True
    def tick(sender,event):
        if bool(getattr(Rhino.RhinoApp,'InCommand',False)):return
        pointer=MAC_STATE/'rhino-active-attempt.json'
        if not pointer.exists():return
        value=read_json(MAC_STATE,pointer.name)
        require(set(value)=={'attempt','study_id','runtime_sha256','nonce'}
            and value['study_id']==spec['study_id'] and value['runtime_sha256']==digest(freeze)
            and type(value['nonce']) is str and len(value['nonce'])==64
            and all(c in '0123456789abcdef' for c in value['nonce'])
            and type(value['attempt']) is int and 0<=value['attempt']<=spec['run_package']['policy'].get('global_loads_max',5),'run_package_rhino_request_scope')
        if value['attempt']==0:
            Rhino.RhinoApp.Idle-=tick;waiting[0]=False
            publish_json(MAC_STATE,'package-dispatcher-detached-'+value['nonce']+'.json',value)
            return
        state=MAC_STATE/('preload-'+str(value['attempt']))
        # After a terminal receipt, a stale pointer is harmless. Never rearm it.
        if (state/'host-continuity-terminal-receipt.json').exists():return
        if not (state/'formal20.zero-prepared.json').exists():return
        Rhino.RhinoApp.Idle-=tick;waiting[0]=False
        try:
            source();authority(spec,freeze,grant)
            publish_json(state,'package-rhino-arm.claim.json',value)
            result=runpy.run_path(str(ROOT/'tools/c5_rhino_formal_reuse_arm.py'),
                init_globals={'FORMAL_ATTEMPT':value['attempt'],'PACKAGE_NEXT':attach},run_name='__main__')
            result['ENTRY_RETURN_BARRIER'].release_after_entry_return()
        except BaseException as error:
            if not (state/'deferred-baseline.failed.json').exists():
                publish_json(state,'deferred-baseline.failed.json',{'study_id':spec['study_id'],
                    'runtime_freeze_sha256':digest(freeze),'error_type':type(error).__name__,
                    'replay_allowed':False,'manual_reconciliation_required':True})
            print('C5_RUN_PACKAGE_PREPARATION_PAUSED_NO_MODEL_RESTART')
    attach()
    print('C5_RUN_PACKAGE_RHINO_WAITING_PRIVATE_OWNER_ENTRY')
    return tick


if __name__=='__main__':PACKAGE_WAIT_DELEGATE=install()
