"""运行轨迹、反馈与黄金样本准入。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agent.runtime import AgentRunResult
from agent.sanitizer import contains_sensitive_data, sanitize_structure
from agent.version import PROMPT_VERSION, TOOL_SCHEMA_VERSION, TRACE_SCHEMA_VERSION, __version__

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRACE_DIR = PROJECT_ROOT / "data" / "traces"
CANDIDATE_FILE = PROJECT_ROOT / "data" / "candidates.jsonl"
GOLDEN_FILE = PROJECT_ROOT / "golden_dataset.jsonl"
FEEDBACK_FILE = PROJECT_ROOT / "data" / "feedback.jsonl"


@dataclass(slots=True)
class GoldenGateResult:
    accepted: bool
    reasons: list[str]
    sanitized_record: dict[str, Any]


def build_trace_record(
    instruction: str,
    run: AgentRunResult,
    *,
    evaluation: Optional[dict[str, Any]] = None,
    feedback: Optional[dict[str, Any]] = None,
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
    if not run.get("scene_checks"):
        reasons.append("missing_scene_check")
    if not human_confirmed:
        reasons.append("human_not_confirmed")
    if not run.get("messages"):
        reasons.append("empty_messages")

    sanitized = sanitize_structure(record)
    if contains_sensitive_data(sanitized):
        reasons.append("sensitive_data_remaining")
    return GoldenGateResult(not reasons, reasons, sanitized)


def save_trace(record: dict[str, Any]) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{record['run_id']}.json"
    path.write_text(json.dumps(sanitize_structure(record), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_candidate(record: dict[str, Any]) -> None:
    append_jsonl(CANDIDATE_FILE, sanitize_structure(record))


def save_golden(gate: GoldenGateResult) -> None:
    if not gate.accepted:
        raise ValueError(f"黄金样本准入失败: {gate.reasons}")
    run = gate.sanitized_record["run"]
    append_jsonl(
        GOLDEN_FILE,
        {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": gate.sanitized_record["run_id"],
            "messages": run["messages"],
            "metadata": {
                "evaluation": gate.sanitized_record["evaluation"],
                "prompt_version": gate.sanitized_record["prompt_version"],
                "tool_schema_version": gate.sanitized_record["tool_schema_version"],
            },
        },
    )


def save_feedback(record: dict[str, Any]) -> None:
    append_jsonl(FEEDBACK_FILE, sanitize_structure(record))
