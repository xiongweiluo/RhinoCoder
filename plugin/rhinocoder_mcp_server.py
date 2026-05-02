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
from typing import Tuple

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
) -> Tuple[bool, str]:
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

    ok, result = await _call_rhino_listener("/draw_sphere", {"radius": radius})
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
    ok, result = await _call_rhino_listener("/draw_box", payload)
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
    ok, result = await _call_rhino_listener("/draw_cylinder", payload)
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
    ok, result = await _call_rhino_listener("/draw_line", payload)
    if not ok:
        return result
    return (
        f"成功：已创建从 ({start_x}, {start_y}, {start_z}) "
        f"到 ({end_x}, {end_y}, {end_z}) 的直线。\n"
        f"GUID = {result}"
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("RhinoCoder MCP Server 启动（stdio transport）")
    logger.info("已注册工具: create_sphere, create_box, create_cylinder, create_line")
    logger.info("等待 MCP 客户端连接…")
    mcp.run(transport="stdio")
