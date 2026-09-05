from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError

from agent import llm
from agent.model_backends import (
    BackendError,
    MockLocalBackend,
    ModelBackend,
    OpenAICompatibleBackend,
)
from agent.router import (
    BackendProfile,
    PrivacyLevel,
    RouteContext,
    RouteMode,
    RouterConfig,
    select_route,
)
from agent.runtime import RunStatus


def _profile(
    backend_id: str,
    model: str,
    *,
    provider: str,
    kind: str,
    cost: int,
    reliability: int,
) -> BackendProfile:
    return BackendProfile(
        backend_id=backend_id,
        model_id=f"{provider}:{model}",
        model=model,
        provider=provider,
        kind=kind,
        cost_tier=cost,
        reliability_rank=reliability,
        typical_latency_ms=100,
    )


def _profiles() -> dict[str, BackendProfile]:
    return {
        "cloud-main": _profile(
            "cloud-main", "main", provider="cloud", kind="cloud", cost=3, reliability=3
        ),
        "cloud-economy": _profile(
            "cloud-economy", "economy", provider="cloud", kind="cloud", cost=1, reliability=2
        ),
        "local-mock": _profile(
            "local-mock", "mock", provider="local", kind="local", cost=0, reliability=1
        ),
    }


def test_high_privacy_is_local_only_even_with_manual_cloud_mode():
    decision = select_route(
        "仅本地处理这个机密项目，不要上传",
        _profiles(),
        config=RouterConfig(mode=RouteMode.MAIN),
    )

    assert decision.privacy_level == PrivacyLevel.HIGH.value
    assert decision.selected_backend == "local-mock"
    assert decision.fallback_backend is None
    assert "manual_mode_overridden" in decision.reason_codes
    assert not next(
        item for item in decision.candidates if item["backend"] == "cloud-main"
    )["eligible"]


def test_complex_tasks_choose_reliable_main_backend():
    decision = select_route(
        "创建参数化立面，然后阵列、旋转并执行布尔差集",
        _profiles(),
        config=RouterConfig(),
    )

    assert decision.task_difficulty >= 4
    assert decision.tool_complexity >= 4
    assert decision.selected_backend == "cloud-main"
    assert decision.fallback_backend == "cloud-economy"
    assert "complex_task_reliable_backend" in decision.reason_codes


def test_simple_and_budget_constrained_tasks_choose_economy_backend():
    simple = select_route("创建一个方块", _profiles(), config=RouterConfig())
    budgeted = select_route(
        "创建方块并读取摘要",
        _profiles(),
        context=RouteContext(task_difficulty=3, tool_complexity=3, cost_budget_usd=0.005),
        config=RouterConfig(),
    )
    latency = select_route(
        "创建方块并读取摘要",
        _profiles(),
        context=RouteContext(
            task_difficulty=3,
            tool_complexity=3,
            latency_budget_ms=20_000,
        ),
        config=RouterConfig(),
    )

    assert simple.selected_backend == "cloud-economy"
    assert budgeted.selected_backend == "cloud-economy"
    assert "strict_cost_budget" in budgeted.reason_codes
    assert latency.selected_backend == "cloud-economy"
    assert "strict_latency_budget" in latency.reason_codes


def test_routing_can_be_disabled_and_fallback_is_bounded():
    decision = select_route(
        "创建一个方块",
        _profiles(),
        config=RouterConfig(enabled=False, max_fallbacks=1),
    )
    config = RouterConfig.from_env({"RHINOCODER_ROUTER_MAX_FALLBACKS": "99"})

    assert decision.selected_backend == "cloud-main"
    assert decision.fallback_backend is None
    assert decision.routing_enabled is False
    assert config.max_fallbacks == 1


def test_disabled_router_cannot_bypass_high_privacy_gate():
    decision = select_route(
        "项目名称: Aurora；请读取 /Users/redteam/client.3dm",
        _profiles(),
        config=RouterConfig(enabled=False),
    )

    assert decision.selected_backend == "local-mock"
    assert decision.fallback_backend is None
    assert "high_privacy_local_only" in decision.reason_codes


@pytest.mark.asyncio
async def test_local_mock_uses_uniform_tool_completion_contract_without_cloud():
    backend = MockLocalBackend(_profiles()["local-mock"])
    tools = [
        {
            "type": "function",
            "function": {"name": "get_scene_summary", "parameters": {"type": "object"}},
        }
    ]

    first = await backend.complete(messages=[{"role": "user", "content": "private"}], tools=tools)
    second = await backend.complete(
        messages=[{"role": "tool", "content": "objects = []"}],
        tools=tools,
    )

    assert first.choices[0].finish_reason == "tool_calls"
    assert first.choices[0].message.tool_calls[0].function.name == "get_scene_summary"
    assert second.choices[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_unavailable_economy_model_is_safe_to_fallback():
    response = httpx.Response(
        404,
        request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
    )

    class Completions:
        async def create(self, **_kwargs):
            raise APIStatusError("model not found", response=response, body=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    backend = OpenAICompatibleBackend(
        _profiles()["cloud-economy"],
        lambda: client,
        base_url="https://example.test/v1",
    )

    with pytest.raises(BackendError) as caught:
        await backend.complete(messages=[], tools=[])

    assert caught.value.code == "llm.model_unavailable"
    assert caught.value.fallback_eligible


class _Message:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, **_kwargs):
        payload = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ]
        return payload


