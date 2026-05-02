"""
plugin/rhinocoder_mcp_server.py

Sprint 2 MVP — 跑通 MCP 物理链路

架构概览
─────────────────────────────────────────────────────────────
[Claude Desktop]
      │  HTTP/SSE
      ▼
[后台线程: asyncio 事件循环 + FastMCP SSE Server]
      │  _schedule_on_main_thread() → concurrent.futures.Future 入队
      ▼
[_work_queue: queue.Queue]
      │  Rhino.RhinoApp.Idle 事件（主线程消费）
      ▼
[Rhino 主线程: rs.AddSphere() 执行，结果写回 Future]
      │  cf_future.set_result() → asyncio.wrap_future() 解除等待
      ▼
[后台线程: 返回结果给 MCP Client]
─────────────────────────────────────────────────────────────

暴露工具（Sprint 2 MVP）:
  create_sphere(radius: float) — 在原点创建球体，返回 GUID

使用方式（在 Rhino Script Editor 中执行）:
  import sys
  sys.path.insert(0, r"/path/to/RhinoCoder/plugin")
  import rhinocoder_mcp_server
  rhinocoder_mcp_server.start_server()

Claude Desktop 配置:
  {
    "mcpServers": {
      "rhinocoder": {
        "url": "http://127.0.0.1:3333/sse"
      }
    }
  }
"""

import asyncio
import concurrent.futures
import logging
import queue
import sys
import threading

# ---------------------------------------------------------------------------
# Logging —— 输出到 stdout，在 Rhino 控制台中可见
# ---------------------------------------------------------------------------
logger = logging.getLogger("rhinocoder.mcp_server")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    _log_handler = logging.StreamHandler(sys.stdout)
    _log_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(_log_handler)

# ---------------------------------------------------------------------------
# MCP SDK
# ---------------------------------------------------------------------------
try:
    from mcp.server.fastmcp import FastMCP
    logger.info("mcp SDK 加载成功")
except ImportError as _import_exc:
    logger.critical(
        "无法导入 mcp SDK: %s\n"
        "请在 Rhino 8 Python 环境执行: pip install mcp",
        _import_exc,
    )
    raise

# ---------------------------------------------------------------------------
# 跨线程工作队列
#
# 后台线程（asyncio）将 (callable, concurrent.futures.Future) 投入队列。
# Rhino 主线程通过 Idle 事件消费队列，执行 callable，将结果或异常写回 Future。
# asyncio 侧通过 asyncio.wrap_future() 等待该 Future 完成。
# ---------------------------------------------------------------------------
_work_queue: "queue.Queue[tuple]" = queue.Queue()


def _idle_handler(sender, e) -> None:  # type: ignore[type-arg]
    """
    注册到 Rhino.RhinoApp.Idle 的回调，在 Rhino 主线程空闲时执行。
    一次性排空队列中所有待处理任务，避免单帧积压。
    """
    while True:
        try:
            func, cf_future = _work_queue.get_nowait()
        except queue.Empty:
            break

        if cf_future.cancelled():
            logger.debug("跳过已取消的 Future")
            continue

        logger.debug("主线程执行任务: %s", getattr(func, "__name__", repr(func)))
        try:
            result = func()
            cf_future.set_result(result)
            logger.debug("任务完成，结果: %s", result)
        except Exception as exc:
            logger.exception("主线程任务抛出异常: %s", exc)
            cf_future.set_exception(exc)


def _schedule_on_main_thread(func) -> concurrent.futures.Future:  # type: ignore[type-arg]
    """
    将 func 调度到 Rhino 主线程执行。

    返回 concurrent.futures.Future。
    在 async 代码中使用 ``await asyncio.wrap_future(returned_future)`` 等待结果。
    此函数本身是线程安全的（queue.Queue 内部有锁）。
    """
    cf_future: concurrent.futures.Future = concurrent.futures.Future()
    _work_queue.put((func, cf_future))
    logger.debug("已入队: %s", getattr(func, "__name__", repr(func)))
    return cf_future


# ---------------------------------------------------------------------------
# FastMCP Server 定义
# ---------------------------------------------------------------------------
MCP_HOST = "127.0.0.1"
MCP_PORT = 3333

mcp = FastMCP(
    "RhinoCoder",
    description="Sprint 2 MVP — 通过 MCP 协议在 Rhino 8 中执行几何体操作",
    host=MCP_HOST,
    port=MCP_PORT,
)


