#!/usr/bin/env python3
"""Owner-only, non-consuming *preflight* for new C5 Rhino task-family overlap.

This intentionally never emits task text or marks the formal20 set frozen. Run
only where the owner controls the original 80 plaintext and new candidates;
development agents must neither invoke it on those inputs nor receive paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.training_views import numeric_template_signature  # noqa: E402
from training.c5_contract import CORE_INVOCATION_TOOLS  # noqa: E402
from training.c5_formal20_plan import FormalPlanError, validate_families  # noqa: E402
from training.c5_holdout import canonical_bytes, sha256_file  # noqa: E402


STRATA = {"core_tool": 12, "multistep": 2, "clarification": 2,
          "refusal": 2, "error_recovery": 2}
MAX_BYTES = 8 * 1024 * 1024


class ExclusionPreflightError(RuntimeError):
    """An input identity or overlap invariant failed; never include task text."""


def _json(path: Path):
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ExclusionPreflightError("missing_or_unbounded_input")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExclusionPreflightError("invalid_json_input") from exc


def _require_owner_private_path(path: Path, worktrees: list[Path]):
    resolved = path.resolve()
    if any(resolved.is_relative_to(root) for root in worktrees):
        raise ExclusionPreflightError("owner_private_input_must_be_outside_all_worktrees")


def _worktrees() -> list[Path]:
    try:
        raw = subprocess.check_output(["git", "worktree", "list", "--porcelain"], cwd=ROOT,
                                      stderr=subprocess.DEVNULL, timeout=10).decode("utf-8")
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ExclusionPreflightError("cannot_verify_worktree_boundaries") from exc
    roots = [Path(line.removeprefix("worktree ")).resolve()
             for line in raw.splitlines() if line.startswith("worktree ")]
    if not roots or ROOT.resolve() not in roots:
        raise ExclusionPreflightError("cannot_verify_worktree_boundaries")
    return roots


def _jsonl(path: Path, *, expected: int | None = None):
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ExclusionPreflightError("missing_or_unbounded_input")
    rows = []
    try:
        with path.open(encoding="utf-8") as stream:
            for raw in stream:
                if not raw.strip():
                    continue
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ExclusionPreflightError("non_object_jsonl_row")
                rows.append(value)
                if len(rows) > 5000:
                    raise ExclusionPreflightError("unbounded_jsonl_rows")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExclusionPreflightError("invalid_jsonl_input") from exc
    if expected is not None and len(rows) != expected:
        raise ExclusionPreflightError("unexpected_row_count")
    return rows


def _text(row: dict) -> str:
    """Accept the new candidate field or a historical family/trace field."""
    for key in ("task_text", "user_step", "instruction"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    records = row.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        value = records[0].get("user_step")
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ExclusionPreflightError("missing_comparable_task_text")


def _texts(row: dict) -> list[str]:
    """Include later user steps too, without comparing target/answer fields."""
    values = [_text(row)]
    for record in row.get('records', []) if isinstance(row.get('records'), list) else []:
        if isinstance(record, dict) and isinstance(record.get('user_step'), str) and record['user_step'].strip():
            values.append(record['user_step'].strip())
    return list(dict.fromkeys(values))


def _merkle_root(rows: list[dict]) -> str:
    nodes = sorted(hashlib.sha256(canonical_bytes(row)).digest() for row in rows)
    if not nodes:
        raise ExclusionPreflightError("empty_original_holdout")
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[index] + nodes[index + 1]).digest()
                 for index in range(0, len(nodes), 2)]
    return nodes[0].hex()


def audit_candidates(candidates: list[dict], development: list[dict], original80: list[dict],
                     extra: list[dict], *, original_root: str,
                     historical_numeric_hashes: set[str]) -> dict:
    """Pure overlap preflight. Passing is deliberately *not* formal freeze."""
    if len(candidates) != 20 or len(development) != 440 or len(original80) != 80 or not extra:
        raise ExclusionPreflightError("incomplete_exclusion_population")
    if _merkle_root(original80) != original_root:
        raise ExclusionPreflightError("original80_identity_mismatch")
    if any(not isinstance(row, dict) for row in candidates + development + original80 + extra):
        raise ExclusionPreflightError("non_object_row")
    if Counter(row.get("stratum") for row in candidates) != STRATA:
        raise ExclusionPreflightError("formal_strata_mismatch")
    tools = [row.get("primary_tool") for row in candidates if row.get("stratum") == "core_tool"]
    if Counter(tools) != Counter(CORE_INVOCATION_TOOLS):
        raise ExclusionPreflightError("core_tool_coverage_mismatch")
    ids, templates = [], []
    for row in candidates:
        family_id, template = row.get("family_id"), row.get("template_family")
        if not isinstance(family_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{3,79}", family_id):
            raise ExclusionPreflightError("invalid_candidate_family_id")
        if not isinstance(template, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{3,79}", template):
            raise ExclusionPreflightError("invalid_candidate_template_family")
        ids.append(family_id)
        templates.append(template)
    if len(set(ids)) != 20 or len(set(templates)) != 20:
        raise ExclusionPreflightError("candidate_family_or_template_reuse")
    historical_ids = {str(row.get("family_id")) for row in development + original80 + extra
                      if row.get("family_id") is not None}
    if set(ids) & historical_ids:
        raise ExclusionPreflightError("candidate_family_id_overlap")
    historical_templates = {row['template_family'] for row in development + original80 + extra
                            if isinstance(row.get('template_family'), str)}
    if set(templates) & historical_templates:
        raise ExclusionPreflightError('candidate_template_family_overlap')
    candidate_text = [numeric_template_signature(_text(row)) for row in candidates]
    excluded_text = [numeric_template_signature(text) for row in development + original80 + extra for text in _texts(row)]
    if len(set(candidate_text)) != 20:
        raise ExclusionPreflightError("candidate_numeric_template_reuse")
    excluded = set(excluded_text)
    if any(text in excluded for text in candidate_text):
        raise ExclusionPreflightError("numeric_template_overlap")
    if any(hashlib.sha256(("historical-text:" + text).encode()).hexdigest() in historical_numeric_hashes
           for text in candidate_text):
        raise ExclusionPreflightError("a5_p2_r_historical_template_overlap")
    for index, text in enumerate(candidate_text):
        if any(SequenceMatcher(None, text, other).ratio() >= 0.92
               for other in excluded_text + candidate_text[:index]):
            raise ExclusionPreflightError("near_duplicate_overlap")
    return {
        "status": "owner_private_automated_exclusion_preflight_only_not_formal_freeze",
        "candidate_count": 20, "development_count": 440, "original80_count": 80,
        "additional_exclusion_count": len(extra),
        "exact_numeric_or_092_near_duplicate_overlap_count": 0,
        "original80_public_merkle_identity_verified": True,
        "original80_rows_read_only_in_owner_private_preflight": 80,
        "manual_semantic_and_complete_r_exclusion_review_still_required": True,
        "formal_commitment_ready": False, "formal_run_authorized": False,
        "holdout_model_generation_calls": 0,
    }


def preflight_paths(candidate: Path, original80: Path, development_paths: list[Path],
                    extra_paths: list[Path]) -> tuple[list[dict], dict, dict]:
    """Owner-only private read. Return no text in the aggregate report/bindings."""
    worktrees = _worktrees()
    for path in (candidate, original80, *extra_paths):
        _require_owner_private_path(path, worktrees)
    if candidate.resolve() == original80.resolve():
        raise ExclusionPreflightError("candidate_and_original80_inputs_must_differ")
    if len(development_paths) != 3 or not extra_paths:
        raise ExclusionPreflightError("complete_development_and_extra_exclusions_required")
    freeze = _json(ROOT / "eval/c5/dataset-v2-freeze-manifest.json")
    original_commitment = _json(ROOT / "eval/c5/final-holdout-commitment.json")
    historical = _json(ROOT / "eval/c5/historical-exclusions.json")
    freeze_sha = sha256_file(ROOT / "eval/c5/dataset-v2-freeze-manifest.json")
    historical_sha = sha256_file(ROOT / "eval/c5/historical-exclusions.json")
    if (original_commitment["exclusions"]["development_dataset_freeze_sha256"] != freeze_sha or
        original_commitment["exclusions"]["historical_exclusions_sha256"] != historical_sha):
        raise ExclusionPreflightError("public_exclusion_identity_mismatch")
    frozen = {item["path"]: item for item in freeze["artifacts"]}
    development = []
    seen = set()
    for path in development_paths:
        item = frozen.get(path.name)
        if item is None or path.name in seen or sha256_file(path) != item["sha256"]:
            raise ExclusionPreflightError("frozen_development_split_identity_mismatch")
        development.extend(_jsonl(path, expected=item["families"]))
        seen.add(path.name)
    if seen != {"train.jsonl", "validation.jsonl", "development.jsonl"}:
        raise ExclusionPreflightError("incomplete_frozen_development_splits")
    extra = [row for path in extra_paths for row in _jsonl(path)]
    candidates = validate_families(_jsonl(candidate, expected=20))
    report = audit_candidates(
        candidates, development,
        _jsonl(original80, expected=80), extra,
        original_root=original_commitment["fingerprints"]["family_merkle_root_sha256"],
        historical_numeric_hashes=set(historical["all_historical_numeric_text_hashes"]),
    )
    bindings = {"development_dataset_freeze_sha256": freeze_sha,
                "historical_exclusions_sha256": historical_sha,
                "original80_public_commitment_file_sha256": sha256_file(ROOT / "eval/c5/final-holdout-commitment.json"),
                "original80_family_merkle_root_sha256": original_commitment["fingerprints"]["family_merkle_root_sha256"],
                "additional_exclusion_file_sha256": sorted(sha256_file(path) for path in extra_paths)}
    return candidates, report, bindings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--original80", type=Path, required=True)
    parser.add_argument("--development", type=Path, action="append", required=True)
    parser.add_argument("--extra-exclusion-jsonl", type=Path, action="append", required=True)
    args = parser.parse_args()
    try:
        _, report, _ = preflight_paths(args.candidate, args.original80,
                                      args.development, args.extra_exclusion_jsonl)
    except (ExclusionPreflightError, FormalPlanError, KeyError, TypeError, OSError, ValueError) as exc:
        # Never print paths, prompts, IDs, or matches in owner terminal output.
        category = str(exc) if isinstance(exc, ExclusionPreflightError) else (
            "formal_case_schema_invalid" if isinstance(exc, FormalPlanError) else "invalid_input_or_identity")
        print(json.dumps({"status": "owner_private_preflight_failed", "category": category}), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
