"""Post-consumption audit of hash-only C5 results; never opens final task bodies.

This is a new audit utility, not a change to the frozen evaluation protocol.
Only explicitly named public files and the owner's metadata ledger are read.
It cannot generate predictions, claim/decrypt a holdout, or authorize Rhino.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from training.c5_execution import digest, sha256_file
from training.c5_final_evaluation import controller_report
from training.c5_holdout import EXPECTED_STRATA, METRIC_FIELDS, summarize_offline_results

PUBLIC_FILES = (
    "public-progress.json", "public-report.json", "public-results.json",
    "consumption-receipt.json", "resource-settlement.json",
)
ROW_KEYS = {
    "family_id", "route", "category", "contract_id", "outcome_correct",
    "critical_safety_error", "repair_count", "dispatch_count", "receipts", *METRIC_FIELDS,
}
RECEIPT_KEYS = {
    "record_id", "stage", "parsed", "name_exact", "arguments_exact", "prompt_sha256",
    "output_sha256", "model_sha256", "schema_sha256", "parser_sha256", "output_tokens", "seconds",
}
SHA = re.compile(r"[0-9a-f]{64}\Z")


class FinalAuditError(RuntimeError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise FinalAuditError(reason)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_public(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "public evidence absent or symlink")
    require(path.stat().st_size <= 10 * 1024**2, "public evidence exceeds bounded size")
    value = json.loads(path.read_text(), object_pairs_hook=_unique_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(FinalAuditError("nonfinite JSON")))
    require(isinstance(value, dict), "public evidence must be an object")
    return value


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, float):
        return (type(actual) in (float, int) and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=0.0))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            _same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _same(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def independent_pair_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute counts, binomial McNemar and seeded paired bootstrap separately."""
    indexed = {route: {r["family_id"]: r for r in rows if r["route"] == route}
               for route in ("base", "lora")}
    ids = sorted(indexed["base"])
    result = {}
    for metric in METRIC_FIELDS:
        pairs = [(int(indexed["base"][i][metric]), int(indexed["lora"][i][metric])) for i in ids]
        wins = sum(a == 0 and b == 1 for a, b in pairs)
        losses = sum(a == 1 and b == 0 for a, b in pairs)
        discordant = wins + losses
        p = (min(1.0, 2.0 * sum(math.comb(discordant, k)
             for k in range(min(wins, losses) + 1)) / 2**discordant) if discordant else 1.0)
        changes = [b-a for a, b in pairs]
        rng = random.Random(20260927)
        samples = sorted(100 * sum(changes[rng.randrange(80)] for _ in range(80)) / 80
                         for _ in range(10000))
        def quantile(q):
            point = (len(samples)-1)*q
            left, right = math.floor(point), math.ceil(point)
            return float(samples[left]*(right-point) + samples[right]*(point-left)
                         if left != right else samples[left])
        result[metric] = {
            "families": 80, "base_correct": sum(a for a, _ in pairs),
            "lora_correct": sum(b for _, b in pairs), "base_only": losses, "lora_only": wins,
            "net_wins_lora_minus_base": wins-losses,
            "difference_percentage_points": 100*(wins-losses)/80,
            "mcnemar_exact_two_sided_p": p,
            "paired_bootstrap_95ci_percentage_points": {
                "low": quantile(.025), "high": quantile(.975), "seed": 20260927, "resamples": 10000},
        }
    return result


