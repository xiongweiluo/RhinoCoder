from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import httpx

from agent.runtime import (
    AgentRunResult,
    CancellationToken,
    EventEmitter,
    RunCancelled,
    RunMetrics,
    RunStatus,
)
import agent.llm as llm


def test_agent_run_result_legacy_unpacking():
    result = AgentRunResult(
        run_id="run-1",
        status=RunStatus.COMPLETED,
        messages=[{"role": "user", "content": "hello"}],
        metrics=RunMetrics(started_at="now"),
    )
    exit_code, messages = result
    assert exit_code == 0
    assert messages[0]["content"] == "hello"
    assert result.to_dict()["status"] == "completed"


def test_event_emitter_sequence_and_callback():
    seen = []

    async def callback(event):
        seen.append(event.type)

    async def scenario():
        emitter = EventEmitter("run-1", callback)
        await emitter.emit("run.started")
        await emitter.emit("tool.started", {"name": "create_box"})
        return emitter.events

    events = asyncio.run(scenario())
    assert [e.seq for e in events] == [1, 2]
    assert seen == ["run.started", "tool.started"]


def test_cancellation_token():
    token = CancellationToken()
    token.raise_if_cancelled()
    token.cancel()
    with pytest.raises(RunCancelled):
        token.raise_if_cancelled()


def test_closed_loop_cannot_finish_before_current_scene_check(monkeypatch):
    class Message:
        def __init__(self, content, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

        def model_dump(self, **_kwargs):
            return {"role": "assistant", "content": self.content}

    scene_call = SimpleNamespace(
        id="call-scene",
        function=SimpleNamespace(name="get_scene_summary", arguments="{}"),
    )
    responses = [
        SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=Message("premature"))],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="tool_calls", message=Message(None, [scene_call]))],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=Message("verified"))],
            usage=None,
        ),
    ]

    class Completions:
        calls = 0

        async def create(self, **_kwargs):
            response = responses[self.calls]
            self.calls += 1
            return response

    completions = Completions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

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
            tool = SimpleNamespace(
                name="get_scene_summary",
                description="scene",
                inputSchema={"type": "object", "properties": {}},
            )
            return SimpleNamespace(tools=[tool])

        async def call_tool(self, _name, arguments):
            assert arguments == {}
            return SimpleNamespace(
                content=[SimpleNamespace(text="场景对象总数: 0\nobjects = []")],
                isError=False,
            )

    monkeypatch.setattr(llm, "make_deepseek_client", lambda: fake_client)
    monkeypatch.setattr(llm, "stdio_client", fake_stdio)
    monkeypatch.setattr(llm, "ClientSession", FakeSession)

    result = asyncio.run(llm.run_agent("verify me", closed_loop=True, max_tool_rounds=4))

    assert result.status is RunStatus.COMPLETED
    assert result.final_text == "verified"
    assert completions.calls == 3
    assert result.metrics.scene_checks == 1
    assert result.metrics.corrections == 1
    assert [event.type for event in result.events].count("scene.checked") == 1


def test_tool_text_failures_are_classified():
    assert llm._tool_output_error_code("参数错误：object_id 不能为空") == "tool.invalid_argument"
    assert llm._tool_output_error_code("失败 [http.invalid_argument]：bad") == "http.invalid_argument"
    assert llm._tool_output_error_code("创建成功") is None


def test_mcp_process_exit_is_recoverable():
    McpError = type("McpError", (Exception,), {})
    error = llm._classify_outer_exception(ExceptionGroup("stdio", [McpError("Connection closed")]))
    assert error.code == "mcp.process_exit"
    assert error.recoverable


def test_llm_timeout_has_specific_recoverable_error(monkeypatch):
    class Completions:
        async def create(self, **_kwargs):
            raise llm.APITimeoutError(request=httpx.Request("POST", "https://example.test"))

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

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
            return SimpleNamespace(tools=[])

    monkeypatch.setattr(llm, "make_deepseek_client", lambda: fake_client)
    monkeypatch.setattr(llm, "stdio_client", fake_stdio)
    monkeypatch.setattr(llm, "ClientSession", FakeSession)

    result = asyncio.run(llm.run_agent("timeout", closed_loop=False))
    assert result.status is RunStatus.FAILED
    assert result.error.code == "llm.timeout"
    assert result.error.recoverable


def test_unrecovered_text_tool_failure_marks_run_failed(monkeypatch):
    class Message:
        def __init__(self, content, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

        def model_dump(self, **_kwargs):
            return {"role": "assistant", "content": self.content}

    move_call = SimpleNamespace(
        id="call-move",
        function=SimpleNamespace(
            name="move_object",
            arguments='{"object_id":"not-a-guid","translate_x":1,"translate_y":0,"translate_z":0}',
        ),
    )
    responses = [
        SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="tool_calls", message=Message(None, [move_call]))],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=Message("无法移动"))],
            usage=None,
        ),
    ]

    class Completions:
        calls = 0

        async def create(self, **_kwargs):
            response = responses[self.calls]
            self.calls += 1
            return response

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
                tools=[SimpleNamespace(name="move_object", description="move", inputSchema={"type": "object"})]
            )

        async def call_tool(self, _name, arguments):
            return SimpleNamespace(
                content=[SimpleNamespace(text="失败 [http.invalid_argument]：GUID 无效")],
                isError=False,
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(llm, "make_deepseek_client", lambda: fake_client)
    monkeypatch.setattr(llm, "stdio_client", fake_stdio)
    monkeypatch.setattr(llm, "ClientSession", FakeSession)

    result = asyncio.run(llm.run_agent("invalid guid", closed_loop=False))
    assert result.status is RunStatus.FAILED
    assert result.error.code == "http.invalid_argument"
    assert result.tool_calls[0].success is False
    assert result.events[-1].type == "run.failed"
