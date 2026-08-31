#!/usr/bin/env python3
"""生成已完成采集 campaign 的可复现数据质量报告。"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.collection_campaign import (  # noqa: E402
    DEFAULT_CAMPAIGN_MANIFEST,
    campaign_attempts,
    golden_task_ids,
    load_campaign,
)


def _run(record: dict[str, Any]) -> dict[str, Any]:
    return record.get("run") or {}


def _metrics(record: dict[str, Any]) -> dict[str, Any]:
    return _run(record).get("metrics") or {}


def _timestamp(record: dict[str, Any]) -> str:
    metrics = _metrics(record)
    return str(metrics.get("started_at") or metrics.get("completed_at") or "")


def _outcome(record: dict[str, Any]) -> str:
    evaluation = record.get("evaluation") or {}
    if evaluation.get("partial"):
        return "partial"
    if _run(record).get("status") == "completed" and evaluation.get("passed"):
        return "full_pass"
    return "failed"


def _sum_cost(records: list[dict[str, Any]], key: str) -> float:
    return round(sum(float(_metrics(record).get(key, 0)) for record in records), 6)


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def summarize(manifest: Path) -> dict[str, Any]:
    campaign = load_campaign(manifest)
    attempts = sorted(campaign_attempts(campaign.campaign_id), key=_timestamp)
    task_attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in attempts:
        task_id = str((record.get("task") or {}).get("task_id") or "")
        if task_id:
            task_attempts[task_id].append(record)

    golden_ids = golden_task_ids(campaign.campaign_id)
    latest = {task_id: rows[-1] for task_id, rows in task_attempts.items()}
    golden_final_records = [latest[task_id] for task_id in golden_ids if task_id in latest]
    first_attempts = [rows[0] for rows in task_attempts.values()]
    outcome_counts = Counter(_outcome(record) for record in attempts)
    first_passes = sum(_outcome(record) == "full_pass" for record in first_attempts)
    recovered = sorted(
        task_id
        for task_id, rows in task_attempts.items()
        if _outcome(rows[0]) != "full_pass" and _outcome(rows[-1]) == "full_pass"
    )
    repeated_without_failure = sorted(
        task_id
        for task_id, rows in task_attempts.items()
        if len(rows) > 1 and all(_outcome(row) == "full_pass" for row in rows)
    )

    failure_reasons = Counter(
        str(reason)
        for record in attempts
        if _outcome(record) != "full_pass"
        for reason in ((record.get("evaluation") or {}).get("failed_reasons") or [])
    )
    tool_errors = Counter(
        str(call.get("error_code") or "unknown")
        for record in attempts
        for call in (_run(record).get("tool_calls") or [])
        if isinstance(call, dict) and not call.get("success")
    )
    correction_events = sum(
        1
        for record in attempts
        for event in (_run(record).get("events") or [])
        if isinstance(event, dict) and event.get("type") == "correction.started"
    )
    correction_attempts = sum(
        1
        for record in attempts
        if int(_metrics(record).get("corrections", 0)) > 0
        or any(
            isinstance(event, dict) and event.get("type") == "correction.started"
            for event in (_run(record).get("events") or [])
        )
    )
    tool_usage = Counter(
        str(call.get("name"))
        for record in golden_final_records
        for call in (_run(record).get("tool_calls") or [])
        if isinstance(call, dict) and call.get("name")
    )
    final_latencies = [float(_metrics(record).get("duration_ms", 0)) for record in golden_final_records]
    failures = []
    for record in attempts:
        outcome = _outcome(record)
        if outcome == "full_pass":
            continue
        run = _run(record)
        failures.append(
            {
                "task_id": (record.get("task") or {}).get("task_id"),
                "outcome": outcome,
                "score": (record.get("evaluation") or {}).get("score"),
                "failed_reasons": (record.get("evaluation") or {}).get("failed_reasons") or [],
                "tool_errors": [
                    {"tool": call.get("name"), "code": call.get("error_code")}
                    for call in run.get("tool_calls") or []
                    if isinstance(call, dict) and not call.get("success")
                ],
            }
        )

    total_tasks = len(campaign.tasks)
    return {
        "campaign_id": campaign.campaign_id,
        "title": campaign.title,
        "target": campaign.target,
        "golden": len(golden_ids),
        "golden_complete": len(golden_ids) == campaign.target,
        "attempts": len(attempts),
        "unique_attempted_tasks": len(task_attempts),
        "first_attempt_full_pass": first_passes,
        "first_attempt_full_pass_rate": _percent(first_passes, total_tasks),
        "eventual_full_pass": sum(_outcome(record) == "full_pass" for record in latest.values()),
        "eventual_full_pass_rate": _percent(
            sum(_outcome(record) == "full_pass" for record in latest.values()), total_tasks
        ),
        "attempt_outcomes": dict(sorted(outcome_counts.items())),
        "recovered_task_ids": recovered,
        "repeated_without_failure_task_ids": repeated_without_failure,
        "difficulty_distribution": dict(sorted(Counter(task["difficulty"] for task in campaign.tasks).items())),
        "tag_coverage": dict(sorted(Counter(tag for task in campaign.tasks for tag in task.get("tags") or []).items())),
        "tool_usage_final_golden": dict(tool_usage.most_common()),
        "correction_events": correction_events,
        "correction_attempts": correction_attempts,
        "tool_error_codes": dict(tool_errors.most_common()),
        "evaluation_failure_reasons": dict(failure_reasons.most_common()),
        "failure_attempts": failures,
        "all_attempt_tokens": sum(int(_metrics(record).get("total_tokens", 0)) for record in attempts),
        "all_attempt_cost_usd": _sum_cost(attempts, "estimated_cost_upper_bound_usd"),
        "golden_final_tokens": sum(int(_metrics(record).get("total_tokens", 0)) for record in golden_final_records),
        "golden_final_cost_usd": _sum_cost(golden_final_records, "estimated_cost_upper_bound_usd"),
        "latency_ms": {
            "mean": round(statistics.mean(final_latencies), 2) if final_latencies else 0.0,
            "median": round(statistics.median(final_latencies), 2) if final_latencies else 0.0,
            "p95": round(_p95(final_latencies), 2),
        },
    }


def _table(mapping: dict[Any, Any], name: str) -> list[str]:
    rows = [f"| {name} | 数量 |", "|---|---:|"]
    rows.extend(f"| {key} | {value} |" for key, value in mapping.items())
    return rows if len(rows) > 2 else [*rows, "| 无 | 0 |"]


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary['title']}数据质量报告",
        "",
        "## 结论",
        "",
        f"- 黄金准入：**{summary['golden']}/{summary['target']}**（{'完成' if summary['golden_complete'] else '未完成'}）。",
        f"- 首次完整通过：**{summary['first_attempt_full_pass']}/{summary['target']}**（{summary['first_attempt_full_pass_rate']:.2f}%）；最终完整通过：**{summary['eventual_full_pass']}/{summary['target']}**（{summary['eventual_full_pass_rate']:.2f}%）。",
        f"- 共 {summary['attempts']} 次运行；恢复成功任务：{', '.join(f'`{item}`' for item in summary['recovered_task_ids']) or '无'}。",
        f"- 闭环纠错：{summary['correction_events']} 个 correction.started 事件，覆盖 {summary['correction_attempts']} 次运行。",
        "",
        "## 覆盖与难度",
        "",
        *_table(summary["difficulty_distribution"], "难度"),
        "",
        f"共覆盖 {len(summary['tag_coverage'])} 个标签。",
        "",
        *_table(summary["tag_coverage"], "标签"),
        "",
        "## 工具覆盖（最终黄金轨迹）",
        "",
        *_table(summary["tool_usage_final_golden"], "工具"),
        "",
        "## 失败与纠错分布",
        "",
        *_table(summary["attempt_outcomes"], "运行结果"),
        "",
        "### 程序化断言失败原因",
        "",
        *_table(summary["evaluation_failure_reasons"], "原因"),
        "",
        "### 工具错误码",
        "",
        *_table(summary["tool_error_codes"], "错误码"),
        "",
        "### 未首次完整通过的运行",
        "",
        "| 任务 | 结果 | 得分 | 断言原因 | 工具错误 |",
        "|---|---|---:|---|---|",
    ]
    for item in summary["failure_attempts"]:
        reasons = "; ".join(map(str, item["failed_reasons"])) or "—"
        errors = "; ".join(f"{error['tool']}:{error['code']}" for error in item["tool_errors"]) or "—"
        score = "—" if item["score"] is None else f"{float(item['score']):.2f}"
        lines.append(f"| `{item['task_id']}` | {item['outcome']} | {score} | {reasons} | {errors} |")
    if not summary["failure_attempts"]:
        lines.append("| — | — | — | 无 | 无 |")
    lines.extend(
        [
            "",
            "## Token、成本与延迟",
            "",
            "| 指标 | 数值 |",
            "|---|---:|",
            f"| 全部尝试 token | {summary['all_attempt_tokens']} |",
            f"| 全部尝试成本上界 | ${summary['all_attempt_cost_usd']:.6f} |",
            f"| 最终黄金 token | {summary['golden_final_tokens']} |",
            f"| 最终黄金成本上界 | ${summary['golden_final_cost_usd']:.6f} |",
            f"| 最终黄金平均延迟 | {summary['latency_ms']['mean']:.2f} ms |",
            f"| 最终黄金中位延迟 | {summary['latency_ms']['median']:.2f} ms |",
            f"| 最终黄金 P95 延迟 | {summary['latency_ms']['p95']:.2f} ms |",
            "",
            "## 复盘结论",
            "",
            "- 失败与 Partial 均保留在错误/Partial 分流中，未作为黄金正样本入库；仅最终通过人工确认的轨迹进入黄金集。",
            "- 可恢复错误应保留为闭环证据：本 campaign 中的群组对齐参数错误由场景自检发现并纠正，最终轨迹仍满足黄金准入。",
            "- 后续扩展任务应优先补强高难组合、布尔、感知、撤销、群组与空间关系，并持续记录首次通过率与恢复成本。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_CAMPAIGN_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(summary), encoding="utf-8")
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
