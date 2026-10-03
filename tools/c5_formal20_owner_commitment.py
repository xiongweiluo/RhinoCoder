#!/usr/bin/env python3
"""Owner-only C5-6 public commitment builder; never a run/approval API.

The owner separately encrypts and round-trip verifies the new private cases.
This tool rechecks the frozen exclusions and writes only path-free metadata.
It cannot prove the completeness of the R inventory or impersonate the owner
attestation. Development agents must not run it on private files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.training_views import numeric_template_signature
from plugin.rhino_listener.c5_research_channel import private_directory
from training.c5_contract import CORE_INVOCATION_TOOLS
from training.c5_formal20_plan import (
    STRATA, STUDY_ID, family_merkle_root, slot_order, slot_order_sha256,
    validate_families,
)
from tools.c5_rhino_formal20_owner_exclusion import (
    ExclusionPreflightError, _json, _require_owner_private_path, _worktrees,
    preflight_paths,
)
from training.c5_holdout import sha256_file


SHA = re.compile(r"[0-9a-f]{64}\Z")
ATTESTATION_KEYS = frozenset({"actor", "full_r_exclusion_inventory_reviewed",
    "semantic_near_duplicate_review_passed", "fixture_and_expected_geometry_reviewed",
    "encryption_roundtrip_verified", "keys_not_shared_with_development_agent", "sealed_at_utc"})
FORBIDDEN_PUBLIC_KEYS = frozenset({"task_text", "user_step", "instruction", "expected_operations",
    "expected_arguments", "fixture_recipe", "final_assertions", "initial_assertions",
    "plaintext", "password", "secret", "key", "private_path", "output_path"})


class FormalCommitmentError(ValueError):
    """Cannot produce a safe, owner-attested public formal commitment."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _merkle_strings(values: list[str]) -> str:
    nodes = sorted(hashlib.sha256(value.encode()).digest() for value in values)
    if not nodes:
        raise FormalCommitmentError("empty_public_fingerprint_input")
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[index] + nodes[index + 1]).digest()
                 for index in range(0, len(nodes), 2)]
    return nodes[0].hex()


