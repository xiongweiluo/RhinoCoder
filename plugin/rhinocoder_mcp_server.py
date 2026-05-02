"""
plugin/rhinocoder_mcp_server.py  —  运行在外部 VS Code 终端（Python 3.10+）

架构
────────────────────────────────────────────────────────────────────
[Claude Desktop / Agent]
      │  MCP stdio
      ▼
[本文件: FastMCP Server（stdio transport）]
      │  create_sphere() / create_box() / create_cylinder() / create_line() 工具被调用
      │  POST http://127.0.0.1:8080/<endpoint>  {params}
      ▼
[Rhino 内部: rhino_http_listener.py]
      │  JSON 响应 {"status": "ok", "guid": "..."}
      ▼
[本文件返回结果给 Agent]
────────────────────────────────────────────────────────────────────

依赖（外部 Python 环境中安装）:
    pip install mcp httpx

Claude Desktop 配置（~/Library/Application Support/Claude/claude_desktop_config.json）:
    {
      "mcpServers": {
        "rhinocoder": {
          "command": "python",
          "args": ["/path/to/RhinoCoder/plugin/rhinocoder_mcp_server.py"]
        }
      }
    }

前提: Rhino 8 内已执行 rhino_http_listener.start_listener()
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Tuple

# ---------------------------------------------------------------------------
# Logging —— 必须输出到 stderr
# stdio transport 使用 stdout 传输 MCP 协议数据，任何写入 stdout 的日志
# 都会破坏协议帧，导致 Claude Desktop 解析失败。
# ---------------------------------------------------------------------------
logger = logging.getLogger("rhinocoder.mcp_server")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    _log_handler = logging.StreamHandler(sys.stderr)
    _log_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(_log_handler)

# ---------------------------------------------------------------------------
# 依赖检查
# ---------------------------------------------------------------------------
try:
    import httpx
except ImportError:
    logger.critical("缺少依赖: pip install httpx")
    sys.exit(1)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    logger.critical("缺少依赖: pip install mcp")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
RHINO_BASE_URL = "http://127.0.0.1:8080"

# 总超时：需略大于 rhino_http_listener.py 中的 REQUEST_TIMEOUT（12s）
# 避免 httpx 在 Rhino 主线程完成前就先超时断连
HTTP_CONNECT_TIMEOUT = 3.0   # TCP 握手超时
HTTP_READ_TIMEOUT = 20.0     # 等待 Rhino 主线程执行并返回响应的最长秒数

# ---------------------------------------------------------------------------
# FastMCP Server（stdio transport）
# ---------------------------------------------------------------------------
mcp = FastMCP("RhinoCoder")


# ---------------------------------------------------------------------------
# 公共 HTTP 调用辅助函数
# ---------------------------------------------------------------------------
async def _call_rhino_listener(
    endpoint: str, payload: dict
) -> Tuple[bool, Any]:
    """
    向 Rhino HTTP Listener 的指定端点发送 POST 请求，统一处理网络异常和 HTTP 错误。

    Returns:
        (True,  guid_string)    —— 成功，guid_string 为 Rhino 返回的对象 GUID
        (False, error_message)  —— 失败，error_message 为可直接回传给 LLM 的描述
    """
    url = f"{RHINO_BASE_URL}{endpoint}"
    timeout = httpx.Timeout(
        connect=HTTP_CONNECT_TIMEOUT,
        read=HTTP_READ_TIMEOUT,
        write=5.0,
        pool=5.0,
    )

    try:
        async with httpx.AsyncClient() as client:
            logger.debug("POST %s  payload=%s", url, payload)
            response = await client.post(url, json=payload, timeout=timeout)

    except httpx.ConnectError:
        msg = (
            f"无法连接到 Rhino HTTP Listener（{url}）。\n"
            "请检查：\n"
            "  1. Rhino 8 是否已打开\n"
            "  2. 是否已在 Rhino Script Editor 中执行过 "
            "rhino_http_listener.start_listener()\n"
            "  3. 防火墙是否放行了 127.0.0.1:8080"
        )
        logger.error(msg)
        return False, msg

    except httpx.ConnectTimeout:
        msg = (
            f"连接 Rhino Listener 超时（>{HTTP_CONNECT_TIMEOUT}s）。"
            "端口 8080 无响应。"
        )
        logger.error(msg)
        return False, msg

    except httpx.ReadTimeout:
        msg = (
            f"等待 Rhino 主线程响应超时（>{HTTP_READ_TIMEOUT}s）。"
            "Rhino 可能正在执行其他长时间操作，请稍后重试。"
        )
        logger.error(msg)
        return False, msg

    except httpx.RequestError as exc:
        msg = f"HTTP 请求错误（{type(exc).__name__}）: {exc}"
        logger.error(msg)
        return False, msg

    # --------------- 解析响应 ---------------
    try:
        data = response.json()
    except Exception:
        msg = (
            f"Rhino Listener 返回了无法解析的响应"
            f"（HTTP {response.status_code}）: {response.text[:300]}"
        )
        logger.error(msg)
        return False, msg

    if response.status_code == 200:
        if "guids" in data:
            guids = data.get("guids", [])
            logger.info("%s 请求成功，GUIDs=%s", endpoint, guids)
            return True, guids
        guid = data.get("guid", "unknown")
        logger.info("%s 请求成功，GUID=%s", endpoint, guid)
        return True, guid

    # 4xx / 5xx 错误
    error_detail = data.get("error", response.text[:300])
    logger.error(
        "Rhino Listener 返回错误 HTTP %d: %s",
        response.status_code,
        error_detail,
    )

    if response.status_code == 504:
        msg = (
            f"失败：Rhino 主线程未在规定时间内响应（HTTP 504）。\n"
            f"详情：{error_detail}\n"
            "建议：检查 Rhino 是否处于模态对话框或长时间阻塞操作中。"
        )
    elif response.status_code == 400:
        msg = f"失败：请求参数错误（HTTP 400）：{error_detail}"
    elif response.status_code == 500:
        msg = f"失败：Rhino 内部错误（HTTP 500）：{error_detail}"
    else:
        msg = f"失败（HTTP {response.status_code}）：{error_detail}"

    return False, msg


# ---------------------------------------------------------------------------
# MCP 工具定义
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_sphere(radius: float) -> str:
    """
    在 Rhino 8 当前文档中，以世界坐标系原点 (0, 0, 0) 为圆心创建一个球体。

    使用场景示例：
      - "创建一个半径 10 的球体"
      - "画一个直径 6 的球，放在原点"（注意：此工具接收半径，需将直径除以 2）

    Args:
        radius: 球体半径，必须为正数。单位与 Rhino 当前文档的单位一致（毫米/厘米/米等）。

    Returns:
        成功时返回包含 Rhino 对象 GUID 的确认消息；失败时返回详细错误描述。
    """
    logger.info("create_sphere 调用，radius=%.4f", radius)

    if radius <= 0:
        return f"参数错误：radius 必须为正数，收到 {radius!r}"

    ok, result = await _call_rhino_listener("/create_sphere", {"radius": radius})
    if not ok:
        return result
    return (
        f"成功：已在原点 (0, 0, 0) 创建半径 {radius} 的球体。\n"
        f"GUID = {result}"
    )


@mcp.tool()
async def create_box(width: float, depth: float, height: float) -> str:
    """
    在 Rhino 8 当前文档中，以世界坐标系原点 (0, 0, 0) 为起始角点创建一个长方体（Box）。

    长方体沿三条世界轴方向延伸：
      - width  → X 轴正方向
      - depth  → Y 轴正方向
      - height → Z 轴正方向
    因此长方体的 8 个顶点范围为 X∈[0, width]，Y∈[0, depth]，Z∈[0, height]。

    使用场景示例：
      - "创建一个 10×5×3 的长方体"（width=10, depth=5, height=3）
      - "画一个边长为 4 的正方体"（width=4, depth=4, height=4）
      - "生成一个宽 20、深 10、高 8 的矩形盒子"

    Args:
        width:  X 轴方向的尺寸，必须为正数。单位与 Rhino 当前文档一致。
        depth:  Y 轴方向的尺寸，必须为正数。单位与 Rhino 当前文档一致。
        height: Z 轴方向的尺寸，必须为正数。单位与 Rhino 当前文档一致。

    Returns:
        成功时返回包含 Rhino 对象 GUID 的确认消息；失败时返回详细错误描述。
    """
    logger.info(
        "create_box 调用，width=%.4f, depth=%.4f, height=%.4f",
        width, depth, height,
    )

    for name, val in (("width", width), ("depth", depth), ("height", height)):
        if val <= 0:
            return f"参数错误：{name} 必须为正数，收到 {val!r}"

    payload = {"width": width, "depth": depth, "height": height}
    ok, result = await _call_rhino_listener("/create_box", payload)
    if not ok:
        return result
    return (
        f"成功：已从原点 (0, 0, 0) 创建 {width}×{depth}×{height} 的长方体。\n"
        f"GUID = {result}"
    )


@mcp.tool()
async def create_cylinder(radius: float, height: float) -> str:
    """
    在 Rhino 8 当前文档中，以世界坐标系原点 (0, 0, 0) 为底面圆心、沿 Z 轴正方向创建一个圆柱体。

    底面圆心位于原点，顶面圆心位于 (0, 0, height)。
    圆柱体两端均封口（实体 Brep），可直接用于布尔运算等操作。

    使用场景示例：
      - "创建一个半径 5、高 12 的圆柱体"
      - "画一根直径 3（半径 1.5）、长度 20 的圆柱形柱子"
      - "生成一个半径 8、高度 8 的等比圆柱"

    Args:
        radius: 底面（和顶面）圆的半径，必须为正数。单位与 Rhino 当前文档一致。
        height: 圆柱体沿 Z 轴的高度，必须为正数。单位与 Rhino 当前文档一致。

    Returns:
        成功时返回包含 Rhino 对象 GUID 的确认消息；失败时返回详细错误描述。
    """
    logger.info("create_cylinder 调用，radius=%.4f, height=%.4f", radius, height)

    for name, val in (("radius", radius), ("height", height)):
        if val <= 0:
            return f"参数错误：{name} 必须为正数，收到 {val!r}"

    payload = {"radius": radius, "height": height}
    ok, result = await _call_rhino_listener("/create_cylinder", payload)
    if not ok:
        return result
    return (
        f"成功：已在原点 (0, 0, 0) 创建半径 {radius}、高度 {height} 的圆柱体。\n"
        f"GUID = {result}"
    )


@mcp.tool()
async def create_line(
    start_x: float, start_y: float, start_z: float,
    end_x: float,   end_y: float,   end_z: float,
) -> str:
    """
    在 Rhino 8 当前文档中，连接两个三维空间点，创建一条直线曲线（Line Curve）。

    直线是最基础的建模元素，可用于：辅助线、结构骨架、后续 Loft/Sweep 的路径等。
    注意：起点和终点不能重合，否则会报参数错误。

    使用场景示例：
      - "从原点画一条到 (10, 0, 0) 的直线"
        → start=(0,0,0), end=(10,0,0)
      - "连接点 A(1, 2, 3) 和点 B(4, 5, 6)"
        → start=(1,2,3), end=(4,5,6)
      - "沿 Z 轴方向从 (5, 5, 0) 画一条长度 20 的线"
        → start=(5,5,0), end=(5,5,20)

    Args:
        start_x: 起点的 X 坐标。单位与 Rhino 当前文档一致。
        start_y: 起点的 Y 坐标。单位与 Rhino 当前文档一致。
        start_z: 起点的 Z 坐标。单位与 Rhino 当前文档一致。
        end_x:   终点的 X 坐标。单位与 Rhino 当前文档一致。
        end_y:   终点的 Y 坐标。单位与 Rhino 当前文档一致。
        end_z:   终点的 Z 坐标。单位与 Rhino 当前文档一致。

    Returns:
        成功时返回包含 Rhino 曲线对象 GUID 的确认消息；失败时返回详细错误描述。
    """
    logger.info(
        "create_line 调用，start=(%.4f,%.4f,%.4f) end=(%.4f,%.4f,%.4f)",
        start_x, start_y, start_z, end_x, end_y, end_z,
    )

    start = [start_x, start_y, start_z]
    end   = [end_x,   end_y,   end_z]

    if start == end:
        return (
            f"参数错误：起点 {start} 和终点 {end} 重合，无法创建零长度直线。"
        )

    payload = {"start": start, "end": end}
    ok, result = await _call_rhino_listener("/create_line", payload)
    if not ok:
        return result
    return (
        f"成功：已创建从 ({start_x}, {start_y}, {start_z}) "
        f"到 ({end_x}, {end_y}, {end_z}) 的直线。\n"
        f"GUID = {result}"
    )


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
        "move_object 调用，object_id=%s, translate=(%.4f,%.4f,%.4f)",
        object_id, translate_x, translate_y, translate_z,
    )

    if not object_id or not isinstance(object_id, str):
        return "参数错误：object_id 必须是非空字符串 GUID"

    payload = {
        "object_id": object_id,
        "translation": [translate_x, translate_y, translate_z],
    }
    ok, result = await _call_rhino_listener("/move_object", payload)
    if not ok:
        return result
    return (
        f"成功：已将对象 {object_id} 平移 "
        f"({translate_x}, {translate_y}, {translate_z})。\n"
        f"GUID = {result}"
    )


@mcp.tool()
async def extrude_curve_straight(
    curve_id: str,
    start_x: float, start_y: float, start_z: float,
    end_x: float,   end_y: float,   end_z: float,
) -> str:
    """
    将 Rhino 文档中已有的曲线沿直线路径挤出，生成曲面或封闭实体。

    【重要】自动加盖逻辑（无需手动处理）：
      - 若输入曲线是【闭合曲线】（如圆形、闭合矩形等），后端自动调用
        CapPlanarHoles 封盖两端，直接生成封闭实体（Solid Brep）。
      - 若输入曲线是【开放曲线】，生成开放曲面（无封盖）。
      - 因此：挤出闭合曲线（如 create_circle 返回的圆）可直接用于布尔运算。

    【重要】本工具需要依赖其他工具返回的 GUID：
      - curve_id 必须是 Rhino 文档中已存在的曲线对象真实 GUID。
      - 最常见来源：create_circle 创建的圆形曲线 GUID。
      - 切勿凭空捏造 GUID 字符串。

    挤出路径由 start→end 向量决定：
      - 挤出长度 = start 到 end 的距离。
      - 常用：start=(0,0,0), end=(0,0,h) 表示沿 Z 轴向上挤出高度 h。
      - start 和 end 不能重合（否则零向量，操作失败）。

    使用场景示例：
      - "把圆形曲线沿 Z 轴挤出 10 个单位，生成圆柱实体"
        → curve_id=<circle_guid>, start=(0,0,0), end=(0,0,10)
      - "生成一个穿透 5 单位厚平板的圆柱钻头（从 -1 挤出到 6，确保贯穿）"
        → start_z=-1, end_z=6

    典型工作流（在实体上打圆孔）：
      1. create_box(20, 20, 5)                          → box_guid
      2. create_circle(10, 10, 0, radius=3)             → circle_guid
      3. extrude_curve_straight(circle_guid,
             start_x=10,start_y=10,start_z=-1,
             end_x=10,end_y=10,end_z=6)                → cyl_guid（贯穿平板）
      4. boolean_difference([box_guid], [cyl_guid])     → [result_guid]

    Args:
        curve_id: 要挤出的曲线 GUID（由 create_circle 等工具返回的字符串）。
        start_x:  挤出路径起点 X 坐标。
        start_y:  挤出路径起点 Y 坐标。
        start_z:  挤出路径起点 Z 坐标。
        end_x:    挤出路径终点 X 坐标。
        end_y:    挤出路径终点 Y 坐标。
        end_z:    挤出路径终点 Z 坐标。

    Returns:
        成功时返回挤出实体/曲面 GUID 的确认消息；失败时返回详细错误描述。
    """
    logger.info(
        "extrude_curve_straight 调用，curve_id=%s, start=(%.4f,%.4f,%.4f) end=(%.4f,%.4f,%.4f)",
        curve_id, start_x, start_y, start_z, end_x, end_y, end_z,
    )

    if not curve_id or not isinstance(curve_id, str):
        return "参数错误：curve_id 必须是非空字符串 GUID"

    start = [start_x, start_y, start_z]
    end   = [end_x,   end_y,   end_z]
    if start == end:
        return "参数错误：start 和 end 点重合，挤出向量为零，无法执行操作。"

    payload = {
        "curve_id": curve_id,
        "start_point": start,
        "end_point": end,
    }
    ok, result = await _call_rhino_listener("/extrude_curve_straight", payload)
    if not ok:
        return result
    return (
        f"成功：已将曲线 {curve_id} 沿路径 "
        f"({start_x},{start_y},{start_z})→({end_x},{end_y},{end_z}) 挤出。\n"
        f"GUID = {result}"
    )


@mcp.tool()
async def boolean_difference(
    input0_ids: list[str],
    input1_ids: list[str],
) -> str:
    """
    对 Rhino 文档中的封闭实体执行布尔差集运算（Boolean Difference）。

    布尔差集语义：
      - input0（被减数/基础体）：要从中"挖去"材料的实体。
      - input1（减数/刀具体）：定义要被挖去形状的实体（切割工具）。
      - 结果：input0 去除与 input1 相交区域后的剩余实体。
      - 运算成功后，input0 和 input1 的原始对象均被 Rhino 删除，返回新生成的结果 GUID 列表。

    【关键前提 — 必读】：
      1. 所有 GUID 必须来自 Rhino 文档中已存在的【封闭实体（Solid Brep）】，
         推荐来源：create_sphere、create_box、create_cylinder，
         或用闭合曲线执行 extrude_curve_straight（自动封盖）的结果。
      2. input0 与 input1 在空间上必须存在真实相交区域；若不相交，运算失败。
      3. 所有 GUID 必须是之前工具调用实际返回的真实字符串，切勿凭空捏造。
      4. 运算后原始对象被删除，不可再对旧 GUID 执行任何操作。

    使用场景示例：
      - "从长方体中挖去一个球形空腔"
        → input0_ids=[box_guid], input1_ids=[sphere_guid]
      - "用圆柱钻头在平板上打孔"（圆柱必须贯穿平板）
        → input0_ids=[plate_guid], input1_ids=[cylinder_guid]
      - "同时用 3 个圆柱打 3 个孔"
        → input0_ids=[base_guid], input1_ids=[cyl1, cyl2, cyl3]

    典型工作流（在 20×20×5 平板上打一个半径 3 的通孔）：
      1. create_box(20, 20, 5)                               → box_guid
      2. create_circle(center_x=10,center_y=10,center_z=0,
                       radius=3)                             → circle_guid
      3. extrude_curve_straight(circle_guid,
             start_x=10,start_y=10,start_z=-1,
             end_x=10,end_y=10,end_z=6)                    → cyl_guid
         （注意：挤出需超出平板厚度两端，确保完全贯穿）
      4. boolean_difference(input0_ids=[box_guid],
                            input1_ids=[cyl_guid])          → [result_guid]

    Args:
        input0_ids: 被减数实体 GUID 字符串列表（基础体，不可为空）。
                    例如：["3f2a1c4b-..."]
        input1_ids: 减数/刀具实体 GUID 字符串列表（切割体，不可为空）。
                    例如：["7b4e8d2a-...", "9c12a0ff-..."]

    Returns:
        成功时返回结果实体 GUID 列表的确认消息（原始对象已被删除）；
        失败时返回详细错误描述（包含可能的原因提示）。
    """
    logger.info(
        "boolean_difference 调用，input0=%s, input1=%s", input0_ids, input1_ids
    )

    if not input0_ids:
        return "参数错误：input0_ids 不能为空列表"
    if not input1_ids:
        return "参数错误：input1_ids 不能为空列表"

    payload = {"input0_ids": input0_ids, "input1_ids": input1_ids}
    ok, result = await _call_rhino_listener("/boolean_difference", payload)
    if not ok:
        return result
    guids_str = ", ".join(result) if isinstance(result, list) else str(result)
    return (
        f"成功：布尔差集完成，共生成 {len(result) if isinstance(result, list) else 1} 个结果实体。\n"
        f"原始对象已删除。结果 GUIDs = [{guids_str}]"
    )


@mcp.tool()
async def create_circle(
    center_x: float,
    center_y: float,
    center_z: float,
    radius: float,
) -> str:
    """
    在 Rhino 8 当前文档中创建一个圆形曲线（平行于世界 XY 平面）。

    圆形曲线是二维轮廓线，常作为后续操作的输入：
      - 配合 extrude_curve_straight 可挤出为圆柱实体（闭合曲线自动封盖）。
      - 配合 boolean_difference 可用挤出的圆柱在实体上打孔。

    平面说明：
      - 圆始终平行于世界 XY 平面，法向量朝 Z 轴正方向。
      - center_z 决定圆所在平面的 Z 高度。

    注意：圆形曲线本身只是轮廓线，没有体积或面积。
    如需生成圆柱实体，必须配合 extrude_curve_straight 使用。

    使用场景示例：
      - "在原点处创建半径 5 的圆"
        → center_x=0, center_y=0, center_z=0, radius=5
      - "创建一个直径 8 的圆"（半径 = 直径 / 2）
        → radius=4
      - "在 Z=10 高度、圆心 (3,4,10) 处创建半径 2 的圆截面"
        → center_x=3, center_y=4, center_z=10, radius=2

    典型工作流（创建圆柱实体）：
      1. create_circle(0, 0, 0, radius=5)                    → circle_guid
      2. extrude_curve_straight(circle_guid,
             start_x=0,start_y=0,start_z=0,
             end_x=0,end_y=0,end_z=10)                      → 封闭圆柱实体 GUID

    Args:
        center_x: 圆心 X 坐标。单位与 Rhino 当前文档一致。
        center_y: 圆心 Y 坐标。单位与 Rhino 当前文档一致。
        center_z: 圆心 Z 坐标（同时决定圆所在平面的高度）。
        radius:   圆的半径，必须为正数。单位与 Rhino 当前文档一致。

    Returns:
        成功时返回包含圆形曲线 GUID 的确认消息；失败时返回详细错误描述。
    """
    logger.info(
        "create_circle 调用，center=(%.4f,%.4f,%.4f), radius=%.4f",
        center_x, center_y, center_z, radius,
    )

    if radius <= 0:
        return f"参数错误：radius 必须为正数，收到 {radius!r}"

    payload = {"center": [center_x, center_y, center_z], "radius": radius}
    ok, result = await _call_rhino_listener("/create_circle", payload)
    if not ok:
        return result
    return (
        f"成功：已在 ({center_x}, {center_y}, {center_z}) 创建半径 {radius} 的圆形曲线。\n"
        f"GUID = {result}"
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("RhinoCoder MCP Server 启动（stdio transport）")
    logger.info(
        "已注册工具: create_sphere, create_box, create_cylinder, create_line, "
        "move_object, extrude_curve_straight, boolean_difference, create_circle"
    )
    logger.info("等待 MCP 客户端连接…")
    mcp.run(transport="stdio")
