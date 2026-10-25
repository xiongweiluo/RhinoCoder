"""Inert entry guard/owned-child CPU controls; no launcher or model imports."""
import copy
import hashlib
import os
from pathlib import Path

import pytest

from eval.test_c5_reuse_field_preparation import binding,Ops
from plugin.rhino_listener.c5_reuse_runtime_scope import read_bytes,ReuseSourceGuard,fixed_paths,approved_entry
from training.c5_reuse_budget import ReuseBudget
from training.c5_reuse_owned_child import OwnedChildStop,POLICY
from training.c5_reuse_admission import AdmissionRegistry


def resources():
    return {'development_seconds_max':100,'remaining_gpu_seconds':1000,'original_cumulative_seconds_max':57600,
            'prior_cumulative_upper_bound_seconds':100,'generation_cutoff_epoch':10000}


@pytest.mark.parametrize('kind',['elapsed','wall_back','mono_back','cutoff','empty'])
def test_complete_loading_idle_reservation_rejects_clock_or_capacity(kind):
    r=resources(); clock=[100,100]
    if kind=='empty': r['remaining_gpu_seconds']=0
    if kind=='empty':
        with pytest.raises(ValueError): ReuseBudget(r,wall=lambda:clock[0],mono=lambda:clock[1])
        return
    b=ReuseBudget(r,wall=lambda:clock[0],mono=lambda:clock[1])
    assert b.check()==40
    if kind=='elapsed': clock[1]=200
    elif kind=='wall_back': clock[0]=99
    elif kind=='mono_back': clock[1]=99
    else: clock[0]=10000
    with pytest.raises(ValueError): b.check()
    if kind=='mono_back':
        with pytest.raises(ValueError): b.observation()
    else: assert b.observation()['physical_gpu_release_independently_verified'] is None


@pytest.mark.parametrize('kind',['fifo','symlink','hardlink','group','size','valid'])
def test_entry_read_is_nonblocking_and_rejects_type_alias_permission(tmp_path,kind):
    p=tmp_path/'public.json'
    if kind=='fifo': os.mkfifo(p,0o600)
    else: p.write_bytes(b'{}'); p.chmod(0o600)
    if kind=='symlink': q=tmp_path/'alias';q.symlink_to(p);p=q
    elif kind=='hardlink': os.link(p,tmp_path/'other')
    elif kind=='group': p.chmod(0o640)
    if kind=='valid': assert read_bytes(p,private=True)==b'{}'
    else:
        with pytest.raises((ValueError,OSError)): read_bytes(p,limit=1 if kind=='size' else 100,private=True)


def test_wrong_entry_root_refuses_before_reading_any_approval(tmp_path):
    assert fixed_paths('mac')['admission_root']!=fixed_paths('gpu')['admission_root']
    with pytest.raises(ValueError,match='fixed_entry_root'): approved_entry(tmp_path,'gpu')
    assert list(tmp_path.iterdir())==[]


def test_source_guard_rehashes_fixed_bytes_and_rejects_extra_public_inputs(tmp_path):
    p=tmp_path/'tools'/ 'safe.py';p.parent.mkdir();p.write_text('pass\n');p.chmod(0o600)
    files={'tools/safe.py':hashlib.sha256(p.read_bytes()).hexdigest()}
    # Avoid unrelated imported test modules for this isolated source fixture.
    g=ReuseSourceGuard(tmp_path,files);g.prefixes=('cpu_source_fixture',)
    assert len(g())==64
    p.write_text('raise RuntimeError()\n')
    with pytest.raises(ValueError,match='byte_drift'):g()
    with pytest.raises(ValueError):ReuseSourceGuard(tmp_path,{'private/cases.json':'a'*64})


class ChildOps(Ops):
    def __init__(self,expected,*,parent=200,**kwargs): super().__init__(expected,**kwargs);self.parent_pid=parent
    def parent(self,pid):return self.parent_pid


@pytest.mark.parametrize('kind',['success','wrong_parent','identity','unknown_send','durability','already_exited'])
def test_qualified_owned_child_before_loading_one_bounded_stop(tmp_path,kind):
    b=binding(tmp_path)
    identity={'pid':100,'uid':1000,'boot_id':'a'*36,'start_ticks':10,'executable_sha256':'a'*64,
              'argv_sha256':'b'*64,'cwd':b['paths']['source_root']}
    ops=ChildOps(identity,parent=999 if kind=='wrong_parent' else 200,fail=kind=='unknown_send')
    events=[]
    def journal(event,value):
        if kind=='durability' and event=='owned_signal_intent':raise OSError('CPU disk failure')
        events.append((event,copy.deepcopy(value)))
    with AdmissionRegistry(b,create=True) as registry:
        if kind=='wrong_parent':
            with pytest.raises(ValueError):OwnedChildStop(b,POLICY,200,100,ops,journal,registry)
            assert 'send' not in ops.calls;return
        child=OwnedChildStop(b,POLICY,200,100,ops,journal,registry)
        try:
            assert events[0][1]['model_loading_started'] is False
            if kind=='identity':ops.drift=True
            elif kind=='already_exited':ops.exited=lambda fd:True
            if kind in ('identity','unknown_send','durability'):
                with pytest.raises((ValueError,OSError)):child.stop()
            else:
                r=child.stop();assert r['exit_observed'] and r['gpu_release_verified'] is None
            assert ops.calls.count('send')==int(kind in ('success','unknown_send'))
            with pytest.raises(ValueError,match='no_retry'):child.stop()
            assert events[-1][0]=='owned_stop_result'
        finally:child.close()
