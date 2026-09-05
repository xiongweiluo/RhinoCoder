"""Deterministic, rule-first routing for RhinoCoder model backends."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping
from uuid import uuid4


class PrivacyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RouteMode(str, Enum):
    AUTO = "auto"
    MAIN = "main"
    ECONOMY = "economy"
    LOCAL = "local"


@dataclass(frozen=True, slots=True)
class BackendProfile:
    backend_id: str
    model_id: str
    model: str
    provider: str
    kind: str
    cost_tier: int
    reliability_rank: int
    typical_latency_ms: int
    supports_tools: bool = True


@dataclass(frozen=True, slots=True)
class RouteContext:
    privacy_level: PrivacyLevel | str | None = None
    task_difficulty: int | None = None
    tool_complexity: int | None = None
    cost_budget_usd: float | None = None
    latency_budget_ms: int | None = None


@dataclass(slots=True)
class RouteDecision:
    route_id: str
    timestamp: str
    selected_backend: str
    selected_model_id: str
    selected_model: str
    privacy_level: str
    task_difficulty: int
    tool_complexity: int
    cost_budget_usd: float | None
    latency_budget_ms: int | None
    reason: str
    reason_codes: list[str] = field(default_factory=list)
    candidates: list[dict[str, object]] = field(default_factory=list)
    fallback_backend: str | None = None
    fallback_from: str | None = None
    fallback_error_code: str | None = None
    degraded: bool = False
    routing_enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def apply_fallback(self, profile: BackendProfile, error_code: str) -> None:
        previous = self.selected_backend
        self.fallback_from = previous
        self.fallback_error_code = error_code
        self.selected_backend = profile.backend_id
        self.selected_model_id = profile.model_id
        self.selected_model = profile.model
        self.degraded = True
        self.reason_codes.append("transient_backend_fallback")
        self.reason = (
            f"{self.reason}；{previous} 出现可降级故障 {error_code}，"
            f"已有限切换到 {profile.backend_id}，并沿用原消息与工具结果。"
        )


@dataclass(frozen=True, slots=True)
class RouterConfig:
    enabled: bool = True
    mode: RouteMode = RouteMode.AUTO
    fallback_enabled: bool = True
    max_fallbacks: int = 1

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RouterConfig":
        source = os.environ if env is None else env
        enabled = _env_bool(source.get("RHINOCODER_ROUTER_ENABLED"), True)
        fallback_enabled = _env_bool(source.get("RHINOCODER_ROUTER_FALLBACK"), True)
        raw_mode = source.get("RHINOCODER_ROUTE_MODE", "auto").strip().lower()
        try:
            mode = RouteMode(raw_mode)
        except ValueError as exc:
            raise ValueError(
                "RHINOCODER_ROUTE_MODE 必须是 auto/main/economy/local"
            ) from exc
        try:
            configured_fallbacks = int(source.get("RHINOCODER_ROUTER_MAX_FALLBACKS", "1"))
        except ValueError as exc:
            raise ValueError("RHINOCODER_ROUTER_MAX_FALLBACKS 必须是整数") from exc
        return cls(
            enabled=enabled,
            mode=mode,
            fallback_enabled=fallback_enabled,
            max_fallbacks=max(0, min(configured_fallbacks, 1)),
        )


HIGH_PRIVACY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:api[_ -]?key|access[_ -]?token|password|secret)\b",
        r"(?:密钥|密码|令牌|机密|绝密|严格保密|不要上传|禁止上云|仅本地|本地处理)",
        r"(?:^|\s)/(?:Users|home|private|Volumes)/[^\s]+",
        r"[A-Z]:\\(?:Users|Projects)\\[^\s]+",
    )
)
MEDIUM_PRIVACY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:客户|业主|项目代号|内部项目|合同|投标)",
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b",
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    )
)
COMPLEXITY_TERMS = {
    "boolean": 2,
    "布尔": 2,
    "参数化": 2,
    "算法": 2,
    "立面": 2,
    "楼梯": 2,
    "阵列": 1,
    "分布": 1,
    "对齐": 1,
    "分组": 1,
    "旋转": 1,
    "缩放": 1,
    "挤出": 1,
    "差集": 2,
    "并集": 2,
    "曲面": 1,
    "多个": 1,
}


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"无效布尔配置: {value}")


def infer_privacy_level(prompt: str) -> PrivacyLevel:
    if any(pattern.search(prompt) for pattern in HIGH_PRIVACY_PATTERNS):
        return PrivacyLevel.HIGH
    if any(pattern.search(prompt) for pattern in MEDIUM_PRIVACY_PATTERNS):
        return PrivacyLevel.MEDIUM
    return PrivacyLevel.LOW


def infer_tool_complexity(prompt: str) -> int:
    score = 1
    lowered = prompt.lower()
    score += sum(weight for term, weight in COMPLEXITY_TERMS.items() if term in lowered)
    coordinate_groups = len(re.findall(r"\([^)]*[-+]?\d+(?:\.\d+)?[^)]*\)", prompt))
    score += min(coordinate_groups, 2)
    sequential = len(re.findall(r"(?:然后|再|接着|并且|同时|之后)", prompt))
    score += min(sequential, 2)
    return max(1, min(score, 5))


def infer_task_difficulty(prompt: str, tool_complexity: int) -> int:
    score = tool_complexity
    if len(prompt) >= 100:
        score += 1
    if len(re.findall(r"\d+(?:\.\d+)?", prompt)) >= 6:
        score += 1
    return max(1, min(score, 5))


def _coerce_privacy(value: PrivacyLevel | str | None, prompt: str) -> PrivacyLevel:
    if value is None:
        return infer_privacy_level(prompt)
    try:
        return value if isinstance(value, PrivacyLevel) else PrivacyLevel(value)
    except ValueError as exc:
        raise ValueError("privacy_level 必须是 low/medium/high") from exc


def _validate_score(name: str, value: int | None, inferred: int) -> int:
    score = inferred if value is None else value
    if not 1 <= score <= 5:
        raise ValueError(f"{name} 必须在 1 到 5 之间")
    return score


def select_route(
    prompt: str,
    profiles: Mapping[str, BackendProfile],
    *,
    context: RouteContext | None = None,
    config: RouterConfig | None = None,
) -> RouteDecision:
    context = context or RouteContext()
    config = config or RouterConfig.from_env()
    required = {"cloud-main", "cloud-economy", "local-mock"}
    missing = required.difference(profiles)
    if missing:
        raise ValueError(f"缺少路由后端: {', '.join(sorted(missing))}")

    privacy = _coerce_privacy(context.privacy_level, prompt)
    if context.cost_budget_usd is not None and context.cost_budget_usd < 0:
        raise ValueError("cost_budget_usd 不能为负数")
    if context.latency_budget_ms is not None and context.latency_budget_ms <= 0:
        raise ValueError("latency_budget_ms 必须大于 0")
    inferred_complexity = infer_tool_complexity(prompt)
    complexity = _validate_score("tool_complexity", context.tool_complexity, inferred_complexity)
    difficulty = _validate_score(
        "task_difficulty",
        context.task_difficulty,
        infer_task_difficulty(prompt, complexity),
    )
    reasons: list[str] = []

    if not config.enabled:
        selected = "cloud-main"
        reasons.append("routing_disabled")
        reason = "混合路由已关闭，固定使用可靠主后端。"
    elif config.mode is not RouteMode.AUTO:
        selected = {
            RouteMode.MAIN: "cloud-main",
            RouteMode.ECONOMY: "cloud-economy",
            RouteMode.LOCAL: "local-mock",
        }[config.mode]
        if privacy is PrivacyLevel.HIGH and selected != "local-mock":
            selected = "local-mock"
            reasons.extend(("manual_mode_overridden", "high_privacy_local_only"))
            reason = "检测到高隐私内容，覆盖手动云端模式并强制使用本地后端。"
        else:
            reasons.append("manual_mode")
            reason = f"按 RHINOCODER_ROUTE_MODE={config.mode.value} 固定选择后端。"
    elif privacy is PrivacyLevel.HIGH:
        selected = "local-mock"
        reasons.append("high_privacy_local_only")
        reason = "检测到高隐私信号，仅允许本地后端；不会降级到云端。"
    elif difficulty >= 4 or complexity >= 4:
        selected = "cloud-main"
        reasons.append("complex_task_reliable_backend")
        reason = "任务难度或工具复杂度较高，优先选择可靠主后端。"
    elif context.cost_budget_usd is not None and context.cost_budget_usd <= 0.01:
        selected = "cloud-economy"
        reasons.append("strict_cost_budget")
        reason = "任务成本预算较紧，且复杂度允许，选择低成本云端后端。"
    elif context.latency_budget_ms is not None and context.latency_budget_ms <= 30_000:
        selected = "cloud-economy"
        reasons.append("strict_latency_budget")
        reason = "任务延迟预算较紧，且复杂度允许，选择低延迟云端后端。"
    elif difficulty <= 2 and complexity <= 2:
        selected = "cloud-economy"
        reasons.append("simple_task_economy_backend")
        reason = "任务简单且隐私风险低，选择低成本云端后端。"
    else:
        selected = "cloud-main"
        reasons.append("balanced_reliable_backend")
        reason = "任务需要多步工具推理，选择可靠主后端。"

    fallback_backend: str | None = None
    if (
        config.enabled
        and config.fallback_enabled
        and config.max_fallbacks > 0
        and privacy is not PrivacyLevel.HIGH
    ):
        fallback_backend = (
            "cloud-main"
            if selected == "cloud-economy"
            else "cloud-economy"
            if selected == "cloud-main"
            else None
        )

    selected_profile = profiles[selected]
    candidate_rows = [
        {
            "backend": profile.backend_id,
            "model_id": profile.model_id,
            "kind": profile.kind,
            "cost_tier": profile.cost_tier,
            "reliability_rank": profile.reliability_rank,
            "typical_latency_ms": profile.typical_latency_ms,
            "eligible": not (privacy is PrivacyLevel.HIGH and profile.kind == "cloud"),
        }
        for profile in profiles.values()
    ]
    return RouteDecision(
        route_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        selected_backend=selected_profile.backend_id,
        selected_model_id=selected_profile.model_id,
        selected_model=selected_profile.model,
        privacy_level=privacy.value,
        task_difficulty=difficulty,
        tool_complexity=complexity,
        cost_budget_usd=context.cost_budget_usd,
        latency_budget_ms=context.latency_budget_ms,
        reason=reason,
        reason_codes=reasons,
        candidates=candidate_rows,
        fallback_backend=fallback_backend,
        routing_enabled=config.enabled,
    )
