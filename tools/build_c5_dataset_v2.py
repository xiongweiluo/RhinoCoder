#!/usr/bin/env python3
"""Build and gate the contract-aligned C5 dataset-v2 development pool."""

from __future__ import annotations

import argparse
import json
import sys
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
            raise C5DatasetError("two-person review ledger is missing")
        families = apply_reviews(families, load_reviews(reviews_path))
    audit = audit_draft(
        families, load_public_mcp_tools(), tokenizer=_tokenizer(), require_reviews=require_reviews
    )
    payload = audit_payload(audit)
    if not audit.passed:
        raise C5DatasetError(f"dataset audit failed with {len(audit.findings)} findings")
    return payload


def freeze() -> dict[str, object]:
    families = _load_families()
    reviews_path = PRIVATE_DIR / "reviews.jsonl"
    if not reviews_path.is_file():
        raise C5DatasetError("two-person review ledger is missing")
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
    parser.add_argument("command", choices=("draft", "audit", "freeze"))
    parser.add_argument("--require-reviews", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "draft":
            result = draft()
        elif args.command == "audit":
            result = audit_command(args.require_reviews)
        else:
            result = freeze()
    except (C5DatasetError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C5 dataset-v2 error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
