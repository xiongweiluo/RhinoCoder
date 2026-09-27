from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.c5_dataset import (
    C5DatasetError,
    EXPECTED_NEW_FAMILIES,
    EXPECTED_TOTAL_FAMILIES,
    FAMILY_TARGETS,
    OWNER_REVIEWER_ID,
    apply_reviews,
    assign_family_splits,
    audit_draft,
    review_template,
    synthetic_core_families,
    synthetic_multistep_families,
    synthetic_noncore_families,
    synthetic_null_families,
)
from training.tool_schema_inventory import load_public_mcp_tools


def _generated():
    return [
        *synthetic_core_families(),
        *synthetic_noncore_families(),
        *synthetic_null_families(),
        *synthetic_multistep_families(),
    ]


def test_generated_family_plan_has_exact_count_and_valid_contract_shapes() -> None:
    families = _generated()
    assert len(families) == EXPECTED_NEW_FAMILIES
    assert len({family["family_id"] for family in families}) == EXPECTED_NEW_FAMILIES
    audit = audit_draft(families, load_public_mcp_tools())
    assert audit.family_count == EXPECTED_NEW_FAMILIES
    assert audit.record_count > EXPECTED_NEW_FAMILIES
    assert all(value >= 20 for value in audit.invocation_tool_families.values())
    assert not any("unknown dataset stage" in finding for finding in audit.findings)


def test_reviews_require_repository_owner_as_only_reviewer() -> None:
    family = synthetic_null_families()[0]
    family_id = family["family_id"]
    family_sha256 = __import__("hashlib").sha256(json.dumps(
        family, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    with pytest.raises(C5DatasetError):
        apply_reviews([family], {family_id: {
            "family_id": family_id,
            "family_sha256": family_sha256,
            "decision": "approve",
            "reviewer_1": "independent-domain-reviewer",
        }})
    accepted = apply_reviews([family], {family_id: {
        "family_id": family_id,
        "family_sha256": family_sha256,
        "decision": "approve",
        "reviewer_1": OWNER_REVIEWER_ID,
        "notes": "intent and abstention checked",
    }})
    assert accepted[0]["review"]["status"] == "approved"
    assert accepted[0]["review"]["reviewer_1"] == OWNER_REVIEWER_ID
    assert "reviewer_2" not in accepted[0]["review"]


def test_review_template_prefills_owner_without_reviewer_2() -> None:
    row = review_template([synthetic_null_families()[0]])[0]
    assert row["reviewer_1"] == OWNER_REVIEWER_ID
    assert row["decision"] == "pending"
    assert "reviewer_2" not in row


def test_review_rejects_reviewer_2_under_owner_only_policy() -> None:
    family = synthetic_null_families()[0]
    family_id = family["family_id"]
    family_sha256 = __import__("hashlib").sha256(json.dumps(
        family, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    with pytest.raises(C5DatasetError, match="must not include reviewer_2"):
        apply_reviews([family], {family_id: {
            "family_id": family_id,
            "family_sha256": family_sha256,
            "decision": "approve",
            "reviewer_1": OWNER_REVIEWER_ID,
            "reviewer_2": "another-reviewer",
        }})


def test_review_cannot_be_reused_after_family_changes() -> None:
    family = synthetic_null_families()[0]
    family_id = family["family_id"]
    stale = __import__("hashlib").sha256(json.dumps(
        family, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    family["records"][0]["user_step"] += " 已修改"
    with pytest.raises(C5DatasetError, match="not bound"):
        apply_reviews([family], {family_id: {
            "family_id": family_id,
            "family_sha256": stale,
            "decision": "approve",
            "reviewer_1": OWNER_REVIEWER_ID,
        }})


def test_family_split_is_exact_and_deterministic() -> None:
    base = synthetic_null_families()[0]
    families = []
    for index in range(EXPECTED_TOTAL_FAMILIES):
        clone = json.loads(json.dumps(base))
        clone["family_id"] = f"family-{index:03d}"
        clone["scenario_key"] = f"scenario-{index:03d}"
        clone["records"][0]["record_id"] = f"record-{index:03d}"
        clone["records"][0]["user_step"] = f"需要澄清的独立合成任务 {index}"
        families.append(clone)
    first = assign_family_splits(families)
    second = assign_family_splits(families)
    assert first == second
    counts = {split: list(first.values()).count(split) for split in FAMILY_TARGETS}
    assert counts == FAMILY_TARGETS
