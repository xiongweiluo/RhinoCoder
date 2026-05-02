"""
plugin/rhino_http_listener.py  —  运行在 Rhino 8 内部（Python 3.9，纯标准库）

架构
────────────────────────────────────────────────────────────────────
[外部 MCP Server]
      │  POST http://127.0.0.1:8080/draw_sphere    {"radius": 15.0}
      │  POST http://127.0.0.1:8080/draw_box       {"width": 10.0, "depth": 5.0, "height": 3.0}
      │  POST http://127.0.0.1:8080/draw_cylinder  {"radius": 4.0, "height": 8.0}
      │  POST http://127.0.0.1:8080/draw_line      {"start": [0,0,0], "end": [10,0,0]}
      ▼
[后台线程: ThreadedHTTPServer  —  _RhinoHTTPHandler.do_POST()]
      │  _PendingWork 入队 _work_queue
      │  work.done.wait(timeout)  ← 阻塞请求处理线程，不影响 UI
      ▼
[_work_queue: queue.Queue]
      │  Rhino.RhinoApp.Idle 主线程消费
      ▼
[Rhino 主线程: rs.Add*()  →  work.result_guid / work.error]
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
    """一次几何体操作请求在主线程和请求处理线程之间共享的状态。"""
    operation: str          # 操作类型，如 "draw_sphere"、"draw_box" 等
    params: dict            # 操作所需参数，由各路由处理器填充
    result_guid: Optional[str] = None
    result_guids: Optional[list] = None
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
# rhinoscriptsyntax 调度 —— 根据操作类型调用对应的 rs.Add* 函数
# 仅在 Rhino 主线程（Idle 回调）中被调用，因此可以安全使用 rs.*
# ---------------------------------------------------------------------------
def _dispatch_rhinoscript(rs, operation: str, params: dict):
    if operation == "create_sphere":
        return rs.AddSphere([0.0, 0.0, 0.0], params["radius"])

    elif operation == "create_box":
        w, d, h = params["width"], params["depth"], params["height"]
        corners = [
            [0, 0, 0], [w, 0, 0], [w, d, 0], [0, d, 0],
            [0, 0, h], [w, 0, h], [w, d, h], [0, d, h],
        ]
        return rs.AddBox(corners)

    elif operation == "create_cylinder":
        return rs.AddCylinder(
            [0.0, 0.0, 0.0],
            params["height"],
            params["radius"],
            cap=True,
        )

    elif operation == "create_line":
        return rs.AddLine(params["start"], params["end"])

    elif operation == "move_object":
        obj = params["object_id"]
        t = params["translation"]
        return rs.MoveObject(obj, t)

    elif operation == "extrude_curve_straight":
        curve_id = params["curve_id"]
        sp = params["start_point"]
        ep = params["end_point"]
        ext_id = rs.ExtrudeCurveStraight(curve_id, sp, ep)
        if ext_id is None:
            raise ValueError(
                "rs.ExtrudeCurveStraight 返回 None（曲线无效或起止点相同）"
            )
        if rs.IsCurveClosed(curve_id):
            rs.CapPlanarHoles(ext_id)  # 原地封盖，GUID 不变，不接收返回值
        return ext_id

    elif operation == "boolean_difference":
        input0_ids = params["input0_ids"]
        input1_ids = params["input1_ids"]
        # 强制将字符串 GUID 转换为 Rhino 内部 GUID 对象，提升兼容性
        obj0 = [rs.coerceguid(i) for i in input0_ids]
        obj1 = [rs.coerceguid(i) for i in input1_ids]
        if any(g is None for g in obj0):
            raise ValueError(f"input0_ids 中存在无法解析的 GUID: {input0_ids}")
        if any(g is None for g in obj1):
            raise ValueError(f"input1_ids 中存在无法解析的 GUID: {input1_ids}")
        new_ids = rs.BooleanDifference(obj0, obj1, delete_input=True)
        if not new_ids:
            raise ValueError(
                "BooleanDifference 返回空结果"
                "（可能原因：实体未相交、几何无效，或运算本身失败）"
            )
        return [str(g) for g in new_ids]

    elif operation == "create_circle":
        return rs.AddCircle(params["center"], params["radius"])

    else:
        raise ValueError(f"未知操作类型: {operation!r}")


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

        # 若 HTTP 请求已超时，跳过执行，避免在 Rhino 中产生"幽灵对象"
        if work.cancelled:
            logger.warning(
                "跳过已超时取消的任务 (op=%s, params=%s)",
                work.operation, work.params,
            )
            continue

        logger.debug("主线程：执行 %s params=%s", work.operation, work.params)
        try:
            import rhinoscriptsyntax as rs  # noqa: PLC0415
            result = _dispatch_rhinoscript(rs, work.operation, work.params)
            if result is None:
                work.error = (
                    f"{work.operation} 返回 None"
                    "（可能原因：文档处于锁定状态，或参数被 Rhino 拒绝）"
                )
                logger.error(work.error)
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
    allow_reuse_address 继承自 HTTPServer 默认值 True，避免重启时端口占用。
    """
    daemon_threads = True


