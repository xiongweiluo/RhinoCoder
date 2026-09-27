#!/usr/bin/env python3
"""Build and gate the contract-aligned C5 dataset-v2 development pool."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_tool_contract_candidate import TOKENIZER_SNAPSHOT  # noqa: E402
from training.c5_dataset import (  # noqa: E402
    C5DatasetError,
    apply_reviews,
    assign_family_splits,
    audit_draft,
    audit_payload,
    build_draft_families,
    build_historical_exclusions,
    freeze_accepted_dataset,
    load_reviews,
    review_recommendations,
    review_template,
)
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402


PRIVATE_DIR = ROOT / "data/training/c5/v2"
PUBLIC_DIR = ROOT / "eval/c5"
SOURCE = ROOT / "data/golden_traces_v2.jsonl"
A5_MANIFEST = ROOT / "data/training/a5/manifest.json"
P2_TASKS = ROOT / "eval/p2/hard_tasks.jsonl"
R_SOURCES = tuple(ROOT / value for value in (
    "eval/r4_v3_new_cases.json",
    "eval/r4_v4_selector_new_cases.json",
    "eval/r4_v5_target_free_new_cases.json",
    "eval/r4_v6_formal_60.jsonl",
    "eval/r4_v7_formal_60.jsonl",
    "eval/r4_v7_formal_expected.json",
    "eval/r4_v8_formal_expected.json",
))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ), encoding="utf-8")


def _load_families() -> list[dict[str, object]]:
    path = PRIVATE_DIR / "draft-families.jsonl"
    if not path.is_file():
        raise C5DatasetError("draft families do not exist; run draft first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _tokenizer():
    from transformers import AutoTokenizer
    if not TOKENIZER_SNAPSHOT.is_dir():
        raise C5DatasetError("pinned tokenizer is unavailable locally; no download attempted")
    return AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)


def draft() -> dict[str, object]:
    exclusions = build_historical_exclusions(
        root=ROOT,
        a5_manifest=A5_MANIFEST,
        p2_tasks=P2_TASKS,
        r_sources=R_SOURCES,
    )
    tools = load_public_mcp_tools()
    families = build_draft_families(SOURCE, exclusions, tools)
    audit = audit_draft(families, tools, tokenizer=_tokenizer(), require_reviews=False)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(PRIVATE_DIR / "draft-families.jsonl", families)
    _write_jsonl(PRIVATE_DIR / "review-template.jsonl", review_template(families))
    public_exclusions = PUBLIC_DIR / "historical-exclusions.json"
    _write_json(public_exclusions, exclusions)
    manifest = {
        "schema_version": "1.0",
        "status": "candidate_review_required",
        "draft_path": "data/training/c5/v2/draft-families.jsonl",
        "draft_sha256": __import__("hashlib").sha256(
            (PRIVATE_DIR / "draft-families.jsonl").read_bytes()
        ).hexdigest(),
        "review_template_sha256": __import__("hashlib").sha256(
            (PRIVATE_DIR / "review-template.jsonl").read_bytes()
        ).hexdigest(),
        "historical_exclusions_sha256": __import__("hashlib").sha256(
            public_exclusions.read_bytes()
        ).hexdigest(),
        "audit": audit_payload(audit),
        "accepted_family_count": 0,
        "training_authorized": False,
        "final_holdout_read": False,
        "final_holdout_rows_read": 0,
    }
    _write_json(PUBLIC_DIR / "dataset-v2-draft-manifest.json", manifest)
    return manifest


def audit_command(require_reviews: bool) -> dict[str, object]:
    families = _load_families()
    if require_reviews:
        reviews_path = PRIVATE_DIR / "reviews.jsonl"
        if not reviews_path.is_file():
            raise C5DatasetError("repository-owner review ledger is missing")
        families = apply_reviews(families, load_reviews(reviews_path))
    audit = audit_draft(
        families, load_public_mcp_tools(), tokenizer=_tokenizer(), require_reviews=require_reviews
    )
    payload = audit_payload(audit)
    if not audit.passed:
        raise C5DatasetError(f"dataset audit failed with {len(audit.findings)} findings")
    return payload


def review_packet() -> dict[str, object]:
    families = _load_families()
    audit = audit_draft(
        families, load_public_mcp_tools(), tokenizer=_tokenizer(), require_reviews=False
    )
    if not audit.passed:
        raise C5DatasetError(f"content QA failed with {len(audit.findings)} findings")
    recommendations = review_recommendations(families)
    recommendation_path = PRIVATE_DIR / "review-recommendations.jsonl"
    _write_jsonl(recommendation_path, recommendations)
    draft_path = PRIVATE_DIR / "draft-families.jsonl"
    payload = {
        "schema_version": "1.0",
        "status": "agent_quality_audit_passed_owner_approval_required",
        "dataset_id": "rhinocoder-c5-dataset-v2",
        "candidate_draft_sha256": __import__("hashlib").sha256(
            draft_path.read_bytes()
        ).hexdigest(),
        "agent_recommendation_sha256": __import__("hashlib").sha256(
            recommendation_path.read_bytes()
        ).hexdigest(),
        "audited_family_count": len(recommendations),
        "agent_recommended_approve_count": sum(
            row["agent_recommendation"] == "approve" for row in recommendations
        ),
        "owner_approved_family_count": 0,
        "required_reviewer_1": "repository_owner",
        "reviewer_2_required": False,
        "agent_self_approval_allowed": False,
        "quality_corrections": ["multistep_scene_coherence_v1"],
        "audit": audit_payload(audit),
        "training_authorized": False,
        "final_holdout_read": False,
        "final_holdout_rows_read": 0,
    }
    _write_json(PUBLIC_DIR / "dataset-v2-review-audit.json", payload)
    return payload


def split_plan() -> dict[str, object]:
    families = _load_families()
    audit = audit_draft(
        families, load_public_mcp_tools(), tokenizer=_tokenizer(), require_reviews=False
    )
    if not audit.passed:
        raise C5DatasetError(f"split planning failed audit with {len(audit.findings)} findings")
    assignments = assign_family_splits(families)
    private_path = PRIVATE_DIR / "provisional-split-assignments.json"
    _write_json(private_path, assignments)
    family_counts: Counter[str] = Counter()
    record_counts: Counter[str] = Counter()
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    invocation_tool_counts: dict[str, Counter[str]] = defaultdict(Counter)
    noncore_selector_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for family in families:
        split = assignments[str(family["family_id"])]
        family_counts[split] += 1
        record_counts[split] += len(family["records"])
        category_counts[split][str(family["category"])] += 1
        invocation_tools = {
            str(record.get("selected_tool"))
            for record in family["records"]
            if record.get("stage") == "invocation"
        }
        invocation_tool_counts[split].update(invocation_tools)
        if family["category"] == "selector_noncore":
            noncore_selector_counts[split][str(family["records"][0]["selected_tool"])] += 1
    payload = {
        "schema_version": "1.0",
        "status": "provisional_split_valid_owner_approval_required",
        "dataset_id": "rhinocoder-c5-dataset-v2",
        "candidate_draft_sha256": __import__("hashlib").sha256(
            (PRIVATE_DIR / "draft-families.jsonl").read_bytes()
        ).hexdigest(),
        "assignment_sha256": __import__("hashlib").sha256(
            private_path.read_bytes()
        ).hexdigest(),
        "split_seed": "rhinocoder-c5-family-v1",
        "family_counts": dict(sorted(family_counts.items())),
        "record_counts": dict(sorted(record_counts.items())),
        "category_counts": {
            split: dict(sorted(values.items()))
            for split, values in sorted(category_counts.items())
        },
        "invocation_tool_family_counts": {
            split: dict(sorted(values.items()))
            for split, values in sorted(invocation_tool_counts.items())
        },
        "noncore_selector_family_counts": {
            split: dict(sorted(values.items()))
            for split, values in sorted(noncore_selector_counts.items())
        },
        "formal_split_locked": False,
        "owner_approved_family_count": 0,
        "training_authorized": False,
        "final_holdout_read": False,
        "final_holdout_rows_read": 0,
    }
    _write_json(PUBLIC_DIR / "dataset-v2-split-plan.json", payload)
    return payload


def freeze() -> dict[str, object]:
    families = _load_families()
    reviews_path = PRIVATE_DIR / "reviews.jsonl"
    if not reviews_path.is_file():
        raise C5DatasetError("repository-owner review ledger is missing")
    accepted = apply_reviews(families, load_reviews(reviews_path))
    audit = audit_draft(
        accepted, load_public_mcp_tools(), tokenizer=_tokenizer(), require_reviews=True
    )
    if not audit.passed:
        raise C5DatasetError(f"reviewed dataset failed with {len(audit.findings)} findings")
    manifest = freeze_accepted_dataset(
        accepted, assign_family_splits(accepted), PRIVATE_DIR / "accepted"
    )
    public = {
        **manifest,
        "private_manifest_sha256": __import__("hashlib").sha256(
            (PRIVATE_DIR / "accepted/manifest.json").read_bytes()
        ).hexdigest(),
        "audit": audit_payload(audit),
    }
    _write_json(PUBLIC_DIR / "dataset-v2-freeze-manifest.json", public)
    return public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("draft", "audit", "review-packet", "plan-split", "freeze")
    )
    parser.add_argument("--require-reviews", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "draft":
            result = draft()
        elif args.command == "audit":
            result = audit_command(args.require_reviews)
        elif args.command == "review-packet":
            result = review_packet()
        elif args.command == "plan-split":
            result = split_plan()
        else:
            result = freeze()
    except (C5DatasetError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C5 dataset-v2 error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
