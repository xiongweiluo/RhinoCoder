"""Opt-in, one-write Rhino Idle session in a disposable headless document.

Only an explicitly signed, consent-consumed envelope can reach the durable
atomic gate. Nothing is registered with the default Listener. The active
document is never a dispatch target, and the temporary key is removed on stop.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import threading
from pathlib import Path

from .candidate_alias_scene import _all_objects, candidate_scene_snapshot
from .candidate_atomic_gate import AtomicGateError, RhinoAtomicGate, rhino_scene_digest
from .candidate_envelope_gate import EnvelopeGateError, verify_and_execute
from .candidate_file_channel import ChannelError, create_private_channel, load_private_secret, read_signed_envelope
from .candidate_readonly_idle_session import ReadonlySessionError, _private_fd, _publish


_CAPTURE = re.compile(r"capture-([0-9a-f]{64})\.json\Z")
_EXECUTE = re.compile(r"execute-([0-9a-f]{64})\.json\Z")
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{24,128}\Z")
REQUEST_BUDGET_VERSION = 2
_SESSION = None


def _pending_requests(names, processed):
    """Bound only unprocessed work; completed request files are audit evidence."""
    return sorted(name for name in names if name not in processed
                  and (_CAPTURE.fullmatch(name) or _EXECUTE.fullmatch(name)))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _content_digest(doc):
    """Content-only check for the active doc; never used as a write gate."""
    import Rhino  # noqa: PLC0415

    options = Rhino.FileIO.SerializationOptions()
    options.WriteUserData = True
    objects = sorted(
        (str(obj.Id), obj.Geometry.ToJSON(options), obj.Attributes.ToJSON(options))
        for obj in _all_objects(doc)
    )
    layers = sorted(
        (str(layer.Id), str(layer.Name), str(layer.ParentLayerId),
         bool(layer.IsVisible), bool(layer.IsLocked), str(layer.Color))
        for layer in doc.Layers if not layer.IsDeleted
    )
    return hashlib.sha256(_canonical({
        "unit": str(doc.ModelUnitSystem), "objects": objects, "layers": layers,
        "absolute_tolerance": float(doc.ModelAbsoluteTolerance),
        "angle_tolerance": float(doc.ModelAngleToleranceRadians),
    }).encode("utf-8")).hexdigest()


def _request(fd, name, *, execute):
    match = (_EXECUTE if execute else _CAPTURE).fullmatch(name)
    if not match:
        raise ReadonlySessionError("invalid_request_name")
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 256):
            raise ReadonlySessionError("unsafe_request")
        raw = os.read(descriptor, 257)
        if len(raw) != info.st_size:
            raise ReadonlySessionError("request_changed")
        value = json.loads(raw, object_pairs_hook=_unique_pairs)
        required = {"version": 1, "nonce": match.group(1)}
        if execute:
            if (not isinstance(value, dict) or set(value) != {"version", "nonce", "request_id"}
                    or value.get("version") != 1 or type(value.get("version")) is not int
                    or value.get("nonce") != match.group(1)
                    or not isinstance(value.get("request_id"), str)
                    or not _REQUEST_ID.fullmatch(value["request_id"])):
                raise ReadonlySessionError("invalid_execute_request")
        elif value != required or type(value.get("version")) is not int:
            raise ReadonlySessionError("invalid_capture_request")
        return match.group(1), value.get("request_id") if execute else None
    finally:
        os.close(descriptor)


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ReadonlySessionError("duplicate_request_key")
        value[key] = item
    return value


def _remove_key(directory):
    channel = Path(directory) / "channel"
    if not channel.exists():
        return
    fd = _private_fd(channel)
    try:
        try:
            os.unlink("handoff.key", dir_fd=fd)
        except FileNotFoundError:
            pass
        os.fsync(fd)
    finally:
        os.close(fd)


class LiveIdleSession:
    def __init__(self, active, fixture, directory):
        self.active_serial = int(active.RuntimeSerialNumber)
        self.active_content_sha256 = _content_digest(active)
        self.fixture = fixture
        self.directory = Path(directory)
        self.thread = threading.get_ident()
        self.gate = RhinoAtomicGate(
            self.directory / "fixture.sqlite3", str(fixture.RuntimeSerialNumber),
            lambda: rhino_scene_digest(fixture), create_ledger=True,
        )
        self.initial_scene = None
        self.processed = set()
        self.attempted = False
        self.failure = None
        self.active = True
        self._callback = self.on_idle

    def _assert_active(self):
        import Rhino  # noqa: PLC0415

        if threading.get_ident() != self.thread or not Rhino.RhinoApp.IsOnMainThread:
            raise ReadonlySessionError("not_rhino_main_thread")
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None or int(doc.RuntimeSerialNumber) != self.active_serial:
            raise ReadonlySessionError("active_document_changed")
        if _content_digest(doc) != self.active_content_sha256:
            raise ReadonlySessionError("active_document_changed")

    def _capture(self):
        self._assert_active()
        scene = candidate_scene_snapshot(self.fixture, self.gate)
        return {"revision": scene["revision"], "scene_sha256": scene["scene_sha256"],
                "summary": scene["summary"]}

    def _dispatch(self, operation, arguments):
        import Rhino  # noqa: PLC0415
        import System  # noqa: PLC0415

        if operation != "create_box":
            raise ReadonlySessionError("unsupported_live_operation")
        if self.attempted is not True:
            raise ReadonlySessionError("dispatch_without_attempt")
        if str(self.fixture.ModelUnitSystem) != "Millimeters":
            raise ReadonlySessionError("unexpected_fixture_unit")
        width, depth, height = (float(arguments[axis]) for axis in ("width", "depth", "height"))
        box = Rhino.Geometry.Box(
            Rhino.Geometry.Plane.WorldXY,
            Rhino.Geometry.Interval(0, width),
            Rhino.Geometry.Interval(0, depth),
            Rhino.Geometry.Interval(0, height),
        )
        brep = box.ToBrep()
        if brep is None or not brep.IsValid:
            raise ReadonlySessionError("invalid_box_geometry")
        object_id = self.fixture.Objects.AddBrep(brep)
        if object_id == System.Guid.Empty:
            raise ReadonlySessionError("rhino_add_failed")
        return {"created": True}

    def _execute(self, request_id):
        self._assert_active()
        if self.attempted:
            return {"status": "rejected", "code": "single_attempt_only"}
        self.attempted = True  # Never retry, including a pre-reservation failure.
        try:
            envelope = read_signed_envelope(self.directory / "channel", request_id)
            payload = envelope["payload"]
            if payload["operation"] != "create_box":
                raise ReadonlySessionError("unsupported_live_operation")
            result = verify_and_execute(
                envelope, secret=load_private_secret(self.directory / "channel"),
                doc=self.fixture, gate=self.gate, dispatch=self._dispatch,
            )
            key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
            row = self.gate.inspect(key)
            objects = _all_objects(self.fixture)
            if (row is None or row["state"] != "done" or len(objects) != 1
                    or not objects[0].Geometry.IsValid):
                raise ReadonlySessionError("postwrite_invariant_failed_manual_review")
            bounds = objects[0].Geometry.GetBoundingBox(True)
            actual = [float(bounds.Max.X - bounds.Min.X),
                      float(bounds.Max.Y - bounds.Min.Y),
                      float(bounds.Max.Z - bounds.Min.Z)]
            expected = [float(payload["arguments"][axis]) for axis in ("width", "depth", "height")]
            if any(abs(a - b) > 1e-7 for a, b in zip(actual, expected)):
                raise ReadonlySessionError("postwrite_dimensions_mismatch_manual_review")
            self._assert_active()
            return {
                "status": "done", "headless_object_count": 1, "box_dimensions_mm": actual,
                "ledger_state": row["state"], "result_sha256": row["result_sha256"],
                "idempotency_key_sha256": result["idempotency_key_sha256"],
                "active_document_unchanged": True,
            }
        except (ChannelError, EnvelopeGateError, AtomicGateError, ReadonlySessionError) as exc:
            code = getattr(exc, "code", str(exc))
            return {"status": "rejected_or_uncertain", "code": code,
                    "ledger_state": self._ledger_state(request_id)}
        except BaseException as exc:
            return {"status": "rejected_or_uncertain", "code": type(exc).__name__,
                    "ledger_state": self._ledger_state(request_id)}

    def _ledger_state(self, request_id):
        try:
            row = self.gate.inspect(hashlib.sha256(request_id.encode("utf-8")).hexdigest())
            return None if row is None else row["state"]
        except Exception:
            return "unknown_manual_review"

    def _finish_deferred_response(self, _fd):
        """Subclasses may hold an execute response until Rhino reaches Idle again."""
        return False

    def _publish_response(self, fd, name, result, *, execute):
        _publish(fd, name, result)

    def on_idle(self, _sender, _args):
        if not self.active or self.failure is not None:
            return
        try:
            import Rhino  # noqa: PLC0415

            if Rhino.RhinoApp.InCommand:
                return
            fd = _private_fd(self.directory)
            try:
                if self.initial_scene is None:
                    self.initial_scene = self._capture()
                    if self.initial_scene["summary"] != {
                        "aliases": [], "object_count": 0, "unit": "Millimeters",
                        "document_key": self.gate.document_key,
                    }:
                        raise ReadonlySessionError("unexpected_fixture")
                    _publish(fd, "initial.json", {"version": 1, "fixture": "empty_headless_mm",
                                                   "scene": self.initial_scene,
                                                   "active_document_content_sha256": self.active_content_sha256})
                if self._finish_deferred_response(fd):
                    return
                pending = _pending_requests(os.listdir(fd), self.processed)
                if len(pending) > 32:
                    raise ReadonlySessionError("too_many_requests")
                for name in pending:
                    execute = bool(_EXECUTE.fullmatch(name))
                    nonce, request_id = _request(fd, name, execute=execute)
                    result = self._execute(request_id) if execute else {
                        "version": 1, "nonce": nonce, "scene": self._capture(),
                    }
                    self._publish_response(
                        fd, ("execute-response-" if execute else "capture-response-")
                        + nonce + ".json", result, execute=execute,
                    )
                    self.processed.add(name)
            finally:
                os.close(fd)
        except BaseException as exc:
            self.failure = type(exc).__name__ + ":" + str(exc)
            self.active = False
            try:
                fd = _private_fd(self.directory)
                try:
                    _publish(fd, "failure.json", {"status": "fail_closed", "reason": self.failure})
                finally:
                    os.close(fd)
            except Exception:
                pass

    def close(self):
        if threading.get_ident() != self.thread:
            raise ReadonlySessionError("not_rhino_main_thread")
        import Rhino  # noqa: PLC0415

        Rhino.RhinoApp.Idle -= self._callback
        self.active = False
        try:
            self.fixture.Dispose()
        finally:
            _remove_key(self.directory)


def start_live_session():
    """Explicit Script Editor entry; snapshot appears on a later Rhino Idle."""
    global _SESSION
    import Rhino  # noqa: PLC0415

    if _SESSION is not None:
        raise ReadonlySessionError("session_already_exists")
    active = Rhino.RhinoDoc.ActiveDoc
    if not Rhino.RhinoApp.IsOnMainThread or active is None:
        raise ReadonlySessionError("main_thread_document_required")
    directory = Path(tempfile.mkdtemp(prefix="rhinocoder-r4-v5-live-"))
    fixture = Rhino.RhinoDoc.CreateHeadless(None)
    if fixture is None or int(fixture.RuntimeSerialNumber) == int(active.RuntimeSerialNumber):
        raise ReadonlySessionError("fixture_unavailable")
    try:
        fixture.ModelUnitSystem = Rhino.UnitSystem.Millimeters
        create_private_channel(directory / "channel")
        session = LiveIdleSession(active, fixture, directory)
        Rhino.RhinoApp.Idle += session._callback
        _SESSION = session
        return str(directory)
    except BaseException:
        try:
            fixture.Dispose()
        finally:
            _remove_key(directory)
        raise


def stop_live_session():
    global _SESSION
    if _SESSION is None:
        raise ReadonlySessionError("session_missing")
    directory = str(_SESSION.directory)
    _SESSION.close()
    _SESSION = None
    return directory