@mcp.tool()
async def create_sphere(radius: float) -> str:
    """
    以原点 (0, 0, 0) 为圆心，在 Rhino 当前文档中创建一个球体。

    Args:
        radius: 球体半径（正数，单位与当前 Rhino 文件单位一致）

    Returns:
        成功时：包含球体 GUID 的确认消息。
        失败时：错误描述字符串。
    """
    logger.info("create_sphere 调用，radius=%.4f", radius)

    if radius <= 0:
        msg = f"参数错误：radius 必须为正数，收到 {radius!r}"
        logger.warning(msg)
        return msg

    def _do_create_sphere() -> str:
        """
        在 Rhino 主线程中执行。
        rhinoscriptsyntax 仅在主线程中导入和调用，符合 Rhino 线程模型要求。
        """
        import rhinoscriptsyntax as rs  # noqa: PLC0415

        logger.debug("主线程：调用 rs.AddSphere([0,0,0], %.4f)", radius)
        guid = rs.AddSphere([0.0, 0.0, 0.0], radius)

        if guid is None:
            raise RuntimeError(
                "rs.AddSphere 返回 None，球体创建失败"
                "（可能原因：文档处于锁定状态，或 radius 被 Rhino 拒绝）"
            )

        logger.info("球体创建成功，GUID=%s", guid)
        return str(guid)

    cf_future = _schedule_on_main_thread(_do_create_sphere)

    try:
        # asyncio.wrap_future 将 concurrent.futures.Future 桥接到当前 asyncio 事件循环。
        # 当主线程调用 cf_future.set_result() 时，此处 await 立即返回。
        guid_str = await asyncio.wrap_future(cf_future)
        return (
            f"成功：已在原点 (0, 0, 0) 创建半径 {radius} 的球体。\n"
            f"GUID = {guid_str}"
        )
    except Exception as exc:
        logger.error("create_sphere 失败: %s", exc)
        return f"失败：{exc}"


# ---------------------------------------------------------------------------
# Server 生命周期管理
# ---------------------------------------------------------------------------
_server_thread: "threading.Thread | None" = None
_idle_registered: bool = False


def _server_thread_target() -> None:
    """
    后台线程入口函数。
    anyio.run()（由 FastMCP.run() 内部调用）会为当前线程创建独立的 asyncio 事件循环，
    与 Rhino 主线程的事件循环完全隔离，不会阻塞 UI。
    """
    logger.info("MCP Server 线程启动 (TID=%d)", threading.get_ident())
    try:
        mcp.run(transport="sse")
    except OSError as exc:
        logger.error(
            "MCP Server 启动失败（端口 %d 可能已被占用）: %s",
            MCP_PORT,
            exc,
        )
    except Exception as exc:
        logger.exception("MCP Server 线程意外崩溃: %s", exc)
    finally:
        logger.info("MCP Server 线程退出")


def start_server() -> None:
    """
    启动 RhinoCoder MCP Server。

    必须从 Rhino 主线程调用（通常在 Script Editor 或 RhinoCoder Panel 初始化时）。
    幂等：重复调用无副作用。
    """
    global _server_thread, _idle_registered

    # 防止重复启动
    if _server_thread is not None and _server_thread.is_alive():
        logger.warning("MCP Server 已在运行，忽略重复启动")
        return

    # 注册 Idle 处理器，用于在主线程派发几何体操作
    if not _idle_registered:
        try:
            import Rhino  # noqa: PLC0415
            Rhino.RhinoApp.Idle += _idle_handler
            _idle_registered = True
            logger.info("已注册 Rhino.RhinoApp.Idle 主线程派发器")
        except ImportError:
            # 在 Rhino 外部（如单元测试）运行时，优雅降级
            logger.warning(
                "Rhino 模块不可用，跳过 Idle 注册（非 Rhino 环境运行）"
            )
        except Exception as exc:
            logger.error("注册 Idle 处理器失败: %s", exc)
            raise

    # 启动后台 Server 线程
    # daemon=True：Rhino 进程退出时，该线程自动终止，无需手动清理
    _server_thread = threading.Thread(
        target=_server_thread_target,
        name="RhinoCoderMCPServer",
        daemon=True,
    )
    _server_thread.start()

    logger.info("=" * 60)
    logger.info("  RhinoCoder MCP Server 已启动")
    logger.info("  SSE 端点 : http://%s:%d/sse", MCP_HOST, MCP_PORT)
    logger.info("  线程名   : %s (TID=%d)", _server_thread.name, _server_thread.ident or -1)
    logger.info("")
    logger.info("  Claude Desktop 配置（~/.config/claude/config.json）:")
    logger.info('  "mcpServers": {')
    logger.info('    "rhinocoder": { "url": "http://%s:%d/sse" }', MCP_HOST, MCP_PORT)
    logger.info("  }")
    logger.info("=" * 60)


def stop_server() -> None:
    """
    注销 Idle 处理器并清理 Server 引用。

    后台 daemon 线程会随 Rhino 进程自动终止；
    此函数主要用于在 Rhino 会话中手动热重载场景。
    """
    global _server_thread, _idle_registered

    if _idle_registered:
        try:
            import Rhino  # noqa: PLC0415
            Rhino.RhinoApp.Idle -= _idle_handler
            _idle_registered = False
            logger.info("已注销 Rhino.RhinoApp.Idle 处理器")
        except Exception as exc:
            logger.warning("注销 Idle 处理器时出错（可忽略）: %s", exc)

    _server_thread = None
    logger.info("MCP Server 已停止")


# ---------------------------------------------------------------------------
# 在 Rhino Script Editor 中直接运行时自动启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    start_server()
