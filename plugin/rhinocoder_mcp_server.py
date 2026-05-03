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
from typing import Any, Optional, Tuple

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
        # api_error_handler 会将内部异常包装成 HTTP 200 + {"status":"error"}，
        # 需要在这里将其转换为 (False, msg) 让调用方走错误处理分支。
        if data.get("status") == "error":
            error_msg = data.get("message", "未知内部错误")
            logger.error("%s 返回应用层错误（HTTP 200）: %s", endpoint, error_msg)
            return False, f"失败：{error_msg}"

        if "guids" in data:
            guids = data.get("guids", [])
            logger.info("%s 请求成功，GUIDs=%s", endpoint, guids)
            return True, guids
        if "guid" in data:
            guid = data.get("guid")
            logger.info("%s 请求成功，GUID=%s", endpoint, guid)
            return True, guid
        # 数据型响应（get_object_info / get_bounding_box / get_selected_objects 等）
        # 响应体中没有 "guid" key，直接返回完整 dict
        logger.info("%s 请求成功，data=%s", endpoint, data)
        return True, data

    # 4xx / 5xx 错误
    error_detail = data.get("message") or data.get("error", response.text[:300])
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
    ok, result = await _call_rhino_listener("/get_selected_objects", {})
    if not ok:
        return result
    object_ids = result.get("object_ids", []) if isinstance(result, dict) else []
    return (
        f"当前选中 {len(object_ids)} 个对象。\n"
        f"object_ids = {object_ids}"
    )


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

    ok, result = await _call_rhino_listener("/get_objects_by_name", {"name": name})
    if not ok:
        return result

    object_ids = result.get("object_ids", []) if isinstance(result, dict) else []
    if object_ids:
        return (
            f"找到 {len(object_ids)} 个名为 {name!r} 的对象。\n"
            f"object_ids = {object_ids}"
        )
    return f"未找到名为 {name!r} 的对象。object_ids = []"


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

    ok, result = await _call_rhino_listener("/get_object_info", {"object_id": object_id})
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

    ok, result = await _call_rhino_listener("/get_bounding_box", {"object_id": object_id})
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
    logger.info("set_object_layer 调用，object_id=%s, layer_name=%r", object_id, layer_name)

    if not object_id or not isinstance(object_id, str):
        return "参数错误：object_id 必须是非空字符串 GUID"
    if not layer_name or not isinstance(layer_name, str) or not layer_name.strip():
        return "参数错误：layer_name 必须是非空字符串"

    payload = {"object_id": object_id, "layer_name": layer_name}
    ok, result = await _call_rhino_listener("/set_object_layer", payload)
    if not ok:
        return result

    if isinstance(result, dict):
        return (
            f"成功：已将对象 {result.get('object_id')} 移至图层 {result.get('layer_name')!r}。\n"
            f"layer_index = {result.get('layer_index')}"
        )
    return f"成功（原始响应）: {result}"


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
        "rotate_object 调用，object_id=%s, angle=%.4f, axis=%s, center=%s",
        object_id, angle_degrees, axis, center_point,
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

    ok, result = await _call_rhino_listener("/rotate_object", payload)
    if not ok:
        return result

    axis_desc = axis if axis is not None else "[0, 0, 1]（默认 Z 轴）"
    center_desc = center_point if center_point is not None else "对象几何中心（自动计算）"
    return (
        f"成功：已将对象 {object_id} 绕轴 {axis_desc}、"
        f"以 {center_desc} 为基准旋转 {angle_degrees}°。\n"
        f"GUID = {result}"
    )


