"""
plugin/rhino_http_listener.py  —  运行在 Rhino 8 内部（Python 3.9，纯标准库）

架构
────────────────────────────────────────────────────────────────────
[外部 MCP Server]
      │  POST http://127.0.0.1:8080/draw_sphere  {"radius": 15.0}
      ▼
[后台线程: ThreadedHTTPServer  —  _RhinoHTTPHandler.do_POST()]
      │  _PendingWork 入队 _work_queue
      │  work.done.wait(timeout)  ← 阻塞请求处理线程，不影响 UI
      ▼
[_work_queue: queue.Queue]
      │  Rhino.RhinoApp.Idle 主线程消费
      ▼
[Rhino 主线程: rs.AddSphere()  →  work.result_guid / work.error]
      │  work.done.set()  → 请求处理线程解除等待
      ▼
[_RhinoHTTPHandler 返回 JSON 响应给 MCP Server]
────────────────────────────────────────────────────────────────────

使用方式（在 Rhino Script Editor 中执行一次即可）:
    import sys
    sys.path.insert(0, r"/path/to/RhinoCoder/plugin")
    import rhino_http_listener
    rhino_http_listener.start_listener()

停止:
    rhino_http_listener.stop_listener()
"""

from __future__ import annotations

import json
import logging
import queue
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

# ---------------------------------------------------------------------------
# Logging —— 输出到 stdout，在 Rhino Python 控制台中可见
# ---------------------------------------------------------------------------
logger = logging.getLogger("rhinocoder.http_listener")
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
# 配置
# ---------------------------------------------------------------------------
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8080
REQUEST_TIMEOUT = 12.0  # 等待主线程执行的最长秒数

# ---------------------------------------------------------------------------
# 跨线程工作单元
# ---------------------------------------------------------------------------
@dataclass
class _PendingWork:
    """一次 draw_sphere 请求在主线程和请求处理线程之间共享的状态。"""
    radius: float
    result_guid: Optional[str] = None
    error: Optional[str] = None
    # 主线程完成后调用 done.set()，请求处理线程在此等待
    done: threading.Event = field(default_factory=threading.Event)
    # 请求处理线程超时后设为 True，通知主线程跳过该任务
    cancelled: bool = False


# ---------------------------------------------------------------------------
# 工作队列 —— 请求处理线程 put，主线程（Idle 事件）get
# ---------------------------------------------------------------------------
_work_queue: queue.Queue = queue.Queue()


# ---------------------------------------------------------------------------
# Rhino.RhinoApp.Idle 回调 —— 在主线程执行几何体操作
# ---------------------------------------------------------------------------
def _idle_handler(sender, e) -> None:  # type: ignore[override]
    """
    注册到 Rhino.RhinoApp.Idle。
    主线程空闲时一次性排空队列，避免单帧积压。
    rhinoscriptsyntax 只在此处（主线程）导入和调用。
    """
    while True:
        try:
            work: _PendingWork = _work_queue.get_nowait()
        except queue.Empty:
            break

        # 若 HTTP 请求已超时，跳过执行，避免在 Rhino 中产生"幽灵球体"
        if work.cancelled:
            logger.warning("跳过已超时取消的任务 (radius=%.4f)", work.radius)
            continue

        logger.debug("主线程：执行 rs.AddSphere(radius=%.4f)", work.radius)
        try:
            import rhinoscriptsyntax as rs  # noqa: PLC0415
            guid = rs.AddSphere([0.0, 0.0, 0.0], work.radius)
            if guid is None:
                work.error = (
                    "rs.AddSphere 返回 None"
                    "（可能原因：文档处于锁定状态，或 radius 被 Rhino 拒绝）"
                )
                logger.error(work.error)
            else:
                work.result_guid = str(guid)
                logger.info("球体创建成功，GUID=%s", work.result_guid)
        except Exception as exc:
            work.error = str(exc)
            logger.exception("主线程执行 rs.AddSphere 失败: %s", exc)
        finally:
            # 无论成功或失败，都通知等待中的 HTTP 处理线程
            work.done.set()


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------
class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """
    每个请求在独立线程中处理（ThreadingMixIn）。
    daemon_threads=True 确保请求处理线程不阻止 Rhino 退出。
    allow_reuse_address 继承自 HTTPServer 默认值 True，避免重启时端口占用。
    """
    daemon_threads = True


