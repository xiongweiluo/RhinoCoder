from __future__ import annotations

import asyncio

import pytest

import agent.ui_server as ui_server
from agent.runtime import (
    AgentEvent,
    AgentRunResult,
    CancellationToken,
    RunMetrics,
    RunStatus,
)


class _FakeClient:
    def __init__(self) -> None:
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_run_manager_broadcast_and_history(monkeypatch):
    manager = ui_server.RunManager()
    client = _FakeClient()
    manager.clients.add(client)  # type: ignore[arg-type]

    async def fake_run_agent(prompt, **kwargs):
        event = AgentEvent("run.started", kwargs["run_id"], 1, "now", {"prompt": prompt})
        await kwargs["event_callback"](event)
        return AgentRunResult(
            run_id=kwargs["run_id"],
            status=RunStatus.COMPLETED,
            metrics=RunMetrics(started_at="now", duration_ms=5),
        )

    monkeypatch.setattr(ui_server, "run_agent", fake_run_agent)
    run_id = await manager.start("create a box")
    await manager.runs[run_id].task
    assert client.messages[0]["type"] == "run.started"
    assert client.messages[-1]["type"] == "history.updated"
    assert client.messages[-1]["history"][0]["run_id"] == run_id
    assert client.messages[-1]["history"][0]["events"][0]["type"] == "run.started"
    assert manager.history[0]["status"] == "completed"
    assert manager.snapshot()["history"][0]["run_id"] == run_id
    assert manager.snapshot()["history"][0]["events"][0]["run_id"] == run_id


@pytest.mark.asyncio
async def test_run_manager_cancel_stops_task(monkeypatch):
    manager = ui_server.RunManager()
    started = asyncio.Event()

    async def fake_run_agent(_prompt, **kwargs):
        await kwargs["event_callback"](
            AgentEvent("planning.started", kwargs["run_id"], 1, "now", {"round": 1})
        )
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(ui_server, "run_agent", fake_run_agent)
    run_id = await manager.start("long task")
    await started.wait()
    snapshot = manager.snapshot()
    assert snapshot["active"][0]["run_id"] == run_id
    assert snapshot["active"][0]["events"][0]["type"] == "planning.started"
    await manager.cancel(run_id)
    await asyncio.gather(manager.runs[run_id].task, return_exceptions=True)
    assert manager.runs[run_id].token.cancelled
    assert manager.runs[run_id].task.done()


def test_replay_path_rejects_traversal():
    with pytest.raises(ValueError):
        ui_server._safe_replay_path("../secret.json")


def test_create_app_has_local_routes():
    app = ui_server.create_app()
    paths = {route.resource.canonical for route in app.router.routes()}
    assert "/ws" in paths
    assert "/api/health" in paths
    assert "/api/replays" in paths


@pytest.mark.asyncio
async def test_precise_rollback_refreshes_scene_and_history(monkeypatch):
    manager = ui_server.RunManager()
    run_id = "run-rollback"
    result = AgentRunResult(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        created_object_ids=["guid-one", "guid-two"],
    )
    manager.runs[run_id] = ui_server.ManagedRun(
        run_id=run_id,
        prompt="two boxes",
        closed_loop=True,
        token=CancellationToken(),
        result=result,
    )
    manager.history.appendleft({"run_id": run_id, "status": "completed"})
    calls = []

    async def fake_post(endpoint, payload):
        calls.append((endpoint, payload))
        if endpoint == "/delete_objects":
            return {"status": "ok", "deleted": ["guid-one", "guid-two"], "failed": []}
        return {"status": "ok", "objects": [{"object_id": "remaining"}], "total": 1}

    monkeypatch.setattr(ui_server, "_rhino_post", fake_post)
    payload = await manager.rollback(run_id)

    assert calls[0] == ("/delete_objects", {"object_ids": ["guid-one", "guid-two"]})
    assert calls[1] == ("/get_scene_summary", {})
    assert payload["scene_summary"]["total"] == 1
    assert manager.runs[run_id].rolled_back
    assert manager.history[0]["rolled_back"] is True
    with pytest.raises(ValueError, match="已经完成精准回滚"):
        await manager.rollback(run_id)


def test_feedback_requires_finished_run_and_updates_history(monkeypatch):
    manager = ui_server.RunManager()
    run_id = "run-feedback"
    managed = ui_server.ManagedRun(
        run_id=run_id,
        prompt="a sphere",
        closed_loop=True,
        token=CancellationToken(),
        result=AgentRunResult(run_id=run_id, status=RunStatus.COMPLETED),
    )
    manager.runs[run_id] = managed
    manager.history.appendleft({"run_id": run_id, "status": "completed"})
    saved = []
    monkeypatch.setattr(ui_server, "save_feedback", saved.append)

    record = manager.record_feedback(run_id, "accepted")
    assert record["label"] == "accepted"
    assert saved[0]["run_id"] == run_id
    assert manager.history[0]["feedback_labels"] == ["accepted"]

    running_id = "run-running"
    manager.runs[running_id] = ui_server.ManagedRun(
        run_id=running_id,
        prompt="pending",
        closed_loop=True,
        token=CancellationToken(),
    )
    with pytest.raises(ValueError, match="尚未结束"):
        manager.record_feedback(running_id, "partial")


def test_undo_can_only_be_marked_once():
    manager = ui_server.RunManager()
    run_id = "run-undo"
    manager.runs[run_id] = ui_server.ManagedRun(
        run_id=run_id,
        prompt="a sphere",
        closed_loop=True,
        token=CancellationToken(),
        result=AgentRunResult(run_id=run_id, status=RunStatus.COMPLETED),
    )
    manager.history.appendleft({"run_id": run_id, "status": "completed"})

    manager.mark_undo_applied(run_id)

    assert manager.history[0]["undo_applied"] is True
    with pytest.raises(ValueError, match="已经执行过 Undo"):
        manager.mark_undo_applied(run_id)