def validate_hash_only_rows(rows: Any, freeze: dict, formal_context: dict, schema_sha256: str) -> None:
    require(isinstance(rows, list) and len(rows) == 160, "need exactly 160 route-family rows")
    base_sha = digest(formal_context["snapshot"])
    indexed = {}
    schema_hashes, parser_hashes = set(), set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == ROW_KEYS, "row fields not hash-only schema")
        require(SHA.fullmatch(str(row["family_id"])) is not None, "family ID must be SHA-256")
        require(row["route"] in {"base", "lora"}, "unknown route")
        key = row["route"], row["family_id"]
        require(key not in indexed, "duplicate route-family pair")
        indexed[key] = row
        require(row["category"] in EXPECTED_STRATA, "unknown stratum")
        require(row["contract_id"] == freeze["contract_id"], "contract drift")
        require(all(type(row[k]) is bool for k in (*METRIC_FIELDS, "outcome_correct", "critical_safety_error")),
                "metric must be boolean")
        require(all(type(row[k]) is int and row[k] >= 0 for k in ("repair_count", "dispatch_count")),
                "invalid repair/dispatch count")
        receipts = row["receipts"]
        require(isinstance(receipts, list) and 1 <= len(receipts) <= 64, "bounded receipts required")
        record_ids = set()
        for rec in receipts:
            require(isinstance(rec, dict) and set(rec) <= RECEIPT_KEYS, "receipt includes nonpublic fields")
            require(SHA.fullmatch(str(rec.get("record_id", ""))) is not None, "record ID must be SHA-256")
            require(rec["record_id"] not in record_ids, "duplicate record ID")
            record_ids.add(rec["record_id"])
            require(rec.get("stage") in {"selector", "invocation"} and type(rec.get("parsed")) is bool,
                    "invalid stage or parse flag")
            for k in ("model_sha256", "schema_sha256", "parser_sha256"):
                require(SHA.fullmatch(str(rec.get(k, ""))) is not None, "receipt lineage hash missing")
            require(rec["model_sha256"] == (freeze["adapter_sha256"] if row["route"] == "lora" else base_sha),
                    "receipt model identity drift")
            schema_hashes.add(rec["schema_sha256"]); parser_hashes.add(rec["parser_sha256"])
            if "output_sha256" in rec:
                require(all(SHA.fullmatch(str(rec.get(k, ""))) for k in ("prompt_sha256", "output_sha256")),
                        "generation hash missing")
                require(type(rec.get("output_tokens")) is int and rec["output_tokens"] >= 0,
                        "invalid token count")
                require(type(rec.get("seconds")) in (float, int) and math.isfinite(rec["seconds"])
                        and rec["seconds"] >= 0, "invalid generation duration")
            else:
                require(rec["parsed"] is False and rec["stage"] == "invocation"
                        and not {"prompt_sha256", "output_tokens", "seconds"}.intersection(rec),
                        "non-generated invocation must fail closed")
            if rec["parsed"]:
                require("output_sha256" in rec and all(type(rec.get(k)) is bool
                        for k in ("name_exact", "arguments_exact")), "accepted output lacks score/hash")
                require(not rec["arguments_exact"] or rec["name_exact"], "arguments cannot pass wrong tool")
        derived = {
            "parse_exact": all(r["parsed"] for r in receipts),
            "tool_name_exact": all(r["parsed"] and r.get("name_exact", False) for r in receipts),
            "arguments_exact": all(r["parsed"] and r.get("arguments_exact", False) for r in receipts),
            "sequence_exact": all(r["parsed"] and r.get("name_exact", False)
                                  and r.get("arguments_exact", False) for r in receipts),
        }
        require(all(row[k] == v for k, v in derived.items()), "family score disagrees with receipts")
    expected_parser = digest({name: freeze["implementation_sha256"][name] for name in (
        "training/c5_contract.py", "training/tool_contract_candidate.py",
        "training/tool_contract_v3_candidate.py", "training/tool_selector_v4_candidate.py")})
    require(schema_hashes == {schema_sha256} and parser_hashes == {expected_parser},
            "schema/parser identity differs from freeze")
    for route in ("base", "lora"):
        subset = [r for r in rows if r["route"] == route]
        require(len(subset) == 80 and dict(Counter(r["category"] for r in subset)) == EXPECTED_STRATA,
                "route stratum counts differ from commitment")
    for route, family in indexed:
        partner = indexed.get(("lora" if route == "base" else "base", family))
        require(partner is not None and partner["category"] == indexed[route, family]["category"],
                "unpaired family or category drift")
        current_records = {r["record_id"]: r for r in indexed[route, family]["receipts"]}
        partner_records = {r["record_id"]: r for r in partner["receipts"]}
        require(current_records.keys() == partner_records.keys(), "paired record sets differ")
        for name, rec in current_records.items():
            other = partner_records[name]
            require(rec["stage"] == other["stage"], "paired stages differ")
            if rec["stage"] == "selector":
                require(rec.get("prompt_sha256") == other.get("prompt_sha256"),
                        "paired selector inputs differ")


