"""真实黄金轨迹采集 campaign 的定义、校验、断点续采与统计。"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.trace_store import (
    AI_REVIEWED,
    AI_REVIEWED_FILE,
    GOLDEN,
    GOLDEN_FILE,
    TRACE_DIR,
    classify_trace_disposition,
    save_feedback,
    save_golden_batch,
    validate_ai_review_candidate,
    validate_golden_candidate,
)
from agent.runtime import utc_now
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
    inherited_golden_campaign_ids: list[str]


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_manifest_tasks(
    path: Path,
    *,
    ancestors: set[Path] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """读取一个 campaign，并支持以只读方式组合已冻结的上游 campaign。"""
    path = path.resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"campaign 文件越出项目目录: {path}")
    ancestors = set(ancestors or ())
    if path in ancestors:
        raise ValueError(f"campaign 引用循环: {path}")
    ancestors.add(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0":
        raise ValueError("campaign schema_version 必须为 1.0")

    tasks: list[dict[str, Any]] = []
    inherited = manifest.get("source_campaign_manifests") or []
    if not isinstance(inherited, list):
        raise ValueError("source_campaign_manifests 必须是数组")
    for relative in inherited:
        child_path = (path.parent / str(relative)).resolve()
        _, child_tasks = _load_manifest_tasks(child_path, ancestors=ancestors)
        tasks.extend(child_tasks)
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
    return manifest, tasks


def load_campaign(path: Path = DEFAULT_CAMPAIGN_MANIFEST) -> CampaignDefinition:
    path = path.resolve()
    manifest, tasks = _load_manifest_tasks(path)
    campaign_id = str(manifest.get("campaign_id", "")).strip()
    if not campaign_id:
        raise ValueError("campaign_id 不能为空")
    inherited_golden_campaign_ids = manifest.get("inherited_golden_campaign_ids") or []
    if not isinstance(inherited_golden_campaign_ids, list):
        raise ValueError("inherited_golden_campaign_ids 必须是数组")
    inherited_golden_campaign_ids = [
        str(value).strip() for value in inherited_golden_campaign_ids if str(value).strip()
    ]
    if len(set(inherited_golden_campaign_ids)) != len(inherited_golden_campaign_ids):
        raise ValueError("inherited_golden_campaign_ids 不能重复")
    if campaign_id in inherited_golden_campaign_ids:
        raise ValueError("campaign 不能继承自身的黄金轨迹")

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
        inherited_golden_campaign_ids=inherited_golden_campaign_ids,
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
    metadata = {
        "campaign_id": campaign.campaign_id,
        "task_id": task["id"],
        "tags": list(task.get("tags") or []),
        "difficulty": int(task.get("difficulty", 0)),
    }
    if task.get("requires_clean_tool_trace"):
        metadata["requires_clean_tool_trace"] = True
    return metadata


def golden_task_ids(campaign_id: str, path: Path = GOLDEN_FILE) -> set[str]:
    found: set[str] = set()
    for row in _read_jsonl(path):
        task = ((row.get("metadata") or {}).get("task") or {})
        if task.get("campaign_id") == campaign_id and task.get("task_id"):
            found.add(str(task["task_id"]))
    return found


def campaign_golden_task_ids(
    campaign: CampaignDefinition,
    path: Path = GOLDEN_FILE,
) -> set[str]:
    """返回本 campaign 与其冻结上游已确认的任务 ID。"""
    campaign_ids = {campaign.campaign_id, *campaign.inherited_golden_campaign_ids}
    found: set[str] = set()
    for row in _read_jsonl(path):
        task = ((row.get("metadata") or {}).get("task") or {})
        if task.get("campaign_id") in campaign_ids and task.get("task_id"):
            found.add(str(task["task_id"]))
    return found


def _campaign_golden_rows(
    campaign: CampaignDefinition,
    path: Path,
) -> dict[str, dict[str, Any]]:
    """按任务 ID 返回当前 campaign 及其冻结上游的黄金记录。"""
    campaign_ids = {campaign.campaign_id, *campaign.inherited_golden_campaign_ids}
    rows: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        task = ((row.get("metadata") or {}).get("task") or {})
        task_id = str(task.get("task_id") or "")
        if task.get("campaign_id") in campaign_ids and task_id:
            rows[task_id] = row
    return rows


def ai_reviewed_candidates(
    campaign_id: str,
    *,
    path: Path = AI_REVIEWED_FILE,
    golden_path: Path = GOLDEN_FILE,
) -> list[dict[str, Any]]:
    """返回仍待人类批量确认的 AI 审核候选。"""
    golden_ids = golden_task_ids(campaign_id, golden_path)
    latest: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        task = row.get("task") or {}
        if (
            task.get("campaign_id") == campaign_id
            and task.get("task_id")
            and validate_ai_review_candidate(row).accepted
        ):
            latest[str(task["task_id"])] = row
    return [row for task_id, row in latest.items() if task_id not in golden_ids]


def ai_reviewed_task_ids(
    campaign_id: str,
    *,
    path: Path = AI_REVIEWED_FILE,
    golden_path: Path = GOLDEN_FILE,
) -> set[str]:
    return {
        str((row.get("task") or {}).get("task_id"))
        for row in ai_reviewed_candidates(campaign_id, path=path, golden_path=golden_path)
    }


def batch_id_for_task(
    campaign: CampaignDefinition,
    task: dict[str, Any],
    *,
    batch_size: int = 5,
) -> str:
    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    task_ids = [str(item["id"]) for item in campaign.tasks]
    try:
        index = task_ids.index(str(task["id"]))
    except ValueError as exc:
        raise ValueError(f"任务不属于 campaign: {task.get('id')}") from exc
    return f"{campaign.campaign_id}-batch-{index // batch_size + 1:02d}"


def _batch_tasks(
    campaign: CampaignDefinition,
    batch_id: str,
    *,
    batch_size: int = 5,
) -> list[dict[str, Any]]:
    matching = [
        task
        for task in campaign.tasks
        if batch_id_for_task(campaign, task, batch_size=batch_size) == batch_id
    ]
    if not matching:
        raise ValueError(f"未知审核批次: {batch_id}")
    return matching


def review_batch_summary(
    campaign: CampaignDefinition,
    batch_id: str,
    *,
    batch_size: int = 5,
    candidate_path: Path = AI_REVIEWED_FILE,
    golden_path: Path = GOLDEN_FILE,
    trace_dir: Path = TRACE_DIR,
) -> dict[str, Any]:
    tasks = _batch_tasks(campaign, batch_id, batch_size=batch_size)
    golden_ids = campaign_golden_task_ids(campaign, golden_path)
    candidates = {
        str((row.get("task") or {}).get("task_id")): row
        for row in ai_reviewed_candidates(
            campaign.campaign_id,
            path=candidate_path,
            golden_path=golden_path,
        )
    }
    golden_rows = _campaign_golden_rows(campaign, golden_path)
    rows: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(task["id"])
        candidate = candidates.get(task_id)
        status = "golden" if task_id in golden_ids else "ai_reviewed_candidate" if candidate else "missing"
        golden_row = golden_rows.get(task_id) or {}
        trace_path = trace_dir / f"{golden_row.get('run_id')}.json" if golden_row.get("run_id") else None
        golden_trace = _read_json(trace_path) if trace_path else {}
        run = (candidate or golden_trace).get("run") or {}
        metrics = run.get("metrics") or {}
        evaluation = (candidate or golden_trace).get("evaluation") or {}
        review_history = ((golden_row.get("metadata") or {}).get("review_history") or [])
        review = ((candidate or {}).get("feedback") or {}).get("review") or (
            (review_history[-1].get("review") or {}) if review_history else {}
        )
        rows.append(
            {
                "task_id": task_id,
                "instruction": task["instruction"],
                "status": status,
                "score": evaluation.get("score"),
                "scene_checks": len(run.get("scene_checks") or []),
                "tool_calls": len(run.get("tool_calls") or []),
                "tokens": int(metrics.get("total_tokens", 0)),
                "cost_usd": float(metrics.get("estimated_cost_upper_bound_usd", 0)),
                "visual_evidence": review.get("visual_evidence"),
                "review_note": review.get("note"),
            }
        )
    ready = all(row["status"] in {"golden", "ai_reviewed_candidate"} for row in rows)
    return {
        "campaign_id": campaign.campaign_id,
        "batch_id": batch_id,
        "batch_size": len(tasks),
        "ready_for_human_review": ready,
        "golden": sum(row["status"] == "golden" for row in rows),
        "ai_reviewed_candidates": sum(row["status"] == "ai_reviewed_candidate" for row in rows),
        "missing": sum(row["status"] == "missing" for row in rows),
        "total_tokens": sum(row["tokens"] for row in rows),
        "estimated_cost_upper_bound_usd": round(sum(row["cost_usd"] for row in rows), 6),
        "tasks": rows,
    }


def promote_review_batch(
    campaign: CampaignDefinition,
    batch_id: str,
    *,
    human_note: str = "",
    batch_size: int = 5,
    candidate_path: Path = AI_REVIEWED_FILE,
    golden_path: Path = GOLDEN_FILE,
) -> int:
    """将一个完整批次的 AI 候选在单次人类确认后原子晋级为黄金样本。"""
    summary = review_batch_summary(
        campaign,
        batch_id,
        batch_size=batch_size,
        candidate_path=candidate_path,
        golden_path=golden_path,
    )
    if not summary["ready_for_human_review"]:
        batch_task_ids = {row["task_id"] for row in summary["tasks"]}
        latest_raw: dict[str, dict[str, Any]] = {}
        for row in _read_jsonl(candidate_path):
            task = row.get("task") or {}
            task_id = str(task.get("task_id") or "")
            if task.get("campaign_id") == campaign.campaign_id and task_id in batch_task_ids:
                latest_raw[task_id] = row
        for task_id, candidate in latest_raw.items():
            gate = validate_ai_review_candidate(candidate)
            if not gate.accepted:
                raise ValueError(f"{task_id} 黄金晋级失败: {gate.reasons}")
        raise ValueError(f"批次尚未收齐，缺少 {summary['missing']} 条")
    candidates = {
        str((row.get("task") or {}).get("task_id")): row
        for row in ai_reviewed_candidates(
            campaign.campaign_id,
            path=candidate_path,
            golden_path=golden_path,
        )
    }
    batch_task_ids = {row["task_id"] for row in summary["tasks"]}
    timestamp = utc_now()
    gates = []
    feedback_rows = []
    for task_id, candidate in candidates.items():
        if task_id not in batch_task_ids:
            continue
        ai_feedback = candidate.get("feedback") or {}
        promoted = {
            **candidate,
            "review_history": [*(candidate.get("review_history") or []), ai_feedback],
            "feedback": {
                "label": "accepted",
                "source": "human_review",
                "mode": "batch",
                "batch_id": batch_id,
                "timestamp": timestamp,
                "note": str(human_note)[:1000],
            },
        }
        promoted.pop("disposition", None)
        gate = validate_golden_candidate(promoted, human_confirmed=True)
        if not gate.accepted:
            raise ValueError(f"{task_id} 黄金晋级失败: {gate.reasons}")
        gates.append(gate)
        feedback_rows.append(
            {
                "run_id": promoted["run_id"],
                "instruction": promoted["instruction"],
                "label": "accepted",
                "source": "human_review",
                "mode": "batch",
                "batch_id": batch_id,
                "note": str(human_note)[:1000],
                "task": promoted.get("task"),
                "timestamp": timestamp,
            }
        )
    if not gates:
        return 0

    written = save_golden_batch(gates, path=golden_path)
    for feedback in feedback_rows:
        save_feedback(feedback)
    return written


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
    if feedback.get("label") == AI_REVIEWED and feedback.get("source") == "ai_visual_review":
        return AI_REVIEWED
    if feedback.get("source") != "human_review":
        return "unreviewed"
    gate = validate_golden_candidate(
        record,
        human_confirmed=feedback.get("label") == "accepted",
    )
    return classify_trace_disposition(record, gate)


def _record_timestamp(record: dict[str, Any]) -> str:
    feedback = record.get("feedback") or {}
    metrics = (record.get("run") or {}).get("metrics") or {}
    return str(
        feedback.get("timestamp")
        or metrics.get("completed_at")
        or metrics.get("started_at")
        or ""
    )


def campaign_summary(
    campaign: CampaignDefinition,
    *,
    golden_path: Path = GOLDEN_FILE,
    candidate_path: Path = AI_REVIEWED_FILE,
    trace_dir: Path = TRACE_DIR,
) -> dict[str, Any]:
    golden_ids = campaign_golden_task_ids(campaign, golden_path)
    ai_candidate_ids = ai_reviewed_task_ids(
        campaign.campaign_id,
        path=candidate_path,
        golden_path=golden_path,
    )
    attempts = campaign_attempts(campaign.campaign_id, trace_dir)
    latest: dict[str, dict[str, Any]] = {}
    for record in attempts:
        task_id = str((record.get("task") or {}).get("task_id", ""))
        if task_id and (
            task_id not in latest
            or _record_timestamp(record) >= _record_timestamp(latest[task_id])
        ):
            latest[task_id] = record
    dispositions = Counter(
        AI_REVIEWED if task_id in ai_candidate_ids else trace_disposition(record)
        for task_id, record in latest.items()
        if task_id not in golden_ids
    )
    dispositions[GOLDEN] = len(golden_ids)
    pending = [task["id"] for task in campaign.tasks if task["id"] not in golden_ids]
    collection_pending = [
        task["id"]
        for task in campaign.tasks
        if task["id"] not in golden_ids and task["id"] not in ai_candidate_ids
    ]
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
    for task_id, record in latest.items():
        if task_id in golden_ids:
            continue
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
        "ai_reviewed_candidates": len(ai_candidate_ids),
        "remaining": campaign.target - len(golden_ids),
        "remaining_to_collect": len(collection_pending),
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
        "collection_pending_task_ids": collection_pending,
    }
