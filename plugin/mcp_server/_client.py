"""
mcp_server/_client.py  —  运行在外部 VS Code 终端（Python 3.10+）

MCP 侧唯一的 HTTP 客户端，封装对 Rhino HTTP Listener 的所有网络通信。

公开接口：
  call_rhino(endpoint, payload) -> (ok: bool, result: Any)

  ok=True  时，result 为：
    str        — 单体操作返回的 GUID（如 create_sphere）
    list[str]  — 多体操作返回的 GUID 列表（如 boolean_difference）
    dict       — 数据型操作返回的完整字典（如 get_bounding_box、get_scene_summary）

  ok=False 时，result 为可直接回传给 LLM 的中文错误描述字符串。

设计约束：
  - 此文件只能运行在外部 Python 3.10+ 环境，严禁导入任何 Rhino 专属库。
  - logger 必须输出到 stderr，不得写入 stdout（stdio transport 使用 stdout 传输
    MCP 协议帧，任何非协议内容写入 stdout 都会导致 Claude Desktop 解析失败）。

依赖：
  pip install httpx
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Tuple

# ---------------------------------------------------------------------------
# Logging —— 严格输出到 stderr，保护 stdout 给 MCP stdio transport 专用
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
# 依赖检查（在模块导入阶段即报错，而不是运行时静默失败）
# ---------------------------------------------------------------------------
try:
    import httpx
except ImportError:
    logger.critical("缺少依赖: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
RHINO_BASE_URL = "http://127.0.0.1:8080"

# 连接超时：TCP 握手的最长等待时间
HTTP_CONNECT_TIMEOUT = 3.0

# 读取超时：需略大于 rhino_listener 中的 REQUEST_TIMEOUT（12s），
# 避免 httpx 在 Rhino 主线程完成前就先断开连接。
HTTP_READ_TIMEOUT = 20.0


# ---------------------------------------------------------------------------
# 公共 HTTP 调用函数
# ---------------------------------------------------------------------------
async def call_rhino(endpoint: str, payload: dict) -> Tuple[bool, Any]:
    """
    向 Rhino HTTP Listener 的指定端点发送 POST 请求。

    统一处理网络层异常（连接失败、超时）、HTTP 层错误（4xx/5xx）以及
    应用层错误（HTTP 200 + {"status": "error"}），所有失败路径均返回
    (False, 中文错误描述)，调用方无需关心错误来源，可直接将描述回传给 LLM。

    Args:
        endpoint: HTTP 路径，如 "/create_sphere"。
        payload:  JSON 请求体字典。

    Returns:
        (True,  data)           — 成功
        (False, error_message)  — 失败
    """
    url = f"{RHINO_BASE_URL}{endpoint}"
    timeout = httpx.Timeout(
        connect=HTTP_CONNECT_TIMEOUT,
        read=HTTP_READ_TIMEOUT,
        write=5.0,
        pool=5.0,
    )

    # ── 发送请求 ────────────────────────────────────────────────────────────
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

    # ── 解析响应体 ──────────────────────────────────────────────────────────
    try:
        data = response.json()
    except Exception:
        msg = (
            f"Rhino Listener 返回了无法解析的响应"
            f"（HTTP {response.status_code}）: {response.text[:300]}"
        )
        logger.error(msg)
        return False, msg

    # ── HTTP 200：区分应用层成功与应用层错误 ────────────────────────────────
    if response.status_code == 200:
        # api_error_handler 将内部异常包装为 HTTP 200 + {"status":"error"}，
        # 在此处将其转换为 (False, msg) 让调用方统一走错误处理分支。
        if data.get("status") == "error":
            error_msg = data.get("message", "未知内部错误")
            logger.error("%s 返回应用层错误（HTTP 200）: %s", endpoint, error_msg)
            return False, f"失败：{error_msg}"

        # 多体操作（boolean_difference 等）：响应包含 "guids" 列表
        if "guids" in data:
            guids = data.get("guids", [])
            logger.info("%s 请求成功，GUIDs=%s", endpoint, guids)
            return True, guids

        # 单体操作（create_sphere 等）：响应包含单个 "guid" 字符串
        if "guid" in data:
            guid = data.get("guid")
            logger.info("%s 请求成功，GUID=%s", endpoint, guid)
            return True, guid

        # 数据型操作（get_bounding_box / get_scene_summary 等）：返回完整 dict
        logger.info("%s 请求成功，data=%s", endpoint, data)
        return True, data

    # ── HTTP 4xx / 5xx ──────────────────────────────────────────────────────
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
