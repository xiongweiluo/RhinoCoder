import json

import pytest

from agent.model_backends import ControlledLocalOpenAIBackend
from agent.router import BackendProfile
from eval.p2_hard import _audit_model_comparison_protocol, _controlled_local_backends
from training.p2_inference_server import _normalize_messages, _parse_tool_calls


def _profile() -> BackendProfile:
    return BackendProfile(
        backend_id="local-test",
        model_id="controlled-local:test",
        model="test",
        provider="controlled-local",
        kind="local",
        cost_tier=0,
        reliability_rank=1,
        typical_latency_ms=1,
    )


def test_controlled_backend_rejects_non_loopback_endpoint():
    with pytest.raises(ValueError, match="loopback"):
        ControlledLocalOpenAIBackend(
            _profile(),
            lambda: None,
            base_url="http://example.invalid/v1",
        )


def test_model_output_tool_calls_are_normalized_for_openai_agent():
    text = (
        '<tool_call>{"name":"create_sphere","arguments":{"center":[0,0,0],"radius":6}}</tool_call>'
        '<tool_call>{"name":"get_scene_summary","arguments":{}}</tool_call>'
    )
    calls = _parse_tool_calls(text)
    assert [call["function"]["name"] for call in calls] == [
        "create_sphere",
        "get_scene_summary",
    ]
    assert json.loads(calls[0]["function"]["arguments"])["radius"] == 6


def test_prior_tool_arguments_are_converted_back_to_template_objects():
    messages = [{
        "role": "assistant",
        "tool_calls": [{
            "type": "function",
            "function": {"name": "get_scene_summary", "arguments": "{}"},
        }],
    }]
    normalized = _normalize_messages(messages)
    assert normalized[0]["tool_calls"][0]["function"]["arguments"] == {}


def test_comparison_registry_preserves_frozen_route_roles(monkeypatch):
    monkeypatch.setenv("RHINOCODER_P2_INFERENCE_TOKEN", "x" * 32)
    monkeypatch.setenv("RHINOCODER_P2_INFERENCE_URL", "http://127.0.0.1:18080/v1")
    registry = _controlled_local_backends("base")
    assert set(registry) == {"cloud-main", "cloud-economy", "local-mock"}
    assert all(item.profile.provider == "controlled-local" for item in registry.values())
    assert all(item.profile.kind == "local" for item in registry.values())


def test_model_comparison_protocol_matches_implementation_contract():
    protocol = _audit_model_comparison_protocol()
    assert protocol["task_set"]["task_count"] == 30
    assert protocol["task_set"]["holdout_read"] == 0
