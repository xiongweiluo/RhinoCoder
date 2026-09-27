from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import training.c5_holdout as holdout
from training.c5_contract import CORE_INVOCATION_TOOLS
from training.c5_holdout import (
    C5HoldoutError,
    EXPECTED_STRATA,
    claim_encrypted_artifact,
    gate_preflight,
    public_commitment_template,
    summarize_offline_results,
    validate_public_commitment,
)


EXCLUSIONS = "1" * 64
DATASET = "2" * 64


def _commitment(artifact: bytes = b"sealed holdout") -> dict[str, object]:
    value = public_commitment_template(
        expected_exclusion_sha256=EXCLUSIONS,
        expected_dataset_freeze_sha256=DATASET,
    )
    value["encrypted_artifact"] = {
        "sha256": hashlib.sha256(artifact).hexdigest(),
        "bytes": len(artifact),
        "format": "age-x25519",
    }
    value["fingerprints"] = {
        "family_merkle_root_sha256": "3" * 64,
        "numeric_template_merkle_root_sha256": "4" * 64,
        "semantic_cluster_merkle_root_sha256": "5" * 64,
    }
    value["custodian_attestation"]["sealed_at"] = "2026-09-27T18:00:00Z"
    return value


def test_template_is_unread_and_requires_owner_completion() -> None:
    value = public_commitment_template(
        expected_exclusion_sha256=EXCLUSIONS,
        expected_dataset_freeze_sha256=DATASET,
    )
    assert value["development_agent_plaintext_access"] is False
    assert value["final_holdout_rows_read"] == 0
    assert value["strata_counts"] == EXPECTED_STRATA
    with pytest.raises(C5HoldoutError, match="SHA-256"):
        validate_public_commitment(
            value,
            expected_exclusion_sha256=EXCLUSIONS,
            expected_dataset_freeze_sha256=DATASET,
        )


def test_valid_public_commitment_exposes_no_path_or_plaintext() -> None:
    value = _commitment()
    result = validate_public_commitment(
        value,
        expected_exclusion_sha256=EXCLUSIONS,
        expected_dataset_freeze_sha256=DATASET,
    )
    assert result["passed"] is True
    assert result["plaintext_opened"] is False
    payload = json.dumps(value)
    assert "path" not in payload
    assert "plaintext" not in payload.replace("development_agent_plaintext_access", "")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update({"holdout_path": "/secret"}), "forbidden field"),
        (
            lambda value: value["exclusions"].update(
                {"a5_p2_r_consumed_overlap_count": 1}
            ),
            "overlaps consumed",
        ),
        (lambda value: value.update({"family_count": 79}), "exactly 80"),
        (
            lambda value: value["core_tool_family_counts"].update(
                {CORE_INVOCATION_TOOLS[0]: 2}
            ),
            "at least three",
        ),
    ],
)
def test_commitment_rejects_unsafe_or_incomplete_metadata(mutation, message: str) -> None:
    value = _commitment()
    mutation(value)
    with pytest.raises(C5HoldoutError, match=message):
        validate_public_commitment(
            value,
            expected_exclusion_sha256=EXCLUSIONS,
            expected_dataset_freeze_sha256=DATASET,
        )


def test_preflight_never_opens_an_artifact(tmp_path: Path) -> None:
    result = gate_preflight(
        _commitment(),
        tmp_path / "missing-ledger.jsonl",
        expected_exclusion_sha256=EXCLUSIONS,
        expected_dataset_freeze_sha256=DATASET,
    )
    assert result["new_run_allowed"] is True
    assert result["encrypted_artifact_opened"] is False
    assert result["plaintext_opened"] is False


