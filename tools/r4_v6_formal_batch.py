#! python 3
"""Rhino UI-thread controller for fresh, disposable formal-evaluation fixtures.

Run this once through Rhino's Script > Run. The local evaluator submits one
private request at a time. This never touches the default Listener or active
document geometry; every case receives a new unsaved headless document.
"""

from __future__ import annotations

import json
import importlib
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Rhino  # noqa: E402
import System  # noqa: E402
from plugin.rhino_listener import candidate_v6_live_session as v6  # noqa: E402
from plugin.rhino_listener.candidate_readonly_idle_session import _private_fd, _publish  # noqa: E402
from tools import r4_v6_formal_seed as seed_module  # noqa: E402

_CONTROLLER = None


def _read_private(path):
    fd = _private_fd(path.parent)
    try:
        item = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            info = os.fstat(item)
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.getuid() or info.st_size > 4096):
                raise RuntimeError("unsafe_formal_batch_request")
            raw = os.read(item, info.st_size + 1)
            if len(raw) != info.st_size:
                raise RuntimeError("formal_batch_request_changed")
        finally:
            os.close(item)
    finally:
        os.close(fd)
    return json.loads(raw)


def _publish_private(directory, name, value):
    fd = _private_fd(directory)
    try:
        _publish(fd, name, value)
    finally:
        os.close(fd)


