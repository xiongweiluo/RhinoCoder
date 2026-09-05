"""
mcp_server/schemas_property.py  —  运行在外部 Python 3.10+ 环境

四大家族 · 属性修改（property）家族的 MCP 工具 Schema 注册：
  set_object_layer, set_object_color

公开接口：
  register(mcp, call_rhino) -> None
    将本家族全部 2 个工具注册到传入的 FastMCP 实例。
    call_rhino 为异步 HTTP 调用函数：
      async def call_rhino(endpoint: str, payload: dict) -> Tuple[bool, Any]

设计约束：
  - 严禁 import rhinoscriptsyntax / Rhino / scriptcontext 等 Rhino 专属库。
  - logger 继承自 rhinocoder.mcp_server（由 _client.py 配置），
    输出到 stderr，保护 stdout 给 MCP stdio transport 专用。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("rhinocoder.mcp_server")


def register(mcp, call_rhino) -> None:
    """将 property 家族全部 2 个工具注册到 FastMCP 实例。"""

    # ── 1. set_object_layer ─────────────────────────────────────────────────

    @mcp.tool()
    async def set_object_layer(object_id: str, layer_name: str) -> str:
        """
        修改 Rhino 8 文档中指定对象的图层归属。如果目标图层不存在，则自动创建。

        【重要】本工具需要依赖其他工具返回的 GUID：
          - object_id 必须是 Rhino 文档中现有对象的真实 GUID 字符串。
          - 通常来源于：create_sphere / create_box / get_selected_objects 等工具的返回值。
          - 切勿凭空捏造 GUID，必须使用之前工具调用实际返回的字符串。

        图层说明：
          - layer_name 支持 Rhino 图层全路径格式（如 "Parent::Child"）。
          - 若图层不存在，自动以该名称创建新图层（默认颜色）。
          - 同一对象只能属于一个图层，操作会覆盖原图层归属。

        使用场景示例：
          - "把这个球体移到 'Structure' 图层"
            → object_id=<sphere_guid>, layer_name="Structure"
          - "将刚创建的长方体归入 'Walls' 图层（若不存在则创建）"
            → object_id=<box_guid>, layer_name="Walls"

        典型工作流：
          1. create_box(10, 10, 5)                     → box_guid
          2. set_object_layer(box_guid, "Structure")   → 自动创建图层并归入

        Args:
            object_id:  要修改的对象 GUID（由其他创建工具或 get_selected_objects 返回的字符串）。
            layer_name: 目标图层名称，不存在时自动创建。支持全路径格式（"Parent::Child"）。

        Returns:
            成功时返回确认消息，包含对象 ID、图层名称和图层索引；失败时返回详细错误描述。
        """
        logger.info(
            "set_object_layer 调用，object_id_present=%s, layer_name_length=%d",
            bool(object_id),
            len(layer_name) if isinstance(layer_name, str) else 0,
        )

        if not object_id or not isinstance(object_id, str):
            return "参数错误：object_id 必须是非空字符串 GUID"
        if not layer_name or not isinstance(layer_name, str) or not layer_name.strip():
            return "参数错误：layer_name 必须是非空字符串"

        payload = {"object_id": object_id, "layer_name": layer_name}
        ok, result = await call_rhino("/set_object_layer", payload)
        if not ok:
            return result

        if isinstance(result, dict):
            return (
                f"成功：已将对象 {result.get('object_id')} 移至图层 {result.get('layer_name')!r}。\n"
                f"layer_index = {result.get('layer_index')}"
            )
        return f"成功（原始响应）: {result}"

    # ── 2. set_object_color ─────────────────────────────────────────────────

    @mcp.tool()
    async def set_object_color(
        object_ids: list[str],
        r: int,
        g: int,
        b: int,
    ) -> str:
        """
        修改 Rhino 8 文档中一个或多个对象的显示颜色（RGB）。

        颜色立即应用并刷新视口，无需手动 Redraw。

        【重要】所有 GUID 必须来自 Rhino 文档中真实存在的对象，切勿凭空捏造。

        使用场景示例：
          - "把这个球体改成红色"
            → object_ids=[sphere_guid], r=255, g=0, b=0
          - "将选中的柱子全部改为蓝色"
            → object_ids=[c1, c2, c3], r=0, g=0, b=255
          - "把长方体改成半透明灰（RGB 128,128,128）"
            → r=128, g=128, b=128

        典型工作流：
          1. create_box(10, 10, 10)                         → box_guid
          2. set_object_color([box_guid], r=255, g=165, b=0) → 橙色

        Args:
            object_ids: 需要改色的对象 GUID 列表，至少包含 1 个元素。
            r: 红色通道，整数，范围 0–255。
            g: 绿色通道，整数，范围 0–255。
            b: 蓝色通道，整数，范围 0–255。

        Returns:
            成功时返回已改色对象数量的确认消息；失败时返回详细错误描述。
        """
        logger.info(
            "set_object_color 调用，count=%d, rgb=(%d,%d,%d)",
            len(object_ids) if object_ids else 0, r, g, b,
        )

        if not object_ids:
            return "参数错误：object_ids 不能为空列表"

        for ch_name, val in (("r", r), ("g", g), ("b", b)):
            if not isinstance(val, int) or not 0 <= val <= 255:
                return f"参数错误：{ch_name} 必须是 0–255 的整数，收到 {val!r}"

        payload = {"object_ids": object_ids, "r": r, "g": g, "b": b}
        ok, result = await call_rhino("/set_object_color", payload)
        if not ok:
            return result

        changed = result.get("changed", len(object_ids)) if isinstance(result, dict) else len(object_ids)
        return (
            f"成功：已将 {changed} 个对象的颜色设置为 RGB({r}, {g}, {b})。"
        )
