#! python 3
"""Explicit Rhino Script Editor entry for versioned research safety lifecycle.

No model invocation, opt-in grant, or automatic geometry write. This is not
the C5 twelve-tool executor. The backend is loaded in a fresh private module
namespace, not retrospectively attributed to already cached candidate code.
"""
from __future__ import annotations

import json
import importlib
import importlib.util
import os
import stat
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for name, module in tuple(sys.modules.items()):
    if ("candidate_" in name or name.startswith("rhino_research_")) and getattr(module, "_SESSION", None) is not None:
        raise RuntimeError("existing_candidate_fixture_must_not_be_reused")

# Rhino embeds Python 3.9; importing training/__init__ would eagerly import
# slots=True dataclasses. A fresh package identity also prevents an earlier
# Script Editor cache from masquerading as current, frozen source bytes.
NAMESPACE = "rhino_research_"+uuid.uuid4().hex
spec = importlib.util.spec_from_file_location(
    NAMESPACE, ROOT/"plugin/rhino_listener/__init__.py",
    submodule_search_locations=[str(ROOT/"plugin/rhino_listener")])
package = importlib.util.module_from_spec(spec)
sys.modules[NAMESPACE] = package
spec.loader.exec_module(package)

import Rhino  # noqa: E402
v6 = importlib.import_module(NAMESPACE+".candidate_v6_live_session")
_content_digest = importlib.import_module(NAMESPACE+".candidate_live_idle_session")._content_digest
private_io = importlib.import_module(NAMESPACE+".candidate_readonly_idle_session")
_private_fd, _publish = private_io._private_fd, private_io._publish
ResearchLifecycle = importlib.import_module(NAMESPACE+".research_lifecycle").ResearchLifecycle
safety = importlib.import_module(NAMESPACE+".research_safety")
require, source_inventory, verify_loaded_sources = safety.require, safety.source_inventory, safety.verify_loaded_sources


def publish(directory, name, value):
    fd = _private_fd(directory)
    try:
        _publish(fd, name, value)
    finally:
        os.close(fd)


def read_request(path):
    parent = _private_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and 0 < info.st_size <= 4096,
                    "unsafe research request")
            raw = os.read(fd, info.st_size+1)
            require(len(raw) == info.st_size, "research request changed")
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate research request key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite request")))


class RhinoBackend:
    def __init__(self, directory):
        require(Rhino.RhinoApp.IsOnMainThread and Rhino.RhinoDoc.ActiveDoc is not None,
                "Rhino main-thread active document required")
        require(v6._SESSION is None, "existing candidate fixture must not be reused")
        self.directory = directory
        self.active_serial = int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber)
        self.inventory = source_inventory(ROOT)
        self.callback = None
        self.guard()
        publish(directory, "source-inventory.json", self.inventory)

    def guard(self):
        require(Rhino.RhinoApp.IsOnMainThread and Rhino.RhinoDoc.ActiveDoc is not None
                and int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber) == self.active_serial,
                "active document identity/main-thread changed")
        verify_loaded_sources(ROOT, self.inventory, tuple(sys.modules.values()))

    def active_digest(self):
        self.guard()
        return _content_digest(Rhino.RhinoDoc.ActiveDoc)

    def open_empty(self):
        return v6.start_v6_session()

    def ready_empty(self, directory):
        session = v6._SESSION
        require(session is not None and str(session.directory) == directory, "fixture identity changed")
        if session.initial_scene is None:
            require(session.failure is None, "fixture initial capture failed")
            return False
        require(not session._capture()["objects"], "research initial fixture is not empty")
        return True

    def close_known(self, directory):
        session = v6._SESSION
        require(session is not None and str(session.directory) == directory and session._settling is None,
                "fixture identity unknown or write still in flight")
        closed = v6.stop_v6_session()
        # The actual channel filename is handoff.key, not the historic
        # archiver's channel/secret test. Both must be absent.
        removed = not any((Path(directory)/"channel"/name).exists()
                          for name in ("handoff.key", "secret"))
        return closed, removed

    def publish_capture(self, capture):
        publish(self.directory, "final-active-%03d.json" % capture["close_seq"], capture)

    def stop(self):
        Rhino.RhinoApp.Idle -= self.callback


class Controller:
    def __init__(self):
        self.directory = Path(tempfile.mkdtemp(prefix="rhinocoder-research-safety-"))
        self.backend = RhinoBackend(self.directory)
        self.lifecycle = ResearchLifecycle(self.backend)
        self.backend.callback = self.on_idle
        self.failed = False
        publish(self.directory, "bootstrap.json", {
            "version": 2, "scope": "isolated_unsaved_headless_mm",
            "initial_active_sha256": self.lifecycle.initial_sha256,
            "formal_quality_claim": False, "model_invocation_allowed": False,
        })
        Rhino.RhinoApp.Idle += self.backend.callback

    def on_idle(self, _sender, _event):
        if self.failed or self.lifecycle.stopped or Rhino.RhinoApp.InCommand:
            return
        seq = self.lifecycle.seq
        try:
            if self.lifecycle.pending is not None:
                result = self.lifecycle.finish_open()
            else:
                path = self.directory/("request-%03d.json" % seq)
                if not path.exists():
                    return
                result = self.lifecycle.handle(read_request(path))
            if result is not None:
                publish(self.directory, "response-%03d.json" % seq, result)
        except BaseException as exc:
            self.failed = True
            if v6._SESSION is not None:
                v6._SESSION.blocked = True
            # Retain known resources for human reconciliation; do not retry an
            # uncertain close or claim a successful stop/cleanup.
            try:
                publish(self.directory, "failure-%03d.json" % seq, {
                    "status": "fail_closed_cleanup_unverified", "reason": type(exc).__name__+":"+str(exc),
                    "known_session_dir": None if self.lifecycle.current is None else self.lifecycle.current[1],
                })
            finally:
                Rhino.RhinoApp.Idle -= self.backend.callback


if __name__ == "__main__":
    controller = Controller()
    print("RESEARCH_SAFETY_BATCH_V2 " + str(controller.directory))