class FormalBatch:
    def __init__(self):
        if not Rhino.RhinoApp.IsOnMainThread or Rhino.RhinoDoc.ActiveDoc is None:
            raise RuntimeError("formal_batch_requires_active_ui_document")
        if v6._SESSION is not None:
            raise RuntimeError("existing_v6_fixture")
        self.directory = Path(tempfile.mkdtemp(prefix="rhinocoder-r4-v6-formal-batch-"))
        self.active = Rhino.RhinoDoc.ActiveDoc
        self.active_serial = int(self.active.RuntimeSerialNumber)
        self.seq = 1
        self.current = None
        self.drifted = False
        self.pending_open = None
        self.stopped = False
        self._callback = self.on_idle
        Rhino.RhinoApp.Idle += self._callback

    def _guard(self):
        if (not Rhino.RhinoApp.IsOnMainThread or Rhino.RhinoDoc.ActiveDoc is None
                or int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber) != self.active_serial):
            raise RuntimeError("formal_batch_active_document_changed")
        if self.current is not None:
            v6._SESSION._assert_active()

    def on_idle(self, _sender, _event):
        if self.stopped:
            return
        try:
            if self.pending_open is not None:
                self._guard()
                case_id, fixture, session_dir = self.pending_open
                if not (Path(session_dir) / "initial.json").exists():
                    return
                if fixture != "empty":
                    seed_module.seed_formal_fixture(fixture)
                self._guard()
                _publish_private(self.directory, "response-%03d.json" % self.seq, {
                    "status": "opened", "case_id": case_id,
                    "session_dir": session_dir, "fixture": fixture,
                })
                self.pending_open = None
                self.seq += 1
                return
            if self.current is not None:
                session_dir = Path(self.current[1])
                requests = [item for item in session_dir.glob("formal-drift-request-*.json")
                            if not (session_dir / item.name.replace("-request-", "-response-")).exists()]
                if requests:
                    if len(requests) != 1 or self.drifted:
                        raise RuntimeError("formal_drift_request_conflict")
                    self._inject_drift(requests[0])
                    return
        except BaseException as exc:
            self._fail(exc)
            return
        request_path = self.directory / ("request-%03d.json" % self.seq)
        if not request_path.exists():
            return
        try:
            self._guard()
            request = _read_private(request_path)
            if (not isinstance(request, dict) or set(request) != {"version", "seq", "action", "fixture", "case_id"}
                    or request["version"] != 1 or request["seq"] != self.seq
                    or request["action"] not in {"open", "close", "stop"}
                    or not isinstance(request["case_id"], str)):
                raise RuntimeError("invalid_formal_batch_request")
            action = request["action"]
            if action == "open":
                if self.current is not None or request["fixture"] not in {
                        "empty", "seeded_one", "seeded_selected", "seeded_two",
                        "read_two_shifted", "read_two_selected", "read_three",
                        "read_one_shifted_selected", "read_four",
                        "read_one_unselected_offset"}:
                    raise RuntimeError("formal_batch_open_conflict")
                session_dir = v6.start_v6_session()
                self.current = (request["case_id"], session_dir)
                self.drifted = False
                self.pending_open = (request["case_id"], request["fixture"], session_dir)
                return
            elif action == "close":
                if self.current is None or self.current[0] != request["case_id"]:
                    raise RuntimeError("formal_batch_close_conflict")
                if request["fixture"] != "none":
                    raise RuntimeError("formal_batch_close_fixture_invalid")
                session_dir = v6.stop_v6_session()
                if session_dir != self.current[1]:
                    raise RuntimeError("formal_batch_close_directory_changed")
                self.current = None
                result = {"status": "closed", "case_id": request["case_id"],
                          "session_dir": session_dir, "key_removed":
                          not (Path(session_dir) / "channel" / "secret").exists()}
            else:
                if self.current is not None or request["fixture"] != "none":
                    raise RuntimeError("formal_batch_stop_conflict")
                result = {"status": "stopped", "case_id": request["case_id"]}
                self.stopped = True
                Rhino.RhinoApp.Idle -= self._callback
            _publish_private(self.directory, "response-%03d.json" % self.seq, result)
            self.seq += 1
        except BaseException as exc:
            self._fail(exc)

    def _inject_drift(self, path):
        self._guard()
        session = v6._SESSION
        if session is None or session.blocked or session._settling is not None:
            raise RuntimeError("formal_drift_session_unavailable")
        request = _read_private(path)
        nonce = path.name[len("formal-drift-request-"):-len(".json")]
        if (not isinstance(request, dict) or set(request) != {
                "version", "case_id", "nonce", "expected_write_attempts"}
                or request["version"] != 1 or request["case_id"] != self.current[0]
                or request["nonce"] != nonce or len(nonce) != 64
                or not all(c in "0123456789abcdef" for c in nonce)
                or type(request["expected_write_attempts"]) is not int
                or request["expected_write_attempts"] not in (0, 1)
                or session.write_attempts != request["expected_write_attempts"]):
            raise RuntimeError("formal_drift_request_invalid")
        before = session._capture()
        if "drift-marker" in before["summary"]["aliases"]:
            raise RuntimeError("formal_drift_marker_exists")
        box = Rhino.Geometry.Box(
            Rhino.Geometry.Plane.WorldXY,
            Rhino.Geometry.Interval(1000, 1001),
            Rhino.Geometry.Interval(1000, 1001),
            Rhino.Geometry.Interval(1000, 1001),
        )
        attributes = session.fixture.CreateDefaultAttributes()
        attributes.Name = "drift-marker"
        if session.fixture.Objects.AddBrep(box.ToBrep(), attributes) == System.Guid.Empty:
            raise RuntimeError("formal_drift_add_failed")
        after = session._capture()
        if (after["revision"] <= before["revision"]
                or after["summary"]["object_count"] != before["summary"]["object_count"] + 1
                or after["scene_sha256"] == before["scene_sha256"]):
            raise RuntimeError("formal_drift_readback_failed")
        self.drifted = True
        _publish_private(Path(self.current[1]), "formal-drift-response-" + nonce + ".json", {
            "version": 1, "nonce": nonce, "case_id": self.current[0],
            "before_scene_sha256": before["scene_sha256"],
            "after_scene_sha256": after["scene_sha256"],
            "active_document_unchanged": True,
            "marker": {"alias": "drift-marker", "min": [1000, 1000, 1000],
                       "max": [1001, 1001, 1001]},
        })

    def _fail(self, exc):
        if v6._SESSION is not None:
            v6._SESSION.blocked = True
        try:
            _publish_private(self.directory, "failure-%03d.json" % self.seq, {
                "status": "fail_closed", "reason": type(exc).__name__ + ":" + str(exc),
            })
        except BaseException:
            pass
        self.stopped = True
        Rhino.RhinoApp.Idle -= self._callback


if __name__ == "__main__":
    if _CONTROLLER is not None:
        raise RuntimeError("formal_batch_already_running")
    if v6._SESSION is not None:
        raise RuntimeError("existing_v6_fixture_must_be_closed")
    seed_module = importlib.reload(seed_module)
    _CONTROLLER = FormalBatch()
    print("R4_V6_FORMAL_BATCH " + str(_CONTROLLER.directory))
