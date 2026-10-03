"""Read-only, metadata-only validator for owner-sealed C5-6 formal20.

This does not locate, open or decrypt the encrypted artifact or any task row;
validation does not grant an execution claim or owner approval.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Mapping

from training.c5_contract import CORE_INVOCATION_TOOLS
from training.c5_formal20_plan import STRATA, STUDY_ID


SHA = re.compile(r"[0-9a-f]{64}\Z")
TOP_KEYS = frozenset({"schema_version", "status", "study_id", "custodian_identity",
    "reviewer_2_required", "development_agent_plaintext_access", "family_count",
    "route_slots", "strata_counts", "core_tool_family_counts", "slot_seed",
    "slot_order_sha256", "family_merkle_root_sha256", "numeric_template_merkle_root_sha256",
    "encrypted_artifact", "exclusions", "custodian_attestation", "formal_model_calls",
    "formal_route_slots_consumed", "execution_ready"})
FORBIDDEN = frozenset({"task_text", "user_step", "instruction", "expected_operations",
    "fixture_recipe", "final_assertions", "initial_assertions", "plaintext",
    "secret", "password", "private_path", "key"})


class FormalCommitmentValidationError(ValueError):
    """Public metadata is incomplete, sensitive, or inconsistent."""


def _walk(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key).lower()
            if name in FORBIDDEN or name.endswith("_path"):
                raise FormalCommitmentValidationError("forbidden_public_field")
            _walk(child)
    elif isinstance(value, list):
        for child in value:
            _walk(child)


def _sha(value: Any):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise FormalCommitmentValidationError("invalid_public_digest")


def validate_public_commitment(value: Mapping[str, Any], *,
                               expected_development_freeze_sha256: str,
                               expected_historical_exclusions_sha256: str,
                               expected_original80_commitment_file_sha256: str,
                               expected_original80_merkle_root_sha256: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != TOP_KEYS:
        raise FormalCommitmentValidationError("public_commitment_fields")
    _walk(value)
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["status"] != "sealed_unconsumed_c5_rhino_formal20_not_execution_authority"
            or value["study_id"] != STUDY_ID or value["custodian_identity"] != "repository_owner"
            or value["reviewer_2_required"] is not False
            or value["development_agent_plaintext_access"] is not False
            or type(value["family_count"]) is not int or value["family_count"] != 20
            or type(value["route_slots"]) is not int or value["route_slots"] != 40
            or value["strata_counts"] != STRATA
            or value["core_tool_family_counts"] != {name: 1 for name in CORE_INVOCATION_TOOLS}
            or type(value["slot_seed"]) is not int or value["slot_seed"] != 20261003
            or value["formal_model_calls"] != 0 or value["formal_route_slots_consumed"] != 0
            or value["execution_ready"] is not False):
        raise FormalCommitmentValidationError("public_formal_boundary_differs")
    for key in ("slot_order_sha256", "family_merkle_root_sha256", "numeric_template_merkle_root_sha256"):
        _sha(value[key])
    encrypted = value["encrypted_artifact"]
    if (not isinstance(encrypted, Mapping) or set(encrypted) != {"sha256", "bytes", "format"}
            or type(encrypted["bytes"]) is not int or not 0 < encrypted["bytes"] <= 10 * 1024 * 1024
            or encrypted["format"] not in {"age-x25519", "aes-256-gcm"}):
        raise FormalCommitmentValidationError("encrypted_artifact_metadata")
    _sha(encrypted["sha256"])
    exclusions = value["exclusions"]
    if (not isinstance(exclusions, Mapping) or set(exclusions) != {
            "development_dataset_freeze_sha256", "historical_exclusions_sha256",
            "original80_public_commitment_file_sha256", "original80_family_merkle_root_sha256",
            "additional_exclusion_file_sha256",
            "automated_exact_numeric_or_092_near_duplicate_overlap_count",
            "original80_public_merkle_identity_verified_by_owner_preflight"}):
        raise FormalCommitmentValidationError("public_exclusion_binding_fields")
    bindings = (
        ("development_dataset_freeze_sha256", expected_development_freeze_sha256),
        ("historical_exclusions_sha256", expected_historical_exclusions_sha256),
        ("original80_public_commitment_file_sha256", expected_original80_commitment_file_sha256),
        ("original80_family_merkle_root_sha256", expected_original80_merkle_root_sha256),
    )
    if any(exclusions[key] != expected for key, expected in bindings):
        raise FormalCommitmentValidationError("public_exclusion_source_identity_differs")
    extra = exclusions["additional_exclusion_file_sha256"]
    if not isinstance(extra, list) or not 1 <= len(extra) <= 32 or len(set(extra)) != len(extra):
        raise FormalCommitmentValidationError("additional_exclusion_inventory_invalid")
    for item in extra: _sha(item)
    if (type(exclusions["automated_exact_numeric_or_092_near_duplicate_overlap_count"]) is not int
            or exclusions["automated_exact_numeric_or_092_near_duplicate_overlap_count"] != 0
            or exclusions["original80_public_merkle_identity_verified_by_owner_preflight"] is not True):
        raise FormalCommitmentValidationError("public_exclusion_result_incomplete")
    attestation = value["custodian_attestation"]
    if (not isinstance(attestation, Mapping) or set(attestation) != {"actor", "sealed_at_utc",
            "full_r_exclusion_inventory_reviewed", "semantic_near_duplicate_review_passed",
            "fixture_and_expected_geometry_reviewed", "encryption_roundtrip_verified",
            "keys_not_shared_with_development_agent"}
            or attestation["actor"] != "repository_owner"
            or not isinstance(attestation["sealed_at_utc"], str)
            or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z", attestation["sealed_at_utc"])
            or any(attestation[key] is not True for key in (
                "full_r_exclusion_inventory_reviewed", "semantic_near_duplicate_review_passed",
                "fixture_and_expected_geometry_reviewed", "encryption_roundtrip_verified",
                "keys_not_shared_with_development_agent"))):
        raise FormalCommitmentValidationError("owner_attestation_incomplete")
    try:
        datetime.fromisoformat(attestation["sealed_at_utc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise FormalCommitmentValidationError("owner_seal_time_invalid") from exc
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise FormalCommitmentValidationError("public_commitment_not_canonical") from exc
    return {"status": "public_formal20_commitment_validated_not_execution_authority",
            "public_commitment_sha256": hashlib.sha256(raw).hexdigest(),
            "family_count": 20, "route_slots": 40,
            "private_task_rows_read": 0, "encrypted_artifact_opened": False,
            "formal_model_calls": 0, "execution_ready": False}
