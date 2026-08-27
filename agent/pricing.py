"""Versioned model pricing and cache-aware cost calculation."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Mapping
from urllib.parse import urlparse


DEEPSEEK_PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing/"
DEEPSEEK_PRICING_CHECKED_AT = "2026-08-27"


@dataclass(frozen=True, slots=True)
class ModelPricing:
    model: str
    input_cache_hit_per_m_tokens: float
    input_cache_miss_per_m_tokens: float
    output_per_m_tokens: float
    currency: str = "USD"
    source: str = DEEPSEEK_PRICING_SOURCE
    checked_at: str = DEEPSEEK_PRICING_CHECKED_AT
    schedule: str = "regular"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    prompt_tokens: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    cache_unknown_tokens: int
    completion_tokens: int
    input_cost_lower_bound_usd: float
    input_cost_upper_bound_usd: float
    output_cost_usd: float
    total_cost_lower_bound_usd: float
    total_cost_upper_bound_usd: float
    estimated_cost_usd: float
    status: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


OFFICIAL_DEEPSEEK_PRICING: dict[str, ModelPricing] = {
    "deepseek-v4-flash": ModelPricing(
        model="deepseek-v4-flash",
        input_cache_hit_per_m_tokens=0.0028,
        input_cache_miss_per_m_tokens=0.14,
        output_per_m_tokens=0.28,
    ),
    "deepseek-v4-pro": ModelPricing(
        model="deepseek-v4-pro",
        input_cache_hit_per_m_tokens=0.003625,
        input_cache_miss_per_m_tokens=0.435,
        output_per_m_tokens=0.87,
    ),
}


def _optional_float(env: Mapping[str, str], name: str) -> float | None:
    value = env.get(name, "").strip()
    return float(value) if value else None


def resolve_model_pricing(
    model: str,
    base_url: str,
    env: Mapping[str, str] | None = None,
) -> ModelPricing | None:
    """Resolve explicit overrides first, then official DeepSeek regular pricing."""
    values = os.environ if env is None else env
    cache_hit = _optional_float(values, "LLM_INPUT_CACHE_HIT_COST_PER_M_TOKENS")
    cache_miss = _optional_float(values, "LLM_INPUT_CACHE_MISS_COST_PER_M_TOKENS")
    output = _optional_float(values, "LLM_OUTPUT_COST_PER_M_TOKENS")
    legacy_input = _optional_float(values, "LLM_INPUT_COST_PER_M_TOKENS")
    if cache_hit is None and legacy_input is not None:
        cache_hit = legacy_input
    if cache_miss is None and legacy_input is not None:
        cache_miss = legacy_input
    explicit_values = (cache_hit, cache_miss, output)
    # Older .env templates used three zero values to mean "pricing disabled".
    # Preserve compatibility by treating that combination as unset.
    has_explicit_pricing = any(value is not None and value > 0 for value in explicit_values)
    if has_explicit_pricing:
        if None in (cache_hit, cache_miss, output):
            return None
        return ModelPricing(
            model=model,
            input_cache_hit_per_m_tokens=float(cache_hit),
            input_cache_miss_per_m_tokens=float(cache_miss),
            output_per_m_tokens=float(output),
            source="environment",
            checked_at=values.get("LLM_PRICING_CHECKED_AT", "user-configured"),
            schedule=values.get("LLM_PRICING_SCHEDULE", "custom"),
        )

    hostname = (urlparse(base_url).hostname or "").lower()
    if hostname == "api.deepseek.com":
        return OFFICIAL_DEEPSEEK_PRICING.get(model)
    return None


def calculate_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int = 0,
    pricing: ModelPricing,
) -> CostBreakdown:
    prompt_tokens = max(int(prompt_tokens), 0)
    completion_tokens = max(int(completion_tokens), 0)
    cache_hit_tokens = min(max(int(cache_hit_tokens), 0), prompt_tokens)
    cache_miss_tokens = min(
        max(int(cache_miss_tokens), 0),
        prompt_tokens - cache_hit_tokens,
    )
    cache_unknown_tokens = prompt_tokens - cache_hit_tokens - cache_miss_tokens
    per_m = 1_000_000
    known_input_cost = (
        cache_hit_tokens * pricing.input_cache_hit_per_m_tokens
        + cache_miss_tokens * pricing.input_cache_miss_per_m_tokens
    ) / per_m
    input_lower = known_input_cost + (
        cache_unknown_tokens * pricing.input_cache_hit_per_m_tokens / per_m
    )
    input_upper = known_input_cost + (
        cache_unknown_tokens * pricing.input_cache_miss_per_m_tokens / per_m
    )
    output_cost = completion_tokens * pricing.output_per_m_tokens / per_m
    total_lower = input_lower + output_cost
    total_upper = input_upper + output_cost
    status = "exact" if cache_unknown_tokens == 0 else "range"
    return CostBreakdown(
        prompt_tokens=prompt_tokens,
        cache_hit_tokens=cache_hit_tokens,
        cache_miss_tokens=cache_miss_tokens,
        cache_unknown_tokens=cache_unknown_tokens,
        completion_tokens=completion_tokens,
        input_cost_lower_bound_usd=round(input_lower, 8),
        input_cost_upper_bound_usd=round(input_upper, 8),
        output_cost_usd=round(output_cost, 8),
        total_cost_lower_bound_usd=round(total_lower, 8),
        total_cost_upper_bound_usd=round(total_upper, 8),
        # Unknown cache tokens use the cache-miss price as a conservative estimate.
        estimated_cost_usd=round(total_upper, 8),
        status=status,
    )
