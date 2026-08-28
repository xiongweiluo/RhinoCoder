"""真实黄金轨迹采集 campaign 的定义、校验、断点续采与统计。"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.trace_store import (
    GOLDEN,
    GOLDEN_FILE,
    TRACE_DIR,
    classify_trace_disposition,
    validate_golden_candidate,
)
from eval.run_eval import load_tasks

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAMPAIGN_MANIFEST = PROJECT_ROOT / "eval" / "collection" / "phase1_30.json"


@dataclass(slots=True)
class CampaignDefinition:
    campaign_id: str
    title: str
    target: int
    tasks: list[dict[str, Any]]
    manifest_path: Path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def load_campaign(path: Path = DEFAULT_CAMPAIGN_MANIFEST) -> CampaignDefinition:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0":
        raise ValueError("campaign schema_version 必须为 1.0")
    campaign_id = str(manifest.get("campaign_id", "")).strip()
    if not campaign_id:
        raise ValueError("campaign_id 不能为空")

    tasks: list[dict[str, Any]] = []
    for relative in manifest.get("source_task_files") or []:
        task_path = (path.parent / str(relative)).resolve()
        if not task_path.is_relative_to(PROJECT_ROOT):
            raise ValueError(f"任务文件越出项目目录: {relative}")
        tasks.extend(load_tasks(task_path))
    excluded = {str(task_id) for task_id in manifest.get("exclude_task_ids") or []}
    tasks = [task for task in tasks if str(task.get("id")) not in excluded]
    additional = manifest.get("additional_tasks") or []
    if not isinstance(additional, list):
        raise ValueError("additional_tasks 必须是数组")
    tasks.extend(additional)

    target = int(manifest.get("target", 0))
    findings = validate_campaign_tasks(tasks, target=target, requirements=manifest.get("diversity_requirements") or {})
    if findings:
        raise ValueError("campaign 校验失败: " + "; ".join(findings))
    return CampaignDefinition(
        campaign_id=campaign_id,
        title=str(manifest.get("title") or campaign_id),
        target=target,
        tasks=tasks,
        manifest_path=path,
    )


def validate_campaign_tasks(
    tasks: list[dict[str, Any]],
    *,
    target: int,
    requirements: dict[str, Any],
) -> list[str]:
    findings: list[str] = []
    ids = [str(task.get("id", "")).strip() for task in tasks]
    instructions = [str(task.get("instruction", "")).strip() for task in tasks]
    if len(tasks) != target:
        findings.append(f"任务数 {len(tasks)} != target {target}")
    if len(set(ids)) != len(ids) or any(not task_id for task_id in ids):
        findings.append("任务 ID 为空或重复")
    if len(set(instructions)) != len(instructions) or any(not item for item in instructions):
        findings.append("任务指令为空或重复")
    for task in tasks:
        if not isinstance(task.get("asserts"), list) or not task["asserts"]:
            findings.append(f"{task.get('id')}: asserts 不能为空")
        if not isinstance(task.get("tags"), list) or not task["tags"]:
            findings.append(f"{task.get('id')}: tags 不能为空")
        if not isinstance(task.get("difficulty"), int) or not 1 <= task["difficulty"] <= 5:
            findings.append(f"{task.get('id')}: difficulty 必须为 1-5")
        for index, spec in enumerate(task.get("asserts") or [], 1):
            kind = spec.get("kind") if isinstance(spec, dict) else None
            required = {
                "count": {"selector", "n"},
                "property": {"selector", "props"},
                "spatial": {"a", "b", "relation"},
            }.get(kind)
            if required is None or not required.issubset(spec):
                findings.append(f"{task.get('id')}: assert #{index} 结构无效")
    unique_tags = {tag for task in tasks for tag in task.get("tags") or []}
    min_tags = int(requirements.get("min_unique_tags", 0))
    if len(unique_tags) < min_tags:
        findings.append(f"唯一标签数 {len(unique_tags)} < {min_tags}")
    hard_count = sum(1 for task in tasks if int(task.get("difficulty", 0)) >= 4)
    min_hard = int(requirements.get("min_difficulty_4_or_higher", 0))
    if hard_count < min_hard:
        findings.append(f"难度 4+ 任务数 {hard_count} < {min_hard}")
    required_tags = {str(tag) for tag in requirements.get("required_tags") or []}
    missing_tags = sorted(required_tags - unique_tags)
    if missing_tags:
        findings.append(f"缺少必须覆盖的标签: {missing_tags}")
    normalized = Counter(
        re.sub(r"\d+(?:\.\d+)?", "<N>", instruction).strip().lower()
        for instruction in instructions
    )
    max_templates = int(requirements.get("max_numeric_template_duplicates", 0))
    if max_templates:
        repeated = [signature for signature, count in normalized.items() if count > max_templates]
        if repeated:
            findings.append(f"存在仅替换数字的重复任务模板: {len(repeated)} 组")
    return findings


def task_metadata(campaign: CampaignDefinition, task: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_id": campaign.campaign_id,
        "task_id": task["id"],
        "tags": list(task.get("tags") or []),
        "difficulty": int(task.get("difficulty", 0)),
    }


def golden_task_ids(campaign_id: str, path: Path = GOLDEN_FILE) -> set[str]:
    found: set[str] = set()
    for row in _read_jsonl(path):
        task = ((row.get("metadata") or {}).get("task") or {})
        if task.get("campaign_id") == campaign_id and task.get("task_id"):
            found.add(str(task["task_id"]))
    return found


def campaign_attempts(campaign_id: str, trace_dir: Path = TRACE_DIR) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    if not trace_dir.is_dir():
        return attempts
    for path in sorted(trace_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (record.get("task") or {}).get("campaign_id") == campaign_id:
            attempts.append(record)
    return attempts


def trace_disposition(record: dict[str, Any]) -> str:
    feedback = record.get("feedback") or {}
    if feedback.get("source") != "human_review":
        return "unreviewed"
    gate = validate_golden_candidate(
        record,
        human_confirmed=feedback.get("label") == "accepted",
    )
    return classify_trace_disposition(record, gate)


def campaign_summary(
    campaign: CampaignDefinition,
    *,
    golden_path: Path = GOLDEN_FILE,
    trace_dir: Path = TRACE_DIR,
) -> dict[str, Any]:
    golden_ids = golden_task_ids(campaign.campaign_id, golden_path)
    attempts = campaign_attempts(campaign.campaign_id, trace_dir)
    latest: dict[str, dict[str, Any]] = {}
    for record in attempts:
        task_id = str((record.get("task") or {}).get("task_id", ""))
        if task_id:
            latest[task_id] = record
    dispositions = Counter(trace_disposition(record) for record in latest.values())
    dispositions[GOLDEN] = len(golden_ids)
    pending = [task["id"] for task in campaign.tasks if task["id"] not in golden_ids]
    golden_tasks = [task for task in campaign.tasks if task["id"] in golden_ids]
    metrics = [record.get("run", {}).get("metrics", {}) for record in attempts]
    tool_usage = Counter(
        str(call.get("name"))
        for record in attempts
        for call in (record.get("run", {}).get("tool_calls") or [])
        if isinstance(call, dict) and call.get("name")
    )
    evaluation_failures = Counter(
        str(reason)
        for record in latest.values()
        for reason in ((record.get("evaluation") or {}).get("failed_reasons") or [])
    )
    gate_failures: Counter[str] = Counter()
    for record in latest.values():
        feedback = record.get("feedback") or {}
        if feedback.get("source") != "human_review":
            gate_failures["human_review_missing"] += 1
            continue
        gate = validate_golden_candidate(
            record,
            human_confirmed=feedback.get("label") == "accepted",
        )
        gate_failures.update(gate.reasons)
    return {
        "campaign_id": campaign.campaign_id,
        "title": campaign.title,
        "target": campaign.target,
        "unique_instructions": len({task["instruction"] for task in campaign.tasks}),
        "unique_tags": len({tag for task in campaign.tasks for tag in task.get("tags") or []}),
        "difficulty_distribution": dict(sorted(Counter(task["difficulty"] for task in campaign.tasks).items())),
        "attempts": len(attempts),
        "attempted_tasks": len(latest),
        "golden": len(golden_ids),
        "remaining": campaign.target - len(golden_ids),
        "latest_dispositions": dict(sorted(dispositions.items())),
        "golden_difficulty_distribution": dict(sorted(Counter(task["difficulty"] for task in golden_tasks).items())),
        "golden_tag_coverage": dict(sorted(Counter(tag for task in golden_tasks for tag in task.get("tags") or []).items())),
        "tool_usage": dict(tool_usage.most_common()),
        "evaluation_failure_reasons": dict(evaluation_failures.most_common()),
        "gate_failure_reasons": dict(gate_failures.most_common()),
        "total_tokens": sum(int(metric.get("total_tokens", 0)) for metric in metrics),
        "estimated_cost_lower_bound_usd": round(sum(float(metric.get("estimated_cost_lower_bound_usd", 0)) for metric in metrics), 6),
        "estimated_cost_upper_bound_usd": round(sum(float(metric.get("estimated_cost_upper_bound_usd", 0)) for metric in metrics), 6),
        "pending_task_ids": pending,
    }
