"""Opt-in Rhino-main-thread write gate; never registered as a Listener route.

Python 3.9 standard library only. A durable reservation is committed *before*
the first possible Rhino mutation; a lost acknowledgement cannot cause replay.
The caller must supply an independently verified one-use human authorization.
This module does not create or verify such an authorization itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path


_KEY = re.compile(r"[A-Za-z0-9_-]{24,128}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class AtomicGateError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def rhino_scene_digest(doc):
    """Read the active document on the UI thread, failing closed on any gap.

    RhinoCommon's archival JSON covers geometry and object attributes; neither
    raw geometry nor object IDs are stored in the ledger or returned here.
    """

    import Rhino  # noqa: PLC0415

    options = Rhino.FileIO.SerializationOptions()
    options.WriteUserData = True
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.NormalObjects = True
    settings.HiddenObjects = True
    settings.LockedObjects = True
    settings.ReferenceObjects = True
    settings.IncludeLights = True
    settings.IncludeGrips = True
    items = []
    for obj in doc.Objects.GetObjectList(settings):
        if obj.Geometry is None or obj.Attributes is None:
            raise AtomicGateError("scene_unreadable")
        items.append((str(obj.Id), obj.Geometry.ToJSON(options), obj.Attributes.ToJSON(options)))
    items.sort(key=lambda item: item[0])
    layers = sorted(
        (str(layer.Id), str(layer.Name), str(layer.ParentLayerId),
         bool(layer.IsVisible), bool(layer.IsLocked), str(layer.Color))
        for layer in doc.Layers if not layer.IsDeleted
    )
    document = (
        str(doc.ModelUnitSystem), float(doc.ModelAbsoluteTolerance),
        float(doc.ModelAngleToleranceRadians),
        # Monotone process-local watermarks also reject add/delete/undo ABA
        # even if the final object serialization becomes identical again.
        int(Rhino.DocObjects.RhinoObject.NextRuntimeSerialNumber),
        int(doc.NextUndoRecordSerialNumber),
    )
    return _hash(_json({"document": document, "objects": items, "layers": layers}))


class RhinoAtomicGate:
    """One live document session, one UI thread, with SQLite at-most-once keys."""

    def __init__(self, path, document_identity, scene_digest, *,
                 create_ledger=False, clock=time.time):
        self.path = Path(path)
        if self.path.is_symlink():
            raise AtomicGateError("unsafe_ledger_path")
        if not isinstance(document_identity, str) or not document_identity:
            raise AtomicGateError("invalid_document")
        self.document_key = _hash(document_identity + ":" + secrets.token_hex(16))
        self._scene_digest = scene_digest
        self._thread = threading.get_ident()
        self.clock = clock
        if create_ledger:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise AtomicGateError("ledger_already_exists") from exc
            os.close(descriptor)
        elif not self.path.is_file():
            raise AtomicGateError("ledger_missing_manual_review")
        with sqlite3.connect(str(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            if create_ledger:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS candidate_scene (
                    document_key TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    scene_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidate_write (
                    idempotency_key TEXT PRIMARY KEY,
                    document_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL,
                    expected_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('reserved','done','uncertain')),
                    result_sha256 TEXT,
                    created_at INTEGER NOT NULL,
                    finished_at INTEGER
                );
                """)
            else:
                found = {row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                if not {"candidate_scene", "candidate_write"} <= found:
                    raise AtomicGateError("ledger_invalid_manual_review")
        os.chmod(str(self.path), 0o600)

    def _assert_thread(self):
        if threading.get_ident() != self._thread:
            raise AtomicGateError("not_rhino_main_thread")

    @contextmanager
    def _tx(self):
        db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _read_scene(self, db):
        digest = self._scene_digest()
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise AtomicGateError("scene_unreadable")
        row = db.execute(
            "SELECT revision,scene_sha256 FROM candidate_scene WHERE document_key=?",
            (self.document_key,),
        ).fetchone()
        if row is None:
            revision = 0
            db.execute("INSERT INTO candidate_scene VALUES(?,?,?)", (self.document_key, revision, digest))
        elif row["scene_sha256"] != digest:
            revision = row["revision"] + 1
            db.execute("UPDATE candidate_scene SET revision=?,scene_sha256=? WHERE document_key=?",
                       (revision, digest, self.document_key))
        else:
            revision = row["revision"]
        return {"document_key": self.document_key, "revision": revision, "scene_sha256": digest}

    def snapshot(self):
        self._assert_thread()
        with self._tx() as db:
            state = self._read_scene(db)
        return state

    def execute(self, key, expected, operation, arguments, dispatch):
        """Reserve before dispatch; duplicates/conflicts/uncertainty never dispatch.

        Must run synchronously on Rhino's UI thread with a trusted dispatcher.
        Does not authorize itself and is deliberately not exposed over HTTP.
        """

        self._assert_thread()
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise AtomicGateError("invalid_key")
        if not isinstance(operation, str) or not operation or not callable(dispatch):
            raise AtomicGateError("invalid_operation")
        try:
            signature = _hash(_json({"operation": operation, "arguments": arguments}))
        except (TypeError, ValueError) as exc:
            raise AtomicGateError("invalid_arguments") from exc
        if not isinstance(expected, dict):
            raise AtomicGateError("invalid_expected_state")
        with self._tx() as db:
            prior = db.execute("SELECT * FROM candidate_write WHERE idempotency_key=?", (key,)).fetchone()
            if prior is not None:
                if (prior["document_key"] != self.document_key or prior["request_sha256"] != signature
                    or prior["expected_revision"] != expected.get("revision")
                    or prior["expected_sha256"] != expected.get("scene_sha256")):
                    raise AtomicGateError("idempotency_conflict")
                raise AtomicGateError("already_reserved_manual_review")
            current = self._read_scene(db)
            drifted = expected != current
            if not drifted:
                db.execute(
                    "INSERT INTO candidate_write VALUES(?,?,?,?,?,?,?,?,?)",
                    (key, self.document_key, signature, current["revision"],
                     current["scene_sha256"], "reserved", None, int(self.clock()), None),
                )
        if drifted:
            raise AtomicGateError("scene_changed")
        # Durable barrier: no Rhino mutation before the transaction commits.
        try:
            result = dispatch(operation, arguments)
            if result is None:
                raise AtomicGateError("empty_result")
            result_digest = _hash(_json(result))
        except BaseException:
            self._mark(key, "uncertain", None)
            raise
        try:
            with self._tx() as db:
                self._read_scene(db)
                db.execute(
                    "UPDATE candidate_write SET state='done',result_sha256=?,finished_at=? "
                    "WHERE idempotency_key=? AND state='reserved'",
                    (result_digest, int(self.clock()), key),
                )
        except BaseException:
            # Reservation remains durable even if post-write bookkeeping fails.
            raise AtomicGateError("execution_uncertain_manual_review")
        return result

    def _mark(self, key, state, result_digest):
        try:
            with self._tx() as db:
                db.execute(
                    "UPDATE candidate_write SET state=?,result_sha256=?,finished_at=? "
                    "WHERE idempotency_key=? AND state='reserved'",
                    (state, result_digest, int(self.clock()), key),
                )
        except Exception:
            pass  # Never remove the durable pre-write reservation.

    def inspect(self, key):
        self._assert_thread()
        db = sqlite3.connect(str(self.path))
        try:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM candidate_write WHERE idempotency_key=?", (key,)).fetchone()
            return dict(row) if row is not None else None
        finally:
            db.close()
