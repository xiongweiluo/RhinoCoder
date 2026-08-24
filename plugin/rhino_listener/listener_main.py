"""
rhino_listener/listener_main.py  —  运行在 Rhino 8 内部（Python 3.9，纯标准库）

架构
────────────────────────────────────────────────────────────────────
[外部 MCP Server]
      │  POST http://127.0.0.1:8080/<endpoint>  {params}
      ▼
[后台线程: _ThreadedHTTPServer  —  _RhinoHTTPHandler.do_POST()]
      │  路由查 _ROUTE_TABLE → _route_*(h)（已包裹 api_error_handler）
      │  → h._enqueue_and_wait(operation, params)
      │  → _PendingWork 入队 _work_queue
      │  → work.done.wait(timeout)  ← 阻塞请求处理线程
      ▼
[_work_queue: queue.Queue]（来自 ._types）
      │  Rhino.RhinoApp.Idle 主线程消费
      ▼
[Rhino 主线程: _idle_handler]
      │  → 查 _DISPATCH_TABLE[operation] → _exec_fn(rs, params)
      │  → work.result_guid / result_guids / result_data / error
      │  → work.done.set()
      ▼
[_RhinoHTTPHandler 返回 JSON 响应给 MCP Server]
────────────────────────────────────────────────────────────────────

使用方式（在 Rhino Script Editor 中执行一次即可）:
    import sys
    sys.path.insert(0, r"/path/to/RhinoCoder/plugin")
    from rhino_listener import listener_main
    listener_main.start_listener()

停止:
    listener_main.stop_listener()

设计约束：
  - 本文件仅在顶层 import 标准库。
  - Rhino / rhinoscriptsyntax / scriptcontext 均在运行时局部导入
    （函数体内 import），保证本文件可在非 Rhino 环境被 import 而不崩溃。
  - api_error_handler 在本文件定义并在构建 _ROUTE_TABLE 时统一注入，
    各 tools_*.py 模块无需关心装饰器。
"""

from __future__ import annotations

import functools
import json
import logging
import queue
import sys
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Optional

# ---------------------------------------------------------------------------
# 导入包内共享状态（_work_queue, _PendingWork）
# ---------------------------------------------------------------------------
from ._types import _PendingWork, _work_queue

# ---------------------------------------------------------------------------
# 导入四大业务模块（双表 ROUTE_HANDLERS / DISPATCH_HANDLERS）
# ---------------------------------------------------------------------------
from . import tools_geometry
from . import tools_transform
from . import tools_property
from . import tools_perception

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
LISTEN_HOST     = "127.0.0.1"
LISTEN_PORT     = 8080
REQUEST_TIMEOUT = 12.0  # 等待主线程执行的最长秒数
IDEMPOTENCY_CACHE_SIZE = 256

_idempotency_cache: "OrderedDict[str, tuple[str, dict]]" = OrderedDict()
_idempotency_lock = threading.Lock()


def _error_payload(code: str, message: str, recoverable: bool = False) -> dict:
    return {
        "status": "error",
        "message": message,
        "error": {"code": code, "recoverable": recoverable},
    }


def _normalize_response(status: int, data: dict) -> dict:
    """为旧路由生成的错误响应补齐统一错误信封。"""
    if status < 400 or data.get("status") != "error" or data.get("error"):
        return data
    code = {
        400: "http.invalid_argument",
        401: "http.unauthorized",
        403: "http.forbidden",
        404: "http.not_found",
        409: "http.conflict",
        429: "http.rate_limited",
        504: "rhino.main_thread_timeout",
    }.get(status, "http.server_error" if status >= 500 else "http.request_error")
    return {
        **data,
        "error": {"code": code, "recoverable": status in {429, 502, 503, 504}},
    }


# ---------------------------------------------------------------------------
# api_error_handler —— 路由函数防护装饰器
# ---------------------------------------------------------------------------
def api_error_handler(fn):
    """
    捕获路由函数（_route_* 风格，第一参数为 h: _RhinoHTTPHandler）内部抛出
    的任何异常，强制返回 HTTP 200 + {"status": "error", "message": "..."}，
    让 LLM Agent 能从 message 中读取错误并触发自我修正。
    """
    @functools.wraps(fn)
    def wrapper(h, *args, **kwargs):
        try:
            return fn(h, *args, **kwargs)
        except Exception as exc:
            logger.exception("api_error_handler 捕获未处理异常 [%s]: %s", fn.__name__, exc)
            try:
                h._send_json(
                    200,
                    _error_payload("listener.internal", f"发生了内部错误: {exc}"),
                )
            except Exception:
                pass
    return wrapper


# ---------------------------------------------------------------------------
# 动态聚合路由表与派发表
# ---------------------------------------------------------------------------
_TOOL_MODULES = [
    tools_geometry,
    tools_transform,
    tools_property,
    tools_perception,
]

