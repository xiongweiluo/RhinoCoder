#! python 3
"""Explicit new owner approval before any actual CLR subscription/canary.

Fixed observation state, no fixture/model/holdout/private-input argument.
This entry is a review artifact until both exact hashes are approved.
"""
import importlib
import importlib.util
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run():
    # Dedicated package aliases prevent using cached project implementations
    # from previously run ScriptEditor tabs or unrelated worktrees.
    prefix='rhino_c5_observer_'+uuid.uuid4().hex
    for suffix,folder in (('',ROOT),('.plugin',ROOT/'plugin'),
        ('.plugin.rhino_listener',ROOT/'plugin/rhino_listener')):
        name=prefix+suffix
        # Namespace containers do not execute unrelated package __init__ code.
        import types
        module=types.ModuleType(name);module.__path__=[str(folder)]
        sys.modules[name]=module
    scope_module=importlib.import_module(prefix+'.plugin.rhino_listener.c5_host_observer_scope')
    core=importlib.import_module(prefix+'.plugin.rhino_listener.c5_host_observer')
    io=importlib.import_module(prefix+'.plugin.rhino_listener.c5_research_channel')
    native=importlib.import_module(prefix+'.plugin.rhino_listener.c5_research_native')
    spec,freeze,approval,guard=scope_module.scope()
    STATE=scope_module.STATE
    io.publish_json(STATE,'observer.started.json',{'probe_id':core.PROBE_ID,'runtime_freeze_sha256':native.digest(freeze),
        'spec_sha256':native.digest(spec),'replay_allowed':False,'model_calls':0,'holdout_rows_read':0})
    journal=core.ObservationJournal(STATE,native.digest(freeze))
    package=sys.modules[prefix+'.plugin.rhino_listener']
    try:
        backend_module=importlib.import_module(prefix+'.plugin.rhino_listener.c5_host_observer_clr')
        backend=backend_module.ClrObserverBackend(spec,ROOT)
        package._HOST_OBSERVER=backend  # Preserve exact delegate for manual reconciliation if removal is uncertain.
    except BaseException as exc:
        journal.append('begin',{'scope':'existing_host_capability_only_not_clean_baseline','no_fixture_model_holdout_or_tool_dispatch':True})
        journal.append('failure',{'error_type':type(exc).__name__,'phase':'backend_construction'})
        journal.append('finished',{'failures':[type(exc).__name__],'unsubscribe_call_completed':False,
            'clean_baseline_claimed':False,'formal_execution_ready':False})
        receipt=journal.seal()
    else:
        receipt=core.run_probe(journal,backend,guard=guard,max_seconds=spec['max_seconds'])
    # Public receipt only. No raw module names, paths, type text, scene or tasks.
    import json
    print(json.dumps(receipt,sort_keys=True))
    return receipt


if __name__=='__main__':run()
