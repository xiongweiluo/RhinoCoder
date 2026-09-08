"""RhinoCoder 本地 UI 服务、WebSocket 事件流与运行控制。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from agent.privacy import minimize_for_cloud, sanitize_for_log
from agent.runtime import AgentEvent, AgentRunResult, CancellationToken, RunError, RunStatus, new_run_id, utc_now
from agent.sanitizer import sanitize_text
from agent.trace_store import save_feedback
from agent.version import __version__
from eval.scene_assert import verify

UI_ROOT = _HERE.parent / "ui"
UI_DIST = UI_ROOT / "dist"
REPLAY_DIR = PROJECT_ROOT / "eval" / "replays"
DEMO_CATALOG_PATH = PROJECT_ROOT / "docs" / "demo" / "p1-scenarios.json"
RHINO_BASE_URL = os.environ.get("RHINOCODER_RHINO_URL", "http://127.0.0.1:8080")
TERMINAL_EVENT_TYPES = {"run.completed", "run.failed", "run.cancelled"}
LINEAGE_ID_KEYS = {"run_id", "route_id", "decision_id", "request_id", "call_id", "tool_call_id"}


def _pseudonymize_object_id(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"object-{digest}"


def _browser_safe(value: Any, *, parent_key: str = "") -> Any:
    """Minimize browser payloads while preserving geometry and lineage evidence."""
    minimized = minimize_for_cloud(value, parent_key=parent_key)
    key = parent_key.lower()
    if isinstance(minimized, dict):
        return {
            str(item_key): _browser_safe(item, parent_key=str(item_key))
            for item_key, item in minimized.items()
        }
    if isinstance(minimized, (list, tuple)):
        if key in {"created_object_ids", "object_ids"}:
            return [
                _pseudonymize_object_id(str(item))
                for item in minimized
                if item not in (None, "")
            ]
        return [_browser_safe(item, parent_key=parent_key) for item in minimized]
    if isinstance(minimized, str):
        if key in {"object_id", "rhino_object_id"}:
            return _pseudonymize_object_id(minimized)
        if key in LINEAGE_ID_KEYS:
            return minimized
        return sanitize_text(minimized)
    return minimized


def _load_demo_catalog() -> dict[str, Any]:
    payload = json.loads(DEMO_CATALOG_PATH.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if payload.get("schema_version") != "1.0" or not isinstance(scenarios, list):
        raise ValueError("P1 演示场景清单格式无效")
    identifiers = [item.get("id") for item in scenarios if isinstance(item, dict)]
    if len(identifiers) != 3 or len(set(identifiers)) != 3:
        raise ValueError("P1 必须精确提供三个唯一演示场景")
    return payload


def _scenario_by_id(scenario_id: str) -> dict[str, Any]:
    for scenario in _load_demo_catalog()["scenarios"]:
        if scenario.get("id") == scenario_id:
            return scenario
    raise KeyError(f"未知演示场景: {scenario_id}")


def _public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    evidence = scenario.get("evidence") or {}
    return _browser_safe(
        {
            key: value
            for key, value in scenario.items()
            if key != "asserts"
        }
        | {
            "evidence": {
                **evidence,
                "href": f"/evidence/{evidence.get('path', '')}",
            },
            "read_only_url": f"/?demo={scenario['id']}",
        }
    )


def _scene_from_events(events: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for event in reversed(events):
        if event.get("type") != "scene.checked":
            continue
        summary = (event.get("payload") or {}).get("scene_summary")
        if isinstance(summary, dict) and isinstance(summary.get("objects"), list):
            return summary
    return None


def _load_replay(name: str) -> dict[str, Any]:
    payload = json.loads(_safe_replay_path(name).read_text(encoding="utf-8"))
    privacy = payload.get("privacy") or {}
    events = payload.get("events")
    if (
        payload.get("sample") is not True
        or payload.get("provenance") != "synthetic"
        or privacy.get("reviewed") is not True
        or privacy.get("contains_real_trace_data") is not False
        or not isinstance(events, list)
        or not events
    ):
        raise ValueError("Replay 未通过公开只读准入")
    sequences = [event.get("seq") for event in events if isinstance(event, dict)]
    if sequences != list(range(1, len(events) + 1)):
        raise ValueError("Replay 事件序号无效")
    return payload


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
    demo_scenario_id: Optional[str] = None
    scene_before: Optional[dict[str, Any]] = None
    scene_after: Optional[dict[str, Any]] = None
    scene_capture_error: Optional[str] = None
    evaluation: Optional[dict[str, Any]] = None
    pending_terminal_event: Optional[dict[str, Any]] = None


class RunManager:
    def __init__(self) -> None:
        self.runs: dict[str, ManagedRun] = {}
        self.history: deque[dict[str, Any]] = deque(maxlen=50)
        self.clients: set[web.WebSocketResponse] = set()

    async def broadcast(self, message: dict[str, Any]) -> None:
        public_message = _browser_safe(message)
        stale: list[web.WebSocketResponse] = []
        for client in self.clients:
            try:
                await client.send_json(public_message)
            except (ConnectionResetError, RuntimeError):
                stale.append(client)
        for client in stale:
            self.clients.discard(client)

    async def start(
        self,
        prompt: str,
        *,
        closed_loop: bool = True,
        demo_scenario_id: Optional[str] = None,
    ) -> str:
        scenario = _scenario_by_id(demo_scenario_id) if demo_scenario_id else None
        if scenario is not None:
            prompt = str(scenario["input"])
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("指令不能为空")
        run_id = new_run_id()
        managed = ManagedRun(
            run_id=run_id,
            prompt=prompt,
            closed_loop=closed_loop,
            token=CancellationToken(),
            demo_scenario_id=demo_scenario_id,
        )
        self.runs[run_id] = managed

        async def on_event(event: AgentEvent) -> None:
            data = event.to_dict()
            if event.type in TERMINAL_EVENT_TYPES:
                managed.pending_terminal_event = data
                return
            managed.events.append(data)
            await self.broadcast(data)

        async def execute() -> None:
            try:
                if scenario is not None:
                    try:
                        managed.scene_before = await _read_scene_summary()
                        await self.broadcast(
                            {
                                "type": "run.context",
                                "run_id": run_id,
                                "payload": {"scene_before": managed.scene_before},
                            }
                        )
                    except Exception as exc:
                        managed.scene_capture_error = sanitize_for_log(str(exc))
                managed.result = await run_agent(
                    prompt,
                    closed_loop=closed_loop,
                    event_callback=on_event,
                    cancellation_token=managed.token,
                    run_id=run_id,
                )
                if scenario is not None and managed.result.status is RunStatus.COMPLETED:
                    try:
                        managed.scene_after = await _read_scene_summary()
                    except Exception as exc:
                        managed.scene_capture_error = sanitize_for_log(str(exc))
                        managed.scene_after = _scene_from_events(managed.events)
                    if managed.scene_after is not None:
                        managed.evaluation = verify(
                            managed.scene_after,
                            list(scenario.get("asserts") or []),
                        )
                final_events = self._append_assertions_and_terminal(managed, scenario)
                for event in final_events:
                    await self.broadcast(event)
                self.history.appendleft(
                    self._history_item(managed)
                )
                await self.broadcast(
                    {"type": "history.updated", "history": list(self.history)}
                )
            except asyncio.CancelledError:
                managed.result = AgentRunResult(
                    run_id=run_id,
                    status=RunStatus.CANCELLED,
                    error=RunError(
                        "run.cancelled",
                        "任务已由用户取消",
                        recoverable=True,
                    ),
                )
                managed.pending_terminal_event = {
                    "type": "run.cancelled",
                    "run_id": run_id,
                    "seq": len(managed.events) + 1,
                    "timestamp": utc_now(),
                    "payload": {
                        "status": "cancelled",
                        "error": {
                            "code": "run.cancelled",
                            "message": "任务已由用户取消",
                            "recoverable": True,
                        },
                    },
                }
                final_events = self._append_assertions_and_terminal(managed, scenario)
                for event in final_events:
                    await self.broadcast(event)
                self.history.appendleft(self._history_item(managed))
                await self.broadcast(
                    {"type": "history.updated", "history": list(self.history)}
                )
            except Exception as exc:
                managed.result = AgentRunResult(
                    run_id=run_id,
                    status=RunStatus.FAILED,
                    error=RunError(
                        "ui.run_manager",
                        sanitize_for_log(str(exc)),
                        recoverable=True,
                    ),
                )
                managed.pending_terminal_event = {
                    "type": "run.failed",
                    "run_id": run_id,
                    "seq": len(managed.events) + 1,
                    "timestamp": utc_now(),
                    "payload": {
                        "status": "failed",
                        "error": {
                            "code": "ui.run_manager",
                            "message": sanitize_for_log(str(exc)),
                            "recoverable": True,
                        },
                    },
                }
                final_events = self._append_assertions_and_terminal(managed, scenario)
                for event in final_events:
                    await self.broadcast(event)
                self.history.appendleft(self._history_item(managed))
                await self.broadcast(
                    {"type": "history.updated", "history": list(self.history)}
                )

        managed.task = asyncio.create_task(execute(), name=f"rhinocoder-{run_id}")
        return run_id

    def _append_assertions_and_terminal(
        self,
        managed: ManagedRun,
        scenario: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        appended: list[dict[str, Any]] = []
        next_seq = max((int(event.get("seq", 0)) for event in managed.events), default=0) + 1
        if managed.evaluation is not None:
            for result in managed.evaluation.get("results") or []:
                spec = result.get("spec") or {}
                event = {
                    "type": "assertion.checked",
                    "run_id": managed.run_id,
                    "seq": next_seq,
                    "timestamp": utc_now(),
                    "payload": {
                        "name": spec.get("label") or spec.get("kind") or "demo_assertion",
                        "success": bool(result.get("ok")),
                        "expected": spec.get("expected_text") or spec,
                        "actual": "最终场景匹配" if result.get("ok") else result.get("reason"),
                        "source": "p1_demo_scene_assert",
                    },
                }
                managed.events.append(event)
                appended.append(event)
                next_seq += 1

        if managed.pending_terminal_event is not None:
            terminal = managed.pending_terminal_event
        elif managed.result is not None:
            terminal_type = {
                RunStatus.COMPLETED: "run.completed",
                RunStatus.CANCELLED: "run.cancelled",
            }.get(managed.result.status, "run.failed")
            terminal = {
                "type": terminal_type,
                "run_id": managed.run_id,
                "seq": next_seq,
                "timestamp": utc_now(),
                "payload": {
                    "status": managed.result.status.value,
                    "metrics": managed.result.metrics.to_dict(),
                },
            }
            if managed.result.error is not None:
                terminal["payload"]["error"] = {
                    "code": managed.result.error.code,
                    "message": managed.result.error.message,
                    "recoverable": managed.result.error.recoverable,
                }
        else:
            terminal = {
                "type": "run.failed",
                "run_id": managed.run_id,
                "seq": next_seq,
                "timestamp": utc_now(),
                "payload": {
                    "status": "failed",
                    "error": {
                        "code": "ui.missing_terminal_event",
                        "message": "运行未产生终态事件",
                        "recoverable": True,
                    },
                },
            }
        if (
            managed.result is not None
            and managed.result.status is RunStatus.COMPLETED
            and managed.evaluation is not None
            and not managed.evaluation.get("passed")
        ):
            terminal = {
                **terminal,
                "type": "run.failed",
                "payload": {
                    **(terminal.get("payload") or {}),
                    "status": "failed",
                    "error": {
                        "code": "demo.assertion_failed",
                        "message": "Agent 已结束，但固定演示场景的几何断言未全部通过。",
                        "recoverable": True,
                    },
                },
            }
        terminal["seq"] = next_seq
        managed.events.append(terminal)
        appended.append(terminal)
        return appended

    def _history_item(self, managed: ManagedRun) -> dict[str, Any]:
        result = managed.result
        assertion_failed = bool(
            result
            and result.status is RunStatus.COMPLETED
            and managed.evaluation is not None
            and not managed.evaluation.get("passed")
        )
        return {
            "run_id": managed.run_id,
            "prompt": managed.prompt,
            "closed_loop": managed.closed_loop,
            "status": "failed" if assertion_failed else result.status.value if result else "failed",
            "metrics": result.to_dict()["metrics"] if result else {},
            "created_object_ids": result.created_object_ids if result else [],
            "events": list(managed.events),
            "route_decision": result.route_decision if result else None,
            "privacy_decision": result.privacy_decision if result else None,
            "control_scene": managed.control_scene,
            "scene_before": managed.scene_before,
            "scene_after": managed.scene_after,
            "scene_capture_error": managed.scene_capture_error,
            "evaluation": managed.evaluation,
            "demo_scenario_id": managed.demo_scenario_id,
            "feedback_labels": list(managed.feedback_labels),
            "rolled_back": managed.rolled_back,
            "undo_applied": managed.undo_applied,
            "is_replay": False,
            "audit_summary": {
                "browser_payload": "minimized",
                "raw_trace_exposed": False,
                "object_ids": "pseudonymized",
                "event_count": len(managed.events),
            },
        }

    async def cancel(self, run_id: str) -> None:
        managed = self._get_run(run_id)
        managed.token.cancel()
        if managed.task and not managed.task.done():
            managed.task.cancel()

    async def retry(self, run_id: str) -> str:
        managed = self._get_run(run_id)
        return await self.start(
            managed.prompt,
            closed_loop=managed.closed_loop,
            demo_scenario_id=managed.demo_scenario_id,
        )

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
                        "scene_before": managed.scene_before,
                        "demo_scenario_id": managed.demo_scenario_id,
                    }
                )
        return _browser_safe({"type": "snapshot", "history": list(self.history), "active": active})

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


async def _read_scene_summary() -> dict[str, Any]:
    scene = await _rhino_post("/get_scene_summary", {})
    objects = scene.get("objects", [])
    return {
        "objects": objects if isinstance(objects, list) else [],
        "total": int(scene.get("total", len(objects) if isinstance(objects, list) else 0)),
        "capped": bool(scene.get("capped", False)),
    }


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


async def _demo_scenarios(_: web.Request) -> web.Response:
    catalog = _load_demo_catalog()
    return web.json_response(
        {
            "schema_version": catalog["schema_version"],
            "privacy": catalog.get("privacy") or {},
            "scenarios": [_public_scenario(item) for item in catalog["scenarios"]],
        }
    )


async def _replay_content(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    replay = _load_replay(name)
    scenario = _scenario_by_id(str(replay.get("demo_scenario", "")))
    if scenario.get("replay") != name:
        raise web.HTTPNotFound(text="Replay 不属于公开场景清单")
    events = replay["events"]
    scene_after = replay.get("scene_after") or _scene_from_events(events)
    return web.json_response(
        _browser_safe(
            {
                "name": replay.get("name"),
                "scenario": _public_scenario(scenario),
                "events": events,
                "scene_before": replay.get("scene_before") or {"total": 0, "capped": False, "objects": []},
                "scene_after": scene_after,
                "read_only": True,
                "audit_summary": {
                    "provenance": "synthetic",
                    "privacy_reviewed": True,
                    "contains_real_trace_data": False,
                    "browser_payload": "minimized",
                    "raw_trace_exposed": False,
                    "object_ids": "pseudonymized",
                    "event_count": len(events),
                },
            }
        )
    )


async def _evidence(request: web.Request) -> web.FileResponse:
    name = request.match_info["name"]
    allowed = {
        str((item.get("evidence") or {}).get("path", ""))
        for item in _load_demo_catalog()["scenarios"]
    }
    if Path(name).name != name or name not in allowed:
        raise web.HTTPNotFound(text="未知证据文件")
    path = PROJECT_ROOT / "docs" / name
    if not path.is_file():
        raise web.HTTPNotFound(text="证据文件不存在")
    return web.FileResponse(path, headers={"Content-Type": "text/markdown; charset=utf-8"})


def _safe_replay_path(name: str) -> Path:
    if Path(name).name != name:
        raise ValueError("非法 Replay 文件名")
    path = REPLAY_DIR / name
    if path.suffix != ".json" or not path.is_file():
        raise FileNotFoundError(name)
    return path


async def _stream_replay(manager: RunManager, name: str) -> None:
    data = _load_replay(name)
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
                        demo_scenario_id=str(data.get("demo_scenario_id") or "") or None,
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
                            "payload": _browser_safe({"result": result, "scene_summary": scene_summary}),
                        }
                    )
                elif message_type == "rollback":
                    run_id = str(data.get("run_id", ""))
                    payload = await manager.rollback(run_id)
                    await manager.broadcast(
                        {"type": "history.updated", "history": list(manager.history)}
                    )
                    await socket.send_json(
                        {"type": "control.completed", "action": "rollback", "run_id": run_id, "payload": _browser_safe(payload)}
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
                        "payload": {"message": sanitize_for_log(str(exc)), "recoverable": True},
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
    app.router.add_get("/api/demo-scenarios", _demo_scenarios)
    app.router.add_get("/api/replays/{name}", _replay_content)
    app.router.add_get("/evidence/{name}", _evidence)
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
