"""Opt-in Rhino UI-thread scene snapshots after Script Editor returns.

This session only reads a document and writes private audit files. It has no
model input, consent, envelope, dispatch, or geometry-writing method. Requests
are local 0600 files under its 0700 directory; no default Listener route is
registered. The original write-grade digest (including both monotone clocks)
is unchanged.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import tempfile
import threading
from pathlib import Path

from .candidate_alias_scene import candidate_scene_snapshot
from .candidate_atomic_gate import RhinoAtomicGate, rhino_scene_digest


_REQUEST = re.compile(r"request-([0-9a-f]{64})\.json\Z")
_NOFOLLOW = os.O_NOFOLLOW
_DIRECTORY = os.O_DIRECTORY
_SESSION = None


class ReadonlySessionError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ReadonlySessionError("duplicate_request_key")
        value[key] = item
    return value


def _private_fd(path):
    fd = os.open(str(path), os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise ReadonlySessionError("unsafe_session_directory")
    return fd


def _request_id(fd, name):
    match = _REQUEST.fullmatch(name)
    if not match:
        return None
    file_fd = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=fd)
    try:
        info = os.fstat(file_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 160):
            raise ReadonlySessionError("unsafe_request")
        raw = os.read(file_fd, 161)
        if len(raw) != info.st_size:
            raise ReadonlySessionError("request_changed")
        value = json.loads(raw, object_pairs_hook=_unique_pairs)
        if not isinstance(value, dict) or value != {"version": 1, "request_id": match.group(1)}:
            raise ReadonlySessionError("invalid_request")
    finally:
        os.close(file_fd)
    return match.group(1)


def _publish(fd, name, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    temporary = ".publish-" + secrets.token_hex(24)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                             0o600, dir_fd=fd)
        try:
            if os.write(descriptor, raw) != len(raw):
                raise ReadonlySessionError("audit_write_incomplete")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        # The reader treats the final name as ready; the temporary name is
        # deliberately outside every request/response filename pattern.
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


class ReadonlyIdleSession:
    def __init__(self, doc, directory):
        self.doc = doc
        self.directory = Path(directory)
        self.serial = int(doc.RuntimeSerialNumber)
        self.thread = threading.get_ident()
        self.gate = RhinoAtomicGate(
            self.directory / "candidate.sqlite3", str(self.serial),
            lambda: rhino_scene_digest(doc), create_ledger=True,
        )
        self.initial_written = False
        self.processed = set()
        self.active = True
        self.failure = None
        self._callback = self.on_idle

    def _capture(self, request_id):
        import Rhino  # noqa: PLC0415

        if threading.get_ident() != self.thread or not Rhino.RhinoApp.IsOnMainThread:
            raise ReadonlySessionError("not_rhino_main_thread")
        if (Rhino.RhinoDoc.ActiveDoc is None
                or int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber) != self.serial):
            raise ReadonlySessionError("active_document_changed")
        scene = candidate_scene_snapshot(self.doc, self.gate)
        return {
            "version": 1, "request_id": request_id, "document_serial": self.serial,
            "scene": {"revision": scene["revision"], "scene_sha256": scene["scene_sha256"],
                      "summary": scene["summary"]},
            "no_consent": True, "no_dispatch": True,
        }

    def on_idle(self, _sender, _args):
        if not self.active or self.failure is not None:
            return
        try:
            import Rhino  # noqa: PLC0415

            if Rhino.RhinoApp.InCommand:
                return
            fd = _private_fd(self.directory)
            try:
                if not self.initial_written:
                    _publish(fd, "initial.json", self._capture("initial"))
                    self.initial_written = True
                pending = sorted(name for name in os.listdir(fd) if _REQUEST.fullmatch(name))
                if len(pending) > 32:
                    raise ReadonlySessionError("too_many_requests")
                for name in pending:
                    request_id = _request_id(fd, name)
                    if request_id in self.processed:
                        continue
                    _publish(fd, "response-" + request_id + ".json", self._capture(request_id))
                    self.processed.add(request_id)
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


def start_readonly_session():
    """Call once from Script Editor; first snapshot arrives on a later Idle."""
    global _SESSION
    import Rhino  # noqa: PLC0415

    if _SESSION is not None:
        raise ReadonlySessionError("session_already_exists")
    if not Rhino.RhinoApp.IsOnMainThread or Rhino.RhinoDoc.ActiveDoc is None:
        raise ReadonlySessionError("main_thread_document_required")
    directory = Path(tempfile.mkdtemp(prefix="rhinocoder-r4-v5-idle-"))
    session = ReadonlyIdleSession(Rhino.RhinoDoc.ActiveDoc, directory)
    Rhino.RhinoApp.Idle += session._callback
    _SESSION = session
    return str(directory)


def stop_readonly_session():
    global _SESSION
    if _SESSION is None:
        raise ReadonlySessionError("session_missing")
    directory = str(_SESSION.directory)
    _SESSION.close()
    _SESSION = None
    return directory
