"""
plugin/rhinocoder_mcp_server.py  —  运行在外部 VS Code 终端（Python 3.10+）

架构
────────────────────────────────────────────────────────────────────
[Claude Desktop / Agent]
      │  MCP stdio
      ▼
[本文件: FastMCP Server（stdio transport）]
      │  create_sphere() 工具被调用
      │  POST http://127.0.0.1:8080/draw_sphere  {"radius": <float>}
      ▼
[Rhino 内部: rhino_http_listener.py]
      │  JSON 响应 {"status": "ok", "guid": "..."}
      ▼
[本文件返回结果给 Claude]
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
RHINO_LISTENER_URL = "http://127.0.0.1:8080/draw_sphere"

# 总超时：需略大于 rhino_http_listener.py 中的 REQUEST_TIMEOUT（12s）
# 避免 httpx 在 Rhino 主线程完成前就先超时断连
HTTP_CONNECT_TIMEOUT = 3.0   # TCP 握手超时
HTTP_READ_TIMEOUT = 20.0     # 等待 Rhino 主线程执行并返回响应的最长秒数

# ---------------------------------------------------------------------------
# FastMCP Server（stdio transport）
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "RhinoCoder",
    description=(
        "通过 HTTP 桥接在 Rhino 8 中执行几何体操作。"
        "前提：Rhino 内已运行 rhino_http_listener.start_listener()"
    ),
)


@mcp.tool()
async def create_sphere(radius: float) -> str:
    """
    在 Rhino 8 当前文档中，以原点 (0, 0, 0) 为圆心创建一个球体。

    Args:
        radius: 球体半径（必须为正数，单位与 Rhino 文件单位一致）

    Returns:
        成功时返回包含 GUID 的确认消息；失败时返回详细错误描述。
    """
    logger.info("create_sphere 调用，radius=%.4f", radius)

    # 前置校验，避免无意义的网络请求
    if radius <= 0:
        msg = f"参数错误：radius 必须为正数，收到 {radius!r}"
        logger.warning(msg)
        return msg

    payload = {"radius": radius}
    timeout = httpx.Timeout(
        connect=HTTP_CONNECT_TIMEOUT,
        read=HTTP_READ_TIMEOUT,
        write=5.0,
        pool=5.0,
    )

    try:
        async with httpx.AsyncClient() as client:
            logger.debug("POST %s  payload=%s", RHINO_LISTENER_URL, payload)
            response = await client.post(
                RHINO_LISTENER_URL,
                json=payload,
                timeout=timeout,
            )

    except httpx.ConnectError:
        msg = (
            f"无法连接到 Rhino HTTP Listener（{RHINO_LISTENER_URL}）。\n"
            "请检查：\n"
            "  1. Rhino 8 是否已打开\n"
            "  2. 是否已在 Rhino Script Editor 中执行过 "
            "rhino_http_listener.start_listener()\n"
            "  3. 防火墙是否放行了 127.0.0.1:8080"
        )
        logger.error(msg)
        return msg

    except httpx.ConnectTimeout:
        msg = (
            f"连接 Rhino Listener 超时（>{HTTP_CONNECT_TIMEOUT}s）。"
            "端口 8080 无响应。"
        )
        logger.error(msg)
        return msg

    except httpx.ReadTimeout:
        msg = (
            f"等待 Rhino 主线程响应超时（>{HTTP_READ_TIMEOUT}s）。"
            "Rhino 可能正在执行其他长时间操作，请稍后重试。"
        )
        logger.error(msg)
        return msg

    except httpx.RequestError as exc:
        msg = f"HTTP 请求错误（{type(exc).__name__}）: {exc}"
        logger.error(msg)
        return msg

    # --------------- 解析响应 ---------------
    try:
        data = response.json()
    except Exception:
        msg = (
            f"Rhino Listener 返回了无法解析的响应"
            f"（HTTP {response.status_code}）: {response.text[:300]}"
        )
        logger.error(msg)
        return msg

    if response.status_code == 200:
        guid = data.get("guid", "unknown")
        logger.info("create_sphere 成功，GUID=%s", guid)
        return (
            f"成功：已在原点 (0, 0, 0) 创建半径 {radius} 的球体。\n"
            f"GUID = {guid}"
        )

    # 4xx / 5xx 错误
    error_detail = data.get("error", response.text[:300])
    logger.error(
        "Rhino Listener 返回错误 HTTP %d: %s",
        response.status_code,
        error_detail,
    )

    if response.status_code == 504:
        return (
            f"失败：Rhino 主线程未在规定时间内响应（HTTP 504）。\n"
            f"详情：{error_detail}\n"
            "建议：检查 Rhino 是否处于模态对话框或长时间阻塞操作中。"
        )
    if response.status_code == 400:
        return f"失败：请求参数错误（HTTP 400）：{error_detail}"
    if response.status_code == 500:
        return f"失败：Rhino 内部错误（HTTP 500）：{error_detail}"

    return f"失败（HTTP {response.status_code}）：{error_detail}"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("RhinoCoder MCP Server 启动（stdio transport）")
    logger.info("等待 MCP 客户端连接…")
    mcp.run(transport="stdio")
