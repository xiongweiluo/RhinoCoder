"""Fake UI events with real private I/O/SQLite; zero Rhino/model/GPU calls."""
import ast
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.test_c5_research_gate import fixture, envelope
from plugin.rhino_listener import c5_research_session as module
from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import NativeError


class Event:
    def __init__(self): self.handlers=[]
    def __iadd__(self,handler): self.handlers.append(handler); return self
    def __isub__(self,handler): self.handlers.remove(handler); return self


def setup(tmp_path,monkeypatch):
    backend,atomic,gate = fixture(tmp_path)
    backend.serial, backend.active_serial, backend.initial_active_sha, backend.closed = 2,1,'e'*64,False
    closes=[]
    def close():
        closes.append(True); backend.closed=True
        return {'fixture_registry_absent':True}
    backend.close=close
    rhino=SimpleNamespace(RhinoApp=SimpleNamespace(IsOnMainThread=True,Idle=Event()),
                          RhinoDoc=SimpleNamespace(ActiveDoc=SimpleNamespace(RuntimeSerialNumber=1)))
    monkeypatch.setitem(sys.modules,'Rhino',rhino)
    monkeypatch.setattr(module,'active_content_digest',lambda _:'e'*64)
    root=tmp_path/'channel'
    root.mkdir(mode=0o700)
    publish_json(root,'handoff.key',{'key_hex':(b'x'*32).hex()})
    source=['f'*64]
    bridge=module.IdleBridge(gate,root,key_name='handoff.key',source_sha256='f'*64,
                             guard_source=lambda:source[0],clock=lambda:100,monotonic=lambda:100)
    bridge.attach()
    return backend,atomic,gate,bridge,rhino,source,closes


def control(baseline_action,**changes):
    p={'version':1,'request_id':secrets.token_urlsafe(24),'task_sha256':'b'*64,'owner_freeze_sha256':'a'*64,
       'action':baseline_action,'expires_at':200}
    p.update(changes)
    return {'kind':'control','envelope':{'payload':p,'signature':signature(b'x'*32,p)}}


def test_actual_file_sequence_settles_without_second_dispatch_then_close_key_stop(tmp_path,monkeypatch):
    backend,atomic,gate,bridge,rhino,source,closes=setup(tmp_path,monkeypatch)
    assert read_json(bridge.directory,'bootstrap.json')['fixture_serial']==2
    publish_json(bridge.directory,'request-0001.json',{'kind':'execute','envelope':envelope(atomic)})
    bridge.tick()
    assert backend.calls==['create_box'] and bridge.pending is not None
    assert read_json(bridge.directory,'execute-0001.json')['status']=='done'
    for _ in range(3): bridge.tick()
    result=read_json(bridge.directory,'response-0001.json')
    assert result['stable_idle_samples']==3 and len(result['settling_samples'])==3
    assert backend.calls==['create_box'] and bridge.seq==2
    publish_json(bridge.directory,'request-0002.json',control('close'))
    bridge.tick()
    assert read_json(bridge.directory,'response-0002.json')['key_absence']['actual_absence_checked']
    assert not (bridge.directory/'handoff.key').exists() and closes==[True]
    publish_json(bridge.directory,'request-0003.json',control('stop'))
    bridge.tick()
    assert read_json(bridge.directory,'response-0003.json')['hook_removed_in_same_callback']
    assert bridge.stopped and rhino.RhinoApp.Idle.handlers==[]
    bridge.tick()
    assert closes==[True] and backend.calls==['create_box']


@pytest.mark.parametrize('change',[{'action':'open'},{'task_sha256':'c'*64},{'owner_freeze_sha256':'c'*64},
                                  {'expires_at':99},{'expires_at':401},{'version':True}])
def test_bad_controls_no_native_write_close_or_key_delete(tmp_path,monkeypatch,change):
    backend,atomic,gate,bridge,rhino,source,closes=setup(tmp_path,monkeypatch)
    with pytest.raises(NativeError): bridge.handle(control('capture',**change))
    assert not backend.calls and not closes and (bridge.directory/'handoff.key').exists()


def test_duplicate_control_source_or_active_drift_denied(tmp_path,monkeypatch):
    backend,atomic,gate,bridge,rhino,source,closes=setup(tmp_path,monkeypatch)
    value=control('capture')
    assert bridge.handle(value)['status']=='captured'
    with pytest.raises(NativeError): bridge.handle(value)
    source[0]='d'*64
    with pytest.raises(NativeError): bridge.handle(control('close'))
    source[0]='f'*64
    rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber=3
    with pytest.raises(NativeError): bridge.handle(control('close'))
    assert not backend.calls and not closes


def test_settling_timeout_preserves_execute_and_blocks_replay_but_allows_signed_cleanup(tmp_path,monkeypatch):
    backend,atomic,gate,bridge,rhino,source,closes=setup(tmp_path,monkeypatch)
    publish_json(bridge.directory,'request-0001.json',{'kind':'execute','envelope':envelope(atomic)})
    bridge.tick()
    bridge.monotonic=lambda:116
    bridge.tick()
    assert read_json(bridge.directory,'response-0001.json')['status']=='failed_no_retry'
    assert read_json(bridge.directory,'execute-0001.json')['ledger_row']['state']=='done'
    assert bridge.blocked and backend.calls==['create_box']
    with pytest.raises(NativeError): bridge.handle({'kind':'execute','envelope':envelope(atomic)})
    assert bridge.handle(control('close'))['status']=='closed' and closes==[True]
    assert bridge.handle(control('stop'))['status']=='stopped'


def test_stop_before_close_and_second_attach_fail_closed(tmp_path,monkeypatch):
    backend,atomic,gate,bridge,rhino,source,closes=setup(tmp_path,monkeypatch)
    with pytest.raises(NativeError): bridge.handle(control('stop'))
    with pytest.raises(NativeError): bridge.attach()
    assert len(rhino.RhinoApp.Idle.handlers)==1 and not closes
    ast.parse(Path(module.__file__).read_text(),feature_version=(3,9))
