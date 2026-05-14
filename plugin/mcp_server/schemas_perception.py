"""
mcp_server/schemas_perception.py  —  运行在外部 Python 3.10+ 环境

四大家族 · 视觉感知（perception）家族的 MCP 工具 Schema 注册：
  get_selected_objects, get_objects_by_name, get_object_info,
  get_bounding_box, get_scene_summary

公开接口：
  register(mcp, call_rhino) -> None
    将本家族全部 5 个工具注册到传入的 FastMCP 实例。
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
    """将 perception 家族全部 5 个工具注册到 FastMCP 实例。"""

    # ── 1. get_selected_objects ─────────────────────────────────────────────

    @mcp.tool()
    async def get_selected_objects() -> str:
        """
        返回 Rhino 8 当前文档中所有已被用户选中对象的 GUID 列表。

        【空间推理基础工具】
        这是 Agent 进行空间推理的起点：先用此工具获知用户当前关注的对象，
        再调用 get_object_info / get_bounding_box 深入分析，避免盲目操作。

        行为说明：
          - 若用户当前未选中任何对象，返回空列表 []，不报错。
          - 返回的每个 GUID 可直接传入 get_object_info、get_bounding_box、
            move_object、boolean_difference 等工具。

        Returns:
            成功时返回 JSON 格式字典，包含键 "object_ids"（GUID 字符串列表）；
            失败时返回详细错误描述。
            示例（有选中）：{"object_ids": ["3f2a1c4b-...", "7b4e8d2a-..."]}
            示例（无选中）：{"object_ids": []}
        """
        logger.info("get_selected_objects 调用")
        ok, result = await call_rhino("/get_selected_objects", {})
        if not ok:
            return result
        object_ids = result.get("object_ids", []) if isinstance(result, dict) else []
        return (
            f"当前选中 {len(object_ids)} 个对象。\n"
            f"object_ids = {object_ids}"
        )

    # ── 2. get_objects_by_name ──────────────────────────────────────────────

    @mcp.tool()
    async def get_objects_by_name(name: str) -> str:
        """
        通过物体名称获取 GUID，用于精准定位场景中已命名的几何体。

        【语义寻址工具】
        相比 get_selected_objects（依赖用户手动选择），此工具通过 Rhino 对象的
        Name 属性进行精确匹配，无需用户交互，是最健壮的对象定位方式。

        行为说明：
          - 精确匹配（区分大小写）：仅返回 Attributes.Name 与 name 完全相同的对象。
          - 支持多重匹配：若场景中存在多个同名对象，全部返回。
          - 若无匹配，返回空列表 []，不报错。

        给对象命名的方式：
          - 在 Rhino 中选中对象 → Properties 面板 → Name 字段
          - 或通过 set_object_name 工具（若已注册）

        使用场景示例：
          - "获取名为 'wall_01' 的物体 GUID"
            → name="wall_01"
          - "找到场景中所有命名为 'column' 的柱子"
            → name="column"，返回全部匹配 GUID

        典型工作流：
          1. get_objects_by_name("base_plate")      → ["guid1"]
          2. get_bounding_box("guid1")              → 获取尺寸和位置
          3. move_object("guid1", ...)              → 精准移动

        Args:
            name: 要搜索的对象名称字符串，与 Rhino 对象的 Name 属性完全匹配。

        Returns:
            成功时返回包含匹配对象 GUID 列表的描述；失败时返回详细错误描述。
            示例（有匹配）：找到 2 个名为 'column' 的对象。object_ids = [...]
            示例（无匹配）：未找到名为 'column' 的对象。object_ids = []
        """
        logger.info("get_objects_by_name 调用，name=%r", name)

        if not isinstance(name, str):
            return "参数错误：name 必须是字符串"

        ok, result = await call_rhino("/get_objects_by_name", {"name": name})
        if not ok:
            return result

        object_ids = result.get("object_ids", []) if isinstance(result, dict) else []
        if object_ids:
            return (
                f"找到 {len(object_ids)} 个名为 {name!r} 的对象。\n"
                f"object_ids = {object_ids}"
            )
        return f"未找到名为 {name!r} 的对象。object_ids = []"

    # ── 3. get_object_info ──────────────────────────────────────────────────

    @mcp.tool()
    async def get_object_info(object_id: str) -> str:
        """
        获取 Rhino 8 文档中指定对象的元数据：类型、名称和图层。

        【空间推理基础工具】
        在执行任何修改操作（移动、布尔运算等）之前，Agent 应先调用此工具
        确认目标对象的类型和所在图层，避免对错误类型的对象执行无效操作。

        类型字段语义（"type" 字段为人类可读字符串，非原始整数）：
          Point / PointCloud / Curve / Surface / Polysurface / Mesh /
          Light / Annotation / InstanceReference / ...

        典型工作流：
          1. get_selected_objects()            → ["guid1"]
          2. get_object_info("guid1")          → type="Polysurface", layer="Default"
          3. 确认类型后再执行 boolean_difference 等操作

        Args:
            object_id: 目标对象的 GUID 字符串（由创建工具或 get_selected_objects 返回）。

        Returns:
            成功时返回包含 object_id、type、name、layer 的 JSON 字典描述；
            失败时返回详细错误描述。
        """
        logger.info("get_object_info 调用，object_id=%s", object_id)

        if not object_id or not isinstance(object_id, str):
            return "参数错误：object_id 必须是非空字符串 GUID"

        ok, result = await call_rhino("/get_object_info", {"object_id": object_id})
        if not ok:
            return result

        if isinstance(result, dict):
            info = result
        else:
            return f"意外响应格式: {result}"

        return (
            f"对象信息：\n"
            f"  object_id = {info.get('object_id')}\n"
            f"  type      = {info.get('type')}\n"
            f"  name      = {info.get('name') or '(未命名)'}\n"
            f"  layer     = {info.get('layer')}"
        )

    # ── 4. get_bounding_box ─────────────────────────────────────────────────

    @mcp.tool()
    async def get_bounding_box(object_id: str) -> str:
        """
        获取 Rhino 8 文档中指定对象的世界坐标系包围盒（Axis-Aligned Bounding Box）。

        【空间推理基础工具】
        这是 Agent 进行精确空间推理不可或缺的工具：
          - 通过 center 判断对象当前位置，计算平移向量
          - 通过 vertices 获取尺寸（max-min），判断是否需要缩放
          - 通过 vertices[0]（min角）和 vertices[6]（max角）快速推断包围盒范围
          - 配合 move_object 实现精确对齐和布局

        坐标精度：所有数值统一保留 4 位小数，兼顾建模精度与 Token 效率。

        返回结构：
          {
            "object_id": "<GUID>",
            "vertices": [[x,y,z], ...],   # 8 个角点，世界坐标系
            "center":   [cx, cy, cz]      # 包围盒中心点
          }
        vertices 顺序（Rhino 标准）：
          [0] = (min_x, min_y, min_z)  [1] = (max_x, min_y, min_z)
          [2] = (max_x, max_y, min_z)  [3] = (min_x, max_y, min_z)
          [4] = (min_x, min_y, max_z)  [5] = (max_x, min_y, max_z)
          [6] = (max_x, max_y, max_z)  [7] = (min_x, max_y, max_z)

        Args:
            object_id: 目标对象的 GUID 字符串（由创建工具或 get_selected_objects 返回）。

        Returns:
            成功时返回格式化的包围盒信息（8 顶点 + 中心点，坐标保留 4 位小数）；
            失败时返回详细错误描述。
        """
        logger.info("get_bounding_box 调用，object_id=%s", object_id)

        if not object_id or not isinstance(object_id, str):
            return "参数错误：object_id 必须是非空字符串 GUID"

        ok, result = await call_rhino("/get_bounding_box", {"object_id": object_id})
        if not ok:
            return result

        if isinstance(result, dict):
            bbox = result
        else:
            return f"意外响应格式: {result}"

        vertices = bbox.get("vertices", [])
        center   = bbox.get("center", [])
        min_pt   = vertices[0] if vertices else "N/A"
        max_pt   = vertices[6] if len(vertices) > 6 else "N/A"
        return (
            f"包围盒信息（object_id={bbox.get('object_id')}）：\n"
            f"  min 角点 = {min_pt}\n"
            f"  max 角点 = {max_pt}\n"
            f"  center   = {center}\n"
            f"  全部 8 顶点 = {vertices}"
        )

    # ── 5. get_scene_summary ────────────────────────────────────────────────

    @mcp.tool()
    async def get_scene_summary() -> str:
        """
        获取当前 Rhino 场景中所有可见物体的精简信息列表。

        【场景审计员 — 闭环视觉感知核心工具】
        当你不确定场景状态、找不到物体、需要获取物体尺寸/颜色/群组，
        或者用户让你基于现有场景进行修改时，请务必先调用此工具『看一眼』。

        行为说明：
          - 仅返回可见（非隐藏、非锁定）的普通对象，忽略灯光、注释等辅助对象。
          - 每个物体返回：object_id、name、type、center、layer、color、groups、size。
          - 最多返回前 50 个对象，防止 Token 爆炸。

        返回字段说明：
          - object_id: Rhino 对象的 GUID 字符串，可直接传入其他工具使用。
          - name:      对象名称，未命名时为 "Unnamed"。
          - type:      对象类型的人类可读字符串（如 "Polysurface"、"Extrusion"、"Curve"）。
          - center:    包围盒中心点 [x, y, z]，保留 2 位小数。
          - layer:     对象所在图层名。
          - color:     显示颜色 [R, G, B]，ByLayer 时自动解析为图层实际颜色。
          - groups:    对象所属群组名称列表，不属于任何组时为 []。
          - size:      包围盒尺寸 [长, 宽, 高]（XYZ 方向），保留 2 位小数。

        使用场景示例：
          - "帮我看看场景里有什么" → 调用此工具
          - "找到所有红色的物体" → 调用此工具后按 color 筛选
          - "在现有场景基础上添加一个盖板" → 先调用此工具了解现有物体尺寸和位置

        Returns:
            成功时返回包含场景摘要的描述（对象数量 + 详细列表）；失败时返回详细错误描述。
        """
        logger.info("get_scene_summary 调用")
        ok, result = await call_rhino("/get_scene_summary", {})
        if not ok:
            return result

        if isinstance(result, dict):
            objects  = result.get("objects", [])
            total    = result.get("total", len(objects))
            capped   = result.get("capped", False)
            cap_note = f"（场景共有 {total} 个对象，已截取前 50 个）" if capped else ""
            return (
                f"场景中共有 {len(objects)} 个可见对象{cap_note}。\n"
                f"objects = {objects}"
            )
        return f"成功（原始响应）: {result}"
