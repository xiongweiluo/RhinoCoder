"""
rhino_listener/tools_geometry.py  —  运行在 Rhino 8 内部（Python 3.9）

四大家族 · 几何生成（geometry）家族的完整实现：
  create_sphere, create_box, create_cylinder, create_line,
  create_circle, extrude_curve_straight, boolean_difference

公开接口（双表导出）：
  ROUTE_HANDLERS    — {"/endpoint": fn(h)}       HTTP 路由层：验证参数 + 工作入队
  DISPATCH_HANDLERS — {"operation": fn(rs, params)} 执行层：Rhino 主线程 rhinoscriptsyntax 调用

设计约束：
  - _route_* 函数：只使用标准库，通过参数 h（_RhinoHTTPHandler 实例）与
    HTTP 层交互（h._parse_body / h._send_json / h._enqueue_and_wait）。
    @api_error_handler 由 listener_main.py 在聚合路由表时统一包裹，此处无需导入。
  - _exec_* 函数：仅在 Rhino 主线程（Idle 回调）被调用，可安全使用 rs.*。
    需要 Rhino C# API 的函数在函数体内执行局部 import Rhino as _Rhino。
  - 严禁在此文件顶层 import rhinoscriptsyntax / Rhino / mcp / httpx。
"""

from __future__ import annotations

import logging

from .validation import are_guids, is_guid

logger = logging.getLogger("rhinocoder.http_listener")


# ===========================================================================
# HTTP 路由层 — 参数验证 + 工作入队
# (self → h：函数签名由实例方法改为普通函数，逻辑零改动)
# ===========================================================================

