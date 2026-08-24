from __future__ import annotations

import asyncio

import pytest

import agent.ui_server as ui_server
from agent.runtime import AgentEvent, AgentRunResult, RunMetrics, RunStatus


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
    assert manager.history[0]["status"] == "completed"
    assert manager.snapshot()["history"][0]["run_id"] == run_id


@pytest.mark.asyncio
async def test_run_manager_cancel_stops_task(monkeypatch):
    manager = ui_server.RunManager()
    started = asyncio.Event()

    async def fake_run_agent(_prompt, **_kwargs):
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(ui_server, "run_agent", fake_run_agent)
    run_id = await manager.start("long task")
    await started.wait()
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
