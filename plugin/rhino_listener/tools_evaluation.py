# -*- coding: utf-8 -*-
"""Token-protected P2 fixture and fault controls for real-Rhino evaluation.

These routes are deliberately not exposed through MCP.  They only prepare or
inspect synthetic evaluation scenes and are disabled unless Rhino has loaded a
non-placeholder ``RHINOCODER_EVAL_TOKEN``.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path


_STATE_LOCK = threading.Lock()
_FIXTURE_STATE = {"fixture_id": None, "objects": {}, "specs": {}}
_FAULT_STATE = {"drop_response_operation": None, "remaining": 0}


def _error(code: str, message: str, recoverable: bool = False) -> dict:
    return {
        "status": "error",
        "message": message,
        "error": {"code": code, "recoverable": recoverable},
    }


def _authorize(h) -> bool:
    expected = os.environ.get("RHINOCODER_EVAL_TOKEN", "").strip()
    provided = h.headers.get("X-RhinoCoder-Eval-Token", "").strip()
    if not expected or expected.startswith("<"):
        h._send_json(503, _error("eval.controls_disabled", "评测控制端点未启用", True))
        return False
    if provided != expected:
        h._send_json(403, _error("eval.invalid_token", "评测令牌无效"))
        return False
    return True


def _load_fixture(fixture_id: str, expected_sha256: str) -> dict:
    path = Path(__file__).resolve().parents[2] / "eval" / "p2" / "fixtures.json"
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError("fixtures.json SHA-256 与冻结 manifest 不一致")
    payload = json.loads(raw.decode("utf-8"))
    fixtures = payload.get("fixtures") or {}
    if fixture_id not in fixtures:
        raise ValueError("未知 P2 fixture_id: %s" % fixture_id)
    return fixtures[fixture_id]


def _route_setup_p2_fixture(h) -> None:
    if not _authorize(h):
        return
    data = h._parse_body()
    if data is None:
        return
    fixture_id = data.get("fixture_id")
    expected_sha256 = data.get("fixtures_sha256")
    if not isinstance(fixture_id, str) or not fixture_id:
        h._send_json(400, _error("eval.invalid_fixture", "缺少 fixture_id"))
        return
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        h._send_json(400, _error("eval.invalid_fixture_hash", "缺少冻结 fixtures SHA-256"))
        return
    try:
        fixture = _load_fixture(fixture_id, expected_sha256)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        h._send_json(409, _error("eval.fixture_integrity", str(exc)))
        return
    h._enqueue_and_wait("setup_p2_fixture", {"fixture_id": fixture_id, "fixture": fixture})


def _route_mutate_p2_fixture(h) -> None:
    if not _authorize(h):
        return
    data = h._parse_body()
    if data is None:
        return
    mutation_id = data.get("mutation_id")
    if mutation_id != "replace_target_after_first_lookup":
        h._send_json(400, _error("eval.invalid_mutation", "不支持的冻结场景变更"))
        return
    h._enqueue_and_wait("mutate_p2_fixture", {"mutation_id": mutation_id})


def _route_inspect_p2_fixture(h) -> None:
    if not _authorize(h):
        return
    data = h._parse_body()
    if data is None:
        return
    h._enqueue_and_wait("inspect_p2_fixture", {})


def _route_configure_p2_fault(h) -> None:
    if not _authorize(h):
        return
    data = h._parse_body()
    if data is None:
        return
    fault_id = data.get("fault_id")
    if fault_id != "drop_first_create_box_response_after_commit":
        h._send_json(400, _error("eval.invalid_fault", "不支持的冻结故障"))
        return
    with _STATE_LOCK:
        _FAULT_STATE["drop_response_operation"] = "create_box"
        _FAULT_STATE["remaining"] = 1
    h._send_json(200, {"status": "ok", "fault_id": fault_id, "armed": True})


def consume_response_drop(operation: str) -> bool:
    """Atomically consume the one-shot lost-response fault after cache commit."""
    with _STATE_LOCK:
        if (
            _FAULT_STATE["drop_response_operation"] == operation
            and _FAULT_STATE["remaining"] > 0
        ):
            _FAULT_STATE["remaining"] -= 1
            return True
    return False


def _clear_scene(rs) -> None:
    import scriptcontext as sc  # noqa: PLC0415

    objects = list(rs.AllObjects() or [])
    if objects:
        rs.DeleteObjects(objects)
    remaining = list(rs.AllObjects() or [])
    if remaining and sc.doc:
        for object_id in remaining:
            sc.doc.Objects.Delete(object_id, True)
    remaining = list(rs.AllObjects() or [])
    if remaining:
        raise RuntimeError("P2 场景清理不完整")
    if sc.doc:
        sc.doc.ClearUndoRecords(True)


def _box_corners(center, size):
    cx, cy, cz = [float(value) for value in center]
    sx, sy, sz = [float(value) for value in size]
    x0, x1 = cx - sx / 2.0, cx + sx / 2.0
    y0, y1 = cy - sy / 2.0, cy + sy / 2.0
    z0, z1 = cz - sz / 2.0, cz + sz / 2.0
    return [
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ]


def _create_object(rs, spec: dict):
    kind = spec["kind"]
    if kind == "box":
        object_id = rs.AddBox(_box_corners(spec["center"], spec["size"]))
    elif kind == "sphere":
        object_id = rs.AddSphere(spec["center"], float(spec["radius"]))
    elif kind == "cylinder":
        object_id = rs.AddCylinder(spec["base"], float(spec["height"]), float(spec["radius"]), True)
    else:
        raise ValueError("不支持的 fixture 几何类型: %s" % kind)
    if object_id is None:
        raise RuntimeError("Rhino 创建 fixture 对象失败: %s" % spec["logical_id"])

    name = spec.get("name")
    if name:
        rs.ObjectName(object_id, name)
    layer = spec.get("layer")
    if layer:
        if not rs.IsLayer(layer):
            rs.AddLayer(layer)
        rs.ObjectLayer(object_id, layer)
    color = spec.get("color")
    if color:
        rs.ObjectColor(object_id, tuple(int(value) for value in color))
    angle = float(spec.get("rotation_z_degrees") or 0)
    if angle:
        rs.RotateObject(object_id, spec["center"], angle, [0, 0, 1], copy=False)
    return object_id


def _expanded_specs(fixture: dict) -> list[dict]:
    specs = []
    for generator in fixture.get("generators") or []:
        if generator.get("kind") != "box_grid":
            raise ValueError("不支持的 fixture generator")
        count = int(generator["count"])
        columns = int(generator["columns"])
        origin = generator["origin"]
        step = generator["step"]
        for index in range(count):
            row, column = divmod(index, columns)
            specs.append({
                "logical_id": "%s%03d" % (generator["logical_id_prefix"], index + 1),
                "kind": "box",
                "size": generator["size"],
                "center": [
                    origin[0] + column * step[0],
                    origin[1] + row * step[1],
                    origin[2] + (row * columns + column) * step[2],
                ],
                "color": generator.get("color"),
                "name": "%s%03d" % (generator.get("name_prefix", "Generated"), index + 1),
            })
    specs.extend(fixture.get("objects") or [])
    return specs


def _exec_setup_p2_fixture(rs, params: dict):
    _clear_scene(rs)
    specs = _expanded_specs(params["fixture"])
    object_ids = {}
    group_members = {}
    for spec in specs:
        object_id = _create_object(rs, spec)
        logical_id = spec["logical_id"]
        object_ids[logical_id] = str(object_id)
        for group in spec.get("groups") or []:
            group_members.setdefault(group, []).append(object_id)
    for group, members in group_members.items():
        if not rs.IsGroup(group):
            rs.AddGroup(group)
        rs.AddObjectsToGroup(members, group)
    rs.UnselectAllObjects()
    for spec in specs:
        if spec.get("selected"):
            rs.SelectObject(object_ids[spec["logical_id"]])
    rs.Redraw()
    with _STATE_LOCK:
        _FIXTURE_STATE["fixture_id"] = params["fixture_id"]
        _FIXTURE_STATE["objects"] = dict(object_ids)
        _FIXTURE_STATE["specs"] = {spec["logical_id"]: dict(spec) for spec in specs}
        _FAULT_STATE["drop_response_operation"] = None
        _FAULT_STATE["remaining"] = 0
    return {
        "fixture_id": params["fixture_id"],
        "object_ids": object_ids,
        "object_count": len(object_ids),
    }


def _exec_mutate_p2_fixture(rs, params: dict):
    with _STATE_LOCK:
        fixture_id = _FIXTURE_STATE["fixture_id"]
        old_id = _FIXTURE_STATE["objects"].get("target_panel")
        spec = _FIXTURE_STATE["specs"].get("target_panel")
    if fixture_id != "stale_target_panel" or not old_id or not spec:
        raise ValueError("当前 fixture 不支持该变更")
    if not rs.DeleteObject(old_id):
        raise RuntimeError("无法替换 stale target")
    new_id = _create_object(rs, spec)
    with _STATE_LOCK:
        _FIXTURE_STATE["objects"]["target_panel"] = str(new_id)
    rs.Redraw()
    return {"logical_id": "target_panel", "old_id": old_id, "new_id": str(new_id)}


def _bbox_payload(rs, object_id):
    bbox = rs.BoundingBox(object_id)
    if bbox is None:
        return None
    mn, mx = bbox[0], bbox[6]
    def coords(point):
        if hasattr(point, "X"):
            return [round(float(point.X), 4), round(float(point.Y), 4), round(float(point.Z), 4)]
        return [round(float(point[0]), 4), round(float(point[1]), 4), round(float(point[2]), 4)]
    low, high = coords(mn), coords(mx)
    return {
        "min": low,
        "max": high,
        "center": [round((low[index] + high[index]) / 2.0, 4) for index in range(3)],
        "size": [round(high[index] - low[index], 4) for index in range(3)],
    }


def _exec_inspect_p2_fixture(rs, params: dict):
    del params
    with _STATE_LOCK:
        fixture_id = _FIXTURE_STATE["fixture_id"]
        object_ids = dict(_FIXTURE_STATE["objects"])
        specs = {key: dict(value) for key, value in _FIXTURE_STATE["specs"].items()}
        fault_remaining = int(_FAULT_STATE["remaining"])
    objects = {}
    for logical_id, object_id in object_ids.items():
        exists = bool(rs.IsObject(object_id))
        item = {"object_id": object_id, "exists": exists, "role": specs[logical_id].get("role", "fixture")}
        if exists:
            color = rs.ObjectColor(object_id)
            item.update({
                "name": rs.ObjectName(object_id) or "",
                "layer": rs.ObjectLayer(object_id) or "",
                "color": [int(color.R), int(color.G), int(color.B)] if color else [0, 0, 0],
                "groups": list(rs.ObjectGroups(object_id) or []),
                "bbox": _bbox_payload(rs, object_id),
            })
        objects[logical_id] = item
    return {
        "fixture_id": fixture_id,
        "objects": objects,
        "fault_remaining": fault_remaining,
        "scene_object_count": len(rs.NormalObjects() or []),
    }


ROUTE_HANDLERS = {
    "/setup_p2_fixture": _route_setup_p2_fixture,
    "/mutate_p2_fixture": _route_mutate_p2_fixture,
    "/inspect_p2_fixture": _route_inspect_p2_fixture,
    "/configure_p2_fault": _route_configure_p2_fault,
}

DISPATCH_HANDLERS = {
    "setup_p2_fixture": _exec_setup_p2_fixture,
    "mutate_p2_fixture": _exec_mutate_p2_fixture,
    "inspect_p2_fixture": _exec_inspect_p2_fixture,
}
