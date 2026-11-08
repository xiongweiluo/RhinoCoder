"""Fake Rhino scope and disposal contracts; never imports a live Rhino."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_native import NativeError
from plugin.rhino_listener.lora_development_native import DevelopmentDoc
from training.c5_formal20_plan import _schemas


def backend(monkeypatch):
    live = {}
    class Docs:
        def FromRuntimeSerialNumber(self, serial): return live.get(serial)
        @property
        def ActiveDoc(self): raise AssertionError('existing user document must never be read')
    doc = SimpleNamespace(RuntimeSerialNumber=42, IsHeadless=True, Path=None, ModelUnitSystem='Millimeters')
    doc.Dispose = lambda: live.pop(42)
    live[42] = doc
    rhino = SimpleNamespace(RhinoDoc=Docs(), RhinoApp=SimpleNamespace(IsOnMainThread=True))
    monkeypatch.setitem(sys.modules, 'Rhino', rhino)
    return DevelopmentDoc(doc, _schemas()), rhino, live


def test_scope_and_close_never_access_existing_active_document(monkeypatch):
    value, rhino, live = backend(monkeypatch)
    monkeypatch.setattr(value, 'readback', lambda: {'public_fixture': True})
    value.guard()
    receipt = value.close()
    assert not live and receipt['fixture_registry_absent'] and not receipt['existing_document_content_read']
    with pytest.raises(NativeError): value.close()


def test_bad_fixture_readback_still_disposes_exact_owned_document(monkeypatch):
    value, rhino, live = backend(monkeypatch)
    def bad(): raise ValueError('synthetic bad geometry')
    monkeypatch.setattr(value, 'readback', bad)
    receipt = value.close()
    assert not live and receipt['readback_error'] == 'ValueError' and receipt['fixture_before_close_native'] is None


@pytest.mark.parametrize('fault', ['path', 'thread', 'headless', 'unit', 'unregistered'])
def test_changed_owned_scope_refuses_dispatch(monkeypatch, fault):
    value, rhino, live = backend(monkeypatch)
    if fault == 'path': value.doc.Path = '/existing/project.3dm'
    if fault == 'thread': rhino.RhinoApp.IsOnMainThread = False
    if fault == 'headless': value.doc.IsHeadless = False
    if fault == 'unit': value.doc.ModelUnitSystem = 'Meters'
    if fault == 'unregistered': live.clear()
    with pytest.raises(NativeError): value.guard()


def test_embedded_modules_are_python39_and_have_no_training_dependency():
    root = Path(__file__).resolve().parents[1] / 'plugin/rhino_listener'
    for name in ['lora_development_native.py', 'lora_development_host.py', 'lora_development_channel.py',
                 'lora_development_admission.py', 'lora_development_session.py']:
        text = (root / name).read_text()
        ast.parse(text, feature_version=(3, 9))
        assert 'from training' not in text and 'import training' not in text
