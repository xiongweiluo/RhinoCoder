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
            route_decision={
                "selected_backend": "cloud-main",
                "selected_model": "reliable-model",
                "reason": "complex task",
                "degraded": False,
            },
        )

    monkeypatch.setattr(ui_server, "run_agent", fake_run_agent)
    run_id = await manager.start("create a box")
    await manager.runs[run_id].task
    assert client.messages[0]["type"] == "run.started"
    assert client.messages[-1]["type"] == "history.updated"
    assert client.messages[-1]["history"][0]["run_id"] == run_id
    assert client.messages[-1]["history"][0]["events"][0]["type"] == "run.started"
    assert manager.history[0]["status"] == "completed"
    assert manager.history[0]["route_decision"]["selected_backend"] == "cloud-main"
    assert manager.snapshot()["history"][0]["run_id"] == run_id
    assert manager.snapshot()["history"][0]["events"][0]["run_id"] == run_id


@pytest.mark.asyncio
async def test_run_manager_cancel_stops_task(monkeypatch):
    manager = ui_server.RunManager()
    client = _FakeClient()
    manager.clients.add(client)  # type: ignore[arg-type]
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
    assert manager.history[0]["status"] == "cancelled"
    assert manager.history[0]["events"][-1]["type"] == "run.cancelled"
    assert client.messages[-1]["type"] == "history.updated"


@pytest.mark.asyncio
async def test_retry_preserves_fixed_demo_scenario(monkeypatch):
    manager = ui_server.RunManager()
    original = ui_server.ManagedRun(
        run_id="run-demo-retry",
        prompt=ui_server._scenario_by_id("self-correction")["input"],
        closed_loop=True,
        token=CancellationToken(),
        demo_scenario_id="self-correction",
    )
    manager.runs[original.run_id] = original
    captured = {}

    async def fake_start(prompt, *, closed_loop=True, demo_scenario_id=None):
        captured.update(
            prompt=prompt,
            closed_loop=closed_loop,
            demo_scenario_id=demo_scenario_id,
        )
        return "run-retried"

    monkeypatch.setattr(manager, "start", fake_start)

    assert await manager.retry(original.run_id) == "run-retried"
    assert captured == {
        "prompt": original.prompt,
        "closed_loop": True,
        "demo_scenario_id": "self-correction",
    }


def test_replay_path_rejects_traversal():
    with pytest.raises(ValueError):
        ui_server._safe_replay_path("../secret.json")


def test_create_app_has_local_routes():
    app = ui_server.create_app()
    paths = {route.resource.canonical for route in app.router.routes()}
    assert "/ws" in paths
    assert "/api/health" in paths
    assert "/api/replays" in paths
    assert "/api/demo-scenarios" in paths
    assert "/api/replays/{name}" in paths
    assert "/evidence/{name}" in paths


def test_p1_catalog_has_three_traceable_public_scenarios():
    catalog = ui_server._load_demo_catalog()
    scenarios = catalog["scenarios"]

    assert [item["id"] for item in scenarios] == [
        "normal-loop",
        "self-correction",
        "privacy-route",
    ]
    assert {item["replay"] for item in scenarios} == {
        "basic_stack.json",
        "self_correction.json",
        "table_group.json",
    }
    for scenario in scenarios:
        assert scenario["goal"]
        assert scenario["input"]
        assert scenario["expected"]
        assert scenario["asserts"]
        assert (ui_server.PROJECT_ROOT / "docs" / scenario["evidence"]["path"]).is_file()
        public = ui_server._public_scenario(scenario)
        assert "asserts" not in public
        assert public["read_only_url"] == f"/?demo={scenario['id']}"


