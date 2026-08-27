"""
rhino_listener/tools_transform.py  —  运行在 Rhino 8 内部（Python 3.9）

四大家族 · 空间变换（transform）家族的完整实现：
  move_object, rotate_object, scale_object, align_objects,
  distribute_objects, group_objects, place_on_at, undo_last_action

公开接口（双表导出）：
  ROUTE_HANDLERS    — {"/endpoint": fn(h)}          HTTP 路由层：验证参数 + 工作入队
  DISPATCH_HANDLERS — {"operation": fn(rs, params)}  执行层：Rhino 主线程 rhinoscriptsyntax 调用

【核心算法说明】
  _exec_align_objects  — 群组感知（Group-Aware）多维对齐：将群组视为刚体整体，
                         联合包围盒参与目标值计算，权重 = 1（不因成员多而放大）。
  _exec_place_on_at    — 6 轴向语义化吸附：贴合指定方位包围盒边界，同时在垂直截面居中。
  _exec_distribute_objects — 动态游标等距分布算法：按空间自然顺序排序后逐步推进游标。

设计约束：
  - _route_* 函数：只使用标准库，通过参数 h（_RhinoHTTPHandler 实例）与
    HTTP 层交互。@api_error_handler 由 listener_main.py 在聚合路由表时统一包裹。
  - _exec_* 函数：仅在 Rhino 主线程（Idle 回调）被调用，可安全使用 rs.*。
    需要 Rhino C# API（_Rhino.RhinoDoc / _Rhino.Geometry）的函数在函数体内
    执行局部 import Rhino as _Rhino，避免模块加载时的环境污染。
  - 严禁在此文件顶层 import rhinoscriptsyntax / Rhino / mcp / httpx。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("rhinocoder.http_listener")


# ===========================================================================
# HTTP 路由层 — 参数验证 + 工作入队
# (self → h：函数签名由实例方法改为普通函数，逻辑零改动)
# ===========================================================================

def _route_move_object(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_id = data.get("object_id")
    if not object_id or not isinstance(object_id, str):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: object_id (expected non-empty string GUID)"},
        )
        return

    raw_t = data.get("translation")
    if raw_t is None:
        h._send_json(400, {"status": "error", "message": "Missing field: translation"})
        return
    try:
        translation = [float(raw_t[0]), float(raw_t[1]), float(raw_t[2])]
    except (TypeError, IndexError, ValueError) as exc:
        h._send_json(
            400, {"status": "error", "message": f"Invalid translation (expected [x, y, z]): {exc}"}
        )
        return

    h._enqueue_and_wait(
        "move_object", {"object_id": object_id, "translation": translation}
    )


def _route_rotate_object(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_id = data.get("object_id")
    if not object_id or not isinstance(object_id, str):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: object_id (expected non-empty string GUID)"},
        )
        return

    try:
        angle_degrees = float(data["angle_degrees"])
    except KeyError:
        h._send_json(400, {"status": "error", "message": "Missing field: angle_degrees"})
        return
    except (TypeError, ValueError) as exc:
        h._send_json(400, {"status": "error", "message": f"Invalid angle_degrees value: {exc}"})
        return

    params: dict = {"object_id": object_id, "angle_degrees": angle_degrees}

    raw_axis = data.get("axis")
    if raw_axis is not None:
        try:
            axis = [float(raw_axis[0]), float(raw_axis[1]), float(raw_axis[2])]
        except (TypeError, IndexError, ValueError) as exc:
            h._send_json(
                400, {"status": "error", "message": f"Invalid axis (expected [x, y, z]): {exc}"}
            )
            return
        if all(v == 0.0 for v in axis):
            h._send_json(400, {"status": "error", "message": "axis cannot be a zero vector [0, 0, 0]"})
            return
        params["axis"] = axis

    raw_center = data.get("center_point")
    if raw_center is not None:
        try:
            params["center_point"] = [float(raw_center[0]), float(raw_center[1]), float(raw_center[2])]
        except (TypeError, IndexError, ValueError) as exc:
            h._send_json(
                400, {"status": "error", "message": f"Invalid center_point (expected [x, y, z]): {exc}"}
            )
            return

    h._enqueue_and_wait("rotate_object", params)


def _route_scale_object(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_id = data.get("object_id")
    if not object_id or not isinstance(object_id, str):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: object_id (expected non-empty string GUID)"},
        )
        return

    raw_scale = data.get("scale_factor")
    if raw_scale is None:
        h._send_json(400, {"status": "error", "message": "Missing field: scale_factor"})
        return
    try:
        scale_factor = [float(raw_scale[0]), float(raw_scale[1]), float(raw_scale[2])]
    except (TypeError, IndexError, ValueError) as exc:
        h._send_json(
            400, {"status": "error", "message": f"Invalid scale_factor (expected [sx, sy, sz]): {exc}"}
        )
        return
    for i, v in enumerate(scale_factor):
        if v <= 0:
            axis_name = ["X", "Y", "Z"][i]
            h._send_json(
                400,
                {"status": "error", "message": f"scale_factor[{i}] ({axis_name}) must be positive, got {v}"},
            )
            return

    params: dict = {"object_id": object_id, "scale_factor": scale_factor}

    raw_center = data.get("center_point")
    if raw_center is not None:
        try:
            params["center_point"] = [float(raw_center[0]), float(raw_center[1]), float(raw_center[2])]
        except (TypeError, IndexError, ValueError) as exc:
            h._send_json(
                400, {"status": "error", "message": f"Invalid center_point (expected [x, y, z]): {exc}"}
            )
            return

    h._enqueue_and_wait("scale_object", params)


def _route_align_objects(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_ids = data.get("object_ids")
    if not isinstance(object_ids, list) or len(object_ids) < 2:
        h._send_json(
            400,
            {
                "status": "error",
                "message": (
                    "Missing or invalid field: object_ids "
                    "(expected list with at least 2 GUID strings)"
                ),
            },
        )
        return
    if not all(isinstance(g, str) and g for g in object_ids):
        h._send_json(
            400,
            {"status": "error", "message": "All elements in object_ids must be non-empty GUID strings"},
        )
        return

    axis = str(data.get("axis", "X")).upper()
    if axis not in ("X", "Y", "Z"):
        h._send_json(
            400,
            {"status": "error", "message": f"Invalid axis {axis!r}: must be 'X', 'Y', or 'Z'"},
        )
        return

    alignment = str(data.get("alignment", "center")).lower()
    if alignment not in ("min", "center", "max"):
        h._send_json(
            400,
            {"status": "error", "message": f"Invalid alignment {alignment!r}: must be 'min', 'center', or 'max'"},
        )
        return

    h._enqueue_and_wait(
        "align_objects",
        {"object_ids": object_ids, "axis": axis, "alignment": alignment},
    )


def _route_distribute_objects(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_ids = data.get("object_ids")
    if not isinstance(object_ids, list) or len(object_ids) < 2:
        h._send_json(
            400,
            {
                "status": "error",
                "message": (
                    "Missing or invalid field: object_ids "
                    "(expected list with at least 2 GUID strings)"
                ),
            },
        )
        return
    if not all(isinstance(g, str) and g for g in object_ids):
        h._send_json(
            400,
            {"status": "error", "message": "All elements in object_ids must be non-empty GUID strings"},
        )
        return

    axis = str(data.get("axis", "X")).upper()
    if axis not in ("X", "Y", "Z"):
        h._send_json(
            400,
            {"status": "error", "message": f"Invalid axis {axis!r}: must be 'X', 'Y', or 'Z'"},
        )
        return

    raw_spacing = data.get("spacing")
    if raw_spacing is None:
        h._send_json(400, {"status": "error", "message": "Missing field: spacing"})
        return
    try:
        spacing = float(raw_spacing)
    except (TypeError, ValueError) as exc:
        h._send_json(400, {"status": "error", "message": f"Invalid spacing value: {exc}"})
        return
    if spacing < 0:
        h._send_json(
            400,
            {"status": "error", "message": f"spacing must be non-negative, got {spacing}"},
        )
        return

    h._enqueue_and_wait(
        "distribute_objects",
        {"object_ids": object_ids, "axis": axis, "spacing": spacing},
    )


def _route_group_objects(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_ids = data.get("object_ids")
    if not isinstance(object_ids, list) or len(object_ids) < 2:
        h._send_json(
            400,
            {"status": "error", "message": "打组失败：至少需要提供 2 个物体 ID"},
        )
        return
    if not all(isinstance(g, str) and g for g in object_ids):
        h._send_json(
            400,
            {"status": "error", "message": "All elements in object_ids must be non-empty GUID strings"},
        )
        return

    group_name = data.get("group_name")
    if group_name is not None:
        if not isinstance(group_name, str) or not group_name.strip():
            h._send_json(
                400,
                {"status": "error", "message": "group_name must be a non-empty string if provided"},
            )
            return
        group_name = group_name.strip()

    params: dict = {"object_ids": object_ids}
    if group_name:
        params["group_name"] = group_name

    h._enqueue_and_wait("group_objects", params)


def _route_place_on_at(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    target_id = data.get("target_id")
    if not target_id or not isinstance(target_id, str):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: target_id (expected non-empty string GUID)"},
        )
        return

    reference_id = data.get("reference_id")
    if not reference_id or not isinstance(reference_id, str):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: reference_id (expected non-empty string GUID)"},
        )
        return

    side = data.get("side")
    if not side or not isinstance(side, str):
        h._send_json(
            400,
            {"status": "error", "message": 'Missing or invalid field: side (expected one of "top","bottom","left","right","front","back")'},
        )
        return

    side = side.lower()
    valid_sides = ("top", "bottom", "left", "right", "front", "back")
    if side not in valid_sides:
        h._send_json(
            400,
            {"status": "error", "message": f"Invalid side {side!r}: must be one of {valid_sides}"},
        )
        return

    h._enqueue_and_wait(
        "place_on_at",
        {"target_id": target_id, "reference_id": reference_id, "side": side},
    )


def _route_undo_last_action(h) -> None:
    # 无需请求体：直接派发，无参数
    h._enqueue_and_wait("undo_last_action", {})


def _route_delete_objects(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_ids = data.get("object_ids")
    if not isinstance(object_ids, list) or not object_ids:
        h._send_json(
            400,
            {
                "status": "error",
                "message": (
                    "Missing or invalid field: object_ids "
                    "(expected non-empty list of GUID strings)"
                ),
            },
        )
        return
    if not all(isinstance(g, str) and g for g in object_ids):
        h._send_json(
            400,
            {"status": "error", "message": "All elements in object_ids must be non-empty GUID strings"},
        )
        return

    h._enqueue_and_wait("delete_objects", {"object_ids": object_ids})


def _route_reset_environment(h) -> None:
    import os  # noqa: PLC0415

    expected = os.environ.get("RHINOCODER_EVAL_TOKEN", "").strip()
    provided = h.headers.get("X-RhinoCoder-Eval-Token", "").strip()
    if not expected or expected.startswith("<"):
        h._send_json(
            503,
            {
                "status": "error",
                "message": "评测清场端点未启用：Rhino 进程未配置 RHINOCODER_EVAL_TOKEN",
                "error": {"code": "eval.reset_disabled", "recoverable": True},
            },
        )
        return
    if provided != expected:
        h._send_json(
            403,
            {
                "status": "error",
                "message": "评测令牌无效，拒绝清空场景",
                "error": {"code": "eval.invalid_token", "recoverable": False},
            },
        )
        return
    # 仅显式评测请求可进入主线程执行清场。
    h._enqueue_and_wait("reset_environment", {})


# ===========================================================================
# Rhino 主线程执行层 — rhinoscriptsyntax 调用（零逻辑改动）
# ===========================================================================

def _exec_move_object(rs, params: dict):
    obj = params["object_id"]
    t   = params["translation"]
    if rs.IsGroup(obj):
        members = rs.ObjectsByGroup(obj) or []
        if not members:
            raise ValueError(f"群组 '{obj}' 不含任何成员对象，无法移动")
        results = rs.MoveObjects(members, t)
        if results is None:
            raise ValueError(
                f"rs.MoveObjects 返回 None（群组 '{obj}' 移动失败，"
                "请检查群组成员是否有效或文档是否处于锁定状态）"
            )
        return obj  # 返回群组名称，保持接口一致
    return rs.MoveObject(obj, t)


def _exec_rotate_object(rs, params: dict):
    import Rhino as _Rhino  # 仅此函数需要 C# API 做包围盒兜底

    obj_id        = params["object_id"]
    angle_degrees = params["angle_degrees"]
    axis          = params.get("axis", [0.0, 0.0, 1.0])

    if "center_point" in params:
        center = params["center_point"]
    else:
        bbox = rs.BoundingBox(obj_id)
        if bbox is None:
            rh_guid = rs.coerceguid(obj_id)
            rh_obj  = _Rhino.RhinoDoc.ActiveDoc.Objects.FindId(rh_guid) if rh_guid else None
            if rh_obj is not None and rh_obj.Geometry is not None:
                bb = rh_obj.Geometry.GetBoundingBox(True)
                if bb.IsValid:
                    mn, mx = bb.Min, bb.Max
                    bbox = [
                        (mn.X, mn.Y, mn.Z), (mx.X, mn.Y, mn.Z),
                        (mx.X, mx.Y, mn.Z), (mn.X, mx.Y, mn.Z),
                        (mn.X, mn.Y, mx.Z), (mx.X, mn.Y, mx.Z),
                        (mx.X, mx.Y, mx.Z), (mn.X, mx.Y, mx.Z),
                    ]
        if bbox is None:
            raise ValueError(f"无法获取对象 {obj_id} 的包围盒，无法计算几何中心")
        min_pt, max_pt = bbox[0], bbox[6]
        center = [
            (min_pt[0] + max_pt[0]) / 2.0,
            (min_pt[1] + max_pt[1]) / 2.0,
            (min_pt[2] + max_pt[2]) / 2.0,
        ]

    result = rs.RotateObject(obj_id, center, angle_degrees, axis)
    if result is None:
        raise ValueError(
            f"rs.RotateObject 返回 None（对象 {obj_id} 旋转失败，"
            "请检查 GUID 是否有效或文档是否处于锁定状态）"
        )
    return result


def _exec_scale_object(rs, params: dict):
    import Rhino as _Rhino  # 仅此函数需要 C# API 做包围盒兜底

    obj_id       = params["object_id"]
    scale_factor = params["scale_factor"]

    if "center_point" in params:
        center = params["center_point"]
    else:
        bbox = rs.BoundingBox(obj_id)
        if bbox is None:
            rh_guid = rs.coerceguid(obj_id)
            rh_obj  = _Rhino.RhinoDoc.ActiveDoc.Objects.FindId(rh_guid) if rh_guid else None
            if rh_obj is not None and rh_obj.Geometry is not None:
                bb = rh_obj.Geometry.GetBoundingBox(True)
                if bb.IsValid:
                    mn, mx = bb.Min, bb.Max
                    bbox = [
                        (mn.X, mn.Y, mn.Z), (mx.X, mn.Y, mn.Z),
                        (mx.X, mx.Y, mn.Z), (mn.X, mx.Y, mn.Z),
                        (mn.X, mn.Y, mx.Z), (mx.X, mn.Y, mx.Z),
                        (mx.X, mx.Y, mx.Z), (mn.X, mx.Y, mx.Z),
                    ]
        if bbox is None:
            raise ValueError(f"无法获取对象 {obj_id} 的包围盒，无法计算几何中心")
        min_pt, max_pt = bbox[0], bbox[6]
        center = [
            (min_pt[0] + max_pt[0]) / 2.0,
            (min_pt[1] + max_pt[1]) / 2.0,
            (min_pt[2] + max_pt[2]) / 2.0,
        ]

    result = rs.ScaleObject(obj_id, center, scale_factor)
    if result is None:
        raise ValueError(
            f"rs.ScaleObject 返回 None（对象 {obj_id} 缩放失败，"
            "请检查 GUID 是否有效或 scale_factor 是否含零值）"
        )
    return result


def _exec_align_objects(rs, params: dict):
    """群组感知（Group-Aware）多维对齐：群组视为刚体整体，权重 = 1。"""
    import Rhino as _Rhino  # 联合包围盒兜底计算需要 C# API

    object_ids = params["object_ids"]
    axis       = params["axis"]       # "X" | "Y" | "Z"（已大写）
    alignment  = params["alignment"]  # "min" | "center" | "max"（已小写）
    axis_idx   = {"X": 0, "Y": 1, "Z": 2}[axis]

    # ── 辅助：从 Point3d 或 tuple 统一读取轴向坐标 ─────────────────────────
    def _get_axis_val(pt):
        return float(getattr(pt, axis) if hasattr(pt, axis) else pt[axis_idx])

    # ── 辅助：安全获取一组对象的联合包围盒，兼容 Extrusion 等 rs.BoundingBox
    #          可能返回 None 的类型 ────────────────────────────────────────────
    def _safe_bbox_for_ids(ids):
        bbox = rs.BoundingBox(ids)
        if bbox is not None:
            return bbox
        combined_bb = None
        for mid in ids:
            rh_guid = rs.coerceguid(mid)
            rh_obj  = (
                _Rhino.RhinoDoc.ActiveDoc.Objects.FindId(rh_guid)
                if rh_guid else None
            )
            if rh_obj is not None and rh_obj.Geometry is not None:
                bb = rh_obj.Geometry.GetBoundingBox(True)
                if bb.IsValid:
                    combined_bb = (
                        bb if combined_bb is None
                        else _Rhino.Geometry.BoundingBox.Union(combined_bb, bb)
                    )
        if combined_bb is None:
            return None
        mn, mx = combined_bb.Min, combined_bb.Max
        return [
            (mn.X, mn.Y, mn.Z), (mx.X, mn.Y, mn.Z),
            (mx.X, mx.Y, mn.Z), (mn.X, mx.Y, mn.Z),
            (mn.X, mn.Y, mx.Z), (mx.X, mn.Y, mx.Z),
            (mx.X, mx.Y, mx.Z), (mn.X, mx.Y, mx.Z),
        ]

    # ── 构建对齐单元列表（每个群组/对象算一个刚体单元）────────────────────
    units = []
    for item in object_ids:
        if rs.IsGroup(item):
            members  = rs.ObjectsByGroup(item) or []
            if not members:
                raise ValueError(f"群组 '{item}' 不含任何成员对象，无法对齐")
            bbox     = _safe_bbox_for_ids(members)
            is_group = True
        else:
            members  = [item]
            bbox     = _safe_bbox_for_ids([item])
            is_group = False

        if bbox is None:
            raise ValueError(
                f"无法获取 '{item}' 的包围盒"
                "（对象/群组不存在、类型不支持，或几何无效）"
            )
        units.append({"is_group": is_group, "id": item,
                      "members": members, "bbox": bbox})

    # ── 计算对齐目标值（群组作为整体参与，权重 = 1）────────────────────────
    overall_min = min(_get_axis_val(u["bbox"][0]) for u in units)
    overall_max = max(_get_axis_val(u["bbox"][6]) for u in units)

    if alignment == "min":
        target_val = overall_min
    elif alignment == "max":
        target_val = overall_max
    else:  # center
        target_val = (overall_min + overall_max) / 2.0

    # ── 逐单元平移 ─────────────────────────────────────────────────────────
    moved_count = 0
    for unit in units:
        bbox    = unit["bbox"]
        obj_min = _get_axis_val(bbox[0])
        obj_max = _get_axis_val(bbox[6])

        if alignment == "min":
            current_val = obj_min
        elif alignment == "max":
            current_val = obj_max
        else:
            current_val = (obj_min + obj_max) / 2.0

        delta = target_val - current_val
        if abs(delta) < 1e-9:
            moved_count += 1
            continue

        translation             = [0.0, 0.0, 0.0]
        translation[axis_idx]   = delta

        if unit["is_group"]:
            results = rs.MoveObjects(unit["members"], translation)
            if results is None:
                raise ValueError(
                    f"rs.MoveObjects 返回 None（群组 '{unit['id']}' 移动失败）"
                )
        else:
            result = rs.MoveObject(unit["id"], translation)
            if result is None:
                raise ValueError(
                    f"rs.MoveObject 返回 None（对象 {unit['id']} 移动失败，"
                    "请检查 GUID 是否有效或文档是否处于锁定状态）"
                )
        moved_count += 1

    return {
        "moved":      moved_count,
        "total":      len(object_ids),
        "axis":       axis,
        "alignment":  alignment,
        "target_val": round(target_val, 4),
    }


def _exec_distribute_objects(rs, params: dict):
    """动态游标等距分布算法：按 axis 方向中心点升序排序后逐步推进游标。"""
    object_ids = params["object_ids"]
    axis       = params["axis"]     # "X" | "Y" | "Z"（已大写）
    spacing    = params["spacing"]  # float, >= 0

    axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis]

    # ── 一次性采集所有包围盒 ──────────────────────────────────────────────
    bboxes = []
    for oid in object_ids:
        bbox = rs.BoundingBox(oid)
        if bbox is None:
            raise ValueError(
                f"无法获取对象 {oid} 的包围盒"
                "（对象不存在、类型不支持，或几何无效）"
            )
        bboxes.append(bbox)

    # ── 按 axis 方向中心点升序排列，保证分布顺序符合空间自然顺序 ──────────
    # bbox[0] = min 角点，bbox[6] = max 角点；用 getattr 读 Point3d 属性
    def _center_on_axis(bbox):
        return (getattr(bbox[0], axis) + getattr(bbox[6], axis)) / 2.0

    order         = sorted(range(len(object_ids)), key=lambda i: _center_on_axis(bboxes[i]))
    sorted_ids    = [object_ids[i] for i in order]
    sorted_bboxes = [bboxes[i]     for i in order]

    # ── 动态游标：第一个物体不动，从其 Max 边界开始建立游标 ──────────────
    first_max          = getattr(sorted_bboxes[0][6], axis)
    current_target_min = first_max + spacing

    moved_count = 1  # 第一个不动，但计入总数
    for oid, bbox in zip(sorted_ids[1:], sorted_bboxes[1:]):
        obj_min = getattr(bbox[0], axis)
        obj_max = getattr(bbox[6], axis)

        delta = current_target_min - obj_min
        if abs(delta) >= 1e-9:
            translation            = [0.0, 0.0, 0.0]
            translation[axis_idx]  = delta
            result = rs.MoveObject(oid, translation)
            if result is None:
                raise ValueError(
                    f"rs.MoveObject 返回 None（对象 {oid} 移动失败，"
                    "请检查 GUID 是否有效或文档是否处于锁定状态）"
                )

        # 游标推进：新 Max = 原 Max + delta，再加净间距
        current_target_min = obj_max + delta + spacing
        moved_count += 1

    return {
        "moved":   moved_count,
        "total":   len(object_ids),
        "axis":    axis,
        "spacing": spacing,
    }


def _exec_group_objects(rs, params: dict):
    import uuid as _uuid  # 标准库，用于自动生成群组名
    object_ids = params["object_ids"]
    group_name = params.get("group_name") or _uuid.uuid4().hex[:8]

    rs.AddGroup(group_name)
    rs.AddObjectsToGroup(object_ids, group_name)
    rs.Redraw()
    return {
        "group_name": group_name,
        "count":      len(object_ids),
    }


def _exec_place_on_at(rs, params: dict):
    """6 轴向语义化吸附：贴合包围盒边界 + 垂直截面自动居中。"""
    import Rhino as _Rhino  # 兜底包围盒计算需要 C# API

    target_id    = params["target_id"]
    reference_id = params["reference_id"]
    side         = params["side"]   # 已小写，由 _route_place_on_at 保证

    # ── 安全获取包围盒（兼容 Extrusion 等 rs.BoundingBox 可能返回 None 的类型）
    def _safe_bbox(oid):
        bbox = rs.BoundingBox(oid)
        if bbox is None:
            rh_guid = rs.coerceguid(oid)
            rh_obj  = (
                _Rhino.RhinoDoc.ActiveDoc.Objects.FindId(rh_guid)
                if rh_guid else None
            )
            if rh_obj is not None and rh_obj.Geometry is not None:
                bb = rh_obj.Geometry.GetBoundingBox(True)
                if bb.IsValid:
                    mn, mx = bb.Min, bb.Max
                    bbox = [
                        (mn.X, mn.Y, mn.Z), (mx.X, mn.Y, mn.Z),
                        (mx.X, mx.Y, mn.Z), (mn.X, mx.Y, mn.Z),
                        (mn.X, mn.Y, mx.Z), (mx.X, mn.Y, mx.Z),
                        (mx.X, mx.Y, mx.Z), (mn.X, mx.Y, mx.Z),
                    ]
        return bbox

    # rs.BoundingBox 返回 Point3d 对象列表；fallback 路径返回 tuple 列表。
    # 统一用 _c() 读取坐标，兼容两种类型。
    def _c(pt, idx):
        return float(getattr(pt, ("X", "Y", "Z")[idx]) if hasattr(pt, "X") else pt[idx])

    bbox_t = _safe_bbox(target_id)
    if bbox_t is None:
        raise ValueError(f"无法获取目标对象 {target_id} 的包围盒（对象不存在或几何无效）")

    bbox_r = _safe_bbox(reference_id)
    if bbox_r is None:
        raise ValueError(f"无法获取参考对象 {reference_id} 的包围盒（对象不存在或几何无效）")

    # bbox[0] = min 角点，bbox[6] = max 角点
    t_min = [_c(bbox_t[0], i) for i in range(3)]
    t_max = [_c(bbox_t[6], i) for i in range(3)]
    t_cen = [(t_min[i] + t_max[i]) / 2.0 for i in range(3)]

    r_min = [_c(bbox_r[0], i) for i in range(3)]
    r_max = [_c(bbox_r[6], i) for i in range(3)]
    r_cen = [(r_min[i] + r_max[i]) / 2.0 for i in range(3)]

    # ── 计算三维平移向量：贴合轴方向分量 + 垂直截面两轴居中分量 ───────────
    tx, ty, tz = 0.0, 0.0, 0.0

    if side == "top":
        tz = r_max[2] - t_min[2]   # Target 底面 → Reference 顶面
        tx = r_cen[0] - t_cen[0]   # XY 居中
        ty = r_cen[1] - t_cen[1]
    elif side == "bottom":
        tz = r_min[2] - t_max[2]   # Target 顶面 → Reference 底面
        tx = r_cen[0] - t_cen[0]
        ty = r_cen[1] - t_cen[1]
    elif side == "right":
        tx = r_max[0] - t_min[0]   # Target 左面 → Reference 右面
        ty = r_cen[1] - t_cen[1]   # YZ 居中
        tz = r_cen[2] - t_cen[2]
    elif side == "left":
        tx = r_min[0] - t_max[0]   # Target 右面 → Reference 左面
        ty = r_cen[1] - t_cen[1]
        tz = r_cen[2] - t_cen[2]
    elif side == "back":
        ty = r_max[1] - t_min[1]   # Target 前面 → Reference 后面
        tx = r_cen[0] - t_cen[0]   # XZ 居中
        tz = r_cen[2] - t_cen[2]
    elif side == "front":
        ty = r_min[1] - t_max[1]   # Target 后面 → Reference 前面
        tx = r_cen[0] - t_cen[0]
        tz = r_cen[2] - t_cen[2]
    else:
        raise ValueError(f"未知方位: {side!r}")

    translation = [tx, ty, tz]
    result = rs.MoveObject(target_id, translation)
    if result is None:
        raise ValueError(
            f"rs.MoveObject 返回 None（对象 {target_id} 移动失败，"
            "请检查 GUID 是否有效或文档是否处于锁定状态）"
        )

    rs.Redraw()
    return {
        "message":     f"已将目标物体吸附至参考物体的 '{side}' 方位，并完成截面居中对齐",
        "target_id":   target_id,
        "translation": [round(v, 4) for v in translation],
    }


def _exec_undo_last_action(rs, params: dict):
    rs.Command("! _Undo ", False)
    rs.Redraw()
    return {"status": "ok", "message": "已成功撤销上一步操作"}


def _exec_delete_objects(rs, params: dict):
    object_ids = params["object_ids"]
    deleted: list[str] = []
    failed: list[str] = []
    for oid in object_ids:
        if rs.DeleteObject(oid):
            deleted.append(oid)
        else:
            failed.append(oid)
    rs.Redraw()
    return {
        "deleted": deleted,
        "failed":  failed,
        "count":   len(deleted),
    }


def _exec_reset_environment(rs, params: dict):
    import scriptcontext as sc  # noqa: PLC0415

    # 物理层删除：直接操作文档数据库，不依赖 UI 命令行
    all_objs = rs.AllObjects()
    if all_objs:
        rs.DeleteObjects(all_objs)

    # 时空层抹除：调用 RhinoCommon 原生方法清空撤销内存
    if sc.doc:
        # RhinoCommon 5+ 公开的最小重载需要 purgeDeletedObjects 布尔参数。
        sc.doc.ClearUndoRecords(True)

    rs.Redraw()
    return {"message": "场景已清空，撤销栈已清除"}


# ===========================================================================
# 公开双表接口
# ===========================================================================

ROUTE_HANDLERS = {
    "/move_object":         _route_move_object,
    "/rotate_object":       _route_rotate_object,
    "/scale_object":        _route_scale_object,
    "/align_objects":       _route_align_objects,
    "/distribute_objects":  _route_distribute_objects,
    "/group_objects":       _route_group_objects,
    "/place_on_at":         _route_place_on_at,
    "/undo_last_action":    _route_undo_last_action,
    "/delete_objects":      _route_delete_objects,
    "/reset_environment":   _route_reset_environment,
}

DISPATCH_HANDLERS = {
    "move_object":        _exec_move_object,
    "rotate_object":      _exec_rotate_object,
    "scale_object":       _exec_scale_object,
    "align_objects":      _exec_align_objects,
    "distribute_objects": _exec_distribute_objects,
    "group_objects":      _exec_group_objects,
    "place_on_at":        _exec_place_on_at,
    "undo_last_action":   _exec_undo_last_action,
    "delete_objects":     _exec_delete_objects,
    "reset_environment":  _exec_reset_environment,
}
