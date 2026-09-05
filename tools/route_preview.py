#!/usr/bin/env python3
"""Preview a RhinoCoder route decision without calling Rhino or any model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.llm import (  # noqa: E402
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    make_deepseek_client,
)
from agent.model_backends import build_default_backends  # noqa: E402
from agent.router import PrivacyLevel, RouteContext, RouterConfig, select_route  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="Instruction to classify; it is never sent to a model")
    parser.add_argument("--privacy", choices=[item.value for item in PrivacyLevel])
    parser.add_argument("--difficulty", type=int)
    parser.add_argument("--tool-complexity", type=int)
    parser.add_argument("--cost-budget", type=float)
    parser.add_argument("--latency-budget-ms", type=int)
    args = parser.parse_args()

    backends = build_default_backends(
        main_model=DEEPSEEK_MODEL,
        main_base_url=DEEPSEEK_BASE_URL,
        main_client_factory=make_deepseek_client,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )
    context = RouteContext(
        privacy_level=args.privacy,
        task_difficulty=args.difficulty,
        tool_complexity=args.tool_complexity,
        cost_budget_usd=args.cost_budget,
        latency_budget_ms=args.latency_budget_ms,
    )
    decision = select_route(
        args.prompt,
        {name: backend.profile for name, backend in backends.items()},
        context=context,
        config=RouterConfig.from_env(),
    )
    print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
