from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.c5_dataset import (
    C5DatasetError,
    CORE_SYNTHETIC_FAMILY_TARGETS,
    EXPECTED_NEW_FAMILIES,
    EXPECTED_TOTAL_FAMILIES,
    FAMILY_TARGETS,
    OWNER_REVIEWER_ID,
    apply_reviews,
    assign_family_splits,
    audit_draft,
    review_recommendations,
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
    assert all(
        audit.invocation_tool_families[tool] >= target
        for tool, target in CORE_SYNTHETIC_FAMILY_TARGETS.items()
    )
    assert not any("unknown dataset stage" in finding for finding in audit.findings)


def test_multistep_families_keep_one_scene_context_across_all_steps() -> None:
    for family in synthetic_multistep_families():
        context = family["scenario_key"].split(":", 3)[2]
        assert len(family["records"]) == 6
        assert all(context in record["user_step"] for record in family["records"])
        for record in family["records"]:
            for value in (record.get("arguments") or {}).values():
                if isinstance(value, str) and value.endswith(("-A", "-B")):
                    assert value.startswith(context)
                if isinstance(value, list):
                    assert all(
                        not isinstance(item, str)
                        or not item.endswith(("-A", "-B"))
                        or item.startswith(context)
                        for item in value
                    )


def test_content_audit_rejects_selector_invocation_drift() -> None:
    families = _generated()
    target = next(family for family in families if family["category"] == "core_invocation")
    invocation = next(record for record in target["records"] if record["stage"] == "invocation")
    invocation["user_step"] += " 漂移"
    audit = audit_draft(families, load_public_mcp_tools())
    assert any("selector/invocation pair" in finding for finding in audit.findings)


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


def test_agent_recommendations_cannot_be_used_as_owner_approval() -> None:
    family = synthetic_null_families()[0]
    recommendation = review_recommendations([family])[0]
    assert recommendation["agent_recommendation"] == "approve"
    assert recommendation["owner_decision"] == "pending"
    assert "decision" not in recommendation
    with pytest.raises(C5DatasetError, match="not approved"):
        apply_reviews([family], {family["family_id"]: recommendation})


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
    families = _generated()
    core_by_tool = {}
    for family in families:
        for record in family["records"]:
            if record["stage"] == "invocation":
                core_by_tool.setdefault(record["selected_tool"], family)
    source_tools = ["create_box"] * 63 + ["create_cylinder"] * 20 + ["create_sphere"] * 20
    for index, tool in enumerate(source_tools):
        clone = json.loads(json.dumps(core_by_tool[tool]))
        clone["family_id"] = f"source-family-{index:03d}"
        clone["scenario_key"] = f"source:scenario-{index:03d}"
        clone["category"] = "historical_source"
        clone["source_kind"] = "golden_trace_after_historical_exclusion"
        clone["source_task_hashes"] = [f"source-hash-{index:03d}"]
        clone["records"] = [record for record in clone["records"] if record["variant"] == "main"]
        for ordinal, record in enumerate(clone["records"]):
            record["record_id"] = f"source-record-{index:03d}-{ordinal}"
        families.append(clone)
    assert len(families) == EXPECTED_TOTAL_FAMILIES
    first = assign_family_splits(families)
    second = assign_family_splits(families)
    assert first == second
    counts = {split: list(first.values()).count(split) for split in FAMILY_TARGETS}
    assert counts == FAMILY_TARGETS
    tool_counts = {split: {} for split in FAMILY_TARGETS}
    for family in families:
        split = first[family["family_id"]]
        tools = {
            record["selected_tool"]
            for record in family["records"]
            if record["stage"] == "invocation"
        }
        for tool in tools:
            tool_counts[split][tool] = tool_counts[split].get(tool, 0) + 1
    assert all(value >= 20 for value in tool_counts["train"].values())
    assert all(
        tool_counts[split][tool] >= 4
        for split in ("validation", "development")
        for tool in CORE_SYNTHETIC_FAMILY_TARGETS
    )
