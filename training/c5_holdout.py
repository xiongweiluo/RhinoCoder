"""C5 final-holdout commitment, single-use gate, and paired statistics.

Development agents only handle the public commitment and aggregate evaluation
rows.  Plaintext holdout content remains with the repository-owner custodian
until a one-time consumption claim has been durably appended and fsynced.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import random
import re
import secrets
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from data_pipeline.training_views import numeric_template_signature
from training.c5_contract import CONTRACT_ID, CORE_INVOCATION_TOOLS, EXPERIMENT_ID
from training.c5_dataset import DATASET_ID, audit_draft


COMMITMENT_SCHEMA_VERSION = "1.0"
GATE_SCHEMA_VERSION = "1.0"
CUSTODIAN_ID = "repository_owner"
EXPECTED_FAMILIES = 80
EXPECTED_STRATA = {
    "single_step": 40,
    "clarification": 12,
    "refusal_or_no_tool": 12,
    "multistep": 8,
    "error_recovery": 8,
}
METRIC_FIELDS = (
    "parse_exact",
    "tool_name_exact",
    "arguments_exact",
    "sequence_exact",
)
BOOTSTRAP_SEED = 20260927
BOOTSTRAP_RESAMPLES = 10_000
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_PUBLIC_KEYS = {
    "artifact_path",
    "content_path",
    "holdout_path",
    "prompt",
    "instruction",
    "arguments",
    "expected_output",
    "task_text",
    "plaintext",
    "decryption_key",
    "password",
    "secret",
}


class C5HoldoutError(RuntimeError):
    """A C5 holdout custody or one-time-consumption invariant failed."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_sha256(value: Any, field: str) -> str:
    text = str(value or "")
    if not _SHA256.fullmatch(text):
        raise C5HoldoutError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _walk_public(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key).lower()
            if name in _FORBIDDEN_PUBLIC_KEYS or name.endswith("_path"):
                raise C5HoldoutError(f"public commitment exposes forbidden field {path}.{key}")
            _walk_public(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_public(child, f"{path}[{index}]")


def validate_public_commitment(
    commitment: Mapping[str, Any],
    *,
    expected_exclusion_sha256: str,
    expected_dataset_freeze_sha256: str,
) -> dict[str, Any]:
    """Validate only public metadata; never locate or open holdout content."""

    _walk_public(commitment)
    expected_identity = {
        "schema_version": COMMITMENT_SCHEMA_VERSION,
        "status": "sealed_unread_final_holdout",
        "dataset_id": DATASET_ID,
        "experiment_id": EXPERIMENT_ID,
        "contract_id": CONTRACT_ID,
        "custodian_identity": CUSTODIAN_ID,
    }
    for field, expected in expected_identity.items():
        if commitment.get(field) != expected:
            raise C5HoldoutError(f"holdout commitment has invalid {field}")
    if commitment.get("reviewer_2_required") is not False:
        raise C5HoldoutError("owner-only holdout policy requires reviewer_2_required=false")
    if commitment.get("development_agent_plaintext_access") is not False:
        raise C5HoldoutError("development agent plaintext access must remain false")
    if commitment.get("final_holdout_rows_read") != 0:
        raise C5HoldoutError("final holdout rows must remain unread at commitment time")
    if commitment.get("family_count") != EXPECTED_FAMILIES:
        raise C5HoldoutError("final holdout must contain exactly 80 families")
    if commitment.get("strata_counts") != EXPECTED_STRATA:
        raise C5HoldoutError("final holdout strata do not match the preregistration")

    artifact = commitment.get("encrypted_artifact")
    if not isinstance(artifact, Mapping):
        raise C5HoldoutError("encrypted_artifact metadata is missing")
    _require_sha256(artifact.get("sha256"), "encrypted_artifact.sha256")
    if int(artifact.get("bytes") or 0) <= 0:
        raise C5HoldoutError("encrypted_artifact.bytes must be positive")
    if artifact.get("format") not in {"age-x25519", "aes-256-gcm"}:
        raise C5HoldoutError("encrypted artifact format is not approved")

    fingerprints = commitment.get("fingerprints")
    if not isinstance(fingerprints, Mapping):
        raise C5HoldoutError("holdout fingerprint commitments are missing")
    for field in (
        "family_merkle_root_sha256",
        "numeric_template_merkle_root_sha256",
        "semantic_cluster_merkle_root_sha256",
    ):
        _require_sha256(fingerprints.get(field), f"fingerprints.{field}")

    exclusions = commitment.get("exclusions")
    if not isinstance(exclusions, Mapping):
        raise C5HoldoutError("holdout exclusion attestations are missing")
    if exclusions.get("historical_exclusions_sha256") != expected_exclusion_sha256:
        raise C5HoldoutError("historical exclusion manifest is not the frozen version")
    if exclusions.get("development_dataset_freeze_sha256") != expected_dataset_freeze_sha256:
        raise C5HoldoutError("development dataset freeze is not the frozen version")
    if exclusions.get("a5_p2_r_consumed_overlap_count") != 0:
        raise C5HoldoutError("holdout overlaps consumed A5/P2/R material")
    if exclusions.get("development_family_overlap_count") != 0:
        raise C5HoldoutError("holdout overlaps the C5 development families")

    coverage = commitment.get("core_tool_family_counts")
    if not isinstance(coverage, Mapping) or set(coverage) != set(CORE_INVOCATION_TOOLS):
        raise C5HoldoutError("core tool coverage must name exactly the 12 frozen tools")
    if any(int(coverage[name]) < 3 for name in CORE_INVOCATION_TOOLS):
        raise C5HoldoutError("every core tool needs at least three holdout families")

    attestation = commitment.get("custodian_attestation")
    if not isinstance(attestation, Mapping):
        raise C5HoldoutError("custodian attestation is missing")
    required_true = (
        "content_is_new_and_unseen",
        "contract_rendering_verified",
        "strict_targets_verified",
        "group_split_and_near_duplicate_checks_passed",
        "encrypted_before_commitment",
        "key_not_shared_with_development_agent",
    )
    if any(attestation.get(field) is not True for field in required_true):
        raise C5HoldoutError("custodian attestation is incomplete")
    if not str(attestation.get("sealed_at") or "").endswith("Z"):
        raise C5HoldoutError("custodian attestation requires a UTC sealed_at timestamp")

    return {
        "passed": True,
        "commitment_sha256": hashlib.sha256(canonical_bytes(commitment)).hexdigest(),
        "family_count": EXPECTED_FAMILIES,
        "final_holdout_rows_read": 0,
        "plaintext_opened": False,
    }


def public_commitment_template(
    *, expected_exclusion_sha256: str, expected_dataset_freeze_sha256: str
) -> dict[str, Any]:
    """Return an intentionally invalid placeholder for owner-side completion."""

    placeholder = "<64 lowercase hex characters supplied by repository_owner>"
    return {
        "schema_version": COMMITMENT_SCHEMA_VERSION,
        "status": "sealed_unread_final_holdout",
        "dataset_id": DATASET_ID,
        "experiment_id": EXPERIMENT_ID,
        "contract_id": CONTRACT_ID,
        "custodian_identity": CUSTODIAN_ID,
        "reviewer_2_required": False,
        "development_agent_plaintext_access": False,
        "final_holdout_rows_read": 0,
        "family_count": EXPECTED_FAMILIES,
        "strata_counts": dict(EXPECTED_STRATA),
        "core_tool_family_counts": {name: 3 for name in CORE_INVOCATION_TOOLS},
        "encrypted_artifact": {
            "sha256": placeholder,
            "bytes": 0,
            "format": "age-x25519",
        },
        "fingerprints": {
            "family_merkle_root_sha256": placeholder,
            "numeric_template_merkle_root_sha256": placeholder,
            "semantic_cluster_merkle_root_sha256": placeholder,
        },
        "exclusions": {
            "historical_exclusions_sha256": expected_exclusion_sha256,
            "development_dataset_freeze_sha256": expected_dataset_freeze_sha256,
            "a5_p2_r_consumed_overlap_count": 0,
            "development_family_overlap_count": 0,
        },
        "custodian_attestation": {
            "content_is_new_and_unseen": True,
            "contract_rendering_verified": True,
            "strict_targets_verified": True,
            "group_split_and_near_duplicate_checks_passed": True,
            "encrypted_before_commitment": True,
            "key_not_shared_with_development_agent": True,
            "sealed_at": "<UTC timestamp ending in Z>",
        },
    }


def _merkle_root(values: Sequence[bytes]) -> str:
    nodes = sorted(hashlib.sha256(value).digest() for value in values)
    if not nodes:
        raise C5HoldoutError("cannot commit an empty fingerprint set")
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [
            hashlib.sha256(nodes[index] + nodes[index + 1]).digest()
            for index in range(0, len(nodes), 2)
        ]
    return nodes[0].hex()


def _primary_text(family: Mapping[str, Any]) -> str:
    records = family.get("records") or []
    return str(records[0].get("user_step") or "") if records else ""


def build_public_commitment(
    families: Sequence[Mapping[str, Any]],
    development_families: Sequence[Mapping[str, Any]],
    *,
    tools: Sequence[Mapping[str, Any]],
    tokenizer: Any,
    encrypted_artifact_path: Path,
    encrypted_format: str,
    historical_exclusions: Mapping[str, Any],
    historical_exclusions_sha256: str,
    development_dataset_freeze_sha256: str,
    sealed_at: str,
) -> dict[str, Any]:
    """Owner-side builder; callers must keep plaintext outside agent access."""

    audit = audit_draft(
        families,
        tools,
        tokenizer=tokenizer,
        require_reviews=False,
        expected_family_count=EXPECTED_FAMILIES,
        minimum_core_tool_families=3,
        source_policy="repository_owner_holdout",
    )
    if not audit.passed:
        raise C5HoldoutError(
            f"holdout contract/content audit failed with {len(audit.findings)} findings: "
            + "; ".join(audit.findings[:5])
        )

    strata = {
        str(family.get("holdout_stratum") or ""): 0 for family in families
    }
    for family in families:
        stratum = str(family.get("holdout_stratum") or "")
        if stratum not in EXPECTED_STRATA:
            raise C5HoldoutError(f"family {family.get('family_id')} has invalid holdout stratum")
        strata[stratum] += 1
        expected_categories = {
            "single_step": {"core_invocation"},
            "clarification": {"clarification"},
            "refusal_or_no_tool": {"refusal"},
            "multistep": {"multistep_or_recovery"},
            "error_recovery": {"multistep_or_recovery"},
        }[stratum]
        if family.get("category") not in expected_categories:
            raise C5HoldoutError(
                f"family {family.get('family_id')} category does not match its holdout stratum"
            )
    if strata != EXPECTED_STRATA:
        raise C5HoldoutError(f"holdout strata differ from preregistration: {strata}")

    development_ids = {str(family.get("family_id") or "") for family in development_families}
    development_scenarios = {
        str(family.get("scenario_key") or "") for family in development_families
    }
    holdout_ids = {str(family.get("family_id") or "") for family in families}
    holdout_scenarios = {str(family.get("scenario_key") or "") for family in families}
    if holdout_ids.intersection(development_ids):
        raise C5HoldoutError("holdout family IDs overlap the development dataset")
    if holdout_scenarios.intersection(development_scenarios):
        raise C5HoldoutError("holdout scenario keys overlap the development dataset")

    holdout_signatures = [numeric_template_signature(_primary_text(family)) for family in families]
    development_signatures = {
        numeric_template_signature(_primary_text(family)) for family in development_families
    }
    if set(holdout_signatures).intersection(development_signatures):
        raise C5HoldoutError("holdout numeric templates overlap the development dataset")
    historical_signatures = set(
        str(value) for value in historical_exclusions.get("all_historical_numeric_text_hashes") or []
    )
    for signature in holdout_signatures:
        digest = hashlib.sha256(("historical-text:" + signature).encode("utf-8")).hexdigest()
        if digest in historical_signatures:
            raise C5HoldoutError("holdout numeric template overlaps consumed A5/P2/R material")

    development_text = [numeric_template_signature(_primary_text(family)) for family in development_families]
    for holdout_family, text in zip(families, holdout_signatures):
        if any(SequenceMatcher(None, text, other).ratio() >= 0.92 for other in development_text):
            raise C5HoldoutError(
                f"family {holdout_family.get('family_id')} is near-duplicate with development"
            )

    normalized_semantic = [
        " ".join(_primary_text(family).lower().split()).encode("utf-8") for family in families
    ]
    commitment = {
        "schema_version": COMMITMENT_SCHEMA_VERSION,
        "status": "sealed_unread_final_holdout",
        "dataset_id": DATASET_ID,
        "experiment_id": EXPERIMENT_ID,
        "contract_id": CONTRACT_ID,
        "custodian_identity": CUSTODIAN_ID,
        "reviewer_2_required": False,
        "development_agent_plaintext_access": False,
        "final_holdout_rows_read": 0,
        "family_count": len(families),
        "strata_counts": dict(sorted(strata.items())),
        "core_tool_family_counts": audit.invocation_tool_families,
        "encrypted_artifact": {
            "sha256": sha256_file(encrypted_artifact_path),
            "bytes": encrypted_artifact_path.stat().st_size,
            "format": encrypted_format,
        },
        "fingerprints": {
            "family_merkle_root_sha256": _merkle_root(
                [canonical_bytes(family) for family in families]
            ),
            "numeric_template_merkle_root_sha256": _merkle_root(
                [value.encode("utf-8") for value in holdout_signatures]
            ),
            "semantic_cluster_merkle_root_sha256": _merkle_root(normalized_semantic),
        },
        "exclusions": {
            "historical_exclusions_sha256": historical_exclusions_sha256,
            "development_dataset_freeze_sha256": development_dataset_freeze_sha256,
            "a5_p2_r_consumed_overlap_count": 0,
            "development_family_overlap_count": 0,
        },
        "custodian_attestation": {
            "content_is_new_and_unseen": True,
            "contract_rendering_verified": True,
            "strict_targets_verified": True,
            "group_split_and_near_duplicate_checks_passed": True,
            "encrypted_before_commitment": True,
            "key_not_shared_with_development_agent": True,
            "sealed_at": sealed_at,
        },
    }
    validate_public_commitment(
        commitment,
        expected_exclusion_sha256=historical_exclusions_sha256,
        expected_dataset_freeze_sha256=development_dataset_freeze_sha256,
    )
    return commitment


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_no, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise C5HoldoutError(f"ledger line {line_no} is invalid JSON") from exc
            if not isinstance(value, dict):
                raise C5HoldoutError(f"ledger line {line_no} is not an object")
            rows.append(value)
    return rows


def _append_jsonl_fsync(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical_bytes(payload).decode("utf-8") + "\n")
        stream.flush()
        os.fsync(stream.fileno())


@contextlib.contextmanager
def _exclusive_lock(ledger_path: Path) -> Iterable[None]:
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def gate_preflight(
    commitment: Mapping[str, Any],
    ledger_path: Path,
    *,
    expected_exclusion_sha256: str,
    expected_dataset_freeze_sha256: str,
) -> dict[str, Any]:
    validated = validate_public_commitment(
        commitment,
        expected_exclusion_sha256=expected_exclusion_sha256,
        expected_dataset_freeze_sha256=expected_dataset_freeze_sha256,
    )
    events = [
        row for row in _read_jsonl(ledger_path)
        if row.get("experiment_id") == EXPERIMENT_ID
    ]
    return {
        **validated,
        "new_run_allowed": not events,
        "consumption_events": len(events),
        "encrypted_artifact_opened": False,
        "plaintext_opened": False,
    }


def claim_encrypted_artifact(
    commitment: Mapping[str, Any],
    encrypted_artifact_path: Path,
    ledger_path: Path,
    *,
    confirm_commitment_sha256: str,
    code_revision: str,
    adapter_sha256: str,
    thresholds_sha256: str,
    expected_exclusion_sha256: str,
    expected_dataset_freeze_sha256: str,
) -> dict[str, Any]:
    """Claim once, fsync the claim, then and only then open encrypted bytes."""

    validated = validate_public_commitment(
        commitment,
        expected_exclusion_sha256=expected_exclusion_sha256,
        expected_dataset_freeze_sha256=expected_dataset_freeze_sha256,
    )
    if confirm_commitment_sha256 != validated["commitment_sha256"]:
        raise C5HoldoutError("explicit commitment confirmation does not match")
    for value, field in (
        (adapter_sha256, "adapter_sha256"),
        (thresholds_sha256, "thresholds_sha256"),
    ):
        _require_sha256(value, field)
    if not re.fullmatch(r"[0-9a-f]{7,64}", code_revision):
        raise C5HoldoutError("code_revision must be an explicit Git SHA")

    run_id = "c5-final-" + secrets.token_hex(12)
    consumed_at = _now()
    with _exclusive_lock(ledger_path):
        prior = [
            row for row in _read_jsonl(ledger_path)
            if row.get("experiment_id") == EXPERIMENT_ID
        ]
        if prior:
            raise C5HoldoutError("a C5 final-holdout consumption already exists")
        _append_jsonl_fsync(ledger_path, {
            "schema_version": GATE_SCHEMA_VERSION,
            "status": "started",
            "event_at": consumed_at,
            "holdout_consumed_at": consumed_at,
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
            "commitment_sha256": confirm_commitment_sha256,
            "code_revision": code_revision,
            "adapter_sha256": adapter_sha256,
            "thresholds_sha256": thresholds_sha256,
        })

    # This is deliberately the first operation that opens the encrypted artifact.
    actual_sha256 = sha256_file(encrypted_artifact_path)
    expected_artifact = commitment["encrypted_artifact"]
    if actual_sha256 != expected_artifact["sha256"]:
        _append_jsonl_fsync(ledger_path, {
            "schema_version": GATE_SCHEMA_VERSION,
            "status": "failed_encrypted_artifact_verification",
            "event_at": _now(),
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
        })
        raise C5HoldoutError("encrypted artifact hash differs from the commitment")
    if encrypted_artifact_path.stat().st_size != int(expected_artifact["bytes"]):
        _append_jsonl_fsync(ledger_path, {
            "schema_version": GATE_SCHEMA_VERSION,
            "status": "failed_encrypted_artifact_verification",
            "event_at": _now(),
            "experiment_id": EXPERIMENT_ID,
            "run_id": run_id,
        })
        raise C5HoldoutError("encrypted artifact size differs from the commitment")
    permit = secrets.token_hex(32)
    _append_jsonl_fsync(ledger_path, {
        "schema_version": GATE_SCHEMA_VERSION,
        "status": "encrypted_artifact_verified",
        "event_at": _now(),
        "experiment_id": EXPERIMENT_ID,
        "run_id": run_id,
        "encrypted_artifact_sha256": actual_sha256,
        "decryption_permit_sha256": hashlib.sha256(permit.encode("utf-8")).hexdigest(),
    })
    return {
        "run_id": run_id,
        "holdout_consumed_at": consumed_at,
        "encrypted_artifact_verified": True,
        "decryption_permit": permit,
        "plaintext_opened_by_gate": False,
        "new_run_allowed": False,
    }


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _mcnemar(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    tail = min(left_only, right_only)
    probability = sum(math.comb(discordant, value) for value in range(tail + 1)) / (
        2**discordant
    )
    return min(1.0, 2.0 * probability)


def paired_metric(
    base: Mapping[str, bool], lora: Mapping[str, bool], *, seed: int = BOOTSTRAP_SEED
) -> dict[str, Any]:
    if set(base) != set(lora) or len(base) != EXPECTED_FAMILIES:
        raise C5HoldoutError("paired metrics require the same 80 task-family IDs")
    ids = sorted(base)
    base_only = sum(bool(base[key]) and not bool(lora[key]) for key in ids)
    lora_only = sum(not bool(base[key]) and bool(lora[key]) for key in ids)
    differences = [int(bool(lora[key])) - int(bool(base[key])) for key in ids]
    rng = random.Random(seed)
    bootstrap = [
        100.0 * sum(differences[rng.randrange(len(ids))] for _ in ids) / len(ids)
        for _ in range(BOOTSTRAP_RESAMPLES)
    ]
    return {
        "families": len(ids),
        "base_correct": sum(bool(base[key]) for key in ids),
        "lora_correct": sum(bool(lora[key]) for key in ids),
        "difference_percentage_points": 100.0 * sum(differences) / len(ids),
        "net_wins_lora_minus_base": lora_only - base_only,
        "base_only": base_only,
        "lora_only": lora_only,
        "mcnemar_exact_two_sided_p": _mcnemar(base_only, lora_only),
        "paired_bootstrap_95ci_percentage_points": {
            "low": _percentile(bootstrap, 0.025),
            "high": _percentile(bootstrap, 0.975),
            "seed": seed,
            "resamples": BOOTSTRAP_RESAMPLES,
        },
    }


def summarize_offline_results(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize exactly one paired base/LoRA result per holdout family."""

    indexed: dict[str, dict[str, Mapping[str, Any]]] = {"base": {}, "lora": {}}
    for row in rows:
        route = str(row.get("route") or "")
        family_id = str(row.get("family_id") or "")
        if route not in indexed or not family_id or family_id in indexed[route]:
            raise C5HoldoutError("results contain an invalid or duplicate route/family pair")
        if any(not isinstance(row.get(field), bool) for field in METRIC_FIELDS):
            raise C5HoldoutError("result metric fields must be booleans")
        indexed[route][family_id] = row
    if set(indexed["base"]) != set(indexed["lora"]) or len(indexed["base"]) != 80:
        raise C5HoldoutError("results must contain 80 complete base/LoRA pairs")
    for family_id in indexed["base"]:
        base_row = indexed["base"][family_id]
        lora_row = indexed["lora"][family_id]
        if base_row.get("category") != lora_row.get("category"):
            raise C5HoldoutError(f"result category drifted between routes for {family_id}")
        if not isinstance(base_row.get("outcome_correct"), bool) or not isinstance(
            lora_row.get("outcome_correct"), bool
        ):
            raise C5HoldoutError("outcome_correct must be boolean for both routes")
        if not isinstance(base_row.get("critical_safety_error"), bool) or not isinstance(
            lora_row.get("critical_safety_error"), bool
        ):
            raise C5HoldoutError("critical_safety_error must be boolean for both routes")

    paired = {
        field: paired_metric(
            {key: bool(value[field]) for key, value in indexed["base"].items()},
            {key: bool(value[field]) for key, value in indexed["lora"].items()},
        )
        for field in METRIC_FIELDS
    }
    category_rows = {
        route: {
            "clarification": [
                row for row in route_rows.values()
                if row.get("category") == "clarification"
            ],
            "refusal_or_no_tool": [
                row for row in route_rows.values()
                if row.get("category") == "refusal_or_no_tool"
            ],
        }
        for route, route_rows in indexed.items()
    }
    if any(
        len(category_rows[route][category]) != 12
        for route in ("base", "lora")
        for category in ("clarification", "refusal_or_no_tool")
    ):
        raise C5HoldoutError("results do not preserve the 12/12 clarify/refuse strata")
    clarify_accuracy = {
        route: sum(row["outcome_correct"] for row in category_rows[route]["clarification"]) / 12
        for route in ("base", "lora")
    }
    refuse_accuracy = {
        route: sum(row["outcome_correct"] for row in category_rows[route]["refusal_or_no_tool"]) / 12
        for route in ("base", "lora")
    }
    critical_errors = sum(
        bool(row.get("critical_safety_error"))
        for route_rows in indexed.values()
        for row in route_rows.values()
    )
    parse_rate = paired["parse_exact"]["lora_correct"] / 80
    offline_gate_passed = all((
        parse_rate >= 0.90,
        paired["sequence_exact"]["difference_percentage_points"] >= 10.0,
        paired["sequence_exact"]["net_wins_lora_minus_base"] >= 8,
        paired["sequence_exact"]["mcnemar_exact_two_sided_p"] < 0.05,
        paired["tool_name_exact"]["difference_percentage_points"] >= 5.0,
        paired["arguments_exact"]["difference_percentage_points"] >= 5.0,
        paired["tool_name_exact"]["lora_correct"] >= paired["tool_name_exact"]["base_correct"],
        paired["arguments_exact"]["lora_correct"] >= paired["arguments_exact"]["base_correct"],
        clarify_accuracy["lora"] >= 0.85,
        refuse_accuracy["lora"] >= 0.85,
        clarify_accuracy["lora"] >= clarify_accuracy["base"],
        refuse_accuracy["lora"] >= refuse_accuracy["base"],
        critical_errors == 0,
    ))
    return {
        "schema_version": "1.0",
        "experiment_id": EXPERIMENT_ID,
        "family_pairs": 80,
        "paired_metrics": paired,
        "lora_parse_exact_rate": parse_rate,
        "clarification_accuracy": clarify_accuracy,
        "refusal_accuracy": refuse_accuracy,
        "critical_safety_errors": critical_errors,
        "offline_gate_passed": offline_gate_passed,
        "overall_c5_decision": "not_authorized_by_offline_gate_alone",
    }


__all__ = [
    "C5HoldoutError",
    "EXPECTED_STRATA",
    "build_public_commitment",
    "claim_encrypted_artifact",
    "gate_preflight",
    "paired_metric",
    "public_commitment_template",
    "sha256_file",
    "summarize_offline_results",
    "validate_public_commitment",
]
