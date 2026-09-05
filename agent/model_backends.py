"""Uniform completion backends used by the rule-first router."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from openai import (
    AsyncOpenAI,
    AuthenticationError,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
)

from agent.router import BackendProfile


class BackendError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool,
        fallback_eligible: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.fallback_eligible = fallback_eligible


class ModelBackend(ABC):
    profile: BackendProfile
    base_url: str

    @abstractmethod
    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """Return an OpenAI-compatible chat completion response."""


class OpenAICompatibleBackend(ModelBackend):
    def __init__(
        self,
        profile: BackendProfile,
        client_factory: Callable[[], AsyncOpenAI],
        *,
        base_url: str,
    ) -> None:
        self.profile = profile
        self.base_url = base_url
        self._client_factory = client_factory
        self._client: AsyncOpenAI | None = None

    def _client_instance(self) -> AsyncOpenAI:
        if self._client is None:
            try:
                self._client = self._client_factory()
            except EnvironmentError as exc:
                raise BackendError(
                    "config.api_key_missing",
                    str(exc),
                    recoverable=True,
                    fallback_eligible=False,
                ) from exc
        return self._client

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        try:
            return await self._client_instance().chat.completions.create(
                model=self.profile.model,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
            )
        except BackendError:
            raise
        except AuthenticationError as exc:
            raise BackendError(
                "llm.authentication",
                f"{self.profile.backend_id} API Key 无效。",
                recoverable=True,
                fallback_eligible=False,
            ) from exc
        except APITimeoutError as exc:
            raise BackendError(
                "llm.timeout",
                f"{self.profile.backend_id} 响应超时；本轮未执行新的工具调用。",
                recoverable=True,
                fallback_eligible=True,
            ) from exc
        except APIConnectionError as exc:
            raise BackendError(
                "llm.connection",
                f"无法连接到 {self.profile.backend_id}: {exc}",
                recoverable=True,
                fallback_eligible=True,
            ) from exc
        except APIStatusError as exc:
            error_text = str(exc.message).lower()
            model_unavailable = exc.status_code in {400, 404} and "model" in error_text and any(
                marker in error_text for marker in ("not found", "unavailable", "does not exist")
            )
            fallback_eligible = (
                exc.status_code == 429 or exc.status_code >= 500 or model_unavailable
            )
            raise BackendError(
                "llm.model_unavailable" if model_unavailable else "llm.api_status",
                f"{self.profile.backend_id} API 错误 {exc.status_code}: {exc.message}",
                recoverable=fallback_eligible,
                fallback_eligible=fallback_eligible,
            ) from exc


@dataclass(slots=True)
class _MockToolFunction:
    name: str
    arguments: str


@dataclass(slots=True)
class _MockToolCall:
    id: str
    function: _MockToolFunction


class _MockMessage:
    def __init__(self, content: str | None, tool_calls: list[_MockToolCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": "assistant", "content": self.content}
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


class MockLocalBackend(ModelBackend):
    """Deterministic local safety backend for tests and private dry-runs."""

    def __init__(self, profile: BackendProfile) -> None:
        self.profile = profile
        self.base_url = ""

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        tool_names = {
            str(item.get("function", {}).get("name"))
            for item in tools
            if isinstance(item, dict)
        }
        has_tool_result = any(
            message.get("role") == "tool" for message in messages if isinstance(message, dict)
        )
        if "get_scene_summary" in tool_names and not has_tool_result:
            message = _MockMessage(
                None,
                [
                    _MockToolCall(
                        id="local-mock-scene-check",
                        function=_MockToolFunction("get_scene_summary", json.dumps({})),
                    )
                ],
            )
            finish_reason = "tool_calls"
        else:
            message = _MockMessage(
                "本地 Mock 后端已完成安全演练；它不会创建或修改 Rhino 对象。"
            )
            finish_reason = "stop"
        return SimpleNamespace(
            choices=[SimpleNamespace(finish_reason=finish_reason, message=message)],
            usage=None,
        )


def _openai_client(
    *,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
    max_retries: int,
    key_name: str,
) -> AsyncOpenAI:
    if not api_key.strip():
        raise EnvironmentError(f"未找到 {key_name} 环境变量。")
    return AsyncOpenAI(
        api_key=api_key.strip(),
        base_url=base_url,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )


def build_default_backends(
    *,
    main_model: str,
    main_base_url: str,
    main_client_factory: Callable[[], AsyncOpenAI],
    timeout_seconds: float,
    max_retries: int,
    env: Mapping[str, str] | None = None,
) -> dict[str, ModelBackend]:
    source = os.environ if env is None else env
    economy_model = source.get("RHINOCODER_ECONOMY_MODEL", "deepseek-v4-flash").strip()
    economy_base_url = source.get("RHINOCODER_ECONOMY_BASE_URL", main_base_url).strip()
    economy_key = source.get(
        "RHINOCODER_ECONOMY_API_KEY",
        source.get("DEEPSEEK_API_KEY", ""),
    )
    local_model = source.get("RHINOCODER_LOCAL_MODEL", "mock-local-v1").strip()

    main_profile = BackendProfile(
        backend_id="cloud-main",
        model_id=f"deepseek:{main_model}",
        model=main_model,
        provider="deepseek",
        kind="cloud",
        cost_tier=3,
        reliability_rank=3,
        typical_latency_ms=45_000,
    )
    economy_profile = BackendProfile(
        backend_id="cloud-economy",
        model_id=f"deepseek:{economy_model}",
        model=economy_model,
        provider="deepseek",
        kind="cloud",
        cost_tier=1,
        reliability_rank=2,
        typical_latency_ms=20_000,
    )
    local_profile = BackendProfile(
        backend_id="local-mock",
        model_id=f"local:{local_model}",
        model=local_model,
        provider="local",
        kind="local",
        cost_tier=0,
        reliability_rank=1,
        typical_latency_ms=50,
    )
    return {
        main_profile.backend_id: OpenAICompatibleBackend(
            main_profile,
            main_client_factory,
            base_url=main_base_url,
        ),
        economy_profile.backend_id: OpenAICompatibleBackend(
            economy_profile,
            lambda: _openai_client(
                api_key=economy_key,
                base_url=economy_base_url,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                key_name="RHINOCODER_ECONOMY_API_KEY 或 DEEPSEEK_API_KEY",
            ),
            base_url=economy_base_url,
        ),
        local_profile.backend_id: MockLocalBackend(local_profile),
    }