def _response(message, finish_reason):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish_reason, message=message)],
        usage=None,
    )


class _ScriptedBackend(ModelBackend):
    def __init__(self, profile: BackendProfile, steps):
        self.profile = profile
        self.base_url = "https://example.test/v1"
        self.steps = list(steps)
        self.messages_seen = []

    async def complete(self, *, messages, tools):
        self.messages_seen.append(json.loads(json.dumps(messages)))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_high_privacy_runtime_never_calls_cloud_and_does_not_claim_success(monkeypatch):
    @asynccontextmanager
    async def fake_stdio(_params):
        yield object(), object()

    class FakeSession:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            return SimpleNamespace(serverInfo=SimpleNamespace(name="fake"))

        async def list_tools(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="get_scene_summary",
                        description="read only",
                        inputSchema={"type": "object", "properties": {}},
                    )
                ]
            )

        async def call_tool(self, name, arguments):
            assert name == "get_scene_summary"
            assert arguments == {}
            return SimpleNamespace(
                content=[SimpleNamespace(text="场景对象总数: 0\nobjects = []")],
                isError=False,
            )

    cloud_main = _ScriptedBackend(_profiles()["cloud-main"], [])
    cloud_economy = _ScriptedBackend(_profiles()["cloud-economy"], [])
    local = MockLocalBackend(_profiles()["local-mock"])
    monkeypatch.setattr(llm, "stdio_client", fake_stdio)
    monkeypatch.setattr(llm, "ClientSession", FakeSession)

    result = asyncio.run(
        llm.run_agent(
            "仅本地处理这个机密项目，不要上传",
            closed_loop=True,
            router_config=RouterConfig(),
            backend_registry={
                "cloud-main": cloud_main,
                "cloud-economy": cloud_economy,
                "local-mock": local,
            },
        )
    )

    assert result.status is RunStatus.FAILED
    assert result.error.code == "local.mock_only"
    assert result.route_decision["selected_backend"] == "local-mock"
    assert result.route_decision["fallback_backend"] is None
    assert cloud_main.messages_seen == []
    assert cloud_economy.messages_seen == []


def test_transient_fallback_preserves_transcript_and_never_replays_tool_calls(monkeypatch):
    create_call = SimpleNamespace(
        id="create-once",
        function=SimpleNamespace(name="create_box", arguments='{"width": 2}'),
    )
    main = _ScriptedBackend(
        _profiles()["cloud-main"],
        [
            _response(_Message(None, [create_call]), "tool_calls"),
            BackendError(
                "llm.timeout",
                "main timeout",
                recoverable=True,
                fallback_eligible=True,
            ),
        ],
    )
    economy = _ScriptedBackend(
        _profiles()["cloud-economy"],
        [_response(_Message("completed after fallback"), "stop")],
    )
    local = _ScriptedBackend(
        _profiles()["local-mock"],
        [_response(_Message("unused"), "stop")],
    )

    @asynccontextmanager
    async def fake_stdio(_params):
        yield object(), object()

    tool_invocations = []

    class FakeSession:
        def __init__(self, *_args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            return SimpleNamespace(serverInfo=SimpleNamespace(name="fake"))

        async def list_tools(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="create_box",
                        description="create",
                        inputSchema={"type": "object", "properties": {}},
                    )
                ]
            )

        async def call_tool(self, name, arguments):
            tool_invocations.append((name, arguments))
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text="成功：11111111-1111-4111-8111-111111111111"
                    )
                ],
                isError=False,
            )

    monkeypatch.setattr(llm, "stdio_client", fake_stdio)
    monkeypatch.setattr(llm, "ClientSession", FakeSession)
    result = asyncio.run(
        llm.run_agent(
            "complex task",
            closed_loop=False,
            router_config=RouterConfig(mode=RouteMode.MAIN),
            backend_registry={
                "cloud-main": main,
                "cloud-economy": economy,
                "local-mock": local,
            },
        )
    )

    assert result.status is RunStatus.COMPLETED
    assert tool_invocations == [("create_box", {"width": 2})]
    assert result.created_object_ids == ["11111111-1111-4111-8111-111111111111"]
    assert result.route_decision["selected_backend"] == "cloud-economy"
    assert result.route_decision["fallback_from"] == "cloud-main"
    fallback_event = next(event for event in result.events if event.type == "route.fallback")
    assert fallback_event.payload["replayed_tool_calls"] == 0
    assert any(message.get("role") == "tool" for message in economy.messages_seen[0])