# _ROUTE_TABLE:    {"/endpoint": wrapped_route_fn(h)}
# _DISPATCH_TABLE: {"operation": exec_fn(rs, params)}
_ROUTE_TABLE: dict    = {}
_DISPATCH_TABLE: dict = {}

for _mod in _TOOL_MODULES:
    for _path, _fn in _mod.ROUTE_HANDLERS.items():
        if _path in _ROUTE_TABLE:
            raise RuntimeError(
                f"路由冲突：{_path!r} 在多个 tools 模块中重复注册"
            )
        _ROUTE_TABLE[_path] = api_error_handler(_fn)

    for _op, _fn in _mod.DISPATCH_HANDLERS.items():
        if _op in _DISPATCH_TABLE:
            raise RuntimeError(
                f"操作冲突：{_op!r} 在多个 tools 模块中重复注册"
            )
        _DISPATCH_TABLE[_op] = _fn

# 清理循环变量，避免污染模块命名空间
del _mod, _path, _fn, _op


# ---------------------------------------------------------------------------
# Rhino 主线程 Idle 回调
# ---------------------------------------------------------------------------
def _idle_handler(sender, e) -> None:  # type: ignore[override]
    """
    注册到 Rhino.RhinoApp.Idle。
    主线程空闲时一次性排空队列（避免单帧积压），逐个分发给对应的 _exec_ 函数。

    rhinoscriptsyntax / scriptcontext / Rhino 仅在此处（主线程）导入和调用。
    """
    while True:
        try:
            work: _PendingWork = _work_queue.get_nowait()
        except queue.Empty:
            break

        # 若 HTTP 请求已超时，跳过执行，避免在 Rhino 中产生"幽灵对象"
        if work.cancelled:
            logger.warning(
                "跳过已超时取消的任务 (op=%s, params=%s)",
                work.operation, work.params,
            )
            continue

        logger.debug("主线程：执行 %s params=%s", work.operation, work.params)
        try:
            import rhinoscriptsyntax as rs    # noqa: PLC0415
            import scriptcontext as sc        # noqa: PLC0415
            import Rhino as _Rhino            # noqa: PLC0415

            # 强制重置 rhinoscriptsyntax 全局文档上下文，防止 Idle 回调中
            # 出现"线程上下文丢失"导致 rs.* 读不到正确活动文档的问题。
            sc.doc = _Rhino.RhinoDoc.ActiveDoc

            exec_fn = _DISPATCH_TABLE.get(work.operation)
            if exec_fn is None:
                work.error = f"未知操作类型: {work.operation!r}"
                logger.error(work.error)
                continue

            result = exec_fn(rs, work.params)

            if result is None:
                work.error = (
                    f"{work.operation} 返回 None"
                    "（可能原因：文档处于锁定状态，或参数被 Rhino 拒绝）"
                )
                logger.error(work.error)
            elif isinstance(result, dict):
                work.result_data = result
                logger.info("%s 成功，data=%s", work.operation, work.result_data)
            elif isinstance(result, list):
                work.result_guids = result
                logger.info("%s 成功，GUIDs=%s", work.operation, work.result_guids)
            else:
                work.result_guid = str(result)
                logger.info("%s 成功，GUID=%s", work.operation, work.result_guid)

        except Exception as exc:
            work.error = str(exc)
            logger.exception("主线程执行 %s 失败: %s", work.operation, exc)
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
    """
    daemon_threads = True


class _RhinoHTTPHandler(BaseHTTPRequestHandler):
    """处理所有 POST 路由请求，将操作任务派发至 Rhino 主线程。"""

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "rhinocoder-rhino-listener",
                    "queue_size": _work_queue.qsize(),
                    "registered_endpoints": len(_ROUTE_TABLE),
                },
            )
            return
        self._send_json(404, _error_payload("http.not_found", f"Unknown endpoint: {self.path!r}"))

    def do_POST(self) -> None:
        handler = _ROUTE_TABLE.get(self.path)
        if handler:
            handler(self)
        else:
            self._send_json(
                404,
                {
                    **_error_payload("http.not_found", f"Unknown endpoint: {self.path!r}"),
                    "registered_endpoints": sorted(_ROUTE_TABLE.keys()),
                },
            )

    # ------------------------------------------------------------------
    # 公共辅助方法（供 _route_* 函数通过 h.xxx 调用）
    # ------------------------------------------------------------------
    def _parse_body(self) -> Optional[dict]:
        """读取并解析请求体 JSON。解析失败时自动发送 4xx 响应并返回 None。"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(400, _error_payload("http.invalid_content_length", "Invalid Content-Length header"))
            return None

        if content_length == 0:
            self._send_json(400, _error_payload("http.empty_body", "Empty request body"))
            return None

        try:
            raw = self.rfile.read(content_length)
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            self._send_json(400, _error_payload("http.invalid_json", f"Invalid JSON: {exc}"))
        except Exception as exc:
            self._send_json(400, _error_payload("http.read_failed", f"Failed to read request body: {exc}"))
        return None

    def _enqueue_and_wait(self, operation: str, params: dict) -> None:
        """
        将工作单元入队并阻塞等待 Rhino 主线程完成，最后发送 JSON 响应。
        超时返回 504；执行失败返回 200+error；成功返回 200+data/guids/guid。
        """
        idempotency_key = self.headers.get("Idempotency-Key", "").strip()
        request_signature = operation + ":" + json.dumps(params, ensure_ascii=False, sort_keys=True)
        if idempotency_key:
            if not 8 <= len(idempotency_key) <= 128:
                self._send_json(
                    400,
                    _error_payload("http.invalid_idempotency_key", "Idempotency-Key 长度必须为 8-128"),
                )
                return
            with _idempotency_lock:
                cached = _idempotency_cache.get(idempotency_key)
                if cached is not None:
                    cached_signature, cached_payload = cached
                    if cached_signature != request_signature:
                        self._send_json(
                            409,
                            _error_payload(
                                "http.idempotency_conflict",
                                "同一 Idempotency-Key 不能用于不同请求",
                            ),
                        )
                        return
                    _idempotency_cache.move_to_end(idempotency_key)
                    self._send_json(200, cached_payload)
                    return

        work = _PendingWork(operation=operation, params=params)
        _work_queue.put(work)
        logger.info(
            "请求入队 %s(params=%s)，等待 Rhino 主线程（超时 %.1fs）…",
            operation, params, REQUEST_TIMEOUT,
        )

        if not work.done.wait(timeout=REQUEST_TIMEOUT):
            work.cancelled = True
            logger.error(
                "等待 Rhino 主线程超时（%.1fs）。"
                "请确认 Rhino 未处于模态对话框或长时间阻塞操作中。",
                REQUEST_TIMEOUT,
            )
            self._send_json(
                504,
                _error_payload(
                    "rhino.main_thread_timeout",
                    (
                        f"Timeout: Rhino main thread did not respond "
                        f"within {REQUEST_TIMEOUT}s"
                    ),
                    recoverable=True,
                ),
            )
            return

        if work.error:
            logger.error("%s 执行失败: %s", operation, work.error)
            self._send_json(
                200,
                _error_payload("rhino.execution_failed", work.error, recoverable=True),
            )
        elif work.result_data is not None:
            logger.info("%s 完成，data=%s", operation, work.result_data)
            payload = {"status": "ok", **work.result_data}
            self._cache_and_send(idempotency_key, request_signature, payload)
        elif work.result_guids is not None:
            logger.info("%s 完成，GUIDs=%s", operation, work.result_guids)
            payload = {"status": "ok", "guids": work.result_guids}
            self._cache_and_send(idempotency_key, request_signature, payload)
        else:
            logger.info("%s 完成，GUID=%s", operation, work.result_guid)
            payload = {"status": "ok", "guid": work.result_guid}
            self._cache_and_send(idempotency_key, request_signature, payload)

    def _cache_and_send(self, idempotency_key: str, request_signature: str, payload: dict) -> None:
        if idempotency_key:
            with _idempotency_lock:
                _idempotency_cache[idempotency_key] = (request_signature, payload)
                _idempotency_cache.move_to_end(idempotency_key)
                while len(_idempotency_cache) > IDEMPOTENCY_CACHE_SIZE:
                    _idempotency_cache.popitem(last=False)
        self._send_json(200, payload)

    def _send_json(self, status: int, data: dict) -> None:
        data = _normalize_response(status, data)
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
_server_thread: Optional[threading.Thread]       = None
_idle_registered: bool                           = False


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

    _log_startup_banner()


def stop_listener() -> None:
    """
    关闭 HTTP Server 并注销 Idle 处理器。
    用于热重载或退出前清理。
    """
    global _server_instance, _server_thread, _idle_registered

    if _server_instance is not None:
        try:
            _server_instance.shutdown()
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


def _log_startup_banner() -> None:
    """启动成功后打印端点清单，方便在 Rhino 控制台中确认服务状态。"""
    sep = "=" * 68
    logger.info(sep)
    logger.info("  Rhino HTTP Listener 已启动  %s:%d", LISTEN_HOST, LISTEN_PORT)
    logger.info("  已注册端点（共 %d 个）：", len(_ROUTE_TABLE))
    for path in sorted(_ROUTE_TABLE.keys()):
        logger.info("    POST %s", path)
    logger.info("  单体操作返回  {\"status\": \"ok\", \"guid\": \"<GUID>\"}")
    logger.info("  多体操作返回  {\"status\": \"ok\", \"guids\": [...]}")
    logger.info("  数据型操作返回 {\"status\": \"ok\", <fields>}")
    logger.info(sep)
