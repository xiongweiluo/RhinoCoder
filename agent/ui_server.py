"""RhinoCoder 本地 UI 服务、WebSocket 事件流与运行控制。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=False)

import httpx
from aiohttp import WSMsgType, web

from agent.llm import run_agent
from agent.runtime import AgentEvent, AgentRunResult, CancellationToken, new_run_id, utc_now
from agent.trace_store import save_feedback
from agent.version import __version__

UI_ROOT = _HERE.parent / "ui"
UI_DIST = UI_ROOT / "dist"
REPLAY_DIR = PROJECT_ROOT / "eval" / "replays"
RHINO_BASE_URL = os.environ.get("RHINOCODER_RHINO_URL", "http://127.0.0.1:8080")


@dataclass
class ManagedRun:
    run_id: str
    prompt: str
    closed_loop: bool
    token: CancellationToken
    task: Optional[asyncio.Task] = None
    result: Optional[AgentRunResult] = None
    events: list[dict[str, Any]] = field(default_factory=list)
    control_scene: Optional[dict[str, Any]] = None
    feedback_labels: list[str] = field(default_factory=list)
    rolled_back: bool = False
    undo_applied: bool = False


class RunManager:
    def __init__(self) -> None:
        self.runs: dict[str, ManagedRun] = {}
        self.history: deque[dict[str, Any]] = deque(maxlen=50)
        self.clients: set[web.WebSocketResponse] = set()

    async def broadcast(self, message: dict[str, Any]) -> None:
        stale: list[web.WebSocketResponse] = []
        for client in self.clients:
            try:
                await client.send_json(message)
            except (ConnectionResetError, RuntimeError):
                stale.append(client)
        for client in stale:
            self.clients.discard(client)

    async def start(self, prompt: str, *, closed_loop: bool = True) -> str:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("指令不能为空")
        run_id = new_run_id()
        managed = ManagedRun(
            run_id=run_id,
            prompt=prompt,
            closed_loop=closed_loop,
            token=CancellationToken(),
        )
        self.runs[run_id] = managed

        async def on_event(event: AgentEvent) -> None:
            data = event.to_dict()
            managed.events.append(data)
            await self.broadcast(data)

        async def execute() -> None:
            try:
                managed.result = await run_agent(
                    prompt,
                    closed_loop=closed_loop,
                    event_callback=on_event,
                    cancellation_token=managed.token,
                    run_id=run_id,
                )
                self.history.appendleft(
                    {
                        "run_id": run_id,
                        "prompt": prompt,
                        "closed_loop": closed_loop,
                        "status": managed.result.status.value,
                        "metrics": managed.result.to_dict()["metrics"],
                        "created_object_ids": managed.result.created_object_ids,
                        "events": list(managed.events),
                        "route_decision": managed.result.route_decision,
                        "control_scene": managed.control_scene,
                        "feedback_labels": list(managed.feedback_labels),
                        "rolled_back": managed.rolled_back,
                        "undo_applied": managed.undo_applied,
                    }
                )
                await self.broadcast(
                    {"type": "history.updated", "history": list(self.history)}
                )
            except Exception as exc:
                await self.broadcast(
                    {
                        "type": "run.failed",
                        "run_id": run_id,
                        "seq": len(managed.events) + 1,
                        "timestamp": utc_now(),
                        "payload": {
                            "status": "failed",
                            "error": {"code": "ui.run_manager", "message": str(exc)},
                        },
                    }
                )

        managed.task = asyncio.create_task(execute(), name=f"rhinocoder-{run_id}")
        return run_id

    async def cancel(self, run_id: str) -> None:
        managed = self._get_run(run_id)
        managed.token.cancel()
        if managed.task and not managed.task.done():
            managed.task.cancel()

    async def retry(self, run_id: str) -> str:
        managed = self._get_run(run_id)
        return await self.start(managed.prompt, closed_loop=managed.closed_loop)

    async def rollback(self, run_id: str) -> dict[str, Any]:
        managed = self._get_run(run_id)
        if managed.result is None:
            raise ValueError("任务尚未结束，不能回滚")
        if managed.rolled_back:
            raise ValueError("该任务已经完成精准回滚")
        object_ids = managed.result.created_object_ids
        if not object_ids:
            raise ValueError("该任务没有可追踪的已创建对象")
        result = await _rhino_post("/delete_objects", {"object_ids": object_ids})
        scene_summary = await self.capture_scene(run_id)
        managed.rolled_back = not bool(result.get("failed"))
        self._update_history(
            run_id,
            control_scene=scene_summary,
            rolled_back=managed.rolled_back,
        )
        return {"result": result, "scene_summary": scene_summary}

    async def capture_scene(self, run_id: str) -> dict[str, Any]:
        managed = self._get_run(run_id)
        scene = await _rhino_post("/get_scene_summary", {})
        summary = {
            "objects": scene.get("objects", []),
            "total": scene.get("total", len(scene.get("objects", []))),
            "capped": bool(scene.get("capped", False)),
        }
        managed.control_scene = summary
        self._update_history(run_id, control_scene=summary)
        return summary

    def record_feedback(self, run_id: str, label: str, note: str = "") -> dict[str, Any]:
        managed = self._get_run(run_id)
        if managed.result is None:
            raise ValueError("任务尚未结束，不能提交反馈")
        record = {
            "run_id": managed.run_id,
            "instruction": managed.prompt,
            "run_status": managed.result.status.value,
            "label": label,
            "note": note[:1000],
            "timestamp": utc_now(),
        }
        save_feedback(record)
        managed.feedback_labels.append(label)
        self._update_history(run_id, feedback_labels=list(managed.feedback_labels))
        return record

    def mark_undo_applied(self, run_id: str) -> None:
        managed = self._get_run(run_id)
        if managed.undo_applied:
            raise ValueError("该任务已经执行过 Undo")
        managed.undo_applied = True
        self._update_history(run_id, undo_applied=True)

    def _update_history(self, run_id: str, **changes: Any) -> None:
        for item in self.history:
            if item.get("run_id") == run_id:
                item.update(changes)
                return

    def snapshot(self) -> dict[str, Any]:
        active = []
        for managed in self.runs.values():
            if managed.task and not managed.task.done():
                active.append(
                    {
                        "run_id": managed.run_id,
                        "prompt": managed.prompt,
                        "closed_loop": managed.closed_loop,
                        "events": managed.events,
                    }
                )
        return {"type": "snapshot", "history": list(self.history), "active": active}

    def _get_run(self, run_id: str) -> ManagedRun:
        managed = self.runs.get(run_id)
        if managed is None:
            raise KeyError(f"未知 run_id: {run_id}")
        return managed

    async def shutdown(self) -> None:
        for managed in self.runs.values():
            if managed.task and not managed.task.done():
                managed.token.cancel()
                managed.task.cancel()
        pending = [managed.task for managed in self.runs.values() if managed.task]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


RUN_MANAGER_KEY = web.AppKey("run_manager", RunManager)


async def _rhino_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            f"{RHINO_BASE_URL}{endpoint}",
            json=payload,
            timeout=httpx.Timeout(connect=3.0, read=20.0, write=5.0, pool=5.0),
        )
    data = response.json()
    if response.status_code >= 400 or data.get("status") == "error":
        code = (data.get("error") or {}).get("code", f"http.{response.status_code}")
        raise RuntimeError(f"{code}: {data.get('message', response.text[:200])}")
    return data


async def _health(_: web.Request) -> web.Response:
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"{RHINO_BASE_URL}/health", timeout=3.0)
            rhino = response.json()
    except Exception as exc:
        rhino = {"status": "error", "message": str(exc)}
    return web.json_response({"status": "ok", "version": __version__, "rhino": rhino})


async def _replays(_: web.Request) -> web.Response:
    names = sorted(path.name for path in REPLAY_DIR.glob("*.json")) if REPLAY_DIR.is_dir() else []
    return web.json_response({"replays": names})


def _safe_replay_path(name: str) -> Path:
    if Path(name).name != name:
        raise ValueError("非法 Replay 文件名")
    path = REPLAY_DIR / name
    if path.suffix != ".json" or not path.is_file():
        raise FileNotFoundError(name)
    return path


async def _stream_replay(manager: RunManager, name: str) -> None:
    data = json.loads(_safe_replay_path(name).read_text(encoding="utf-8"))
    events = data.get("events", data if isinstance(data, list) else [])
    if not isinstance(events, list):
        raise ValueError("Replay 缺少 events 列表")
    for event in events:
        if isinstance(event, dict):
            replay_event = {**event, "replay": True}
            await manager.broadcast(replay_event)
            await asyncio.sleep(0.08)


async def _websocket(request: web.Request) -> web.WebSocketResponse:
    manager = request.app[RUN_MANAGER_KEY]
    socket = web.WebSocketResponse(heartbeat=20, max_msg_size=1_000_000)
    await socket.prepare(request)
    manager.clients.add(socket)
    await socket.send_json(manager.snapshot())

    try:
        async for message in socket:
            if message.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(message.data)
                message_type = data.get("type")
                if message_type == "instruction":
                    run_id = await manager.start(
                        str(data.get("content", "")),
                        closed_loop=bool(data.get("closed_loop", True)),
                    )
                    await socket.send_json({"type": "control.accepted", "action": "start", "run_id": run_id})
                elif message_type == "cancel":
                    run_id = str(data.get("run_id", ""))
                    await manager.cancel(run_id)
                    await socket.send_json(
                        {
                            "type": "control.completed",
                            "action": "cancel",
                            "run_id": run_id,
                            "payload": {"message": "停止请求已发送"},
                        }
                    )
                elif message_type == "retry":
                    run_id = await manager.retry(str(data.get("run_id", "")))
                    await socket.send_json({"type": "control.accepted", "action": "retry", "run_id": run_id})
                elif message_type == "undo":
                    run_id = str(data.get("run_id", ""))
                    managed = manager._get_run(run_id)
                    if managed.undo_applied:
                        raise ValueError("该任务已经执行过 Undo")
                    result = await _rhino_post("/undo_last_action", {})
                    manager.mark_undo_applied(run_id)
                    scene_summary = await manager.capture_scene(run_id)
                    await manager.broadcast(
                        {"type": "history.updated", "history": list(manager.history)}
                    )
                    await socket.send_json(
                        {
                            "type": "control.completed",
                            "action": "undo",
                            "run_id": run_id,
                            "payload": {"result": result, "scene_summary": scene_summary},
                        }
                    )
                elif message_type == "rollback":
                    run_id = str(data.get("run_id", ""))
                    payload = await manager.rollback(run_id)
                    await manager.broadcast(
                        {"type": "history.updated", "history": list(manager.history)}
                    )
                    await socket.send_json(
                        {"type": "control.completed", "action": "rollback", "run_id": run_id, "payload": payload}
                    )
                elif message_type == "feedback":
                    label = str(data.get("label", ""))
                    if label not in {"accepted", "partial", "rejected"}:
                        raise ValueError("feedback label 必须是 accepted/partial/rejected")
                    run_id = str(data.get("run_id", ""))
                    record = manager.record_feedback(
                        run_id,
                        label,
                        str(data.get("note", "")),
                    )
                    await manager.broadcast(
                        {"type": "history.updated", "history": list(manager.history)}
                    )
                    await socket.send_json(
                        {
                            "type": "control.completed",
                            "action": "feedback",
                            "run_id": run_id,
                            "payload": {"label": record["label"], "timestamp": record["timestamp"]},
                        }
                    )
                elif message_type == "replay":
                    asyncio.create_task(_stream_replay(manager, str(data.get("name", ""))))
                elif message_type == "snapshot":
                    await socket.send_json(manager.snapshot())
                else:
                    raise ValueError(f"未知消息类型: {message_type}")
            except Exception as exc:
                await socket.send_json(
                    {
                        "type": "control.error",
                        "payload": {"message": str(exc), "recoverable": True},
                    }
                )
    finally:
        manager.clients.discard(socket)
    return socket


async def _index(_: web.Request) -> web.FileResponse:
    if (UI_DIST / "index.html").is_file():
        return web.FileResponse(UI_DIST / "index.html")
    return web.FileResponse(UI_ROOT / "fallback.html")


def create_app() -> web.Application:
    app = web.Application()
    manager = RunManager()
    app[RUN_MANAGER_KEY] = manager
    app.router.add_get("/", _index)
    app.router.add_get("/api/health", _health)
    app.router.add_get("/api/replays", _replays)
    app.router.add_get("/ws", _websocket)
    static_root = UI_DIST if UI_DIST.is_dir() else UI_ROOT
    app.router.add_static("/assets", static_root / "assets" if (static_root / "assets").is_dir() else static_root)
    app.on_shutdown.append(lambda _app: manager.shutdown())
    return app


async def start_ui_server(port: int = 7860, host: str = "127.0.0.1") -> web.AppRunner:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("UI 服务只允许绑定本机回环地址")
    runner = web.AppRunner(create_app())
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner


def main() -> None:
    parser = argparse.ArgumentParser(description="RhinoCoder UI Server")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    web.run_app(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
