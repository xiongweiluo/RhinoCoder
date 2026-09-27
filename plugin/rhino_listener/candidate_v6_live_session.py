"""Opt-in multi-step headless Rhino fixture for the isolated R v6 candidate.

Every write still needs a distinct consumed consent, signed envelope, exact
live scene, and durable RhinoAtomicGate reservation. A failed or uncertain
write blocks all later writes in this session; no automatic replay exists.
The active user document remains a read-only identity/content guard.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
import time
from pathlib import Path

from .candidate_alias_scene import _all_objects
from .candidate_atomic_gate import AtomicGateError
from .candidate_envelope_gate import EnvelopeGateError, verify_and_execute
from .candidate_file_channel import ChannelError, create_private_channel, load_private_secret, read_signed_envelope
from .candidate_live_idle_session import LiveIdleSession, ReadonlySessionError, _content_digest, _remove_key
from .candidate_readonly_idle_session import _private_fd, _publish


V6_LIVE_VERSION = 2
MAX_WRITES = 6
_SESSION = None


def _bounds(obj):
    if obj.Geometry is None or not obj.Geometry.IsValid:
        raise ReadonlySessionError("invalid_fixture_geometry")
    box = obj.Geometry.GetBoundingBox(True)
    if not box.IsValid:
        raise ReadonlySessionError("invalid_fixture_bounds")
    return {
        "min": [float(box.Min.X), float(box.Min.Y), float(box.Min.Z)],
        "max": [float(box.Max.X), float(box.Max.Y), float(box.Max.Z)],
    }


def _near(values, expected):
    return len(values) == len(expected) and all(
        math.isfinite(a) and math.isfinite(b) and abs(a - b) <= 1e-7
        for a, b in zip(values, expected)
    )


def verify_postwrite(operation, arguments, before, after):
    """Pure geometry assertion shared by Rhino and the independent Mac verifier."""
    prior = {entry["alias"]: entry for entry in before["objects"]}
    current = {entry["alias"]: entry for entry in after["objects"]}
    if operation == "create_box":
        alias = "box-" + str(len(prior) + 1)
        if set(current) != set(prior) | {alias} or any(current[name] != prior[name] for name in prior):
            raise ReadonlySessionError("postwrite_object_set_mismatch_manual_review")
        box = current[alias]
        if (not _near(box["min"], [0.0, 0.0, 0.0])
                or not _near(box["max"], [float(arguments[axis]) for axis in ("width", "depth", "height")])):
            raise ReadonlySessionError("postwrite_dimensions_mismatch_manual_review")
        return alias
    if operation != "move_object":
        raise ReadonlySessionError("unsupported_live_operation")
    alias = arguments["alias"]
    if set(current) != set(prior) or alias not in prior:
        raise ReadonlySessionError("postmove_object_set_mismatch_manual_review")
    if any(current[name] != prior[name] for name in prior if name != alias):
        raise ReadonlySessionError("postmove_other_object_changed_manual_review")
    vector = [float(arguments[axis]) for axis in ("translate_x", "translate_y", "translate_z")]
    for endpoint in ("min", "max"):
        expected = [value + offset for value, offset in zip(prior[alias][endpoint], vector)]
        if not _near(current[alias][endpoint], expected):
            raise ReadonlySessionError("postmove_bounds_mismatch_manual_review")
    return alias


class V6LiveSession(LiveIdleSession):
    def __init__(self, active, fixture, directory):
        super().__init__(active, fixture, directory)
        self.attempted_ids = set()
        self.write_attempts = 0
        self.blocked = False
        self._settling = None
        self.component_audit_enabled = True
        self.component_sample_index = 0

    def _scene_components(self):
        """Diagnostic only; never substitutes for the existing scene digest."""
        import Rhino  # noqa: PLC0415

        return {
            "global_next_object_serial": int(Rhino.DocObjects.RhinoObject.NextRuntimeSerialNumber),
            "fixture_next_undo_serial": int(self.fixture.NextUndoRecordSerialNumber),
            "fixture_content_sha256": _content_digest(self.fixture),
            "fixture_document_serial": int(self.fixture.RuntimeSerialNumber),
        }

    def _audit_components(self, before, after, first, second):
        if self.component_sample_index >= 2048:
            raise ReadonlySessionError("too_many_component_samples")
        self.component_sample_index += 1
        fd = _private_fd(self.directory)
        try:
            _publish(fd, "scene-component-%04d.json" % self.component_sample_index, {
                "version": 1, "sample": self.component_sample_index,
                "before": before, "after": after,
                "first_scene_sha256": first["scene_sha256"],
                "second_scene_sha256": second["scene_sha256"],
                "first_revision": first["revision"], "second_revision": second["revision"],
            })
        finally:
            os.close(fd)

    def _publish_response(self, fd, name, result, *, execute):
        if execute and result.get("status") == "awaiting_postwrite_idle":
            if self._settling is None or self._settling["response_name"] is not None:
                raise ReadonlySessionError("invalid_postwrite_state")
            self._settling["response_name"] = name
            return
        _publish(fd, name, result)

    def _finish_deferred_response(self, fd):
        pending = self._settling
        if pending is None:
            return False
        if pending["response_name"] is None or time.monotonic() > pending["deadline"]:
            raise ReadonlySessionError("postwrite_settle_timeout_manual_review")
        current = self._capture()
        alias = self._verify_postwrite(
            pending["operation"], pending["arguments"], pending["before"], current,
        )
        if (alias != pending["alias"]
                or current["revision"] <= pending["before"]["revision"]
                or self._ledger_state(pending["request_id"]) != "done"):
            raise ReadonlySessionError("postwrite_settle_mismatch_manual_review")
        digest = current["scene_sha256"]
        pending["idle_captures"] += 1
        if digest == pending["last_digest"]:
            pending["stable_captures"] += 1
        else:
            pending["scene_changes"] += int(pending["last_digest"] is not None)
            pending["last_digest"] = digest
            pending["stable_captures"] = 0
        if pending["stable_captures"] < 2:
            return True
        self._assert_active()
        _publish(fd, pending["response_name"], {
            **pending["response"],
            "after_scene_sha256": digest,
            "headless_object_count": current["summary"]["object_count"],
            "postwrite_idle_captures": pending["idle_captures"],
            "postwrite_scene_changes": pending["scene_changes"],
        })
        self._settling = None
        return True

    def _capture(self):
        audit = getattr(self, "component_audit_enabled", False)
        components_before = self._scene_components() if audit else None
        scene = super()._capture()
        objects = _all_objects(self.fixture)
        entries = []
        for obj in objects:
            alias = obj.Attributes.Name if obj.Attributes is not None else None
            if not isinstance(alias, str) or not alias or alias in {entry["alias"] for entry in entries}:
                raise ReadonlySessionError("fixture_alias_not_unique")
            entries.append({"alias": alias, **_bounds(obj)})
        selected = []
        for obj in self.fixture.Objects.GetSelectedObjects(False, False):
            alias = obj.Attributes.Name if obj.Attributes is not None else None
            if alias not in {entry["alias"] for entry in entries}:
                raise ReadonlySessionError("selected_alias_unavailable")
            selected.append(alias)
        second = super()._capture()
        if audit:
            self._audit_components(components_before, self._scene_components(), scene, second)
        if second != scene:
            raise ReadonlySessionError("scene_changed_during_capture")
        if sorted(entry["alias"] for entry in entries) != sorted(scene["summary"]["aliases"]):
            raise ReadonlySessionError("fixture_summary_mismatch")
        return {**scene, "objects": sorted(entries, key=lambda item: item["alias"]),
                "selected_aliases": sorted(selected)}

    def _dispatch(self, operation, arguments):
        import Rhino  # noqa: PLC0415
        import System  # noqa: PLC0415

        if self.write_attempts <= 0 or self.blocked:
            raise ReadonlySessionError("dispatch_without_authorized_attempt")
        if str(self.fixture.ModelUnitSystem) != "Millimeters":
            raise ReadonlySessionError("unexpected_fixture_unit")
        if operation == "create_box":
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
            alias = "box-" + str(len(_all_objects(self.fixture)) + 1)
            attributes = self.fixture.CreateDefaultAttributes()
            attributes.Name = alias
            object_id = self.fixture.Objects.AddBrep(brep, attributes)
            if object_id == System.Guid.Empty:
                raise ReadonlySessionError("rhino_add_failed")
            return {"created": True, "alias": alias}
        if operation == "move_object":
            target_id = arguments["object_id"]
            vector = arguments["translation"]
            if not isinstance(vector, list) or len(vector) != 3:
                raise ReadonlySessionError("invalid_translation")
            transform = Rhino.Geometry.Transform.Translation(
                float(vector[0]), float(vector[1]), float(vector[2]),
            )
            moved_id = self.fixture.Objects.Transform(target_id, transform, True)
            if moved_id == System.Guid.Empty:
                raise ReadonlySessionError("rhino_move_failed")
            return {"moved": True}
        raise ReadonlySessionError("unsupported_live_operation")

    def _verify_postwrite(self, operation, arguments, before, after):
        return verify_postwrite(operation, arguments, before, after)

    def _execute(self, request_id):
        self._assert_active()
        if request_id in self.attempted_ids:
            return {"status": "rejected", "code": "single_attempt_only"}
        if self.blocked or self.write_attempts >= MAX_WRITES:
            return {"status": "rejected", "code": "session_blocked_or_full"}
        if self._settling is not None:
            return {"status": "rejected", "code": "postwrite_not_settled"}
        self.attempted_ids.add(request_id)
        self.write_attempts += 1
        try:
            before = self._capture()
            envelope = read_signed_envelope(self.directory / "channel", request_id)
            payload = envelope["payload"]
            operation, arguments = payload["operation"], payload["arguments"]
            if operation not in {"create_box", "move_object"}:
                raise ReadonlySessionError("unsupported_live_operation")
            if (payload["scene_revision"] != before["revision"]
                    or payload["scene_sha256"] != before["scene_sha256"]
                    or payload["document_key"] != before["summary"]["document_key"]):
                raise ReadonlySessionError("scene_changed")
            result = verify_and_execute(
                envelope, secret=load_private_secret(self.directory / "channel"),
                doc=self.fixture, gate=self.gate, dispatch=self._dispatch,
            )
            row = self.gate.inspect(hashlib.sha256(request_id.encode("utf-8")).hexdigest())
            if row is None or row["state"] != "done":
                raise ReadonlySessionError("postwrite_invariant_failed_manual_review")
            self._assert_active()
            alias = ("box-" + str(len(before["objects"]) + 1)
                     if operation == "create_box" else arguments["alias"])
            provisional = {
                "status": "done", "operation": operation, "alias": alias,
                "ledger_state": "done", "result_sha256": row["result_sha256"],
                "idempotency_key_sha256": result["idempotency_key_sha256"],
                "before_scene_sha256": before["scene_sha256"],
                "active_document_unchanged": True,
            }
            self._settling = {
                "request_id": request_id, "response_name": None,
                "operation": operation, "arguments": arguments, "before": before,
                "alias": alias, "response": provisional,
                "deadline": time.monotonic() + 20,
                "last_digest": None, "stable_captures": 0,
                "idle_captures": 0, "scene_changes": 0,
            }
            return {"status": "awaiting_postwrite_idle"}
        except (ChannelError, EnvelopeGateError, AtomicGateError, ReadonlySessionError) as exc:
            self.blocked = True
            return {"status": "rejected_or_uncertain", "code": getattr(exc, "code", str(exc)),
                    "ledger_state": self._ledger_state(request_id)}
        except BaseException as exc:
            self.blocked = True
            return {"status": "rejected_or_uncertain", "code": type(exc).__name__,
                    "ledger_state": self._ledger_state(request_id)}


def start_v6_session():
    global _SESSION
    import Rhino  # noqa: PLC0415

    from . import candidate_live_idle_session as v5

    if _SESSION is not None or v5._SESSION is not None:
        raise ReadonlySessionError("session_already_exists")
    active = Rhino.RhinoDoc.ActiveDoc
    if not Rhino.RhinoApp.IsOnMainThread or active is None:
        raise ReadonlySessionError("main_thread_document_required")
    directory = Path(tempfile.mkdtemp(prefix="rhinocoder-r4-v6-live-"))
    fixture = Rhino.RhinoDoc.CreateHeadless(None)
    if fixture is None or int(fixture.RuntimeSerialNumber) == int(active.RuntimeSerialNumber):
        raise ReadonlySessionError("fixture_unavailable")
    try:
        fixture.ModelUnitSystem = Rhino.UnitSystem.Millimeters
        create_private_channel(directory / "channel")
        session = V6LiveSession(active, fixture, directory)
        Rhino.RhinoApp.Idle += session._callback
        _SESSION = session
        return str(directory)
    except BaseException:
        try:
            fixture.Dispose()
        finally:
            _remove_key(directory)
        raise


def stop_v6_session():
    global _SESSION
    if _SESSION is None:
        raise ReadonlySessionError("session_missing")
    directory = str(_SESSION.directory)
    _SESSION.close()
    _SESSION = None
    return directory
