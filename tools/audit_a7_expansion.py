#!/usr/bin/env python3
"""Audit A7 coverage gain, admission evidence, routing, and stop-at-500 policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.collection_campaign import (  # noqa: E402
    ai_reviewed_candidates,
    batch_id_for_task,
    campaign_attempts,
    campaign_golden_task_ids,
    golden_task_ids,
    load_campaign,
)
from agent.router import RouteMode, RouterConfig, select_route  # noqa: E402
from agent.trace_store import GOLDEN_FILE, validate_saved_golden_record  # noqa: E402
from eval.a6_baseline import _profiles  # noqa: E402

DEFAULT_MANIFEST = ROOT / "eval" / "collection" / "a7_500.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def audit(manifest: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    campaign = load_campaign(manifest)
    new_tasks = [task for task in campaign.tasks if task["id"].startswith("a7-")]
    inherited_tasks = [task for task in campaign.tasks if not task["id"].startswith("a7-")]
    inherited_tags = Counter(tag for task in inherited_tasks for tag in task.get("tags") or [])
    combined_tags = Counter(tag for task in campaign.tasks for tag in task.get("tags") or [])
    new_task_ids = {str(task["id"]) for task in new_tasks}
    current_golden_ids = golden_task_ids(campaign.campaign_id)
    candidates = ai_reviewed_candidates(campaign.campaign_id)
    candidate_ids = {str((row.get("task") or {}).get("task_id")) for row in candidates}
    attempts = campaign_attempts(campaign.campaign_id)
    attempted_ids = {
        str((record.get("task") or {}).get("task_id")) for record in attempts
    }

    profiles = _profiles()
    route_config = RouterConfig(
        enabled=True,
        mode=RouteMode.AUTO,
        fallback_enabled=True,
        max_fallbacks=1,
    )
    routes = [
        select_route(task["instruction"], profiles, config=route_config)
        for task in new_tasks
    ]
    route_distribution = Counter(route.selected_backend for route in routes)
    route_mismatches = [
        task["id"]
        for task, route in zip(new_tasks, routes, strict=True)
        if route.selected_backend != task.get("expected_route")
    ]

    gap_planned = Counter(str(task["coverage_gap"]) for task in new_tasks)
    gap_golden = Counter(
        str(task["coverage_gap"])
        for task in new_tasks
        if task["id"] in current_golden_ids
    )
    batch_members = Counter(
        batch_id_for_task(campaign, task) for task in new_tasks
    )
    invalid_batches = {
        batch_id: count
        for batch_id, count in batch_members.items()
        if count != campaign.review_batch_size
    }

    golden_rows = _read_jsonl(GOLDEN_FILE)
    relevant_golden = [
        row
        for row in golden_rows
        if str(((row.get("metadata") or {}).get("task") or {}).get("task_id"))
        in new_task_ids
    ]
    admission_findings = {
        str(row.get("run_id")): validate_saved_golden_record(row)
        for row in relevant_golden
        if validate_saved_golden_record(row)
    }
    evidence_missing = []
    for row in [*candidates, *relevant_golden]:
        task = row.get("task") or ((row.get("metadata") or {}).get("task") or {})
        history = row.get("review_history") or ((row.get("metadata") or {}).get("review_history") or [])
        feedback = row.get("feedback") or ((row.get("metadata") or {}).get("feedback") or {})
        reviews = [feedback, *history]
        evidence = ""
        for review_row in reviews:
            evidence = str(((review_row or {}).get("review") or {}).get("visual_evidence") or evidence)
        if not evidence or not (ROOT / evidence).is_file():
            evidence_missing.append(str(task.get("task_id") or row.get("run_id")))

    introduced_tags = sorted(set(combined_tags) - set(inherited_tags))
    complete = len(campaign_golden_task_ids(campaign)) == campaign.target
    realized_all_gaps = all(gap_golden[gap] == count for gap, count in gap_planned.items())
    passed = not any((
        len(new_tasks) != 200,
        route_mismatches,
        invalid_batches,
        admission_findings,
        evidence_missing,
        complete and not realized_all_gaps,
    ))
    stop_decision = (
        "pause_at_500_pending_unified_evaluation"
        if complete and passed
        else "do_not_expand_until_a7_admission_is_complete"
    )
    return {
        "schema_version": "1.0",
        "campaign_id": campaign.campaign_id,
        "passed": passed,
        "target": campaign.target,
        "inherited_golden": campaign.target - len(new_tasks),
        "new_task_count": len(new_tasks),
        "attempted_new_tasks": len(attempted_ids & new_task_ids),
        "ai_reviewed_candidates": len(candidate_ids),
        "new_golden": len(current_golden_ids),
        "golden_total": len(campaign_golden_task_ids(campaign)),
        "total_tags": len(combined_tags),
        "review_batch_size": campaign.review_batch_size,
        "review_batches": len(batch_members),
        "invalid_batches": invalid_batches,
        "planned_gap_distribution": dict(sorted(gap_planned.items())),
        "golden_gap_distribution": dict(sorted(gap_golden.items())),
        "introduced_tags": introduced_tags,
        "tag_gain": {
            tag: {"before": inherited_tags[tag], "after": combined_tags[tag], "delta": combined_tags[tag] - inherited_tags[tag]}
            for tag in sorted(set(tag for task in new_tasks for tag in task.get("tags") or []))
        },
        "route_distribution": dict(sorted(route_distribution.items())),
        "route_mismatches": route_mismatches,
        "admission_findings": admission_findings,
        "evidence_missing": sorted(set(evidence_missing)),
        "stop_decision": stop_decision,
        "next_expansion_gate": (
            "Only reconsider 1,000-5,000 after C3 unified evaluation identifies a measured, reproducible gap "
            "that cannot be addressed by routing, prompting, or tools."
        ),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# A7 覆盖缺口扩展与 500 条边际价值报告",
        "",
        f"结论：**{'通过' if result['passed'] else '尚未通过'}**。当前黄金准入 "
        f"**{result['golden_total']}/{result['target']}**，A7 新增黄金 "
        f"**{result['new_golden']}/{result['new_task_count']}**。",
        "",
        "## 设计与执行证据",
        "",
        f"- 继承冻结黄金：{result['inherited_golden']} 条；覆盖缺口新增任务：{result['new_task_count']} 条。",
        f"- 审核批次：{result['review_batches']} 批，每批 {result['review_batch_size']} 条；异常批次：{len(result['invalid_batches'])}。",
        f"- 已尝试新增任务：{result['attempted_new_tasks']}；AI 初审候选：{result['ai_reviewed_candidates']}。",
        f"- 规则路由预演：{result['route_distribution']}；与预期不符：{len(result['route_mismatches'])}。",
        f"- 当前黄金集覆盖标签：{result['total_tags']} 个。",
        f"- 新增标签：{', '.join(f'`{tag}`' for tag in result['introduced_tags']) or '无'}。",
        "",
        "| 覆盖缺口 | 计划 | 已进入黄金 |",
        "|---|---:|---:|",
    ]
    for gap, planned in result["planned_gap_distribution"].items():
        lines.append(f"| {gap} | {planned} | {result['golden_gap_distribution'].get(gap, 0)} |")
    lines.extend([
        "",
        "## 准入与证据审计",
        "",
        f"- 黄金准入异常：{len(result['admission_findings'])}。",
        f"- 截图证据缺失：{len(result['evidence_missing'])}。",
        f"- 原子批次结构异常：{len(result['invalid_batches'])}。",
        "",
        "## 500 条后的边际价值决策",
        "",
        f"决策：`{result['stop_decision']}`。",
        "",
        "A7 达标后在 500 条停止扩张。只有 C3 统一评测证明存在可复现、量化且不能优先通过"
        "路由、Prompt 或工具修复的缺口，才重新考虑 1,000–5,000 条；不得因管线已存在而默认扩张。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.manifest)
    rendered_json = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered_json, encoding="utf-8")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_markdown(result), encoding="utf-8")
    if not args.json_output and not args.output:
        print(rendered_json, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
