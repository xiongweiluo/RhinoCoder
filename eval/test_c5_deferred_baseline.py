"""Real stdlib runpy lifecycle + synthetic Idle; no live Rhino/model/tasks."""
import copy
import runpy
import sys

import pytest

from plugin.rhino_listener.c5_deferred_baseline import DeferredBaselineAdmission
from plugin.rhino_listener.c5_host_assurance_v2 import compare_visible_continuity
from plugin.rhino_listener.c5_research_native import NativeError
from eval.test_c5_host_assurance_v2 import data


def gate(fail=None):
    calls=[]
    def seal():
        calls.append('seal')
        if fail:raise RuntimeError('synthetic seal failure')
    g=DeferredBaselineAdmission(source_guard=lambda:calls.append('source'),seal=seal,
        publish_ready=lambda:calls.append('ready'),mark_failure=lambda e:calls.append('failed:'+e),
        dispatch=lambda *args:calls.append('dispatch'))
    return g,calls


def test_no_operation_before_wrapper_return_or_while_command_active():
    g,calls=gate();g.tick(in_command=False);assert calls==[]
    g.release_after_entry_return();g.tick(in_command=True);assert calls==['source']
    g.tick(in_command=False);assert calls==['source','source','seal','ready']
    g.tick(in_command=False);assert calls[-1]=='dispatch'


def test_failed_seal_never_retries_or_dispatches():
    g,calls=gate(fail=True);g.release_after_entry_return();g.tick(in_command=False)
    g.tick(in_command=False);assert calls.count('seal')==1 and 'dispatch' not in calls
    assert g.state=='failed'
    with pytest.raises(NativeError):g.release_after_entry_return()


def test_failed_release_never_seals_or_retries():
    calls=[]
    def release():
        calls.append('release');raise RuntimeError('synthetic receipt failure')
    g=DeferredBaselineAdmission(source_guard=lambda:None,seal=lambda:calls.append('seal'),
        publish_ready=lambda:calls.append('ready'),mark_failure=lambda e:calls.append('failed'),
        dispatch=lambda *args:calls.append('dispatch'),publish_release=release)
    with pytest.raises(RuntimeError):g.release_after_entry_return()
    g.tick(in_command=False)
    with pytest.raises(NativeError):g.release_after_entry_return()
    assert calls==['release','failed'] and g.state=='failed'


def test_real_runpy_restoration_reproduces_a_without_name_whitelist(tmp_path):
    saved=sys.modules['__main__'];original=getattr(saved,'__file__',None)
    script=tmp_path/'synthetic_wrapper.py'
    script.write_text('import sys\ninside_file=sys.modules["__main__"].__file__\ninside_object=id(sys.modules["__main__"])\n')
    result=runpy.run_path(str(script),run_name='__main__')
    assert sys.modules['__main__'] is saved and result['inside_object']!=id(saved)
    assert result['inside_file']!=original
    baseline,now,events=data()
    baseline['python_origins'].append({'module':'__main__','file':result['inside_file'],'object':str(result['inside_object'])})
    now['python_origins'].append({'module':'__main__','file':original,'object':str(id(saved))})
    with pytest.raises(NativeError):compare_visible_continuity(baseline,now,events)


def test_sealing_after_explicit_runpy_return_sees_restored_module(tmp_path):
    seen=[];saved=sys.modules['__main__']
    g=DeferredBaselineAdmission(source_guard=lambda:None,
        seal=lambda:seen.append(sys.modules['__main__']),publish_ready=lambda:None,
        mark_failure=lambda e:pytest.fail(e),dispatch=lambda *args:None)
    script=tmp_path/'synthetic_queue.py';script.write_text('gate.tick(in_command=False)\n')
    runpy.run_path(str(script),run_name='__main__',init_globals={'gate':g})
    assert seen==[]
    g.release_after_entry_return();g.tick(in_command=False)
    assert seen==[saved]


def test_declared_scheduling_does_not_ignore_later_main_module_changes():
    baseline,now,events=data()
    baseline['python_origins'].append({'module':'__main__','file':'stable','object':'1'})
    now=copy.deepcopy(baseline);now['python_origins'][-1]['object']='2'
    with pytest.raises(NativeError):compare_visible_continuity(baseline,now,events)
