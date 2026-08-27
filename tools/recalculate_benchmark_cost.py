"""Recalculate benchmark cost without rerunning Rhino or the LLM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.pricing import calculate_cost, resolve_model_pricing
from eval.run_eval import build_summary, render_markdown


def _model_from_results(results: list[dict[str, Any]]) -> str:
    for result in results:
        for event in ((result.get("run") or {}).get("events") or []):
            if event.get("type") == "run.started" and (event.get("payload") or {}).get("model"):
                return str(event["payload"]["model"])
    raise ValueError("结果中缺少 run.started 模型信息")


def recalculate(payload: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    results = payload.get("results") or []
    model = _model_from_results(results)
    pricing = resolve_model_pricing(model, base_url, env={})
    if pricing is None:
        raise ValueError(f"没有 {model} @ {base_url} 的内置价格")

    legacy_unknown_runs = 0
    for result in results:
        metrics = ((result.get("run") or {}).get("metrics") or {})
        if not metrics:
            continue
        prompt_tokens = int(metrics.get("prompt_tokens", 0) or 0)
        completion_tokens = int(metrics.get("completion_tokens", 0) or 0)
        cache_hit = int(metrics.get("prompt_cache_hit_tokens", 0) or 0)
        cache_miss = int(metrics.get("prompt_cache_miss_tokens", 0) or 0)
        cost = calculate_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit_tokens=cache_hit,
            cache_miss_tokens=cache_miss,
            pricing=pricing,
        )
        if cost.cache_unknown_tokens:
            legacy_unknown_runs += 1
        metrics.update({
            "prompt_cache_hit_tokens": cost.cache_hit_tokens,
            "prompt_cache_miss_tokens": cost.cache_miss_tokens,
            "prompt_cache_unknown_tokens": cost.cache_unknown_tokens,
            "input_cost_lower_bound_usd": cost.input_cost_lower_bound_usd,
            "input_cost_upper_bound_usd": cost.input_cost_upper_bound_usd,
            "output_cost_usd": cost.output_cost_usd,
            "estimated_cost_lower_bound_usd": cost.total_cost_lower_bound_usd,
            "estimated_cost_upper_bound_usd": cost.total_cost_upper_bound_usd,
            "estimated_cost_usd": cost.estimated_cost_usd,
            "cost_estimate_status": cost.status,
        })

    summary = build_summary(results)
    summary["pricing"] = pricing.to_dict()
    summary["legacy_cache_unknown_runs"] = legacy_unknown_runs
    return {"summary": summary, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="重算 RhinoCoder 基准成本，不重新调用 Rhino/LLM")
    parser.add_argument("input", type=Path)
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    repriced = recalculate(payload, base_url=args.base_url)
    json_output = args.json_output or args.input.with_name(f"{args.input.stem}_priced.json")
    report_output = args.report_output or args.input.with_name(f"{args.input.stem}_priced.md")
    json_output.write_text(json.dumps(repriced, ensure_ascii=False, indent=2), encoding="utf-8")
    report_output.write_text(
        render_markdown(repriced["summary"], repriced["results"]),
        encoding="utf-8",
    )
    print(f"JSON: {json_output}")
    print(f"Report: {report_output}")


if __name__ == "__main__":
    main()