def _route_create_sphere(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    try:
        radius = float(data["radius"])
    except KeyError:
        h._send_json(400, {"status": "error", "message": "Missing field: radius"})
        return
    except (TypeError, ValueError) as exc:
        h._send_json(400, {"status": "error", "message": f"Invalid radius value: {exc}"})
        return

    if radius <= 0:
        h._send_json(
            400, {"status": "error", "message": f"radius must be positive, got {radius}"}
        )
        return

    h._enqueue_and_wait("create_sphere", {"radius": radius})


def _route_create_box(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    params: dict = {}
    for fname in ("width", "depth", "height"):
        try:
            val = float(data[fname])
        except KeyError:
            h._send_json(400, {"status": "error", "message": f"Missing field: {fname}"})
            return
        except (TypeError, ValueError) as exc:
            h._send_json(400, {"status": "error", "message": f"Invalid {fname} value: {exc}"})
            return
        if val <= 0:
            h._send_json(
                400, {"status": "error", "message": f"{fname} must be positive, got {val}"}
            )
            return
        params[fname] = val

    h._enqueue_and_wait("create_box", params)


def _route_create_cylinder(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    params: dict = {}
    for fname in ("radius", "height"):
        try:
            val = float(data[fname])
        except KeyError:
            h._send_json(400, {"status": "error", "message": f"Missing field: {fname}"})
            return
        except (TypeError, ValueError) as exc:
            h._send_json(400, {"status": "error", "message": f"Invalid {fname} value: {exc}"})
            return
        if val <= 0:
            h._send_json(
                400, {"status": "error", "message": f"{fname} must be positive, got {val}"}
            )
            return
        params[fname] = val

    h._enqueue_and_wait("create_cylinder", params)


def _route_create_line(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    params: dict = {}
    for pt_name in ("start", "end"):
        raw_pt = data.get(pt_name)
        if raw_pt is None:
            h._send_json(400, {"status": "error", "message": f"Missing field: {pt_name}"})
            return
        try:
            pt = [float(raw_pt[0]), float(raw_pt[1]), float(raw_pt[2])]
        except (TypeError, IndexError, ValueError) as exc:
            h._send_json(
                400,
                {"status": "error", "message": f"Invalid {pt_name} (expected [x, y, z]): {exc}"},
            )
            return
        params[pt_name] = pt

    if params["start"] == params["end"]:
        h._send_json(
            400, {"status": "error", "message": "start and end points must be different"}
        )
        return

    h._enqueue_and_wait("create_line", params)


def _route_create_circle(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    raw_center = data.get("center")
    if raw_center is None:
        h._send_json(400, {"status": "error", "message": "Missing field: center"})
        return
    try:
        center = [float(raw_center[0]), float(raw_center[1]), float(raw_center[2])]
    except (TypeError, IndexError, ValueError) as exc:
        h._send_json(
            400, {"status": "error", "message": f"Invalid center (expected [x, y, z]): {exc}"}
        )
        return

    try:
        radius = float(data["radius"])
    except KeyError:
        h._send_json(400, {"status": "error", "message": "Missing field: radius"})
        return
    except (TypeError, ValueError) as exc:
        h._send_json(400, {"status": "error", "message": f"Invalid radius value: {exc}"})
        return

    if radius <= 0:
        h._send_json(
            400, {"status": "error", "message": f"radius must be positive, got {radius}"}
        )
        return

    h._enqueue_and_wait("create_circle", {"center": center, "radius": radius})


def _route_extrude_curve_straight(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    curve_id = data.get("curve_id")
    if not is_guid(curve_id):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: curve_id (expected non-empty string GUID)"},
        )
        return

    params: dict = {"curve_id": curve_id}
    for pt_name in ("start_point", "end_point"):
        raw_pt = data.get(pt_name)
        if raw_pt is None:
            h._send_json(400, {"status": "error", "message": f"Missing field: {pt_name}"})
            return
        try:
            pt = [float(raw_pt[0]), float(raw_pt[1]), float(raw_pt[2])]
        except (TypeError, IndexError, ValueError) as exc:
            h._send_json(
                400,
                {"status": "error", "message": f"Invalid {pt_name} (expected [x, y, z]): {exc}"},
            )
            return
        params[pt_name] = pt

    if params["start_point"] == params["end_point"]:
        h._send_json(
            400, {"status": "error", "message": "start_point and end_point must be different"}
        )
        return

    h._enqueue_and_wait("extrude_curve_straight", params)


def _route_boolean_difference(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    for field_name in ("input0_ids", "input1_ids"):
        val = data.get(field_name)
        if not val or not isinstance(val, list):
            h._send_json(
                400,
                {
                    "status": "error",
                    "message": (
                        f"Missing or invalid field: {field_name} "
                        "(expected non-empty list of GUID strings)"
                    ),
                },
            )
            return
        if not are_guids(val):
            h._send_json(
                400,
                {"status": "error", "message": f"All elements in {field_name} must be non-empty GUID strings"},
            )
            return

    h._enqueue_and_wait(
        "boolean_difference",
        {"input0_ids": data["input0_ids"], "input1_ids": data["input1_ids"]},
    )


# ===========================================================================
# Rhino 主线程执行层 — rhinoscriptsyntax 调用（零逻辑改动）
# ===========================================================================

def _exec_create_sphere(rs, params: dict):
    return rs.AddSphere([0.0, 0.0, 0.0], params["radius"])


def _exec_create_box(rs, params: dict):
    w, d, ht = params["width"], params["depth"], params["height"]
    corners = [
        [0, 0,  0], [w, 0,  0], [w, d,  0], [0, d,  0],
        [0, 0, ht], [w, 0, ht], [w, d, ht], [0, d, ht],
    ]
    return rs.AddBox(corners)


def _exec_create_cylinder(rs, params: dict):
    return rs.AddCylinder(
        [0.0, 0.0, 0.0],
        params["height"],
        params["radius"],
        cap=True,
    )


def _exec_create_line(rs, params: dict):
    return rs.AddLine(params["start"], params["end"])


def _exec_create_circle(rs, params: dict):
    return rs.AddCircle(params["center"], params["radius"])


def _exec_extrude_curve_straight(rs, params: dict):
    curve_id = params["curve_id"]
    sp = params["start_point"]
    ep = params["end_point"]
    ext_id = rs.ExtrudeCurveStraight(curve_id, sp, ep)
    if ext_id is None:
        raise ValueError(
            "rs.ExtrudeCurveStraight 返回 None（曲线无效或起止点相同）"
        )
    if rs.IsCurveClosed(curve_id):
        rs.CapPlanarHoles(ext_id)  # 原地封盖，GUID 不变，不接收返回值
    return ext_id


def _exec_boolean_difference(rs, params: dict):
    input0_ids = params["input0_ids"]
    input1_ids = params["input1_ids"]
    # 强制将字符串 GUID 转换为 Rhino 内部 GUID 对象，提升兼容性
    obj0 = [rs.coerceguid(i) for i in input0_ids]
    obj1 = [rs.coerceguid(i) for i in input1_ids]
    if any(g is None for g in obj0):
        raise ValueError(f"input0_ids 中存在无法解析的 GUID: {input0_ids}")
    if any(g is None for g in obj1):
        raise ValueError(f"input1_ids 中存在无法解析的 GUID: {input1_ids}")
    new_ids = rs.BooleanDifference(obj0, obj1, delete_input=True)
    if not new_ids:
        raise ValueError(
            "BooleanDifference 返回空结果"
            "（可能原因：实体未相交、几何无效，或运算本身失败）"
        )
    return [str(g) for g in new_ids]


# ===========================================================================
# 公开双表接口
# ===========================================================================

ROUTE_HANDLERS = {
    "/create_sphere":          _route_create_sphere,
    "/create_box":             _route_create_box,
    "/create_cylinder":        _route_create_cylinder,
    "/create_line":            _route_create_line,
    "/create_circle":          _route_create_circle,
    "/extrude_curve_straight": _route_extrude_curve_straight,
    "/boolean_difference":     _route_boolean_difference,
}

DISPATCH_HANDLERS = {
    "create_sphere":          _exec_create_sphere,
    "create_box":             _exec_create_box,
    "create_cylinder":        _exec_create_cylinder,
    "create_line":            _exec_create_line,
    "create_circle":          _exec_create_circle,
    "extrude_curve_straight": _exec_extrude_curve_straight,
    "boolean_difference":     _exec_boolean_difference,
}
