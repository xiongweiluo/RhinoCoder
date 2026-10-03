"""Synthetic UI-free checks for a partially created fixture; zero Rhino calls."""
import sys
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_modelbridge_hub import DevelopmentHub
import plugin.rhino_listener.c5_modelbridge_hub as hub_module
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import NativeError,digest


def stop(hub):
    p={'version':1,'request_id':'synthetic-stop-request-1','action':'stop','slot_id':None,
       'owner_freeze_sha256':digest(hub.freeze),'expires_at':200}
    return {'payload':p,'signature':signature(hub.secret,p)}


def partial_hub():
    hub=object.__new__(DevelopmentHub)
    hub.guard=lambda:None
    hub.freeze={'synthetic':True}
    hub.clock=lambda:100
    hub.secret=b'x'*32
    hub.control_ids=set()
    return hub


def test_hub_cannot_stop_if_new_fixture_was_created_without_child_bridge():
    hub=partial_hub();hub.fixture=object();hub.child=None
    with pytest.raises(NativeError,match='live/unbridged/uncertain'):
        hub.handle(stop(hub))


def test_prior_stopped_child_cannot_attest_new_partially_opened_fixture():
    hub=partial_hub();hub.fixture=object();old_fixture=object()
    hub.child=SimpleNamespace(stopped=True,gate=SimpleNamespace(
        backend=SimpleNamespace(doc=old_fixture,closed=True)))
    with pytest.raises(NativeError,match='live/unbridged/uncertain'):
        hub.handle(stop(hub))


def test_live_current_child_cannot_attest_fixture_close():
    hub=partial_hub();hub.fixture=object()
    hub.child=SimpleNamespace(stopped=False,gate=SimpleNamespace(
        backend=SimpleNamespace(doc=hub.fixture,closed=False)))
    with pytest.raises(NativeError,match='live/unbridged/uncertain'):
        hub.handle(stop(hub))


def test_active_guard_uses_native_content_not_volatile_atomic_watermarks(monkeypatch):
    """Read-only Rhino commands advance global/undo counters without a scene edit."""
    doc=SimpleNamespace(RuntimeSerialNumber=42,object_watermark=707,undo_watermark=11,
                        content='unchanged')
    fake_rhino=SimpleNamespace(RhinoApp=SimpleNamespace(IsOnMainThread=True),
                               RhinoDoc=SimpleNamespace(ActiveDoc=doc))
    monkeypatch.setitem(sys.modules,'Rhino',fake_rhino)
    monkeypatch.setattr(hub_module,'active_content_digest',lambda actual:actual.content)
    monkeypatch.setattr(hub_module,'rhino_scene_digest',lambda _:pytest.fail(
        'the watermark-bearing atomic fixture digest must not guard the active UI'))
    hub=object.__new__(DevelopmentHub)
    hub.source=lambda:None
    hub.active=doc;hub.active_serial=42;hub.initial_active='unchanged'
    hub.guard()
    doc.object_watermark=715;doc.undo_watermark=13
    hub.guard()
    doc.content='changed'
    with pytest.raises(NativeError,match='actual active document changed'):
        hub.guard()
    doc.content='unchanged';fake_rhino.RhinoDoc.ActiveDoc=SimpleNamespace(RuntimeSerialNumber=43)
    with pytest.raises(NativeError,match='actual active document changed'):
        hub.guard()
