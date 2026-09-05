"""运行轨迹、反馈与黄金样本准入。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agent.runtime import AgentRunResult, utc_now
from agent.privacy import sanitize_for_log
from agent.sanitizer import contains_sensitive_data, sanitize_structure
from agent.version import PROMPT_VERSION, TOOL_SCHEMA_VERSION, TRACE_SCHEMA_VERSION, __version__

logger = logging.getLogger("rhinocoder.trace_store")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRACE_DIR = PROJECT_ROOT / "data" / "traces"
CANDIDATE_FILE = PROJECT_ROOT / "data" / "candidates.jsonl"
AI_REVIEWED_FILE = PROJECT_ROOT / "data" / "ai_reviewed_candidates.jsonl"
PARTIAL_FILE = PROJECT_ROOT / "data" / "partial_traces.jsonl"
ERROR_ANALYSIS_FILE = PROJECT_ROOT / "data" / "error_traces.jsonl"
GOLDEN_FILE = PROJECT_ROOT / "data" / "golden_traces_v2.jsonl"
LEGACY_GOLDEN_FILE = PROJECT_ROOT / "golden_dataset.jsonl"
FEEDBACK_FILE = PROJECT_ROOT / "data" / "feedback.jsonl"

GOLDEN = "golden"
CANDIDATE = "candidate"
AI_REVIEWED = "ai_reviewed_candidate"
PARTIAL = "partial"
ERROR_ANALYSIS = "error_analysis"

AI_REVIEW_REQUIRED_CHECKS = {
    "programmatic_assertions",
    "scene_summary",
    "tool_trace",
    "rhino_viewport",
}


@dataclass(slots=True)
class GoldenGateResult:
    accepted: bool
    reasons: list[str]
    sanitized_record: dict[str, Any]


def _has_successful_scene_summary(run: dict[str, Any]) -> bool:
    return any(
        call.get("name") == "get_scene_summary" and call.get("success") is True
        for call in run.get("tool_calls") or []
        if isinstance(call, dict)
    )


def build_trace_record(
    instruction: str,
    run: AgentRunResult,
    *,
    evaluation: Optional[dict[str, Any]] = None,
    feedback: Optional[dict[str, Any]] = None,
    task: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "app_version": __version__,
        "prompt_version": PROMPT_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "run_id": run.run_id,
        "instruction": instruction,
        "run": run.to_dict(),
        "evaluation": evaluation,
        "feedback": feedback,
        "task": task,
    }


def validate_golden_candidate(
    record: dict[str, Any],
    *,
    human_confirmed: bool,
) -> GoldenGateResult:
    reasons: list[str] = []
    run = record.get("run") or {}
    evaluation = record.get("evaluation") or {}
    if run.get("status") != "completed":
        reasons.append("run_not_completed")
    if not evaluation.get("passed"):
        reasons.append("programmatic_assertions_not_passed")
    if evaluation.get("partial"):
        reasons.append("partial_pass_not_golden")
    if not run.get("scene_checks"):
        reasons.append("missing_scene_check")
    if not _has_successful_scene_summary(run):
        reasons.append("missing_successful_get_scene_summary")
    if not human_confirmed:
        reasons.append("human_not_confirmed")
    if (record.get("feedback") or {}).get("label") != "accepted":
        reasons.append("accepted_feedback_missing")
    if (record.get("feedback") or {}).get("source") != "human_review":
        reasons.append("human_feedback_source_missing")
    if not run.get("messages"):
        reasons.append("empty_messages")

    sanitized = sanitize_structure(record)
    sanitized["admission"] = {
        "run_status": run.get("status"),
        "human_confirmed": human_confirmed,
        "assertions_passed": bool(evaluation.get("passed")),
        "partial": bool(evaluation.get("partial")),
        "scene_check_count": len(run.get("scene_checks") or []),
        "successful_get_scene_summary": _has_successful_scene_summary(run),
        "feedback_label": (record.get("feedback") or {}).get("label"),
        "feedback_source": (record.get("feedback") or {}).get("source"),
        "sanitization_applied": True,
    }
    if contains_sensitive_data(sanitized):
        reasons.append("sensitive_data_remaining")
    return GoldenGateResult(not reasons, reasons, sanitized)


def validate_ai_review_candidate(record: dict[str, Any]) -> GoldenGateResult:
    """验证 AI 审核候选；它仍不具备进入黄金集所需的人类确认。"""
    reasons: list[str] = []
    run = record.get("run") or {}
    evaluation = record.get("evaluation") or {}
    feedback = record.get("feedback") or {}
    review = feedback.get("review") or {}
    if run.get("status") != "completed":
        reasons.append("run_not_completed")
    if not evaluation.get("passed"):
        reasons.append("programmatic_assertions_not_passed")
    if evaluation.get("partial"):
        reasons.append("partial_pass_not_ai_candidate")
    if not run.get("scene_checks"):
        reasons.append("missing_scene_check")
    if not _has_successful_scene_summary(run):
        reasons.append("missing_successful_get_scene_summary")
    if not run.get("messages"):
        reasons.append("empty_messages")
    task = record.get("task") or {}
    requires_clean_tool_trace = task.get("requires_clean_tool_trace") or (
        task.get("campaign_id") == "phase2-100" and task.get("task_id") == "p2-011"
    )
    if requires_clean_tool_trace and any(
        not bool(call.get("success")) for call in (run.get("tool_calls") or [])
    ):
        reasons.append("failed_tool_call_requires_manual_review")
    if feedback.get("label") != AI_REVIEWED:
        reasons.append("ai_review_label_missing")
    if feedback.get("source") != "ai_visual_review":
        reasons.append("ai_review_source_missing")
    if review.get("verdict") != "pass":
        reasons.append("ai_review_not_passed")
    checks = {str(item) for item in review.get("checks") or []}
    if not AI_REVIEW_REQUIRED_CHECKS.issubset(checks):
        reasons.append("ai_review_checks_incomplete")
    visual_evidence = str(review.get("visual_evidence") or "").strip()
    if not visual_evidence:
        reasons.append("ai_visual_evidence_missing")
    else:
        evidence_path = Path(visual_evidence)
        resolved_evidence = (PROJECT_ROOT / evidence_path).resolve()
        if evidence_path.is_absolute() or not resolved_evidence.is_relative_to(PROJECT_ROOT):
            reasons.append("ai_visual_evidence_outside_project")
        elif not resolved_evidence.is_file():
            reasons.append("ai_visual_evidence_not_found")

    sanitized = sanitize_structure(record)
    if contains_sensitive_data(sanitized):
        reasons.append("sensitive_data_remaining")
    return GoldenGateResult(not reasons, reasons, sanitized)


def classify_trace_disposition(record: dict[str, Any], gate: GoldenGateResult) -> str:
    """将非黄金轨迹稳定分流，避免 Partial/Fail 混入 SFT 正样本。"""
    if gate.accepted:
        return GOLDEN
    evaluation = record.get("evaluation") or {}
    run = record.get("run") or {}
    if evaluation.get("partial") or (record.get("feedback") or {}).get("label") == "partial":
        return PARTIAL
    if run.get("status") in {"failed", "cancelled"} or not evaluation.get("passed"):
        return ERROR_ANALYSIS
    return CANDIDATE


def validate_saved_golden_record(record: dict[str, Any]) -> list[str]:
    """审计已经落盘的黄金行；空列表表示可安全作为 SFT 正样本。"""
    reasons: list[str] = []
    metadata = record.get("metadata") or {}
    evaluation = metadata.get("evaluation") or {}
    feedback = metadata.get("feedback") or {}
    admission = metadata.get("admission") or {}
    if record.get("schema_version") != TRACE_SCHEMA_VERSION:
        reasons.append("schema_version_mismatch")
    if not record.get("run_id"):
        reasons.append("missing_run_id")
    if not record.get("messages"):
        reasons.append("empty_messages")
    if not evaluation.get("passed") or evaluation.get("partial"):
        reasons.append("evaluation_not_full_pass")
    if feedback.get("label") != "accepted":
        reasons.append("accepted_feedback_missing")
    if feedback.get("source") != "human_review":
        reasons.append("human_feedback_source_missing")
    required_admission = {
        "run_status": "completed",
        "human_confirmed": True,
        "assertions_passed": True,
        "partial": False,
        "successful_get_scene_summary": True,
        "feedback_label": "accepted",
        "feedback_source": "human_review",
        "sanitization_applied": True,
    }
    for key, expected in required_admission.items():
        if admission.get(key) != expected:
            reasons.append(f"admission_{key}_invalid")
    if not isinstance(admission.get("scene_check_count"), int) or admission.get("scene_check_count", 0) < 1:
        reasons.append("admission_scene_check_count_invalid")
    if contains_sensitive_data(record):
        reasons.append("sensitive_data_remaining")
    return reasons


def save_trace(record: dict[str, Any]) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{record['run_id']}.json"
    sanitized = sanitize_structure(record)
    path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from agent.db import record_live_trace

        record_live_trace(sanitized, artifact_path=path)
    except Exception as exc:
        logger.warning(
            "SQLite audit trace write failed for %s: %s",
            record.get("run_id"),
            sanitize_for_log(str(exc)),
        )
    return path


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


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


def _task_key(record: dict[str, Any]) -> tuple[str, str] | None:
    task = record.get("task") or ((record.get("metadata") or {}).get("task") or {})
    campaign_id = str(task.get("campaign_id") or "")
    task_id = str(task.get("task_id") or "")
    return (campaign_id, task_id) if campaign_id and task_id else None


def save_ai_reviewed_candidate(
    record: dict[str, Any],
    *,
    batch_id: str,
    note: str,
    visual_evidence: str,
) -> dict[str, Any]:
    """保存通过程序、轨迹和视口检查的 AI 候选，不冒充黄金样本。"""
    evidence_path = Path(visual_evidence)
    resolved_evidence = (PROJECT_ROOT / evidence_path).resolve()
    if evidence_path.is_absolute() or not resolved_evidence.is_relative_to(PROJECT_ROOT):
        raise ValueError("视口证据必须使用项目内的相对路径")
    if not resolved_evidence.is_file():
        raise ValueError(f"视口证据不存在: {visual_evidence}")
    reviewed = {
        **record,
        "feedback": {
            "label": AI_REVIEWED,
            "source": "ai_visual_review",
            "timestamp": utc_now(),
            "batch_id": batch_id,
            "review": {
                "verdict": "pass",
                "checks": sorted(AI_REVIEW_REQUIRED_CHECKS),
                "note": str(note)[:1000],
                "visual_evidence": visual_evidence,
            },
        },
        "disposition": AI_REVIEWED,
    }
    gate = validate_ai_review_candidate(reviewed)
    if not gate.accepted:
        raise ValueError(f"AI 审核候选准入失败: {gate.reasons}")
    key = _task_key(gate.sanitized_record)
    active_ai_candidates = [
        row for row in _read_jsonl(AI_REVIEWED_FILE)
        if validate_ai_review_candidate(row).accepted
    ]
    existing = active_ai_candidates + _read_jsonl(GOLDEN_FILE)
    if key and any(_task_key(row) == key for row in existing):
        raise ValueError(f"审核任务重复: {key[0]}/{key[1]}")
    append_jsonl(AI_REVIEWED_FILE, gate.sanitized_record)
    return gate.sanitized_record


def save_candidate(record: dict[str, Any]) -> None:
    evaluation = record.get("evaluation") or {}
    run = record.get("run") or {}
    if evaluation.get("partial"):
        raise ValueError("Partial Trace 必须通过 save_rejected_trace 写入独立数据集")
    if run.get("status") in {"failed", "cancelled"} or not evaluation.get("passed"):
        raise ValueError("失败 Trace 必须通过 save_rejected_trace 写入错误分析集")
    payload = {**record, "disposition": CANDIDATE}
    append_jsonl(CANDIDATE_FILE, sanitize_structure(payload))


def save_rejected_trace(record: dict[str, Any], gate: GoldenGateResult) -> tuple[str, Path]:
    disposition = classify_trace_disposition(record, gate)
    if disposition == GOLDEN:
        raise ValueError("已通过黄金准入的轨迹不能保存到拒绝数据集")
    target = {
        PARTIAL: PARTIAL_FILE,
        ERROR_ANALYSIS: ERROR_ANALYSIS_FILE,
        CANDIDATE: CANDIDATE_FILE,
    }[disposition]
    payload = {
        **record,
        "disposition": disposition,
        "gate_reasons": gate.reasons,
        "admission": gate.sanitized_record.get("admission", {}),
    }
    append_jsonl(target, sanitize_structure(payload))
    return disposition, target


def _golden_payload(gate: GoldenGateResult) -> dict[str, Any]:
    if not gate.accepted:
        raise ValueError(f"黄金样本准入失败: {gate.reasons}")
    run = gate.sanitized_record["run"]
    admission = gate.sanitized_record.get("admission") or {}
    if not all(
        (
            admission.get("human_confirmed"),
            admission.get("run_status") == "completed",
            admission.get("assertions_passed"),
            admission.get("successful_get_scene_summary"),
            admission.get("feedback_label") == "accepted",
            admission.get("feedback_source") == "human_review",
            not admission.get("partial"),
        )
    ):
        raise ValueError("黄金样本写入边界的准入审计不完整")
    payload = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "run_id": gate.sanitized_record["run_id"],
        "messages": run["messages"],
        "metadata": {
            "app_version": gate.sanitized_record["app_version"],
            "evaluation": gate.sanitized_record["evaluation"],
            "feedback": gate.sanitized_record["feedback"],
            "review_history": gate.sanitized_record.get("review_history") or [],
            "admission": admission,
            "prompt_version": gate.sanitized_record["prompt_version"],
            "tool_schema_version": gate.sanitized_record["tool_schema_version"],
            "task": gate.sanitized_record.get("task"),
        },
    }
    if contains_sensitive_data(payload):
        raise ValueError("黄金样本写入前仍检测到敏感数据")
    row_reasons = validate_saved_golden_record(payload)
    if row_reasons:
        raise ValueError(f"黄金样本写入行审计失败: {row_reasons}")
    return payload


def save_golden_batch(gates: list[GoldenGateResult], *, path: Path | None = None) -> int:
    """先完整预检，再以一次原子替换写入整批黄金样本。"""
    if not gates:
        return 0
    target = path or GOLDEN_FILE
    existing = _read_jsonl(target)
    seen = {key for row in existing if (key := _task_key(row))}
    payloads: list[dict[str, Any]] = []
    for gate in gates:
        payload = _golden_payload(gate)
        key = _task_key(payload)
        if key and key in seen:
            raise ValueError(f"黄金任务重复: {key[0]}/{key[1]}")
        if key:
            seen.add(key)
        payloads.append(payload)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    rows = existing + payloads
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(target)
    try:
        from agent.db import record_live_golden

        for payload in payloads:
            record_live_golden(payload)
    except Exception as exc:
        logger.warning("SQLite audit golden write failed: %s", sanitize_for_log(str(exc)))
    return len(payloads)


def save_golden(gate: GoldenGateResult) -> None:
    save_golden_batch([gate])


def save_feedback(record: dict[str, Any]) -> None:
    sanitized = sanitize_structure(record)
    append_jsonl(FEEDBACK_FILE, sanitized)
    try:
        from agent.db import record_live_feedback

        record_live_feedback(sanitized)
    except Exception as exc:
        logger.warning(
            "SQLite audit feedback write failed for %s: %s",
            record.get("run_id"),
            sanitize_for_log(str(exc)),
        )
