"""RhinoCoder 统一运行结果、事件流与取消原语。"""

from __future__ import annotations

import inspect
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Optional


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class AgentEvent:
    type: str
    run_id: str
    seq: int
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolCallRecord:
    call_id: str
    name: str
    arguments: dict[str, Any]
    round_index: int
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    success: bool = False
    output: str = ""
    error_code: Optional[str] = None


@dataclass(slots=True)
class RunMetrics:
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    planning_ms: float = 0.0
    tool_execution_ms: float = 0.0
    scene_check_ms: float = 0.0
    tool_rounds: int = 0
    tool_calls: int = 0
    scene_checks: int = 0
    corrections: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunError:
    code: str
    message: str
    recoverable: bool = False
    detail: Optional[str] = None


@dataclass
class AgentRunResult:
    run_id: str
    status: RunStatus
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    metrics: RunMetrics = field(default_factory=lambda: RunMetrics(started_at=utc_now()))
    scene_checks: list[dict[str, Any]] = field(default_factory=list)
    created_object_ids: list[str] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    error: Optional[RunError] = None
    final_text: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.status is RunStatus.COMPLETED else 1

    def __iter__(self):
        """兼容旧调用方的 ``exit_code, messages = await run_agent(...)``。"""
        yield self.exit_code
        yield self.messages

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["exit_code"] = self.exit_code
        return data


EventCallback = Callable[[AgentEvent], Optional[Awaitable[None]]]


class EventEmitter:
    """为单次运行生成严格递增的事件序列。"""

    def __init__(self, run_id: str, callback: Optional[EventCallback] = None) -> None:
        self.run_id = run_id
        self.callback = callback
        self.events: list[AgentEvent] = []
        self._seq = 0

    async def emit(self, event_type: str, payload: Optional[dict[str, Any]] = None) -> AgentEvent:
        self._seq += 1
        event = AgentEvent(
            type=event_type,
            run_id=self.run_id,
            seq=self._seq,
            timestamp=utc_now(),
            payload=payload or {},
        )
        self.events.append(event)
        if self.callback is not None:
            maybe_awaitable = self.callback(event)
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
        return event


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise RunCancelled("任务已由用户取消")


class RunCancelled(Exception):
    pass


def new_run_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def monotonic_ms() -> float:
    return time.monotonic() * 1000.0
