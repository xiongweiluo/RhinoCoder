"""
mcp_server/schemas_transform.py  —  运行在外部 Python 3.10+ 环境

四大家族 · 变换（transform）家族的 MCP 工具 Schema 注册：
  move_object, rotate_object, scale_object, align_objects,
  distribute_objects, group_objects, place_on_at, undo_last_action,
  delete_objects

公开接口：
  register(mcp, call_rhino) -> None
    将本家族全部 9 个工具注册到传入的 FastMCP 实例。
    call_rhino 为异步 HTTP 调用函数：
      async def call_rhino(endpoint: str, payload: dict) -> Tuple[bool, Any]

设计约束：
  - 严禁 import rhinoscriptsyntax / Rhino / scriptcontext 等 Rhino 专属库。
  - logger 继承自 rhinocoder.mcp_server（由 _client.py 配置），
    输出到 stderr，保护 stdout 给 MCP stdio transport 专用。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("rhinocoder.mcp_server")


def register(mcp, call_rhino) -> None:
    """将 transform 家族全部 8 个工具注册到 FastMCP 实例。"""

    # ── 1. move_object ──────────────────────────────────────────────────────

    @mcp.tool()
    async def move_object(
        object_id: str,
        translate_x: float,
        translate_y: float,
        translate_z: float,
    ) -> str:
        """
        将 Rhino 文档中的一个已有对象沿指定向量平移（移动）。

        【重要】本工具需要依赖其他工具返回的 GUID 作为输入：
          - object_id 必须是 Rhino 文档中现有对象的真实 GUID 字符串。
          - 通常来源于：create_sphere、create_box、create_cylinder、create_circle、
            extrude_curve_straight、boolean_difference 等工具的返回值。
          - 切勿凭空捏造 GUID，必须使用之前工具调用实际返回的字符串。

        平移向量含义（世界坐标系增量，非绝对目标坐标）：
          - translate_x/y/z 表示对象在各轴方向上的位移增量。
          - 例如 translate_x=10 表示"沿 X 轴正方向移动 10 个单位"。
          - 对象原位置 + (translate_x, translate_y, translate_z) = 新位置。

        使用场景示例：
          - "将刚创建的球体向右移动 20 个单位"
            → object_id=<sphere_guid>, translate_x=20, translate_y=0, translate_z=0
          - "把长方体沿 Z 轴抬高 5 个单位"
            → object_id=<box_guid>, translate_x=0, translate_y=0, translate_z=5
          - "把圆柱体从原点移到 (10, 20, 0) 处"
            → translate_x=10, translate_y=20, translate_z=0

        典型工作流：
          1. create_box(width=10, depth=10, height=5)  → box_guid
          2. move_object(object_id=box_guid, translate_x=20, translate_y=0, translate_z=0)

        Args:
            object_id:   要移动的对象 GUID（由其他创建工具返回的字符串）。
            translate_x: X 轴方向位移量（正值→X 正方向，负值→X 负方向）。
            translate_y: Y 轴方向位移量。
            translate_z: Z 轴方向位移量。

        Returns:
            成功时返回移动后对象 GUID 的确认消息；失败时返回详细错误描述。
        """
        logger.info(
            "move_object 调用，object_id_present=%s, translate=(%.4f,%.4f,%.4f)",
            bool(object_id), translate_x, translate_y, translate_z,
        )

        if not object_id or not isinstance(object_id, str):
            return "参数错误：object_id 必须是非空字符串 GUID"

        payload = {
            "object_id": object_id,
            "translation": [translate_x, translate_y, translate_z],
        }
        ok, result = await call_rhino("/move_object", payload)
        if not ok:
            return result
        return (
            f"成功：已将对象 {object_id} 平移 "
            f"({translate_x}, {translate_y}, {translate_z})。\n"
            f"GUID = {result}"
        )

    # ── 2. rotate_object ────────────────────────────────────────────────────

    @mcp.tool()
    async def rotate_object(
        object_id: str,
        angle_degrees: float,
        axis: Optional[list[float]] = None,
        center_point: Optional[list[float]] = None,
    ) -> str:
        """
        将 Rhino 8 文档中的一个已有对象绕指定轴旋转指定角度。

        【智能默认值策略 — 重要】
        - axis 默认 Z 轴 [0, 0, 1]：绕 Z 轴旋转是最常见的 2D 布局场景（俯视平面内的旋转），
          无需显式传入。若需绕 X 轴或 Y 轴旋转，必须显式指定。
        - center_point 默认几何中心：底层自动计算对象的包围盒中心作为旋转基准点，
          从而实现"原地旋转"。只有当旋转基准需要是其他特定坐标时，才需显式传入。

        【重要】object_id 必须是 Rhino 文档中现有对象的真实 GUID，
        来源于 create_sphere / create_box / create_cylinder 等创建工具的返回值。
        切勿凭空捏造 GUID 字符串。

        旋转方向遵循右手定则：拇指指向旋转轴正方向，四指弯曲方向为正角度方向。
          - 绕 Z 轴（[0,0,1]）angle_degrees=+90 → 逆时针旋转（俯视图）
          - 绕 Z 轴（[0,0,1]）angle_degrees=-90 → 顺时针旋转（俯视图）

        使用场景示例：
          - "将长方体原地旋转 45°"（绕自身中心、Z 轴旋转）
            → object_id=<box_guid>, angle_degrees=45
            （axis 和 center_point 均省略，自动使用 Z 轴 + 几何中心）
          - "将圆柱体绕 X 轴倾斜 30°"
            → axis=[1, 0, 0], angle_degrees=30
          - "以世界原点为中心，将对象绕 Z 轴旋转 60°"
            → center_point=[0, 0, 0], angle_degrees=60

        典型工作流：
          1. create_box(10, 5, 3)                            → box_guid
          2. rotate_object(box_guid, 45)                     → 绕自身中心、Z 轴旋转 45°

        Args:
            object_id:     要旋转的对象 GUID（由创建工具返回的字符串，不可为空）。
            angle_degrees: 旋转角度（角度制，非弧度）。正值=右手定则正方向，负值=反方向。
                           取值范围不限，可超过 360°（会继续旋转）。
            axis:          旋转轴方向向量，长度为 3 的浮点数列表，如 [0, 0, 1]。
                           向量长度不影响结果（底层自动归一化）。
                           【省略时默认 Z 轴 [0, 0, 1]】，适用于绝大多数俯视平面旋转场景。
                           常用值：X 轴=[1,0,0]，Y 轴=[0,1,0]，Z 轴=[0,0,1]（默认）。
            center_point:  旋转基准点，长度为 3 的浮点数列表，格式 [x, y, z]。
                           【省略时底层自动使用对象包围盒几何中心】，实现原地旋转效果。
                           若需绕世界原点旋转，显式传入 [0, 0, 0]。

        Returns:
            成功时返回旋转后对象 GUID 的确认消息（GUID 不变）；失败时返回详细错误描述。
        """
        logger.info(
            "rotate_object 调用，object_id_present=%s, angle=%.4f, axis=%s, center=%s",
            bool(object_id), angle_degrees, axis, center_point,
        )

        if not object_id or not isinstance(object_id, str):
            return "参数错误：object_id 必须是非空字符串 GUID"

        if axis is not None:
            if not isinstance(axis, list) or len(axis) != 3:
                return "参数错误：axis 必须是长度为 3 的浮点数列表，如 [0, 0, 1]"
            if all(v == 0 for v in axis):
                return "参数错误：axis 不能是零向量 [0, 0, 0]"

        if center_point is not None:
            if not isinstance(center_point, list) or len(center_point) != 3:
                return "参数错误：center_point 必须是长度为 3 的浮点数列表，如 [0, 0, 0]"

        payload: dict[str, Any] = {
            "object_id": object_id,
            "angle_degrees": angle_degrees,
        }
        if axis is not None:
            payload["axis"] = axis
        if center_point is not None:
            payload["center_point"] = center_point

        ok, result = await call_rhino("/rotate_object", payload)
        if not ok:
            return result

        axis_desc   = axis if axis is not None else "[0, 0, 1]（默认 Z 轴）"
        center_desc = center_point if center_point is not None else "对象几何中心（自动计算）"
        return (
            f"成功：已将对象 {object_id} 绕轴 {axis_desc}、"
            f"以 {center_desc} 为基准旋转 {angle_degrees}°。\n"
            f"GUID = {result}"
        )

    # ── 3. scale_object ─────────────────────────────────────────────────────

    @mcp.tool()
    async def scale_object(
        object_id: str,
        scale_factor: list[float],
        center_point: Optional[list[float]] = None,
    ) -> str:
        """
        将 Rhino 8 文档中的一个已有对象沿 XYZ 三个方向进行非均匀（或均匀）缩放。

        【智能默认值策略 — 重要】
        - center_point 默认几何中心：底层自动计算对象的包围盒中心作为缩放基准点，
          从而实现"原地缩放"（对象中心位置不变，向四周扩大/缩小）。
          只有当缩放基准需要固定在某个特定坐标时，才需显式传入（如以原点为锚点缩放）。

        【重要】object_id 必须是 Rhino 文档中现有对象的真实 GUID，
        来源于 create_sphere / create_box / create_cylinder 等创建工具的返回值。

        scale_factor 三个分量分别对应 X / Y / Z 方向的缩放比例：
          - 值 > 1.0：沿该轴方向放大。例如 [2.0, 2.0, 2.0] = 整体等比放大 2 倍。
          - 0 < 值 < 1.0：沿该轴方向缩小。例如 [0.5, 0.5, 1.0] = XY 平面缩小为一半，Z 不变。
          - 值 = 1.0：该轴方向不变。
          - 【禁止】值 ≤ 0：零或负值会导致几何退化或翻转，操作将被拒绝。

        使用场景示例：
          - "将球体均匀放大为原来的 2 倍"
            → scale_factor=[2.0, 2.0, 2.0]
            （center_point 省略，以自身中心为基准）
          - "将长方体 X 方向拉伸为原来的 1.5 倍，Y/Z 不变"
            → scale_factor=[1.5, 1.0, 1.0]
          - "将对象压扁：Z 方向缩小为一半"
            → scale_factor=[1.0, 1.0, 0.5]
          - "以世界原点为锚点，将对象整体缩小为原来的 0.8 倍"
            → scale_factor=[0.8, 0.8, 0.8], center_point=[0, 0, 0]

        典型工作流：
          1. create_cylinder(radius=5, height=10)              → cyl_guid
          2. scale_object(cyl_guid, [1.0, 1.0, 2.0])          → 圆柱高度翻倍，半径不变

        Args:
            object_id:    要缩放的对象 GUID（由创建工具返回的字符串，不可为空）。
            scale_factor: XYZ 三个方向的缩放比例，长度为 3 的正浮点数列表。
                          格式：[scale_x, scale_y, scale_z]，每个值必须 > 0。
                          均匀缩放示例：[2.0, 2.0, 2.0]；
                          非均匀缩放示例：[1.5, 1.0, 0.5]。
            center_point: 缩放基准点，长度为 3 的浮点数列表，格式 [x, y, z]。
                          【省略时底层自动使用对象包围盒几何中心】，对象将以自身中心原地缩放。
                          若需以原点为锚点缩放，显式传入 [0, 0, 0]。

        Returns:
            成功时返回缩放后对象 GUID 的确认消息（GUID 不变）；失败时返回详细错误描述。
        """
        logger.info(
            "scale_object 调用，object_id_present=%s, scale_factor=%s, center=%s",
            bool(object_id), scale_factor, center_point,
        )

        if not object_id or not isinstance(object_id, str):
            return "参数错误：object_id 必须是非空字符串 GUID"

        if not isinstance(scale_factor, list) or len(scale_factor) != 3:
            return "参数错误：scale_factor 必须是长度为 3 的浮点数列表，如 [1.5, 1.5, 1.0]"

        for i, v in enumerate(scale_factor):
            if not isinstance(v, (int, float)) or v <= 0:
                axis_name = ["X", "Y", "Z"][i]
                return (
                    f"参数错误：scale_factor[{i}]（{axis_name} 轴）必须为正数，"
                    f"收到 {v!r}。零或负值会导致几何退化，不允许使用。"
                )

        if center_point is not None:
            if not isinstance(center_point, list) or len(center_point) != 3:
                return "参数错误：center_point 必须是长度为 3 的浮点数列表，如 [0, 0, 0]"

        payload: dict[str, Any] = {
            "object_id": object_id,
            "scale_factor": scale_factor,
        }
        if center_point is not None:
            payload["center_point"] = center_point

        ok, result = await call_rhino("/scale_object", payload)
        if not ok:
            return result

        center_desc = center_point if center_point is not None else "对象几何中心（自动计算）"
        sx, sy, sz  = scale_factor
        return (
            f"成功：已将对象 {object_id} 以 {center_desc} 为基准，"
            f"按 X×{sx} / Y×{sy} / Z×{sz} 完成缩放。\n"
            f"GUID = {result}"
        )

    # ── 4. align_objects ────────────────────────────────────────────────────

    @mcp.tool()
    async def align_objects(
        object_ids: list[str],
        axis: str = "X",
        alignment: str = "center",
    ) -> str:
        """
        将多个 Rhino 8 对象或群组沿指定坐标轴对齐，一键完成多对象空间对齐布局。

        【群组感知（Group-Aware）】
        object_ids 中可直接传入群组名称（Group Name）。底层会将该群组视为一个刚体整体：
          - 群组的联合包围盒（所有成员的并集）参与目标值计算，权重 = 1（不会因成员多而放大权重）。
          - 对齐时整个群组一起平移，群组内各成员的相对位置保持不变。
        可混用单体 GUID 与群组名称，例如 ["guid1", "group_name_A", "guid2"]。

        对齐语义（以 axis="X" 为例）：
          - "min"：所有物体/群组的 X 轴最小边对齐到同一 X 坐标（取各单元最小值中的最小值）。
          - "center"：所有物体/群组的 X 轴包围盒中心对齐到同一 X 坐标（整体范围的中点）。
          - "max"：所有物体/群组的 X 轴最大边对齐到同一 X 坐标（取各单元最大值中的最大值）。

        【重要】单体 GUID 必须来自 Rhino 文档中真实存在的对象；群组名称必须是已通过
        group_objects 工具或 Rhino 内部命令创建的有效群组名，切勿凭空捏造。

        使用场景示例：
          - "让这 4 根柱子左对齐"
            → object_ids=[c1,c2,c3,c4], axis="X", alignment="min"
          - "将 'frame_A' 和 'frame_B' 两个群组底面对齐"
            → object_ids=["frame_A","frame_B"], axis="Z", alignment="min"
          - "单体与群组混合：guid1 和 group_B 顶面对齐"
            → object_ids=["guid1","group_B"], axis="Z", alignment="max"

        典型工作流：
          1. create_box(10,10,10) → g1；create_box(5,5,5) → g2；create_box(8,8,8) → g3
          2. group_objects([g1, g2], group_name="left_group")    ← 打组
          3. align_objects(["left_group", g3], axis="Z", alignment="min")  ← 群组+单体对齐

        Args:
            object_ids: 需要对齐的对象 GUID 或群组名称列表，至少包含 2 个元素。
                        传入群组名称时，底层将该群组作为刚体整体对齐（成员不会被拆散）。
                        可混用单体 GUID 与群组名称。
            axis:       对齐参考轴，只能是 "X"、"Y" 或 "Z"（不区分大小写）。默认 "X"。
            alignment:  对齐方式：
                          "min"    — 最小端对齐（靠左/靠下/靠前）
                          "center" — 包围盒中心对齐（居中）
                          "max"    — 最大端对齐（靠右/靠上/靠后）
                        默认 "center"。

        Returns:
            成功时返回对齐单元数量和目标基准值的确认消息；失败时返回详细错误描述。
        """
        logger.info(
            "align_objects 调用，count=%d, axis=%r, alignment=%r",
            len(object_ids) if object_ids else 0, axis, alignment,
        )

        if not object_ids or len(object_ids) < 2:
            return "参数错误：object_ids 至少需要包含 2 个 GUID"

        axis = axis.upper()
        if axis not in ("X", "Y", "Z"):
            return f"参数错误：axis 必须是 'X'、'Y' 或 'Z'，收到 {axis!r}"

        alignment = alignment.lower()
        if alignment not in ("min", "center", "max"):
            return f"参数错误：alignment 必须是 'min'、'center' 或 'max'，收到 {alignment!r}"

        axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis]

        bboxes: list[dict] = []
        for oid in object_ids:
            ok, result = await call_rhino("/get_bounding_box", {"object_id": oid})
            if not ok:
                return f"获取对象 {oid} 的包围盒失败：{result}"
            if not isinstance(result, dict):
                return f"对象 {oid} 返回了意外的包围盒格式：{result}"
            bboxes.append(result)

        mins    = [bb["vertices"][0][axis_idx] for bb in bboxes]
        maxs    = [bb["vertices"][6][axis_idx] for bb in bboxes]
        centers = [bb["center"][axis_idx]      for bb in bboxes]

        if alignment == "min":
            target = min(mins)
        elif alignment == "max":
            target = max(maxs)
        else:
            target = sum(centers) / len(centers)

        results: list[str] = []
        for oid, bb, obj_min, obj_max, obj_center in zip(
            object_ids, bboxes, mins, maxs, centers
        ):
            if alignment == "min":
                delta = target - obj_min
            elif alignment == "max":
                delta = target - obj_max
            else:
                delta = target - obj_center

            if abs(delta) < 1e-9:
                results.append(f"  {oid}: 无需移动（已对齐）")
                continue

            translation = [0.0, 0.0, 0.0]
            translation[axis_idx] = delta

            ok, move_result = await call_rhino(
                "/move_object",
                {"object_id": oid, "translation": translation},
            )
            if not ok:
                results.append(f"  {oid}: 移动失败 — {move_result}")
            else:
                results.append(
                    f"  {oid}: {axis} 轴偏移 {delta:+.4f} → 对齐完成"
                )

        summary = "\n".join(results)
        return (
            f"成功：已将 {len(object_ids)} 个对象沿 {axis} 轴执行 '{alignment}' 对齐。\n"
            f"目标基准值 = {target:.4f}\n"
            f"{summary}"
        )

    # ── 5. distribute_objects ───────────────────────────────────────────────

    @mcp.tool()
    async def distribute_objects(
        object_ids: list[str],
        spacing: float,
        axis: str = "X",
    ) -> str:
        """
        将多个 Rhino 8 对象沿指定坐标轴以固定净间距进行等距分布（阵列）。

        【本工具的意义】
        等距分布是空间布局最常见操作之一（均匀排列柱子、家具等）。手动实现需要
        逐个计算每个对象的尺寸和位置，本工具将排序、计算偏移、逐个移动的全套
        逻辑封装为一次调用，底层采用动态游标算法，避免重复查询坐标。

        分布语义：
          - 按 axis 方向中心点升序排列后，第一个物体位置保持不动。
          - 后续物体依次紧靠前一个物体，保持指定净间距（包围盒边界之间的距离）。
          - spacing 是相邻两物体包围盒边界之间的净空，不是中心距。

        【重要】所有 GUID 必须来自 Rhino 文档中真实存在的对象，切勿凭空捏造。

        使用场景示例：
          - "将这 3 根柱子沿 X 轴以 5 单位净间距均匀排列"
            → object_ids=[c1,c2,c3], axis="X", spacing=5
          - "沿 Y 轴以 10 单位净间距分布这些盒子"
            → axis="Y", spacing=10
          - "紧密排列（无间隙）：spacing=0"
            → spacing=0

        典型工作流：
          1. create_box(10,10,10) → g1；create_box(5,5,5) → g2；create_box(8,8,8) → g3
          2. distribute_objects([g1,g2,g3], spacing=5, axis="X")

        Args:
            object_ids: 需要分布的对象 GUID 列表，至少包含 2 个元素。
            spacing:    相邻两物体包围盒边界之间的净间距，必须为非负数（0 表示紧密贴合）。
            axis:       分布参考轴，只能是 "X"、"Y" 或 "Z"（不区分大小写）。默认 "X"。

        Returns:
            成功时返回分布摘要（物体数量、轴向、间距）；失败时返回详细错误描述。
        """
        logger.info(
            "distribute_objects 调用，count=%d, axis=%r, spacing=%.4f",
            len(object_ids) if object_ids else 0, axis, spacing,
        )

        if not object_ids or len(object_ids) < 2:
            return "参数错误：object_ids 至少需要包含 2 个 GUID"

        axis_upper = axis.upper()
        if axis_upper not in ("X", "Y", "Z"):
            return f"参数错误：axis 必须是 'X'、'Y' 或 'Z'，收到 {axis!r}"

        if not isinstance(spacing, (int, float)) or spacing < 0:
            return f"参数错误：spacing 必须为非负数，收到 {spacing!r}"

        payload = {
            "object_ids": object_ids,
            "axis": axis_upper,
            "spacing": float(spacing),
        }
        ok, result = await call_rhino("/distribute_objects", payload)
        if not ok:
            return result

        if isinstance(result, dict):
            moved = result.get("moved", len(object_ids))
            return (
                f"成功：已将 {moved} 个对象沿 {axis_upper} 轴"
                f"以净间距 {spacing} 完成等距分布。"
            )
        return f"成功（原始响应）: {result}"

    # ── 6. group_objects ────────────────────────────────────────────────────

    @mcp.tool()
    async def group_objects(
        object_ids: list[str],
        group_name: Optional[str] = None,
    ) -> str:
        """
        将 Rhino 8 文档中的多个对象组合成一个群组（Group）。

        群组是 Rhino 中一种非破坏性的空间层级结构：
          - 群组内各对象保留各自的几何形态和属性，不会被合并。
          - 选中群组中任意成员时，整个群组默认一起被选中。
          - 支持嵌套：群组可以再次被打入更大的群组。
          - 可通过 Rhino 的 Ungroup 命令解散群组，不影响几何体本身。

        【命名规则】
          - 若提供 group_name，使用指定名称；若不提供，底层自动生成 8 位十六进制唯一名称。

        【重要】所有 GUID 必须来自 Rhino 文档中真实存在的对象，切勿凭空捏造。

        使用场景示例：
          - "把这三根柱子打成一组"
            → object_ids=[c1, c2, c3]
          - "将底板和四根柱子编成名为 'frame_01' 的群组"
            → object_ids=[base, p1, p2, p3, p4], group_name="frame_01"

        典型工作流：
          1. create_box(20, 20, 5)   → base_guid
          2. create_cylinder(2, 10)  → col1_guid
          3. create_cylinder(2, 10)  → col2_guid
          4. group_objects([base_guid, col1_guid, col2_guid], group_name="structure")

        Args:
            object_ids:  需要打组的对象 GUID 列表，至少包含 2 个元素。
            group_name:  群组名称（可选）。省略时底层自动生成唯一名称。

        Returns:
            成功时返回群组名称及成员数量的确认消息；失败时返回详细错误描述。
        """
        logger.info(
            "group_objects 调用，count=%d, group_name_length=%d",
            len(object_ids) if object_ids else 0,
            len(group_name) if isinstance(group_name, str) else 0,
        )

        if not object_ids or len(object_ids) < 2:
            return "参数错误：object_ids 至少需要包含 2 个 GUID"

        payload: dict[str, Any] = {"object_ids": object_ids}
        if group_name:
            payload["group_name"] = group_name.strip()

        ok, result = await call_rhino("/group_objects", payload)
        if not ok:
            return result

        if isinstance(result, dict):
            name  = result.get("group_name", "")
            count = result.get("count", len(object_ids))
            return (
                f"成功：已将 {count} 个对象组合为群组。\n"
                f"group_name = {name!r}"
            )
        return f"成功（原始响应）: {result}"

    # ── 7. place_on_at ──────────────────────────────────────────────────────

    @mcp.tool()
    async def place_on_at(
        target_id: str,
        reference_id: str,
        side: str,
    ) -> str:
        """
        将目标物体（Target）精准吸附放置在参考物体（Reference）的指定方位。

        不仅在指定方向上贴合包围盒边界，同时在垂直截面上自动居中对齐：
          - "top" / "bottom" → Z 轴贴合，XY 中心同时对齐到 Reference 中心
          - "left" / "right" → X 轴贴合，YZ 中心同时对齐到 Reference 中心
          - "front" / "back" → Y 轴贴合，XZ 中心同时对齐到 Reference 中心

        【重要】两个 GUID 均必须来自 Rhino 文档中真实存在的对象，切勿凭空捏造。

        side 枚举值（不区分大小写）：
          "top"    — Target 放置于 Reference 正上方，Target 底面紧贴 Reference 顶面
          "bottom" — Target 放置于 Reference 正下方，Target 顶面紧贴 Reference 底面
          "right"  — Target 放置于 Reference 右侧（+X），Target 左面紧贴 Reference 右面
          "left"   — Target 放置于 Reference 左侧（−X），Target 右面紧贴 Reference 左面
          "back"   — Target 放置于 Reference 后侧（+Y），Target 前面紧贴 Reference 后面
          "front"  — Target 放置于 Reference 前侧（−Y），Target 后面紧贴 Reference 前面

        使用场景示例：
          - "把小球放到盒子上面，并居中"
            → target_id=<sphere_guid>, reference_id=<box_guid>, side="top"
          - "将圆柱贴靠到平板右侧，并与平板 YZ 方向居中对齐"
            → target_id=<cyl_guid>, reference_id=<plate_guid>, side="right"

        典型工作流：
          1. create_box(20, 20, 5)                             → base_guid
          2. create_sphere(3)                                  → sphere_guid
          3. place_on_at(sphere_guid, base_guid, "top")        → 球体吸附至盒顶面中心

        Args:
            target_id:    要移动的目标对象 GUID（由创建工具或 get_selected_objects 返回）。
            reference_id: 作为放置基准的参考对象 GUID。
            side:         放置方位，枚举值（不区分大小写）：
                          "top" | "bottom" | "left" | "right" | "front" | "back"

        Returns:
            成功时返回吸附结果确认消息（含实际平移向量）；失败时返回详细错误描述。
        """
        logger.info(
            "place_on_at 调用，target_present=%s, reference_present=%s, side=%r",
            bool(target_id), bool(reference_id), side,
        )

        if not target_id or not isinstance(target_id, str):
            return "参数错误：target_id 必须是非空字符串 GUID"
        if not reference_id or not isinstance(reference_id, str):
            return "参数错误：reference_id 必须是非空字符串 GUID"

        valid_sides = ("top", "bottom", "left", "right", "front", "back")
        side_lower  = side.lower() if isinstance(side, str) else ""
        if side_lower not in valid_sides:
            return f"参数错误：side 必须是 {valid_sides} 之一，收到 {side!r}"

        payload = {
            "target_id":    target_id,
            "reference_id": reference_id,
            "side":         side_lower,
        }
        ok, result = await call_rhino("/place_on_at", payload)
        if not ok:
            return result

        if isinstance(result, dict):
            msg   = result.get("message", "吸附完成")
            trans = result.get("translation", [])
            return (
                f"成功：{msg}\n"
                f"target_id  = {target_id}\n"
                f"平移向量   = {trans}"
            )
        return f"成功（原始响应）: {result}"

    # ── 8. delete_objects ───────────────────────────────────────────────────

    @mcp.tool()
    async def delete_objects(object_ids: list[str]) -> str:
        """
        删除场景中指定 ID 的对象。比撤销更精准。

        【与 undo_last_action 的区别】
        - undo_last_action 按时间线回退，会撤销掉该步之后的所有操作，存在误伤风险。
        - delete_objects 按空间维度精准定位并删除指定 GUID，不影响其他对象。

        【重要】所有 GUID 必须来自 Rhino 文档中真实存在的对象，切勿凭空捏造。
        已被删除或不存在的 GUID 会出现在返回结果的 failed 列表中，不会导致整体失败。

        使用场景示例：
          - "删除刚才创建的那个球体"
            → object_ids=[<sphere_guid>]
          - "把 A、B、C 三个对象都删掉"
            → object_ids=[guid_A, guid_B, guid_C]

        Args:
            object_ids: 要删除的对象 GUID 字符串列表，至少 1 个元素。

        Returns:
            成功时返回删除数量及失败列表；失败时返回详细错误描述。
        """
        logger.info("delete_objects 调用，count=%d", len(object_ids) if object_ids else 0)

        if not object_ids or not isinstance(object_ids, list):
            return "参数错误：object_ids 必须是非空列表"

        payload = {"object_ids": list(object_ids)}
        ok, result = await call_rhino("/delete_objects", payload)
        if not ok:
            return result

        if isinstance(result, dict):
            count  = result.get("count", 0)
            failed = result.get("failed", [])
            msg = f"成功：已删除 {count} 个对象。"
            if failed:
                msg += f"\n以下对象删除失败（GUID 不存在或已删除）：{failed}"
            return msg
        return f"成功（原始响应）: {result}"

    # ── 9. undo_last_action ─────────────────────────────────────────────────

    @mcp.tool()
    async def undo_last_action() -> str:
        """
        撤销 Rhino 8 中的上一步操作（等同于 Ctrl+Z）。

        当用户表示操作有误、要求撤销或返回上一步时调用此工具。
        本工具无需任何参数，直接触发 Rhino 内置 Undo 命令。

        使用场景示例：
          - "撤销在 Rhino 中的上一步操作。注意：该工具一次只能撤销一个原子的 Rhino 步骤。如果用户要求撤销『刚才的一系列操作』（比如刚刚连续执行了移动和缩放），你需要在思考后，根据你刚才调用的工具次数，连续多次调用此工具，直到恢复原状。"
          - "不对，回退一步"
          - "undo"

        Returns:
            成功时返回确认消息；失败时返回详细错误描述。
        """
        logger.info("undo_last_action 调用")
        ok, result = await call_rhino("/undo_last_action", {})
        if not ok:
            return result
        if isinstance(result, dict):
            return result.get("message", "已成功撤销上一步操作")
        return "已成功撤销上一步操作"
