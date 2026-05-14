"""
rhino_listener/tools_property.py  —  运行在 Rhino 8 内部（Python 3.9）

四大家族 · 属性修改（property）家族的完整实现：
  set_object_layer, set_object_color

公开接口（双表导出）：
  ROUTE_HANDLERS    — {"/endpoint": fn(h)}          HTTP 路由层：验证参数 + 工作入队
  DISPATCH_HANDLERS — {"operation": fn(rs, params)}  执行层：Rhino 主线程 rhinoscriptsyntax 调用

设计约束：
  - _route_* 函数：只使用标准库，通过参数 h（_RhinoHTTPHandler 实例）与
    HTTP 层交互。@api_error_handler 由 listener_main.py 在聚合路由表时统一包裹。
  - _exec_* 函数：仅在 Rhino 主线程（Idle 回调）被调用，可安全使用 rs.*。
    set_object_layer 需要 Rhino C# API（_Rhino.DocObjects.Layer / doc.Layers）
    在函数体内执行局部 import Rhino as _Rhino。
  - 严禁在此文件顶层 import rhinoscriptsyntax / Rhino / mcp / httpx。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("rhinocoder.http_listener")


# ===========================================================================
# HTTP 路由层 — 参数验证 + 工作入队
# (self → h：函数签名由实例方法改为普通函数，逻辑零改动)
# ===========================================================================

def _route_set_object_layer(h) -> None:
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

    layer_name = data.get("layer_name")
    if layer_name is None or not isinstance(layer_name, str) or not layer_name.strip():
        h._send_json(
            400,
            {"status": "error", "message": "Missing or invalid field: layer_name (expected non-empty string)"},
        )
        return

    h._enqueue_and_wait("set_object_layer", {"object_id": object_id, "layer_name": layer_name})


def _route_set_object_color(h) -> None:
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

    params: dict = {"object_ids": object_ids}
    for ch in ("r", "g", "b"):
        raw = data.get(ch)
        if raw is None:
            h._send_json(400, {"status": "error", "message": f"Missing field: {ch}"})
            return
        try:
            val = int(raw)
        except (TypeError, ValueError) as exc:
            h._send_json(
                400,
                {"status": "error", "message": f"Invalid {ch} value (expected integer 0-255): {exc}"},
            )
            return
        if not 0 <= val <= 255:
            h._send_json(
                400,
                {"status": "error", "message": f"{ch} must be in range 0-255, got {val}"},
            )
            return
        params[ch] = val

    h._enqueue_and_wait("set_object_color", params)


# ===========================================================================
# Rhino 主线程执行层 — rhinoscriptsyntax 调用（零逻辑改动）
# ===========================================================================

def _exec_set_object_layer(rs, params: dict):
    import Rhino as _Rhino  # 图层 C# API（DocObjects.Layer / doc.Layers）

    obj_id     = params["object_id"]
    layer_name = params["layer_name"].strip()

    rh_guid = rs.coerceguid(obj_id)
    if rh_guid is None:
        raise ValueError(f"无法解析 GUID: {obj_id!r}")

    doc    = _Rhino.RhinoDoc.ActiveDoc
    rh_obj = doc.Objects.FindId(rh_guid)
    if rh_obj is None:
        raise ValueError(f"对象不存在: {obj_id}")

    # FindByFullPath 返回图层 index，不存在时返回 -1
    layer_index = doc.Layers.FindByFullPath(layer_name, True)
    if layer_index < 0:
        new_layer      = _Rhino.DocObjects.Layer()
        new_layer.Name = layer_name
        layer_index    = doc.Layers.Add(new_layer)
        if layer_index < 0:
            raise ValueError(f"无法创建图层: {layer_name!r}")

    rh_obj.Attributes.LayerIndex = layer_index
    if not rh_obj.CommitChanges():
        raise ValueError("CommitChanges() 失败，图层修改可能未生效")

    return {
        "object_id":  obj_id,
        "layer_name": layer_name,
        "layer_index": layer_index,
    }


def _exec_set_object_color(rs, params: dict):
    object_ids   = params["object_ids"]
    r, g, b      = int(params["r"]), int(params["g"]), int(params["b"])
    for oid in object_ids:
        rs.ObjectColor(oid, [r, g, b])
    rs.Redraw()
    return {"changed": len(object_ids)}


# ===========================================================================
# 公开双表接口
# ===========================================================================

ROUTE_HANDLERS = {
    "/set_object_layer": _route_set_object_layer,
    "/set_object_color": _route_set_object_color,
}

DISPATCH_HANDLERS = {
    "set_object_layer": _exec_set_object_layer,
    "set_object_color": _exec_set_object_color,
}
