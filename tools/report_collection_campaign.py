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

from agent.collection_campaign import (
    DEFAULT_CAMPAIGN_MANIFEST,
    campaign_summary,
    load_campaign,
    review_batch_summary,
)


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
        f"| AI 审核候选 | {summary['ai_reviewed_candidates']} |",
        f"| 尚待采集 | {summary['remaining_to_collect']} |",
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


def render_batch_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# 审核批次 {summary['batch_id']}",
        "",
        f"- 状态：{'已收齐，可批量确认' if summary['ready_for_human_review'] else '尚未收齐'}",
        f"- 已是黄金：{summary['golden']}",
        f"- AI 审核候选：{summary['ai_reviewed_candidates']}",
        f"- 缺少：{summary['missing']}",
        f"- Candidate token：{summary['total_tokens']}",
        f"- Candidate 成本上界：${summary['estimated_cost_upper_bound_usd']:.6f}",
        "",
        "| 任务 | 状态 | 得分 | 自检 | 工具调用 | token |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in summary["tasks"]:
        score = "—" if row["score"] is None else f"{float(row['score']):.2f}"
        lines.append(
            f"| `{row['task_id']}` | {row['status']} | {score} | {row['scene_checks']} | "
            f"{row['tool_calls']} | {row['tokens']} |"
        )
    lines.extend(["", "## AI 审核证据", ""])
    for row in summary["tasks"]:
        lines.extend([f"### {row['task_id']}", "", row["instruction"], ""])
        if row.get("review_note"):
            lines.extend([f"审核：{row['review_note']}", ""])
        if row.get("visual_evidence"):
            lines.extend([f"![{row['task_id']} Rhino 视口]({row['visual_evidence']})", ""])
        elif row["status"] == "golden":
            lines.extend(["已在此前逐条人工确认；本批不重复要求确认。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_CAMPAIGN_MANIFEST)
    parser.add_argument("--batch-id", help="输出指定的 5 条审核批次")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--output", type=Path, help="Markdown 输出路径；默认只打印")
    parser.add_argument("--json-output", type=Path, help="可选 JSON 输出路径")
    args = parser.parse_args()
    campaign = load_campaign(args.manifest)
    if args.batch_id:
        summary = review_batch_summary(campaign, args.batch_id, batch_size=args.batch_size)
        markdown = render_batch_markdown(summary)
    else:
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
