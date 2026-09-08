#!/usr/bin/env python3
"""Audit the frozen P2 external-source hard set without opening A5 holdout content."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
P2_DIR = ROOT / "eval" / "p2"
RAW_PATH = P2_DIR / "external-anonymous-tasks.zh-CN.md"
TASKS_PATH = P2_DIR / "hard_tasks.jsonl"
FIXTURES_PATH = P2_DIR / "fixtures.json"
STATISTICS_PATH = P2_DIR / "statistics-protocol.json"
LEAKAGE_PATH = P2_DIR / "leakage-policy.json"
MANIFEST_PATH = P2_DIR / "freeze-manifest.json"

FROZEN_PATHS = (RAW_PATH, TASKS_PATH, FIXTURES_PATH, STATISTICS_PATH, LEAKAGE_PATH)
SCENE_ASSERT_KINDS = {"count", "property", "spatial"}
P2_CHECK_KINDS = {
    "all_touch",
    "bbox_gap",
    "clarification_before_write",
    "created_object_count",
    "created_type_consumed",
    "equal_axis_gaps",
    "error_code",
    "failed_then_successful_tool",
    "fallback_before_first_write",
    "fault_consumed",
    "fixture_geometry_fingerprint_unchanged",
    "fixture_missing_corner_filled",
    "fixture_object_properties",
    "forbidden_create_tools",
    "forbidden_tool",
    "forbidden_tools",
    "group_bbox_gap",
    "group_internal_offsets_unchanged",
    "groups_same_min_face",
    "idempotent_second_rollback",
    "lineage_ids_consistent",
    "listener_idempotency_replay",
    "maximum_created_before_rollback",
    "metrics_present",
    "min_face",
    "min_name_lookups",
    "min_scene_checks",
    "minimum_tool_calls",
    "model_request_redacted",
    "no_cloud_request",
    "no_duplicate_geometry",
    "no_duplicate_successful_mutations",
    "no_route_fallback",
    "no_tool_calls",
    "no_writes_after_cancel",
    "observed_capped_scene",
    "precise_rollback",
    "precise_rollback_created_objects",
    "privacy_decision",
    "preserve_fixture_identity",
    "preserve_no_extra_creation",
    "raw_instruction_absent_from_storage",
    "required_tool",
    "required_tools",
    "route_fallback",
    "same_min_face",
    "selected_backend",
    "single_created_identity",
    "stale_id_recovery_or_safe_failure",
    "status_in",
    "terminal_event",
    "unchanged_fixture_objects",
    "unique_group_count",
}
EXPECTED_CATEGORIES = {
    "long_chain_revision": 6,
    "ambiguity_clarification": 6,
    "error_recovery": 6,
    "existing_scene_perception": 6,
    "privacy_routing": 6,
}


@dataclass(slots=True)
class AuditResult:
    passed: bool = True
    tasks: int = 0
    sources: int = 0
    fixtures: int = 0
    manual_scope_tasks: int = 0
    clarification_tasks: int = 0
    holdout_read: int = 0
    exact_overlap_findings: int = 0
    findings: list[str] = field(default_factory=list)

    def add(self, finding: str) -> None:
        self.passed = False
        self.findings.append(finding)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain an object")
    return payload


def load_tasks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(TASKS_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"hard_tasks.jsonl:{line_no} must contain an object")
        rows.append(row)
    return rows


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _known_training_and_eval_texts() -> set[str]:
    """Read public tasks plus A5 train/validation only; deliberately never glob holdout."""
    texts: set[str] = set()
    for path in sorted((ROOT / "eval" / "tasks").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            instruction = row.get("instruction") if isinstance(row, dict) else None
            if isinstance(instruction, str):
                texts.add(_normalize_text(instruction))
    for split in ("train", "validation"):
        for path in sorted((ROOT / "data" / "training" / "a5" / split).glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                for text in _iter_strings(row):
                    normalized = _normalize_text(text)
                    if len(normalized) >= 12:
                        texts.add(normalized)
    return texts


def audit(root: Path = ROOT) -> AuditResult:
    del root  # paths are intentionally fixed to the repository root
    result = AuditResult()
    try:
        raw = RAW_PATH.read_text(encoding="utf-8")
        tasks = load_tasks()
        fixtures_payload = _read_json(FIXTURES_PATH)
        statistics = _read_json(STATISTICS_PATH)
        leakage = _read_json(LEAKAGE_PATH)
        manifest = _read_json(MANIFEST_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result.add(f"unable to load frozen inputs: {exc}")
        return result

    fixtures = fixtures_payload.get("fixtures") or {}
    result.tasks = len(tasks)
    result.sources = len({str(task.get("source_id") or "") for task in tasks})
    result.fixtures = len(fixtures)
    result.manual_scope_tasks = sum(bool(task.get("manual_checks")) for task in tasks)
    result.clarification_tasks = sum("clarification_answer" in task for task in tasks)
    result.holdout_read = 0

    if len(tasks) != 30:
        result.add(f"expected 30 tasks, found {len(tasks)}")
    expected_ids = [f"P2-HARD-{index:03d}" for index in range(1, 31)]
    expected_sources = [f"P2-SRC-{index:03d}" for index in range(1, 31)]
    if [task.get("id") for task in tasks] != expected_ids:
        result.add("task IDs are not the frozen sequential P2-HARD-001..030 set")
    if [task.get("source_id") for task in tasks] != expected_sources:
        result.add("source IDs are not the frozen sequential P2-SRC-001..030 set")
    raw_ids = re.findall(r"^### (P2-HARD-\d{3}).*source_id: (P2-SRC-\d{3})", raw, re.MULTILINE)
    if raw_ids != list(zip(expected_ids, expected_sources)):
        result.add("raw anonymous source record does not map one-to-one to normalized tasks")

    category_counts = Counter(str(task.get("category") or "") for task in tasks)
    if dict(category_counts) != EXPECTED_CATEGORIES:
        result.add(f"category distribution mismatch: {dict(category_counts)}")
    normalized_instructions = [_normalize_text(str(task.get("instruction") or "")) for task in tasks]
    if any(not item for item in normalized_instructions) or len(set(normalized_instructions)) != len(tasks):
        result.add("normalized instructions are empty or duplicated")

    for task in tasks:
        task_id = str(task.get("id") or "unknown")
        for field_name in (
            "difficulty",
            "task_type",
            "perception_gap",
            "route_boundary",
            "fixture_id",
            "expected_tool_chain",
            "expected_results",
            "asserts",
            "p2_checks",
            "manual_checks",
        ):
            if field_name not in task:
                result.add(f"{task_id}: missing {field_name}")
        if task.get("fixture_id") not in fixtures:
            result.add(f"{task_id}: unknown fixture {task.get('fixture_id')!r}")
        if not 1 <= int(task.get("difficulty") or 0) <= 5:
            result.add(f"{task_id}: difficulty must be 1..5")
        asserts = task.get("asserts") or []
        if not asserts:
            result.add(f"{task_id}: objective scene asserts must not be empty")
        for spec in asserts:
            if spec.get("kind") not in SCENE_ASSERT_KINDS:
                result.add(f"{task_id}: unsupported scene assert {spec.get('kind')!r}")
        checks = task.get("p2_checks") or []
        if not checks:
            result.add(f"{task_id}: p2_checks must not be empty")
        for check in checks:
            if check.get("kind") not in P2_CHECK_KINDS:
                result.add(f"{task_id}: unsupported P2 check {check.get('kind')!r}")
        for check in task.get("manual_checks") or []:
            if not all(str(check.get(field) or "").strip() for field in ("id", "reason", "required_evidence")):
                result.add(f"{task_id}: manual check must declare id, reason, and evidence")

    if statistics.get("protocol_id") != "p2-hard-v1" or statistics.get("task_count") != 30:
        result.add("statistics protocol is not locked to p2-hard-v1 / 30 tasks")
    if statistics.get("not_a_usability_study") is not True:
        result.add("statistics protocol must explicitly reject usability-study claims")
    if leakage.get("holdout_read") != 0 or leakage.get("p2_is_evaluation_only") is not True:
        result.add("leakage policy must lock holdout_read=0 and evaluation-only use")
    forbidden_paths = "\n".join(str(item) for item in leakage.get("forbidden_paths_for_p2_runner") or [])
    if "holdout" not in forbidden_paths:
        result.add("leakage policy does not explicitly forbid A5 holdout paths")

    known_texts = _known_training_and_eval_texts()
    overlaps = sorted(
        task["id"]
        for task, normalized in zip(tasks, normalized_instructions)
        if normalized in known_texts
    )
    result.exact_overlap_findings = len(overlaps)
    if overlaps:
        result.add(f"exact instruction overlap with existing eval/train/validation: {overlaps}")

    training_sources = [
        *sorted((ROOT / "training").glob("**/*.py")),
        *sorted((ROOT / "data_pipeline").glob("**/*.py")),
        ROOT / "tools" / "run_training.py",
        ROOT / "tools" / "build_training_dataset.py",
    ]
    for path in training_sources:
        if path.is_file() and "eval/p2" in path.read_text(encoding="utf-8"):
            result.add(f"training consumer references eval/p2: {path.relative_to(ROOT)}")

    expected_hashes = manifest.get("files") or {}
    expected_relatives = {path.relative_to(ROOT).as_posix() for path in FROZEN_PATHS}
    if set(expected_hashes) != expected_relatives:
        result.add("freeze manifest file set does not exactly match frozen inputs")
    for path in FROZEN_PATHS:
        relative = path.relative_to(ROOT).as_posix()
        actual = sha256_file(path)
        if expected_hashes.get(relative) != actual:
            result.add(f"frozen hash mismatch: {relative}")
    if manifest.get("protocol_id") != "p2-hard-v1" or manifest.get("task_count") != 30:
        result.add("freeze manifest protocol/task count mismatch")
    if manifest.get("holdout_read") != 0:
        result.add("freeze manifest must record holdout_read=0")
    if manifest.get("status") != "frozen":
        result.add("freeze manifest status must be frozen")

    result.passed = not result.findings
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit()
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print(
            f"P2 freeze audit {'passed' if result.passed else 'failed'}: "
            f"tasks={result.tasks}, sources={result.sources}, fixtures={result.fixtures}, "
            f"manual_scope={result.manual_scope_tasks}, clarification={result.clarification_tasks}, "
            f"holdout_read={result.holdout_read}, exact_overlap={result.exact_overlap_findings}"
        )
        for finding in result.findings:
            print(f"  ✗ {finding}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
