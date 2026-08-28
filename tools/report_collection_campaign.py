#!/usr/bin/env python3
"""生成真实黄金数据采集 campaign 的本地 Markdown/JSON 进度报告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.collection_campaign import DEFAULT_CAMPAIGN_MANIFEST, campaign_summary, load_campaign


def _table(mapping: dict[str, Any], left: str, right: str) -> list[str]:
    lines = [f"| {left} | {right} |", "|---|---:|"]
    lines.extend(f"| {key} | {value} |" for key, value in mapping.items())
    if len(lines) == 2:
        lines.append("| 暂无 | 0 |")
    return lines


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary['title']}进度报告",
        "",
        "## 核心进度",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 目标任务 | {summary['target']} |",
        f"| 唯一指令 | {summary['unique_instructions']} |",
        f"| 唯一标签 | {summary['unique_tags']} |",
        f"| 总尝试 | {summary['attempts']} |",
        f"| 已尝试任务 | {summary['attempted_tasks']} |",
        f"| 黄金任务 | {summary['golden']} |",
        f"| 剩余任务 | {summary['remaining']} |",
        f"| 总 token | {summary['total_tokens']} |",
        "| 成本区间 | ${:.6f}–${:.6f} |".format(
            summary["estimated_cost_lower_bound_usd"],
            summary["estimated_cost_upper_bound_usd"],
        ),
        "",
        "## 最新分流",
        "",
        *_table(summary["latest_dispositions"], "分流", "任务数"),
        "",
        "## 黄金难度分布",
        "",
        *_table(summary["golden_difficulty_distribution"], "难度", "任务数"),
        "",
        "## 工具覆盖",
        "",
        *_table(summary["tool_usage"], "工具", "调用次数"),
        "",
        "## 程序断言失败分布",
        "",
        *_table(summary["evaluation_failure_reasons"], "原因", "次数"),
        "",
        "## 黄金准入失败分布",
        "",
        *_table(summary["gate_failure_reasons"], "原因", "次数"),
        "",
        "## 尚未进入黄金集的任务",
        "",
        *(f"- `{task_id}`" for task_id in summary["pending_task_ids"]),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_CAMPAIGN_MANIFEST)
    parser.add_argument("--output", type=Path, help="Markdown 输出路径；默认只打印")
    parser.add_argument("--json-output", type=Path, help="可选 JSON 输出路径")
    args = parser.parse_args()
    campaign = load_campaign(args.manifest)
    summary = campaign_summary(campaign)
    markdown = render_markdown(summary)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(args.output)
    else:
        print(markdown)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