def _check_public(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_PUBLIC_KEYS or str(key).lower().endswith("_path"):
                raise FormalCommitmentError("forbidden_public_field")
            _check_public(child)
    elif isinstance(value, list):
        for child in value:
            _check_public(child)


def build_public_commitment(cases: list[dict], *, bindings: Mapping[str, Any],
                            encrypted: Mapping[str, Any], attestation: Mapping[str, Any],
                            preflight_report: Mapping[str, Any],
                            slot_seed: int = 20261003) -> dict[str, Any]:
    cases = validate_families(cases)
    if (not isinstance(preflight_report, Mapping)
            or preflight_report.get("status") != "owner_private_automated_exclusion_preflight_only_not_formal_freeze"
            or preflight_report.get("candidate_count") != 20
            or preflight_report.get("development_count") != 440
            or preflight_report.get("original80_count") != 80
            or preflight_report.get("original80_public_merkle_identity_verified") is not True
            or preflight_report.get("exact_numeric_or_092_near_duplicate_overlap_count") != 0):
        raise FormalCommitmentError("complete_owner_automated_preflight_missing")
    if set(attestation) != ATTESTATION_KEYS or attestation.get("actor") != "repository_owner":
        raise FormalCommitmentError("direct_owner_attestation_missing")
    flags = ATTESTATION_KEYS - {"actor", "sealed_at_utc"}
    if any(attestation.get(key) is not True for key in flags):
        raise FormalCommitmentError("owner_review_or_encryption_attestation_incomplete")
    sealed = attestation.get("sealed_at_utc")
    if not isinstance(sealed, str) or not sealed.endswith("Z"):
        raise FormalCommitmentError("utc_owner_seal_missing")
    try:
        datetime.fromisoformat(sealed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FormalCommitmentError("invalid_owner_seal_time") from exc
    if (set(encrypted) != {"sha256", "bytes", "format"} or not isinstance(encrypted.get("sha256"), str)
            or not SHA.fullmatch(encrypted["sha256"]) or type(encrypted.get("bytes")) is not int
            or not 0 < encrypted["bytes"] <= 10 * 1024 * 1024
            or encrypted.get("format") not in {"age-x25519", "aes-256-gcm"}):
        raise FormalCommitmentError("encrypted_artifact_metadata_invalid")
    expected_bindings = {"development_dataset_freeze_sha256", "historical_exclusions_sha256",
        "original80_public_commitment_file_sha256", "original80_family_merkle_root_sha256",
        "additional_exclusion_file_sha256"}
    if set(bindings) != expected_bindings or not isinstance(bindings["additional_exclusion_file_sha256"], list) or not bindings["additional_exclusion_file_sha256"]:
        raise FormalCommitmentError("exclusion_binding_incomplete")
    for key, value in bindings.items():
        values = value if isinstance(value, list) else [value]
        if any(not isinstance(item, str) or not SHA.fullmatch(item) for item in values):
            raise FormalCommitmentError("exclusion_binding_digest_invalid")
    order = slot_order(cases, seed=slot_seed)
    commitment = {
        "schema_version": 1,
        "status": "sealed_unconsumed_c5_rhino_formal20_not_execution_authority",
        "study_id": STUDY_ID,
        "custodian_identity": "repository_owner", "reviewer_2_required": False,
        "development_agent_plaintext_access": False,
        "family_count": 20, "route_slots": 40,
        "strata_counts": dict(sorted(Counter(case["stratum"] for case in cases).items())),
        "core_tool_family_counts": {name: 1 for name in CORE_INVOCATION_TOOLS},
        "slot_seed": slot_seed, "slot_order_sha256": slot_order_sha256(order),
        "family_merkle_root_sha256": family_merkle_root(cases),
        "numeric_template_merkle_root_sha256": _merkle_strings([
            numeric_template_signature(case["task_text"]) for case in cases]),
        "encrypted_artifact": dict(encrypted),
        "exclusions": {**dict(bindings), "automated_exact_numeric_or_092_near_duplicate_overlap_count": 0,
                       "original80_public_merkle_identity_verified_by_owner_preflight": True},
        "custodian_attestation": dict(attestation),
        "formal_model_calls": 0, "formal_route_slots_consumed": 0,
        "execution_ready": False,
    }
    if commitment["strata_counts"] != STRATA:
        raise FormalCommitmentError("strata_commitment_differs")
    _check_public(commitment)
    return json.loads(_canonical(commitment))


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    root = private_directory(path.parent)
    try:
        name = path.name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
            raise FormalCommitmentError("public_output_filename_invalid")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(_canonical(value) + b"\n")
                stream.flush(); os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(root)
    finally:
        os.close(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--original80", type=Path, required=True)
    parser.add_argument("--development", type=Path, action="append", required=True)
    parser.add_argument("--extra-exclusion-jsonl", type=Path, action="append", required=True)
    parser.add_argument("--encrypted-artifact", type=Path, required=True)
    parser.add_argument("--encrypted-format", choices=("age-x25519", "aes-256-gcm"), required=True)
    parser.add_argument("--owner-attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        worktrees = _worktrees()
        for path in (args.encrypted_artifact, args.owner_attestation, args.output):
            _require_owner_private_path(path, worktrees)
        if len({p.resolve() for p in (args.candidate, args.original80, args.encrypted_artifact,
                                      args.owner_attestation, args.output)}) != 5:
            raise FormalCommitmentError("owner_private_inputs_and_output_must_differ")
        cases, report, bindings = preflight_paths(args.candidate, args.original80,
                                                   args.development, args.extra_exclusion_jsonl)
        if report["exact_numeric_or_092_near_duplicate_overlap_count"] != 0:
            raise FormalCommitmentError("automated_exclusion_not_clean")
        encrypted_path = args.encrypted_artifact
        encrypted = {"sha256": sha256_file(encrypted_path), "bytes": encrypted_path.stat().st_size,
                     "format": args.encrypted_format}
        commitment = build_public_commitment(cases, bindings=bindings, encrypted=encrypted,
                                              attestation=_json(args.owner_attestation), preflight_report=report)
        _write_exclusive(args.output, commitment)
    except (FormalCommitmentError, ExclusionPreflightError, KeyError, TypeError, OSError, ValueError) as exc:
        # Never echo owner paths, plaintext, keys, task IDs, or match excerpts.
        category = str(exc) if isinstance(exc, (FormalCommitmentError, ExclusionPreflightError)) else "invalid_private_input_or_identity"
        print(json.dumps({"status": "owner_public_commitment_not_created", "category": category}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "owner_public_commitment_created_not_execution_authority",
                      "family_count": 20, "route_slots": 40,
                      "public_commitment_sha256": hashlib.sha256(_canonical(commitment)).hexdigest(),
                      "formal_model_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
