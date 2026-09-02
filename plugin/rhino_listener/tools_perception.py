"""
rhino_listener/tools_perception.py  —  运行在 Rhino 8 内部（Python 3.9）

四大家族 · 视觉感知（perception）家族的完整实现：
  get_selected_objects, get_objects_by_name, get_object_info,
  get_bounding_box, get_scene_summary

公开接口（双表导出）：
  ROUTE_HANDLERS    — {"/endpoint": fn(h)}          HTTP 路由层：验证参数 + 工作入队
  DISPATCH_HANDLERS — {"operation": fn(rs, params)}  执行层：Rhino 主线程 rhinoscriptsyntax 调用

【核心算法说明】
  _exec_get_selected_objects — 即时暴力扫盘：直接遍历 doc.Objects 检查底层 IsSelected
                               状态，绕过 Mac UI 选择集缓存，是 Mac 环境最稳妥的方式。
  _exec_get_objects_by_name  — 优先 rs.AllObjects() 全图层扫描（含锁定/隐藏图层），
                               失败时回退到 doc.Objects 遍历。
  _exec_get_bounding_box     — 群组感知（Group-Aware）：群组路径联合所有成员包围盒；
                               单体路径包含 Extrusion 类型的 C# API 兜底。
  _exec_get_scene_summary    — 场景审计员：采集 object_id / name / type / center /
                               layer / color / groups / size 全量属性，最多返回 50 个。

设计约束：
  - _route_* 函数：只使用标准库，通过参数 h（_RhinoHTTPHandler 实例）与
    HTTP 层交互。@api_error_handler 由 listener_main.py 在聚合路由表时统一包裹。
  - _exec_* 函数：仅在 Rhino 主线程（Idle 回调）被调用，可安全使用 rs.*。
    需要 Rhino C# API 的函数在函数体内执行局部 import Rhino as _Rhino。
  - _OBJECT_TYPE_MAP 从同包的 _types.py 导入，此为包内相对导入，不违反约束。
  - 严禁在此文件顶层 import rhinoscriptsyntax / Rhino / mcp / httpx。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ._types import _OBJECT_TYPE_MAP
from .validation import is_guid

logger = logging.getLogger("rhinocoder.http_listener")


# ===========================================================================
# HTTP 路由层 — 参数验证 + 工作入队
# (self → h：函数签名由实例方法改为普通函数，逻辑零改动)
# ===========================================================================

def _route_get_selected_objects(h) -> None:
    # 无需请求体：直接派发查询，返回当前选中对象的 GUID 列表（可能为空）
    h._enqueue_and_wait("get_selected_objects", {})


def _route_get_objects_by_name(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    name = data.get("name")
    if name is None or not isinstance(name, str):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: name (expected non-empty string)"},
        )
        return

    h._enqueue_and_wait("get_objects_by_name", {"name": name})


def _route_get_object_info(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_id = data.get("object_id")
    if not is_guid(object_id):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: object_id (expected non-empty string GUID)"},
        )
        return

    h._enqueue_and_wait("get_object_info", {"object_id": object_id})


def _route_get_bounding_box(h) -> None:
    data = h._parse_body()
    if data is None:
        return

    object_id = data.get("object_id")
    if not is_guid(object_id):
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: object_id (expected non-empty string GUID)"},
        )
        return

    h._enqueue_and_wait("get_bounding_box", {"object_id": object_id})


def _route_get_scene_summary(h) -> None:
    # 无需请求体：直接派发查询，返回场景中所有可见对象的摘要列表
    h._enqueue_and_wait("get_scene_summary", {})


def _route_capture_viewport(h) -> None:
    """导出当前视口；证据文件只能写入项目的审核目录。"""
    data = h._parse_body()
    if data is None:
        return
    relative_path = data.get("relative_path")
    if not isinstance(relative_path, str) or not relative_path.strip():
        h._send_json(400, {"status": "error", "message": "Missing relative_path"})
        return
    path = Path(relative_path)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.suffix.lower() != ".png"
        or path.parts[:2] != ("data", "review_batches")
    ):
        h._send_json(400, {"status": "error", "message": "Invalid evidence path"})
        return
    h._enqueue_and_wait("capture_viewport", {"relative_path": str(path)})


# ===========================================================================
# Rhino 主线程执行层 — rhinoscriptsyntax 调用（零逻辑改动）
# ===========================================================================

def _exec_get_selected_objects(rs, params: dict):
    """
    即时暴力扫盘：直接遍历内存中所有对象检查底层 IsSelected 状态，
    绕过 Mac UI 选择集缓存和焦点依赖，是 Mac 环境下最稳妥的方式。
    """
    import Rhino as _Rhino

    doc = _Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        open_docs = _Rhino.RhinoDoc.OpenDocuments()
        if open_docs and len(open_docs) > 0:
            doc = open_docs[0]

    ids = []
    if doc is not None:
        for obj in doc.Objects:
            if obj.IsSelected(False) > 0:
                ids.append(str(obj.Id))

    if not ids:
        logger.info("扫盘完毕，未发现选中状态的对象")
    return {"object_ids": ids}


def _exec_capture_viewport(rs, params: dict):
    """在 Rhino 主线程生成真实视口 PNG，供 AI 初审和批量人工复核使用。"""
    import Rhino as _Rhino

    project_root = Path(__file__).resolve().parents[2]
    output_path = (project_root / params["relative_path"]).resolve()
    if not output_path.is_relative_to(project_root):
        raise ValueError("evidence path escapes project root")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    view = _Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
    if view is None:
        raise RuntimeError("没有可用的 Rhino 活动视口")
    capture = _Rhino.Display.ViewCapture()
    capture.Width, capture.Height = 1280, 800
    capture.ScaleScreenItems = False
    bitmap = capture.CaptureToBitmap(view)
    if bitmap is None:
        raise RuntimeError("Rhino 视口截图失败")
    try:
        bitmap.Save(str(output_path))
    finally:
        bitmap.Dispose()
    logger.info("已导出 Rhino 视口证据: %s", output_path)
    return {"visual_evidence": params["relative_path"]}


def _exec_get_objects_by_name(rs, params: dict):
    """
    优先使用 rs.AllObjects() 全图层扫描（含锁定/隐藏图层），
    失败时回退到 doc.Objects 直接遍历。
    """
    import Rhino as _Rhino  # 仅 fallback 路径需要

    name        = params["name"]
    search_name = name.strip()
    matched     = []

    # 优先使用 rs.AllObjects()：在 Mac 版 Rhino 上比直接遍历 doc.Objects 更可靠，
    # 能正确扫描所有图层（包括锁定/隐藏图层）的对象。
    try:
        import rhinoscriptsyntax as _rs_local  # noqa: PLC0415
        all_ids = _rs_local.AllObjects(select=False, include_lights=False, include_grips=False)
        if all_ids:
            for oid in all_ids:
                obj_name = _rs_local.ObjectName(oid)
                if obj_name and obj_name.strip() == search_name:
                    matched.append(str(oid))
    except Exception as _e:
        logger.warning("rs.AllObjects() 扫描失败，回退到 doc.Objects: %s", _e)
        doc = _Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            open_docs = _Rhino.RhinoDoc.OpenDocuments()
            if open_docs and len(open_docs) > 0:
                doc = open_docs[0]
        if doc is not None:
            for obj in doc.Objects:
                attr_name = obj.Attributes.Name if obj.Attributes else None
                if attr_name and attr_name.strip() == search_name:
                    matched.append(str(obj.Id))

    logger.debug("get_objects_by_name('%s') 共找到 %d 个匹配对象", search_name, len(matched))
    return {"object_ids": matched}


def _exec_get_object_info(rs, params: dict):
    obj_id    = params["object_id"]
    type_int  = rs.ObjectType(obj_id)
    type_name = _OBJECT_TYPE_MAP.get(type_int, f"Unknown({type_int})")
    return {
        "object_id": obj_id,
        "type":  type_name,
        "name":  rs.ObjectName(obj_id) or "",
        "layer": rs.ObjectLayer(obj_id) or "",
    }


def _exec_get_bounding_box(rs, params: dict):
    """
    群组感知（Group-Aware）包围盒查询：
      - 群组路径：联合所有成员的包围盒（BoundingBox.Union 兜底）
      - 单体路径：rs.BoundingBox + Extrusion C# API 兜底
    """
    import Rhino as _Rhino  # 群组联合包围盒 + Extrusion 兜底均需 C# API

    obj_id = params["object_id"]

    if rs.IsGroup(obj_id):
        # ── 群组路径：联合所有成员的包围盒 ──────────────────────────────
        members = rs.ObjectsByGroup(obj_id) or []
        if not members:
            raise ValueError(f"群组 '{obj_id}' 不含任何成员对象，无法计算包围盒")
        bbox = rs.BoundingBox(members)
        if bbox is None:
            combined_bb = None
            for mid in members:
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
                raise ValueError(
                    f"无法计算群组 '{obj_id}' 的联合包围盒（成员几何全部无效）"
                )
            mn, mx = combined_bb.Min, combined_bb.Max
            bbox = [
                (mn.X, mn.Y, mn.Z), (mx.X, mn.Y, mn.Z),
                (mx.X, mx.Y, mn.Z), (mn.X, mx.Y, mn.Z),
                (mn.X, mn.Y, mx.Z), (mx.X, mn.Y, mx.Z),
                (mx.X, mx.Y, mx.Z), (mn.X, mx.Y, mx.Z),
            ]
    else:
        # ── 单体路径：原有逻辑，Extrusion 兜底 ──────────────────────────
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
            raise ValueError(
                f"无法获取对象 {obj_id} 的包围盒（对象不存在或几何无效）"
            )

    def _r4(v):
        return round(float(v), 4)

    vertices = [[_r4(pt[0]), _r4(pt[1]), _r4(pt[2])] for pt in bbox]
    center   = [round(sum(v[i] for v in vertices) / 8, 4) for i in range(3)]
    return {
        "object_id": obj_id,
        "vertices":  vertices,
        "center":    center,
    }


def _exec_get_scene_summary(rs, params: dict):
    """
    场景审计员：采集所有可见对象的精简信息，每个对象返回 8 个属性字段：
    object_id / name / type / center / layer / color / groups / size。
    最多返回前 50 个对象，防止 Token 爆炸。
    """
    objs   = rs.NormalObjects() or []
    total  = len(objs)
    capped = total > 50
    objs   = objs[:50]

    def _pt_val(pt, i):
        return float(getattr(pt, ("X", "Y", "Z")[i]) if hasattr(pt, "X") else pt[i])

    result_list = []
    for obj in objs:
        obj_id   = str(obj)
        name     = rs.ObjectName(obj) or "Unnamed"
        type_int = rs.ObjectType(obj)
        type_str = _OBJECT_TYPE_MAP.get(type_int, f"Unknown({type_int})")

        bbox = rs.BoundingBox(obj)
        if bbox is not None:
            try:
                mn, mx = bbox[0], bbox[6]
                center = [
                    round((_pt_val(mn, 0) + _pt_val(mx, 0)) / 2.0, 2),
                    round((_pt_val(mn, 1) + _pt_val(mx, 1)) / 2.0, 2),
                    round((_pt_val(mn, 2) + _pt_val(mx, 2)) / 2.0, 2),
                ]
                size = [
                    round(abs(_pt_val(mx, 0) - _pt_val(mn, 0)), 2),
                    round(abs(_pt_val(mx, 1) - _pt_val(mn, 1)), 2),
                    round(abs(_pt_val(mx, 2) - _pt_val(mn, 2)), 2),
                ]
            except Exception:
                center = [0.0, 0.0, 0.0]
                size   = [0.0, 0.0, 0.0]
        else:
            center = [0.0, 0.0, 0.0]
            size   = [0.0, 0.0, 0.0]

        layer = rs.ObjectLayer(obj) or ""

        try:
            c     = rs.ObjectColor(obj)
            color = [int(c.R), int(c.G), int(c.B)]
        except Exception:
            color = [0, 0, 0]

        groups = list(rs.ObjectGroups(obj) or [])

        result_list.append({
            "object_id": obj_id,
            "name":      name,
            "type":      type_str,
            "center":    center,
            "layer":     layer,
            "color":     color,
            "groups":    groups,
            "size":      size,
        })

    return {
        "objects": result_list,
        "total":   total,
        "capped":  capped,
    }


# ===========================================================================
# 公开双表接口
# ===========================================================================

ROUTE_HANDLERS = {
    "/get_selected_objects": _route_get_selected_objects,
    "/get_objects_by_name":  _route_get_objects_by_name,
    "/get_object_info":      _route_get_object_info,
    "/get_bounding_box":     _route_get_bounding_box,
    "/get_scene_summary":    _route_get_scene_summary,
    "/capture_viewport":     _route_capture_viewport,
}

DISPATCH_HANDLERS = {
    "get_selected_objects": _exec_get_selected_objects,
    "get_objects_by_name":  _exec_get_objects_by_name,
    "get_object_info":      _exec_get_object_info,
    "get_bounding_box":     _exec_get_bounding_box,
    "get_scene_summary":    _exec_get_scene_summary,
    "capture_viewport":     _exec_capture_viewport,
}