def audit_final_export(public_dir: Path, freeze: dict, formal_context: dict,
                       owner_ledger: Path, registry: dict, commitment: dict,
                       schema_sha256: str) -> dict[str, Any]:
    require(not (public_dir / "failed.json").exists(), "failed consumption cannot be certified complete")
    data = {name: read_public(public_dir/name) for name in PUBLIC_FILES}
    report, receipt = data["public-report.json"], data["consumption-receipt.json"]
    progress, settlement = data["public-progress.json"], data["resource-settlement.json"]
    run_id = report["run_id"]
    require(re.fullmatch(r"c5-final-[0-9a-f]{24}", run_id) is not None, "invalid original run ID")
    require(progress["run_id"] == receipt["run_id"] == run_id, "public run IDs disagree")
    require(progress["completed_route_family_pairs"] == 160, "incomplete evaluation")
    require(report["final_holdout_families_consumed"] == 80, "consumption denominator drift")
    require(report["adapter_sha256"] == registry["adapter_sha256"] == freeze["adapter_sha256"],
            "adapter identity differs")
    require(digest(formal_context) == registry["context_sha256"], "formal context drift")
    require(report["final_freeze_sha256"] == digest(freeze), "final freeze differs")
    require(receipt["custodian_identity"] == "repository_owner", "custodian differs")
    require(all(receipt[k] == freeze[k] for k in
                ("adapter_sha256", "code_revision", "commitment_sha256", "thresholds_sha256")),
            "consumption receipt differs from preregistration")
    require(owner_ledger.is_file() and not owner_ledger.is_symlink()
            and owner_ledger.stat().st_size < 1024**2, "owner metadata ledger unavailable")
    ledger = [json.loads(line, object_pairs_hook=_unique_object)
              for line in owner_ledger.read_text().splitlines() if line.strip()]
    require(len(ledger) == 2 and [r["status"] for r in ledger] == ["started", "encrypted_artifact_verified"]
            and all(r["run_id"] == run_id and r["experiment_id"] == freeze["experiment_id"] for r in ledger),
            "need original unique consumption and verified artifact events")
    require(ledger[0]["holdout_consumed_at"] == receipt["holdout_consumed_at"]
            and all(ledger[0][k] == receipt[k] for k in
                    ("adapter_sha256", "code_revision", "commitment_sha256", "thresholds_sha256")),
            "owner ledger differs from remote receipt")
    require(digest(commitment) == freeze["commitment_sha256"]
            and ledger[1].get("encrypted_artifact_sha256") == commitment["encrypted_artifact"]["sha256"],
            "owner verified artifact differs from public commitment")
    require(settlement["new_run_allowed"] is False and settlement["final_budget_seconds_max"] == 14400
            and 0 < report["seconds"] <= settlement["seconds"] <= 14400,
            "resource budget or no-rerun settlement invalid")
    require(all(report[k] is False for k in ("default_route_changed", "rhino_called", "development_agent_plaintext_access")),
            "unexpected product/Rhino/plaintext access")
    rows = data["public-results.json"]["rows"]
    validate_hash_only_rows(rows, freeze, formal_context, schema_sha256)
    stats = independent_pair_statistics(rows)
    require(_same(report["offline"]["paired_metrics"], stats), "independent paired statistics disagree")
    offline = summarize_offline_results(rows)
    compatibility = controller_report(rows, offline["offline_gate_passed"])
    require(_same(report["offline"], offline), "offline aggregate differs from hash-only rows")
    require(_same(report["controller"], compatibility), "controller aggregate differs from receipts")
    return {
        "schema_version": "1.0", "status": "completed_public_evidence_verified",
        "run_id": run_id, "audit_passed": True, "consumption_events": 1,
        "metadata_ledger_entries": 2, "holdout_families_consumed": 80,
        "final_freeze_sha256": digest(freeze), "adapter_sha256": freeze["adapter_sha256"],
        "public_file_sha256": {name: sha256_file(public_dir/name) for name in PUBLIC_FILES},
        "owner_metadata_ledger_sha256": sha256_file(owner_ledger),
        "independent_paired_statistics": stats,
        "offline": offline, "controller": compatibility,
        "new_run_allowed": False, "rhino_execution_authorized": False,
        "overall_c5_decision": "pending_R_research_safety_and_C5_6",
        "plaintext_or_raw_generations_read": False,
        "audit_scope": "recomputed public scores, counts, statistics, timing and hashes; no reparsing private raw generations",
    }