def test_public_replays_match_catalog_and_cover_p1_event_chain():
    expected_types = {
        "normal-loop": {"privacy.assessed", "route.selected", "tool.completed", "scene.checked", "assertion.checked", "run.completed"},
        "self-correction": {"tool.completed", "scene.checked", "assertion.checked", "correction.started", "run.completed"},
        "privacy-route": {"privacy.assessed", "route.selected", "tool.completed", "scene.checked", "assertion.checked", "run.completed"},
    }
    for scenario in ui_server._load_demo_catalog()["scenarios"]:
        replay = ui_server._load_replay(scenario["replay"])
        assert replay["demo_scenario"] == scenario["id"]
        assert replay["scene_before"]["objects"] == []
        assert expected_types[scenario["id"]].issubset({event["type"] for event in replay["events"]})


def test_browser_payload_is_minimized_and_object_ids_are_pseudonymized():
    source = {
        "run_id": "run-lineage-kept",
        "prompt": "client: Example Studio; use /Users/example/private/model.3dm",
        "scene": {
            "objects": [{
                "object_id": "123e4567-e89b-42d3-a456-426614174000",
                "center": [1, 2, 3],
                "layer": "Client Layer",
                "groups": ["Client Group"],
            }]
        },
    }

    public = ui_server._browser_safe(source)

    assert public["run_id"] == "run-lineage-kept"
    assert "Example Studio" not in public["prompt"]
    assert "/Users/example" not in public["prompt"]
    assert public["scene"]["objects"][0]["object_id"].startswith("object-")
    assert public["scene"]["objects"][0]["center"] == [1, 2, 3]
    assert public["scene"]["objects"][0]["layer"] == "<LAYER_REDACTED>"
    assert public["scene"]["objects"][0]["groups"] == ["<GROUP_REDACTED>"]


@pytest.mark.asyncio
async def test_fixed_live_demo_captures_before_after_and_appends_assertions(monkeypatch):
    manager = ui_server.RunManager()
    client = _FakeClient()
    manager.clients.add(client)  # type: ignore[arg-type]
    scene_reads = iter([
        {"total": 0, "capped": False, "objects": []},
        {
            "total": 2,
            "capped": False,
            "objects": [
                {"object_id": "base-id", "name": "Base", "type": "Polysurface", "center": [0, 0, 1], "size": [20, 20, 2], "color": [80, 80, 80], "layer": "Default", "groups": []},
                {"object_id": "sphere-id", "name": "Sphere", "type": "Surface", "center": [0, 0, 10], "size": [16, 16, 16], "color": [255, 0, 0], "layer": "Default", "groups": []},
            ],
        },
    ])

    async def fake_read_scene():
        return next(scene_reads)

    async def fake_run_agent(prompt, **kwargs):
        run_id = kwargs["run_id"]
        assert prompt == ui_server._scenario_by_id("normal-loop")["input"]
        await kwargs["event_callback"](AgentEvent("run.started", run_id, 1, "now", {"prompt": prompt}))
        await kwargs["event_callback"](AgentEvent("scene.checked", run_id, 2, "now", {"scene_summary": {"total": 2, "objects": []}}))
        await kwargs["event_callback"](AgentEvent("run.completed", run_id, 3, "now", {"status": "completed", "metrics": {"duration_ms": 5}}))
        return AgentRunResult(
            run_id=run_id,
            status=RunStatus.COMPLETED,
            metrics=RunMetrics(started_at="now", duration_ms=5),
        )

    monkeypatch.setattr(ui_server, "_read_scene_summary", fake_read_scene)
    monkeypatch.setattr(ui_server, "run_agent", fake_run_agent)

    run_id = await manager.start("ignored by fixed scenario", demo_scenario_id="normal-loop")
    await manager.runs[run_id].task
    item = manager.history[0]

    assert item["scene_before"]["total"] == 0
    assert item["scene_after"]["total"] == 2
    assert item["evaluation"]["passed"] is True
    assert [event["type"] for event in item["events"]][-4:] == [
        "assertion.checked",
        "assertion.checked",
        "assertion.checked",
        "run.completed",
    ]
    assert [event["seq"] for event in item["events"]] == list(range(1, len(item["events"]) + 1))
    assert client.messages[-1]["type"] == "history.updated"


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
