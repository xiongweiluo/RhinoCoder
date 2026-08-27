from __future__ import annotations

from types import SimpleNamespace

from agent import llm
from agent.pricing import calculate_cost, resolve_model_pricing
from agent.runtime import RunMetrics
from tools.recalculate_benchmark_cost import recalculate


def test_official_deepseek_v4_pro_pricing():
    pricing = resolve_model_pricing(
        "deepseek-v4-pro",
        "https://api.deepseek.com/v1",
        env={},
    )
    assert pricing is not None
    assert pricing.input_cache_hit_per_m_tokens == 0.003625
    assert pricing.input_cache_miss_per_m_tokens == 0.435
    assert pricing.output_per_m_tokens == 0.87


def test_legacy_zero_prices_fall_back_to_official_pricing():
    pricing = resolve_model_pricing(
        "deepseek-v4-pro",
        "https://api.deepseek.com/v1",
        env={
            "LLM_INPUT_COST_PER_M_TOKENS": "0",
            "LLM_OUTPUT_COST_PER_M_TOKENS": "0",
        },
    )
    assert pricing is not None
    assert pricing.input_cache_miss_per_m_tokens == 0.435


def test_compatible_provider_requires_explicit_pricing():
    assert resolve_model_pricing("deepseek-v4-pro", "https://example.com/v1", env={}) is None


def test_cost_is_exact_when_cache_split_is_known():
    pricing = resolve_model_pricing("deepseek-v4-pro", "https://api.deepseek.com", env={})
    assert pricing is not None
    cost = calculate_cost(
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        cache_hit_tokens=750_000,
        cache_miss_tokens=250_000,
        pricing=pricing,
    )
    assert cost.status == "exact"
    assert cost.cache_unknown_tokens == 0
    assert cost.estimated_cost_usd == cost.total_cost_lower_bound_usd
    assert cost.estimated_cost_usd == cost.total_cost_upper_bound_usd
    assert cost.estimated_cost_usd == 0.98146875


def test_legacy_prompt_tokens_produce_strict_cost_range():
    pricing = resolve_model_pricing("deepseek-v4-pro", "https://api.deepseek.com", env={})
    assert pricing is not None
    cost = calculate_cost(
        prompt_tokens=1_000_000,
        completion_tokens=0,
        pricing=pricing,
    )
    assert cost.status == "range"
    assert cost.cache_unknown_tokens == 1_000_000
    assert cost.total_cost_lower_bound_usd == 0.003625
    assert cost.total_cost_upper_bound_usd == 0.435
    assert cost.estimated_cost_usd == 0.435


def test_update_usage_records_deepseek_cache_fields(monkeypatch):
    monkeypatch.setattr(llm, "DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr(llm, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    for name in (
        "LLM_INPUT_COST_PER_M_TOKENS",
        "LLM_INPUT_CACHE_HIT_COST_PER_M_TOKENS",
        "LLM_INPUT_CACHE_MISS_COST_PER_M_TOKENS",
        "LLM_OUTPUT_COST_PER_M_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    metrics = RunMetrics(started_at="now")
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=1_000,
            completion_tokens=100,
            total_tokens=1_100,
            prompt_cache_hit_tokens=800,
            prompt_cache_miss_tokens=200,
        )
    )

    llm._update_usage(metrics, response)

    assert metrics.prompt_cache_hit_tokens == 800
    assert metrics.prompt_cache_miss_tokens == 200
    assert metrics.prompt_cache_unknown_tokens == 0
    assert metrics.cost_estimate_status == "exact"
    assert metrics.estimated_cost_usd > 0


def test_update_usage_reads_sdk_extra_cache_fields_from_model_dump(monkeypatch):
    monkeypatch.setattr(llm, "DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr(llm, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    for name in (
        "LLM_INPUT_COST_PER_M_TOKENS",
        "LLM_INPUT_CACHE_HIT_COST_PER_M_TOKENS",
        "LLM_INPUT_CACHE_MISS_COST_PER_M_TOKENS",
        "LLM_OUTPUT_COST_PER_M_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)

    class Usage:
        prompt_tokens = 100
        completion_tokens = 10
        total_tokens = 110

        def model_dump(self):
            return {
                "prompt_cache_hit_tokens": 60,
                "prompt_cache_miss_tokens": 40,
            }

    metrics = RunMetrics(started_at="now")
    llm._update_usage(metrics, SimpleNamespace(usage=Usage()))

    assert metrics.prompt_cache_hit_tokens == 60
    assert metrics.prompt_cache_miss_tokens == 40
    assert metrics.prompt_cache_unknown_tokens == 0
    assert metrics.cost_estimate_status == "exact"


def test_recalculate_legacy_benchmark_without_rerunning_services():
    payload = {
        "results": [
            {
                "id": "task-1",
                "instruction": "test",
                "tags": [],
                "difficulty": 1,
                "mode": "baseline",
                "repeat": 1,
                "attempted": True,
                "passed": True,
                "partial": False,
                "score": 1.0,
                "assertions": [],
                "failed_reasons": [],
                "failure_category": None,
                "infrastructure_error_code": None,
                "scene_summary": {},
                "scene_check_count": 0,
                "correction_count": 0,
                "timings": {"total_ms": 1.0},
                "run": {
                    "events": [
                        {
                            "type": "run.started",
                            "payload": {"model": "deepseek-v4-pro"},
                        }
                    ],
                    "metrics": {
                        "prompt_tokens": 1_000_000,
                        "completion_tokens": 1_000_000,
                        "estimated_cost_usd": 0,
                    },
                    "tool_calls": [],
                },
            }
        ]
    }

    result = recalculate(payload, base_url="https://api.deepseek.com/v1")
    metrics = result["results"][0]["run"]["metrics"]

    assert metrics["cost_estimate_status"] == "range"
    assert metrics["estimated_cost_lower_bound_usd"] == 0.873625
    assert metrics["estimated_cost_upper_bound_usd"] == 1.305
    assert result["summary"]["legacy_cache_unknown_runs"] == 1
