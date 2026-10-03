"""Synthetic UI-free checks for a partially created fixture; zero Rhino calls."""
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_modelbridge_hub import DevelopmentHub
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