class _RhinoHTTPHandler(BaseHTTPRequestHandler):
    """处理 POST /draw_sphere 请求。"""

    def do_POST(self) -> None:
        if self.path == "/draw_sphere":
            self._handle_draw_sphere()
        else:
            self._send_json(404, {"error": f"Unknown endpoint: {self.path}"})

    # ------------------------------------------------------------------
    def _handle_draw_sphere(self) -> None:
        # 1. 解析请求体
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(400, {"error": "Invalid Content-Length header"})
            return

        if content_length == 0:
            self._send_json(400, {"error": "Empty request body"})
            return

        try:
            raw = self.rfile.read(content_length)
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"Invalid JSON: {exc}"})
            return
        except Exception as exc:
            self._send_json(400, {"error": f"Failed to read request body: {exc}"})
            return

        # 2. 校验 radius
        try:
            radius = float(data["radius"])
        except KeyError:
            self._send_json(400, {"error": "Missing field: radius"})
            return
        except (TypeError, ValueError) as exc:
            self._send_json(400, {"error": f"Invalid radius value: {exc}"})
            return

        if radius <= 0:
            self._send_json(
                400, {"error": f"radius must be positive, got {radius}"}
            )
            return

        # 3. 入队并等待主线程执行
        work = _PendingWork(radius=radius)
        _work_queue.put(work)
        logger.info(
            "请求入队 draw_sphere(radius=%.4f)，等待 Rhino 主线程（超时 %.1fs）…",
            radius,
            REQUEST_TIMEOUT,
        )

        if not work.done.wait(timeout=REQUEST_TIMEOUT):
            # 超时：标记取消，防止主线程事后仍然执行
            work.cancelled = True
            logger.error(
                "等待 Rhino 主线程超时（%.1fs）。"
                "请确认 Rhino 未处于模态对话框或长时间阻塞操作中。",
                REQUEST_TIMEOUT,
            )
            self._send_json(
                504,
                {
                    "error": (
                        f"Timeout: Rhino main thread did not respond "
                        f"within {REQUEST_TIMEOUT}s"
                    )
                },
            )
            return

        # 4. 返回结果
        if work.error:
            logger.error("draw_sphere 执行失败: %s", work.error)
            self._send_json(500, {"error": work.error})
        else:
            logger.info("draw_sphere 完成，GUID=%s", work.result_guid)
            self._send_json(200, {"status": "ok", "guid": work.result_guid})

    # ------------------------------------------------------------------
    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # 将 BaseHTTPRequestHandler 的默认 stderr 输出重定向到 logger
        logger.debug("HTTP %s", format % args)


# ---------------------------------------------------------------------------
# Server 生命周期管理
# ---------------------------------------------------------------------------
_server_instance: Optional[_ThreadedHTTPServer] = None
_server_thread: Optional[threading.Thread] = None
_idle_registered: bool = False


def _server_thread_target(server: _ThreadedHTTPServer) -> None:
    """后台线程入口：阻塞在 serve_forever() 直到 server.shutdown() 被调用。"""
    logger.info("HTTP Listener 线程启动 (TID=%d)", threading.get_ident())
    try:
        server.serve_forever()
    except Exception as exc:
        logger.exception("HTTP Listener 线程崩溃: %s", exc)
    finally:
        logger.info("HTTP Listener 线程退出")


def start_listener() -> None:
    """
    启动 Rhino HTTP Listener。

    必须从 Rhino 主线程调用。幂等：重复调用无副作用。
    """
    global _server_instance, _server_thread, _idle_registered

    if _server_thread is not None and _server_thread.is_alive():
        logger.warning("HTTP Listener 已在运行（端口 %d），忽略重复启动", LISTEN_PORT)
        return

    # 注册 Idle 处理器（主线程几何体派发）
    if not _idle_registered:
        try:
            import Rhino  # noqa: PLC0415
            Rhino.RhinoApp.Idle += _idle_handler
            _idle_registered = True
            logger.info("已注册 Rhino.RhinoApp.Idle 主线程派发器")
        except ImportError:
            logger.warning("Rhino 模块不可用，跳过 Idle 注册（非 Rhino 环境运行）")
        except Exception as exc:
            logger.error("注册 Idle 处理器失败: %s", exc)
            raise

    # 创建 HTTP Server（可能因端口占用抛出 OSError）
    try:
        server = _ThreadedHTTPServer((LISTEN_HOST, LISTEN_PORT), _RhinoHTTPHandler)
    except OSError as exc:
        logger.error(
            "HTTP Server 创建失败，端口 %d 可能已被占用: %s\n"
            "可尝试修改 LISTEN_PORT 后重启。",
            LISTEN_PORT,
            exc,
        )
        raise

    _server_instance = server

    # 启动后台线程（daemon=True：Rhino 退出时自动终止）
    _server_thread = threading.Thread(
        target=_server_thread_target,
        args=(server,),
        name="RhinoCoderHTTPListener",
        daemon=True,
    )
    _server_thread.start()

    logger.info("=" * 58)
    logger.info("  Rhino HTTP Listener 已启动")
    logger.info("  端点 : POST http://%s:%d/draw_sphere", LISTEN_HOST, LISTEN_PORT)
    logger.info("  请求体: {\"radius\": <float>}")
    logger.info("  响应体: {\"status\": \"ok\", \"guid\": \"<GUID>\"}")
    logger.info("=" * 58)


def stop_listener() -> None:
    """
    关闭 HTTP Server 并注销 Idle 处理器。
    用于热重载或退出前清理。
    """
    global _server_instance, _server_thread, _idle_registered

    if _server_instance is not None:
        try:
            _server_instance.shutdown()   # 通知 serve_forever() 退出
            _server_instance.server_close()
            logger.info("HTTP Server（端口 %d）已关闭", LISTEN_PORT)
        except Exception as exc:
            logger.warning("关闭 HTTP Server 时出错: %s", exc)
        _server_instance = None

    if _idle_registered:
        try:
            import Rhino  # noqa: PLC0415
            Rhino.RhinoApp.Idle -= _idle_handler
            _idle_registered = False
            logger.info("已注销 Rhino.RhinoApp.Idle 处理器")
        except Exception as exc:
            logger.warning("注销 Idle 处理器时出错（可忽略）: %s", exc)

    _server_thread = None
    logger.info("HTTP Listener 已停止")


# ---------------------------------------------------------------------------
# 在 Rhino Script Editor 中直接运行此脚本时自动启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    start_listener()
