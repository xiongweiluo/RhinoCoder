#! python 3
"""Seed only the current disposable v6 headless document for formal cases.

Run from Rhino Script Editor after a fresh v6 start and before any model call.
This is test setup, never a model-issued write or a product Listener action.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import Rhino  # noqa: E402
import System  # noqa: E402
from plugin.rhino_listener import candidate_v6_live_session as v6  # noqa: E402
from plugin.rhino_listener.candidate_alias_scene import _all_objects  # noqa: E402
from plugin.rhino_listener.candidate_readonly_idle_session import _private_fd, _publish  # noqa: E402


def seed_formal_fixture(name: str, fixture_path: Path | None = None) -> str:
    fixture_path = fixture_path or ROOT / "eval/r4_v6_formal_fixtures.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))["fixtures"]
    if name == "empty" or name not in fixtures:
        raise RuntimeError("unsupported_formal_fixture")
    session = v6._SESSION
    if (session is None or not session.active or session.blocked
            or session.write_attempts != 0 or session._settling is not None
            or not Rhino.RhinoApp.IsOnMainThread):
        raise RuntimeError("formal_fixture_not_pristine")
    session._assert_active()
    before = session._capture()
    if (before["objects"] or before["selected_aliases"]
            or before["summary"]["object_count"] != 0
            or before["summary"]["unit"] != "Millimeters"
            or (session.directory / "formal-seed-receipt.json").exists()
            or list(session.directory.glob("execute-*.json"))):
        raise RuntimeError("formal_fixture_not_empty")
    with sqlite3.connect(session.directory / "fixture.sqlite3") as db:
        if db.execute("SELECT COUNT(*) FROM candidate_write").fetchone()[0] != 0:
            raise RuntimeError("formal_fixture_ledger_not_empty")
    expected = fixtures[name]
    if (not 1 <= len(expected["objects"]) <= 4
            or [item["alias"] for item in expected["objects"]] != [
                "box-" + str(index) for index in range(1, len(expected["objects"]) + 1)]
            or not set(expected["selected_aliases"]) <= {
                item["alias"] for item in expected["objects"]}):
        raise RuntimeError("invalid_formal_fixture_spec")
    inserted = []
    try:
        for item in expected["objects"]:
            low, high = item["min"], item["max"]
            box = Rhino.Geometry.Box(
                Rhino.Geometry.Plane.WorldXY,
                Rhino.Geometry.Interval(low[0], high[0]),
                Rhino.Geometry.Interval(low[1], high[1]),
                Rhino.Geometry.Interval(low[2], high[2]),
            )
            brep = box.ToBrep()
            if brep is None or not brep.IsValid:
                raise RuntimeError("formal_seed_invalid_geometry")
            attributes = session.fixture.CreateDefaultAttributes()
            attributes.Name = item["alias"]
            object_id = session.fixture.Objects.AddBrep(brep, attributes)
            if object_id == System.Guid.Empty:
                raise RuntimeError("formal_seed_add_failed")
            inserted.append(object_id)
        if expected["selected_aliases"]:
            for obj in _all_objects(session.fixture):
                if obj.Attributes.Name in expected["selected_aliases"]:
                    if int(obj.Select(True)) not in (1, 2):
                        raise RuntimeError("formal_seed_select_failed")
        after = session._capture()
        if (after["objects"] != expected["objects"]
                or after["selected_aliases"] != expected["selected_aliases"]
                or after["revision"] <= before["revision"]):
            raise RuntimeError("formal_seed_readback_mismatch")
        session._assert_active()
        fd = _private_fd(session.directory)
        try:
            _publish(fd, "formal-seed-receipt.json", {
                "version": 1, "fixture_name": name,
                "before_scene_sha256": before["scene_sha256"],
                "after_scene_sha256": after["scene_sha256"],
                "objects": after["objects"],
                "selected_aliases": after["selected_aliases"],
                "active_document_unchanged": True,
            })
        finally:
            os.close(fd)
    except BaseException:
        session.blocked = True
        raise
    return str(session.directory)


if __name__ == "__main__":
    raise RuntimeError("run_an_explicit_formal_seed_entrypoint")