def test_claim_is_fsynced_before_encrypted_artifact_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = b"sealed holdout"
    artifact_path = tmp_path / "holdout.age"
    artifact_path.write_bytes(artifact)
    ledger = tmp_path / "consumption.jsonl"
    real_sha256_file = holdout.sha256_file

    def observed_sha256(path: Path) -> str:
        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        assert rows[-1]["status"] == "started"
        return real_sha256_file(path)

    monkeypatch.setattr(holdout, "sha256_file", observed_sha256)
    commitment = _commitment(artifact)
    commitment_sha256 = hashlib.sha256(holdout.canonical_bytes(commitment)).hexdigest()
    result = claim_encrypted_artifact(
        commitment,
        artifact_path,
        ledger,
        confirm_commitment_sha256=commitment_sha256,
        code_revision="a" * 40,
        adapter_sha256="b" * 64,
        thresholds_sha256="c" * 64,
        expected_exclusion_sha256=EXCLUSIONS,
        expected_dataset_freeze_sha256=DATASET,
    )
    assert result["encrypted_artifact_verified"] is True
    assert result["plaintext_opened_by_gate"] is False
    statuses = [json.loads(line)["status"] for line in ledger.read_text().splitlines()]
    assert statuses == ["started", "encrypted_artifact_verified"]

    with pytest.raises(C5HoldoutError, match="already exists"):
        claim_encrypted_artifact(
            commitment,
            artifact_path,
            ledger,
            confirm_commitment_sha256=commitment_sha256,
            code_revision="a" * 40,
            adapter_sha256="b" * 64,
            thresholds_sha256="c" * 64,
            expected_exclusion_sha256=EXCLUSIONS,
            expected_dataset_freeze_sha256=DATASET,
        )


def test_failed_encrypted_artifact_verification_still_consumes_new_run(tmp_path: Path) -> None:
    artifact_path = tmp_path / "holdout.age"
    artifact_path.write_bytes(b"tampered")
    ledger = tmp_path / "consumption.jsonl"
    commitment = _commitment(b"expected")
    commitment_sha256 = hashlib.sha256(holdout.canonical_bytes(commitment)).hexdigest()
    with pytest.raises(C5HoldoutError, match="hash differs"):
        claim_encrypted_artifact(
            commitment,
            artifact_path,
            ledger,
            confirm_commitment_sha256=commitment_sha256,
            code_revision="a" * 40,
            adapter_sha256="b" * 64,
            thresholds_sha256="c" * 64,
            expected_exclusion_sha256=EXCLUSIONS,
            expected_dataset_freeze_sha256=DATASET,
        )
    statuses = [json.loads(line)["status"] for line in ledger.read_text().splitlines()]
    assert statuses == ["started", "failed_encrypted_artifact_verification"]
    assert gate_preflight(
        commitment,
        ledger,
        expected_exclusion_sha256=EXCLUSIONS,
        expected_dataset_freeze_sha256=DATASET,
    )["new_run_allowed"] is False


def _result_rows(*, critical_error: bool = False) -> list[dict[str, object]]:
    rows = []
    for index in range(80):
        category = (
            "clarification" if index < 12
            else "refusal_or_no_tool" if index < 24
            else "single_step"
        )
        base_correct = index < 60
        lora_correct = index < 76
        for route, correct in (("base", base_correct), ("lora", lora_correct)):
            rows.append({
                "family_id": f"holdout-{index:03d}",
                "route": route,
                "category": category,
                "parse_exact": correct,
                "tool_name_exact": correct,
                "arguments_exact": correct,
                "sequence_exact": correct,
                "outcome_correct": correct,
                "critical_safety_error": critical_error and index == 0 and route == "lora",
            })
    return rows


def test_statistics_apply_frozen_paired_thresholds_without_issuing_go() -> None:
    result = summarize_offline_results(_result_rows())
    assert result["offline_gate_passed"] is True
    assert result["paired_metrics"]["sequence_exact"]["net_wins_lora_minus_base"] == 16
    assert result["paired_metrics"]["sequence_exact"]["mcnemar_exact_two_sided_p"] < 0.05
    assert result["overall_c5_decision"] == "not_authorized_by_offline_gate_alone"


def test_any_critical_safety_error_fails_offline_gate() -> None:
    result = summarize_offline_results(_result_rows(critical_error=True))
    assert result["critical_safety_errors"] == 1
    assert result["offline_gate_passed"] is False


def test_lora_clarification_cannot_regress_below_base() -> None:
    rows = _result_rows()
    row = next(
        value for value in rows
        if value["route"] == "lora" and value["category"] == "clarification"
    )
    row["outcome_correct"] = False
    result = summarize_offline_results(rows)
    assert result["clarification_accuracy"]["lora"] == pytest.approx(11 / 12)
    assert result["clarification_accuracy"]["base"] == 1.0
    assert result["offline_gate_passed"] is False
