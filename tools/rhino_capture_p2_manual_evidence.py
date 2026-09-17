# -*- coding: utf-8 -*-
"""Capture privacy-safe Rhino topology evidence for P2-HARD-002 and -014.

Run this file from Rhino 8's ScriptEditor in a blank, disposable document.
It reconstructs the final geometry produced by the frozen baseline tool calls,
checks the BRep topology that Scene Summary cannot expose, and writes two
viewport PNGs plus a minimized JSON report.  It does not change the frozen
18/30 automated score: both source runs remain failed for their recorded
tool-selection/recovery assertions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import Rhino
import System
from Rhino import Display, Geometry
from System.Drawing import Color


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"
REPORT_PATH = ROOT / "docs" / "p2-manual-topology-evidence.json"
TOLERANCE = 0.001


def _clear_document(doc: Rhino.RhinoDoc) -> None:
    for obj in list(doc.Objects):
        doc.Objects.Delete(obj.Id, True)
    doc.Views.Redraw()


def _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float):
    corners = [
        Geometry.Point3d(x0, y0, z0),
        Geometry.Point3d(x1, y0, z0),
        Geometry.Point3d(x1, y1, z0),
        Geometry.Point3d(x0, y1, z0),
        Geometry.Point3d(x0, y0, z1),
        Geometry.Point3d(x1, y0, z1),
        Geometry.Point3d(x1, y1, z1),
        Geometry.Point3d(x0, y1, z1),
    ]
    return Geometry.Brep.CreateFromBox(corners)


def _cutter(x: float, y: float, radius: float, z0: float = -1.0, z1: float = 7.0):
    plane = Geometry.Plane(Geometry.Point3d(x, y, z0), Geometry.Vector3d.ZAxis)
    circle = Geometry.Circle(plane, radius)
    return Geometry.Cylinder(circle, z1 - z0).ToBrep(True, True)


def _difference(base, cutters):
    results = Geometry.Brep.CreateBooleanDifference([base], cutters, TOLERANCE)
    if results is None or len(results) != 1:
        raise RuntimeError("expected exactly one Boolean-difference result")
    return results[0]


def _horizontal_face_loops(brep):
    faces = []
    for face in brep.Faces:
        plane_result = face.TryGetPlane(TOLERANCE)
        if not plane_result[0]:
            continue
        plane = plane_result[1]
        if abs(plane.Normal.Z) < 0.999:
            continue
        bbox = face.GetBoundingBox(True)
        inner = sum(
            1 for loop in face.Loops
            if loop.LoopType == Geometry.BrepLoopType.Inner
        )
        faces.append({
            "z": round((bbox.Min.Z + bbox.Max.Z) / 2.0, 6),
            "inner_loops": inner,
            "total_loops": face.Loops.Count,
        })
    return sorted(faces, key=lambda item: item["z"])


def _analyze(brep, expected_size, expected_holes):
    bbox = brep.GetBoundingBox(True)
    size = [
        round(bbox.Max.X - bbox.Min.X, 6),
        round(bbox.Max.Y - bbox.Min.Y, 6),
        round(bbox.Max.Z - bbox.Min.Z, 6),
    ]
    horizontal = _horizontal_face_loops(brep)
    bottom = horizontal[0] if horizontal else {"inner_loops": -1}
    top = horizontal[-1] if horizontal else {"inner_loops": -1}
    assertions = {
        "closed_solid": bool(brep.IsSolid),
        "bounding_box_matches": all(
            abs(actual - expected) <= TOLERANCE
            for actual, expected in zip(size, expected_size)
        ),
        "top_through_openings": top["inner_loops"] == expected_holes,
        "bottom_through_openings": bottom["inner_loops"] == expected_holes,
        "single_boolean_result": True,
    }
    return {
        "passed": all(assertions.values()),
        "assertions": assertions,
        "actual": {
            "object_count": 1,
            "bounding_box_size": size,
            "brep_face_count": brep.Faces.Count,
            "brep_edge_count": brep.Edges.Count,
            "horizontal_faces": horizontal,
        },
        "expected": {
            "object_count": 1,
            "bounding_box_size": expected_size,
            "through_holes": expected_holes,
            "closed_solid": True,
        },
    }


def _add_result(doc, brep, name):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.Name = name
    attributes.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attributes.ObjectColor = Color.FromArgb(57, 104, 155)
    object_id = doc.Objects.AddBrep(brep, attributes)
    if object_id == System.Guid.Empty:  # pragma: no cover - Rhino-only failure
        raise RuntimeError("failed to add evidence BRep to Rhino")
    return str(object_id)


def _capture(doc, relative_path):
    Rhino.RhinoApp.RunScript("_-SetView _World _Top", False)
    view = doc.Views.ActiveView
    if view is None:
        raise RuntimeError("no active Rhino view")
    viewport = view.ActiveViewport
    viewport.ZoomExtents()
    viewport.Magnify(0.82, False)
    view.Redraw()

    capture = Display.ViewCapture()
    capture.Width = 1280
    capture.Height = 800
    capture.ScaleScreenItems = False
    bitmap = capture.CaptureToBitmap(view)
    if bitmap is None:
        raise RuntimeError("Rhino viewport capture failed")
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        bitmap.Save(str(path))
    finally:
        bitmap.Dispose()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capture_task(doc, *, task_id, source_run_id, result_brep, expected_size,
                  expected_holes, relative_path, reconstruction):
    _clear_document(doc)
    object_id = _add_result(doc, result_brep, task_id + " topology evidence")
    doc.Views.Redraw()
    analysis = _analyze(result_brep, expected_size, expected_holes)
    screenshot_sha256 = _capture(doc, relative_path)
    return {
        "task_id": task_id,
        "frozen_baseline_public_run_id": source_run_id,
        "evidence_scope": "supplemental real-Rhino topology inspection",
        "baseline_score_changed": False,
        "reconstruction": reconstruction,
        "rhino_object_id_recorded_locally_only": bool(object_id),
        "topology": analysis,
        "viewport_evidence": {
            "path": relative_path,
            "sha256": screenshot_sha256,
            "capture": "Rhino 8 top viewport, ViewCapture 1280x800",
        },
    }


def main() -> None:
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        raise RuntimeError("open a blank Rhino document before running")
    if doc.Objects.Count:
        raise RuntimeError(
            "refusing to clear a non-empty Rhino document; open a new disposable document"
        )
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    plate_002 = _box(0, 0, 0, 90, 36, 6)
    cutters_002 = [_cutter(x, 18, 4) for x in (15, 45, 75)]
    result_002 = _difference(plate_002, cutters_002)
    evidence_002 = _capture_task(
        doc,
        task_id="P2-HARD-002",
        source_run_id="c52584c1a3f26b2d",
        result_brep=result_002,
        expected_size=[90.0, 36.0, 6.0],
        expected_holes=3,
        relative_path="docs/assets/p2-hard-002-rhino-topology.png",
        reconstruction={
            "basis": "frozen baseline tool arguments",
            "plate": "90x36x6 from (0,0,0)",
            "cutters": "radius 4 at x=15/45/75, y=18, z=-1..7",
            "note": "Baseline remains failed because created_type_consumed expected create_cylinder but the run used circle extrusions.",
        },
    )

    plate_014 = _box(-30, -20, 0, 30, 20, 6)
    moved_existing_cutter = _cutter(0, 0, 5, -2, 8)
    result_014 = _difference(plate_014, [moved_existing_cutter])
    evidence_014 = _capture_task(
        doc,
        task_id="P2-HARD-014",
        source_run_id="27b30b4d10966ac6",
        result_brep=result_014,
        expected_size=[60.0, 40.0, 6.0],
        expected_holes=1,
        relative_path="docs/assets/p2-hard-014-rhino-topology.png",
        reconstruction={
            "basis": "frozen baseline fixture and tool arguments",
            "plate": "60x40x6 centered at (0,0,3)",
            "existing_cutter": "radius 5, moved from x=50 to x=0, z=-2..8",
            "note": "Baseline remains failed because it moved first and never produced the required failed-then-successful Boolean sequence.",
        },
    )

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "application": "Rhino 8",
            "version": Rhino.RhinoApp.Version.ToString(),
            "document": "blank disposable document",
        },
        "scope": "Topology evidence omitted by Scene Summary; not a rerating of the frozen automated baseline.",
        "holdout_read": 0,
        "tasks": [evidence_002, evidence_014],
        "all_topology_assertions_passed": all(
            item["topology"]["passed"] for item in (evidence_002, evidence_014)
        ),
    }
    REPORT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    archive_path = ROOT / "data" / "demo-recordings" / "p2-topology-evidence.3dm"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    write_options = Rhino.FileIO.FileWriteOptions()
    write_options.SuppressDialogBoxes = True
    if not doc.WriteFile(str(archive_path), write_options):
        raise RuntimeError("failed to save the local Rhino evidence archive")
    print("P2 manual topology evidence written: %s" % REPORT_PATH.name)


if __name__ == "__main__":
    main()
