"""Owner-only final evaluation support, never imported by C5 training.

Development tests use synthetic families only. Real plaintext is supplied by
the independent custodian after a durable single-use claim. Only aggregate
metrics and hashes may be returned to the development agent.
"""
from __future__ import annotations

from collections import Counter
import statistics
from typing import Any, Mapping, Sequence

from data_pipeline.training_views import numeric_template_signature
from training.c5_holdout import (
    C5HoldoutError, EXPECTED_STRATA, _merkle_root, _primary_text, canonical_bytes,
)


def verify_sealed_plaintext(families: Sequence[Any], commitment: Mapping[str, Any]) -> None:
    if len(families) != 80 or len({f["family_id"] for f in families}) != 80:
        raise C5HoldoutError("sealed family count or identity mismatch")
    if dict(Counter(f.get("holdout_stratum") for f in families)) != EXPECTED_STRATA:
        raise C5HoldoutError("sealed strata mismatch")
    fingerprints = {
        "family_merkle_root_sha256": _merkle_root([canonical_bytes(f) for f in families]),
        "numeric_template_merkle_root_sha256": _merkle_root([
            numeric_template_signature(_primary_text(f)).encode() for f in families]),
        "semantic_cluster_merkle_root_sha256": _merkle_root([
            " ".join(_primary_text(f).lower().split()).encode() for f in families]),
    }
    if fingerprints != commitment["fingerprints"]:
        raise C5HoldoutError("decrypted bytes differ from all three committed fingerprints")


def controller_report(rows: Sequence[Mapping[str, Any]], offline_passed: bool) -> dict[str, Any]:
    lora = [r for r in rows if r.get("route") == "lora"]
    if len(lora) != 80 or sum(r.get("route") == "base" for r in rows) != 80:
        raise C5HoldoutError("controller gate requires the same 80 base/LoRA family pairs")
    receipts = [receipt for r in rows for receipt in r["receipts"]]
    accepted = [r for r in receipts if r["parsed"]]
    raw_outputs = [r for r in receipts if "output_sha256" in r]
    valid_hashes = bool(raw_outputs) and all(all(len(str(r.get(key, ""))) == 64 for key in
                          ("prompt_sha256", "output_sha256", "model_sha256", "schema_sha256", "parser_sha256"))
                       for r in raw_outputs) and all("output_sha256" in r for r in accepted)
    completion = sum(r["parse_exact"] for r in lora) / 80
    errors = sum(r["critical_safety_error"] for r in rows)
    repairs = sum(r["repair_count"] for r in rows)
    dispatch = sum(r["dispatch_count"] for r in rows)
    passed = offline_passed and valid_hashes and completion >= .90 and errors == repairs == dispatch == 0
    by_stage = {}
    failure_classes = Counter()
    for receipt in receipts:
        if not receipt["parsed"]:
            label = "missing_or_out_of_scope_selection" if "output_sha256" not in receipt else receipt.get("stage", "unknown") + "_parse_or_schema"
            failure_classes[label] += 1
        elif receipt.get("name_exact") is False:
            failure_classes["wrong_tool"] += 1
        elif receipt.get("arguments_exact") is False:
            failure_classes["wrong_arguments"] += 1
    for stage in ("selector", "invocation"):
        values = [r for r in raw_outputs if r.get("stage") == stage]
        if values:
            latency = sorted(r["seconds"] for r in values)
            seconds = sum(latency)
            tokens = sum(r["output_tokens"] for r in values)
            by_stage[stage] = {"generations":len(values), "tokens":tokens,
                "median_output_tokens":statistics.median(r["output_tokens"] for r in values),
                "median_seconds":statistics.median(latency),
                "p95_seconds":latency[min(len(latency)-1, int(.95*(len(latency)-1)))],
                "tokens_per_second":tokens/seconds if seconds else None}
    by_route = {}
    for route in ("base", "lora"):
        route_rows = [r for r in rows if r.get("route") == route]
        route_receipts = [receipt for r in route_rows for receipt in r["receipts"]
                          if "output_sha256" in receipt]
        family_generation_seconds = sorted(sum(x.get("seconds", 0) for x in r["receipts"])
                                           for r in route_rows)
        seconds = sum(x["seconds"] for x in route_receipts)
        tokens = sum(x["output_tokens"] for x in route_receipts)
        by_route[route] = {"families": len(route_rows), "generations": len(route_receipts),
            "critical_safety_prediction_errors": sum(r["critical_safety_error"] for r in route_rows),
            "generated_tokens": tokens, "generation_seconds": seconds,
            "tokens_per_second": tokens / seconds if seconds else None,
            "median_family_generation_seconds": statistics.median(family_generation_seconds),
            "p95_family_generation_seconds": family_generation_seconds[min(
                len(family_generation_seconds) - 1, int(.95 * (len(family_generation_seconds) - 1)))],
            "latency_scope": "sum of model-generation calls per family; excludes prompt rendering, parsing, network and Rhino"}
    return {"status": "passed" if passed else "blocked_by_offline_gate" if not offline_passed else "failed",
            "passed": passed, "offline_gate_passed": offline_passed,
            "lora_two_stage_protocol_completion_rate": completion,
            "generated_receipt_hash_coverage": valid_hashes,
            "accepted_outputs_schema_valid_rate": 1.0 if accepted else None,
            "accepted_outputs": len(accepted), "generated_outputs": len(raw_outputs),
            "critical_safety_errors": errors, "repair_count": repairs, "dispatch_count": dispatch,
            "generated_tokens": sum(r.get("output_tokens", 0) for r in receipts),
            "generation_seconds": sum(r.get("seconds", 0) for r in receipts),
            "by_stage": by_stage, "by_route": by_route,
            "failure_record_counts": dict(failure_classes),
            "rhino_executed": False, "product_route_authorized": False,
            "measurement_scope": "strict C5 selector/single-schema adapter and fail-closed parsing only; not live consent/geometry or general task quality"}