class _RhinoHTTPHandler(BaseHTTPRequestHandler):
    """处理所有 POST 路由请求，将几何体创建任务派发至 Rhino 主线程。"""

    def do_POST(self) -> None:
        _routes = {
            "/create_sphere":          self._handle_create_sphere,
            "/create_box":             self._handle_create_box,
            "/create_cylinder":        self._handle_create_cylinder,
            "/create_line":            self._handle_create_line,
            "/create_circle":          self._handle_create_circle,
            "/move_object":            self._handle_move_object,
            "/extrude_curve_straight": self._handle_extrude_curve_straight,
            "/boolean_difference":     self._handle_boolean_difference,
        }
        handler = _routes.get(self.path)
        if handler:
            handler()
        else:
            self._send_json(404, {
                "error": f"Unknown endpoint: {self.path!r}",
                "registered_endpoints": sorted(_routes.keys()),
            })

    # ------------------------------------------------------------------
    # 公共辅助方法
    # ------------------------------------------------------------------
    def _parse_body(self) -> Optional[dict]:
        """读取并解析请求体 JSON。解析失败时自动发送 4xx 响应并返回 None。"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(400, {"error": "Invalid Content-Length header"})
            return None

        if content_length == 0:
            self._send_json(400, {"error": "Empty request body"})
            return None

        try:
            raw = self.rfile.read(content_length)
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"Invalid JSON: {exc}"})
        except Exception as exc:
            self._send_json(400, {"error": f"Failed to read request body: {exc}"})
        return None

    def _enqueue_and_wait(self, operation: str, params: dict) -> None:
        """
        将工作单元入队并等待 Rhino 主线程完成，最后发送 JSON 响应。
        超时返回 504；执行失败返回 500；成功返回 200 + GUID。
        """
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
                {
                    "error": (
                        f"Timeout: Rhino main thread did not respond "
                        f"within {REQUEST_TIMEOUT}s"
                    )
                },
            )
            return

        if work.error:
            logger.error("%s 执行失败: %s", operation, work.error)
            self._send_json(500, {"error": work.error})
        elif work.result_guids is not None:
            logger.info("%s 完成，GUIDs=%s", operation, work.result_guids)
            self._send_json(200, {"status": "ok", "guids": work.result_guids})
        else:
            logger.info("%s 完成，GUID=%s", operation, work.result_guid)
            self._send_json(200, {"status": "ok", "guid": work.result_guid})

    # ------------------------------------------------------------------
    # 各路由处理方法
    # ------------------------------------------------------------------
    def _handle_create_sphere(self) -> None:
        data = self._parse_body()
        if data is None:
            return

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

        self._enqueue_and_wait("create_sphere", {"radius": radius})

    def _handle_create_box(self) -> None:
        data = self._parse_body()
        if data is None:
            return

        params: dict = {}
        for fname in ("width", "depth", "height"):
            try:
                val = float(data[fname])
            except KeyError:
                self._send_json(400, {"error": f"Missing field: {fname}"})
                return
            except (TypeError, ValueError) as exc:
                self._send_json(400, {"error": f"Invalid {fname} value: {exc}"})
                return
            if val <= 0:
                self._send_json(
                    400, {"error": f"{fname} must be positive, got {val}"}
                )
                return
            params[fname] = val

        self._enqueue_and_wait("create_box", params)

    def _handle_create_cylinder(self) -> None:
        data = self._parse_body()
        if data is None:
            return

        params: dict = {}
        for fname in ("radius", "height"):
            try:
                val = float(data[fname])
            except KeyError:
                self._send_json(400, {"error": f"Missing field: {fname}"})
                return
            except (TypeError, ValueError) as exc:
                self._send_json(400, {"error": f"Invalid {fname} value: {exc}"})
                return
            if val <= 0:
                self._send_json(
                    400, {"error": f"{fname} must be positive, got {val}"}
                )
                return
            params[fname] = val

        self._enqueue_and_wait("create_cylinder", params)

    def _handle_create_line(self) -> None:
        data = self._parse_body()
        if data is None:
            return

        params: dict = {}
        for pt_name in ("start", "end"):
            raw_pt = data.get(pt_name)
            if raw_pt is None:
                self._send_json(400, {"error": f"Missing field: {pt_name}"})
                return
            try:
                pt = [float(raw_pt[0]), float(raw_pt[1]), float(raw_pt[2])]
            except (TypeError, IndexError, ValueError) as exc:
                self._send_json(
                    400,
                    {"error": f"Invalid {pt_name} (expected [x, y, z]): {exc}"},
                )
                return
            params[pt_name] = pt

        if params["start"] == params["end"]:
            self._send_json(
                400, {"error": "start and end points must be different"}
            )
            return

        self._enqueue_and_wait("create_line", params)

    def _handle_move_object(self) -> None:
        data = self._parse_body()
        if data is None:
            return

        object_id = data.get("object_id")
        if not object_id or not isinstance(object_id, str):
            self._send_json(
                400,
                {"error": "Missing or invalid field: object_id (expected non-empty string GUID)"},
            )
            return

        raw_t = data.get("translation")
        if raw_t is None:
            self._send_json(400, {"error": "Missing field: translation"})
            return
        try:
            translation = [float(raw_t[0]), float(raw_t[1]), float(raw_t[2])]
        except (TypeError, IndexError, ValueError) as exc:
            self._send_json(
                400, {"error": f"Invalid translation (expected [x, y, z]): {exc}"}
            )
            return

        self._enqueue_and_wait(
            "move_object", {"object_id": object_id, "translation": translation}
        )

    def _handle_extrude_curve_straight(self) -> None:
        data = self._parse_body()
        if data is None:
            return

        curve_id = data.get("curve_id")
        if not curve_id or not isinstance(curve_id, str):
            self._send_json(
                400,
                {"error": "Missing or invalid field: curve_id (expected non-empty string GUID)"},
            )
            return

        params: dict = {"curve_id": curve_id}
        for pt_name in ("start_point", "end_point"):
            raw_pt = data.get(pt_name)
            if raw_pt is None:
                self._send_json(400, {"error": f"Missing field: {pt_name}"})
                return
            try:
                pt = [float(raw_pt[0]), float(raw_pt[1]), float(raw_pt[2])]
            except (TypeError, IndexError, ValueError) as exc:
                self._send_json(
                    400,
                    {"error": f"Invalid {pt_name} (expected [x, y, z]): {exc}"},
                )
                return
            params[pt_name] = pt

        if params["start_point"] == params["end_point"]:
            self._send_json(
                400, {"error": "start_point and end_point must be different"}
            )
            return

        self._enqueue_and_wait("extrude_curve_straight", params)

    def _handle_boolean_difference(self) -> None:
        data = self._parse_body()
        if data is None:
            return

        for field_name in ("input0_ids", "input1_ids"):
            val = data.get(field_name)
            if not val or not isinstance(val, list):
                self._send_json(
                    400,
                    {
                        "error": (
                            f"Missing or invalid field: {field_name} "
                            "(expected non-empty list of GUID strings)"
                        )
                    },
                )
                return
            if not all(isinstance(g, str) and g for g in val):
                self._send_json(
                    400,
                    {"error": f"All elements in {field_name} must be non-empty GUID strings"},
                )
                return

        self._enqueue_and_wait(
            "boolean_difference",
            {"input0_ids": data["input0_ids"], "input1_ids": data["input1_ids"]},
        )

    def _handle_create_circle(self) -> None:
        data = self._parse_body()
        if data is None:
            return

        raw_center = data.get("center")
        if raw_center is None:
            self._send_json(400, {"error": "Missing field: center"})
            return
        try:
            center = [float(raw_center[0]), float(raw_center[1]), float(raw_center[2])]
        except (TypeError, IndexError, ValueError) as exc:
            self._send_json(
                400, {"error": f"Invalid center (expected [x, y, z]): {exc}"}
            )
            return

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

        self._enqueue_and_wait("create_circle", {"center": center, "radius": radius})

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

    logger.info("=" * 68)
    logger.info("  Rhino HTTP Listener 已启动")
    logger.info('  /create_sphere           POST {"radius": <float>}')
    logger.info('  /create_box              POST {"width": <float>, "depth": <float>, "height": <float>}')
    logger.info('  /create_cylinder         POST {"radius": <float>, "height": <float>}')
    logger.info('  /create_line             POST {"start": [x,y,z], "end": [x,y,z]}')
    logger.info('  /create_circle           POST {"center": [x,y,z], "radius": <float>}')
    logger.info('  /move_object             POST {"object_id": "<GUID>", "translation": [x,y,z]}')
    logger.info('  /extrude_curve_straight  POST {"curve_id": "<GUID>", "start_point": [x,y,z], "end_point": [x,y,z]}')
    logger.info('  /boolean_difference      POST {"input0_ids": ["<GUID>",...], "input1_ids": ["<GUID>",...]}')
    logger.info("  单体操作返回  {\"status\": \"ok\", \"guid\": \"<GUID>\"}")
    logger.info("  多体操作返回  {\"status\": \"ok\", \"guids\": [\"<GUID>\",...]} (boolean_difference)")
    logger.info("=" * 68)


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