@mcp.tool()
async def align_objects(
    object_ids: list[str],
    axis: str = "X",
    alignment: str = "center",
) -> str:
    """
    将多个 Rhino 8 对象沿指定坐标轴对齐，一键完成多对象空间对齐布局。

    【本工具的意义】
    手动对齐多个物体需要 Agent 对每个物体调用 get_bounding_box + 计算偏移 + move_object，
    步骤繁琐且误差易积累。本工具将全套逻辑封装为一次调用，极大降低计算负担。

    对齐语义（以 axis="X" 为例）：
      - "min"：所有物体的 X 轴最小边（左端面）对齐到同一 X 坐标（最小值中的最小值）。
      - "center"：所有物体的 X 轴包围盒中心对齐到同一 X 坐标（各中心的平均值）。
      - "max"：所有物体的 X 轴最大边（右端面）对齐到同一 X 坐标（最大值中的最大值）。

    【重要】所有 GUID 必须来自 Rhino 文档中真实存在的对象（创建工具或 get_selected_objects
    的返回值），切勿凭空捏造。

    使用场景示例：
      - "让这 4 根柱子左对齐"
        → object_ids=[c1,c2,c3,c4], axis="X", alignment="min"
      - "将这些盒子在 Y 轴方向居中对齐"
        → object_ids=[b1,b2,b3], axis="Y", alignment="center"
      - "所有物体顶面对齐到同一高度"
        → axis="Z", alignment="max"

    典型工作流：
      1. create_box(10,10,10)  → g1；create_box(5,5,5) → g2；create_box(8,8,8) → g3
      2. move_object(g2, 30, 0, 0)；move_object(g3, 60, 0, 0)   ← 先散开
      3. align_objects([g1,g2,g3], axis="Z", alignment="min")    ← 底面对齐

    Args:
        object_ids: 需要对齐的对象 GUID 列表，至少包含 2 个元素。
        axis:       对齐参考轴，只能是 "X"、"Y" 或 "Z"（不区分大小写）。默认 "X"。
        alignment:  对齐方式：
                      "min"    — 最小端对齐（靠左/靠下/靠前）
                      "center" — 包围盒中心对齐（居中）
                      "max"    — 最大端对齐（靠右/靠上/靠后）
                    默认 "center"。

    Returns:
        成功时返回每个对象的移动摘要（原始中心 → 新位置）；失败时返回详细错误描述。
    """
    logger.info(
        "align_objects 调用，count=%d, axis=%r, alignment=%r",
        len(object_ids) if object_ids else 0, axis, alignment,
    )

    # ── 参数校验 ──────────────────────────────────────────────────────────────
    if not object_ids or len(object_ids) < 2:
        return "参数错误：object_ids 至少需要包含 2 个 GUID"

    axis = axis.upper()
    if axis not in ("X", "Y", "Z"):
        return f"参数错误：axis 必须是 'X'、'Y' 或 'Z'，收到 {axis!r}"

    alignment = alignment.lower()
    if alignment not in ("min", "center", "max"):
        return f"参数错误：alignment 必须是 'min'、'center' 或 'max'，收到 {alignment!r}"

    axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis]

    # ── 逐个获取包围盒 ────────────────────────────────────────────────────────
    bboxes: list[dict] = []
    for oid in object_ids:
        ok, result = await _call_rhino_listener("/get_bounding_box", {"object_id": oid})
        if not ok:
            return f"获取对象 {oid} 的包围盒失败：{result}"
        if not isinstance(result, dict):
            return f"对象 {oid} 返回了意外的包围盒格式：{result}"
        bboxes.append(result)

    # ── 计算对齐目标值 ────────────────────────────────────────────────────────
    #  vertices[0] = min 角点，vertices[6] = max 角点，center = 包围盒中心
    mins    = [bb["vertices"][0][axis_idx] for bb in bboxes]
    maxs    = [bb["vertices"][6][axis_idx] for bb in bboxes]
    centers = [bb["center"][axis_idx]      for bb in bboxes]

    if alignment == "min":
        target = min(mins)
    elif alignment == "max":
        target = max(maxs)
    else:  # center
        target = sum(centers) / len(centers)

    # ── 逐个移动到对齐位置 ───────────────────────────────────────────────────
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

        ok, move_result = await _call_rhino_listener(
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
        "scale_object 调用，object_id=%s, scale_factor=%s, center=%s",
        object_id, scale_factor, center_point,
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

    ok, result = await _call_rhino_listener("/scale_object", payload)
    if not ok:
        return result

    center_desc = center_point if center_point is not None else "对象几何中心（自动计算）"
    sx, sy, sz = scale_factor
    return (
        f"成功：已将对象 {object_id} 以 {center_desc} 为基准，"
        f"按 X×{sx} / Y×{sy} / Z×{sz} 完成缩放。\n"
        f"GUID = {result}"
    )


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
    ok, result = await _call_rhino_listener("/distribute_objects", payload)
    if not ok:
        return result

    if isinstance(result, dict):
        moved = result.get("moved", len(object_ids))
        return (
            f"成功：已将 {moved} 个对象沿 {axis_upper} 轴"
            f"以净间距 {spacing} 完成等距分布。"
        )
    return f"成功（原始响应）: {result}"


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
        "place_on_at 调用，target_id=%s, reference_id=%s, side=%r",
        target_id, reference_id, side,
    )

    if not target_id or not isinstance(target_id, str):
        return "参数错误：target_id 必须是非空字符串 GUID"
    if not reference_id or not isinstance(reference_id, str):
        return "参数错误：reference_id 必须是非空字符串 GUID"

    valid_sides = ("top", "bottom", "left", "right", "front", "back")
    side_lower = side.lower() if isinstance(side, str) else ""
    if side_lower not in valid_sides:
        return f"参数错误：side 必须是 {valid_sides} 之一，收到 {side!r}"

    payload = {
        "target_id": target_id,
        "reference_id": reference_id,
        "side": side_lower,
    }
    ok, result = await _call_rhino_listener("/place_on_at", payload)
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
    ok, result = await _call_rhino_listener("/undo_last_action", {})
    if not ok:
        return result
    if isinstance(result, dict):
        return result.get("message", "已成功撤销上一步操作")
    return "已成功撤销上一步操作"


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
    ok, result = await _call_rhino_listener("/set_object_color", payload)
    if not ok:
        return result

    changed = result.get("changed", len(object_ids)) if isinstance(result, dict) else len(object_ids)
    return (
        f"成功：已将 {changed} 个对象的颜色设置为 RGB({r}, {g}, {b})。"
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("RhinoCoder MCP Server 启动（stdio transport）")
    logger.info(
        "已注册工具: create_sphere, create_box, create_cylinder, create_line, "
        "move_object, rotate_object, scale_object, align_objects, distribute_objects, "
        "extrude_curve_straight, boolean_difference, create_circle, "
        "get_selected_objects, get_objects_by_name, "
        "get_object_info, get_bounding_box, set_object_layer, set_object_color, "
        "place_on_at, undo_last_action"
    )
    logger.info("等待 MCP 客户端连接…")
    mcp.run(transport="stdio")
