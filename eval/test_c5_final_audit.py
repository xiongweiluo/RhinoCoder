from __future__ import annotations

import hashlib
import json

import pytest

from training.c5_execution import digest
from training.c5_final_audit import FinalAuditError, audit_final_export
from training.c5_final_evaluation import controller_report
from training.c5_holdout import EXPECTED_STRATA, METRIC_FIELDS, summarize_offline_results


@pytest.fixture
def evidence(tmp_path):
    context = {"snapshot": {"base_revision": "synthetic-only"}}
    commitment = {"encrypted_artifact": {"sha256": "e"*64}}
    implementations = {name: "c"*64 for name in ("training/c5_contract.py", "training/tool_contract_candidate.py",
        "training/tool_contract_v3_candidate.py", "training/tool_selector_v4_candidate.py")}
    freeze = {"adapter_sha256": "a"*64, "code_revision": "d"*40,
              "commitment_sha256": digest(commitment), "thresholds_sha256": "f"*64,
              "implementation_sha256": implementations,
              "experiment_id": "synthetic-final-audit", "contract_id": "synthetic-contract"}
    registry = {"adapter_sha256": freeze["adapter_sha256"], "context_sha256": digest(context)}
    rows = []
    categories = [s for s, n in EXPECTED_STRATA.items() for _ in range(n)]
    for route in ("base", "lora"):
        for i, category in enumerate(categories):
            passed = i < (20 if route == "base" else 77)
            sha = lambda text: hashlib.sha256(text.encode()).hexdigest()
            rec = {"record_id": sha(f"record-{i}"), "stage": "selector", "parsed": passed,
                   "model_sha256": freeze["adapter_sha256"] if route == "lora" else digest(context["snapshot"]),
                   "schema_sha256": "b"*64, "parser_sha256": digest(implementations),
                   "prompt_sha256": sha(f"prompt-{i}"), "output_sha256": sha(f"output-{route}-{i}"),
                   "output_tokens": 4, "seconds": .1}
            if passed:
                rec.update(name_exact=True, arguments_exact=True)
            rows.append({"route": route, "family_id": sha(f"family-{i}"), "category": category,
                         "contract_id": freeze["contract_id"], "outcome_correct": passed,
                         "critical_safety_error": False, "repair_count": 0, "dispatch_count": 0,
                         "receipts": [rec], **{k: passed for k in METRIC_FIELDS}})
    offline = summarize_offline_results(rows)
    report = {"run_id": "c5-final-"+"1"*24, "adapter_sha256": freeze["adapter_sha256"],
              "final_freeze_sha256": digest(freeze), "final_holdout_families_consumed": 80,
              "seconds": 20., "default_route_changed": False, "rhino_called": False,
              "development_agent_plaintext_access": False,
              "offline": offline, "controller": controller_report(rows, offline["offline_gate_passed"])}
    receipt = {k: freeze[k] for k in ("adapter_sha256", "code_revision", "commitment_sha256", "thresholds_sha256")}
    receipt.update(run_id=report["run_id"], custodian_identity="repository_owner",
                   holdout_consumed_at="2026-10-02T14:07:44Z")
    files = {"public-progress.json": {"run_id": report["run_id"], "completed_route_family_pairs": 160},
             "public-report.json": report, "public-results.json": {"rows": rows},
             "consumption-receipt.json": receipt,
             "resource-settlement.json": {"seconds": 20.1, "final_budget_seconds_max": 14400,
                                          "new_run_allowed": False}}
    for name, content in files.items():
        (tmp_path/name).write_text(json.dumps(content))
    first = {k: receipt[k] for k in ("run_id", "holdout_consumed_at", "adapter_sha256",
                                     "code_revision", "commitment_sha256", "thresholds_sha256")}
    first.update(status="started", experiment_id=freeze["experiment_id"])
    second = {"run_id": report["run_id"], "experiment_id": freeze["experiment_id"],
              "status": "encrypted_artifact_verified", "encrypted_artifact_sha256": "e"*64}
    ledger = tmp_path/"owner-metadata.jsonl"
    ledger.write_text(json.dumps(first)+"\n"+json.dumps(second)+"\n")
    return tmp_path, files, freeze, context, ledger, registry, commitment


def audit(e):
    root, _, freeze, context, ledger, registry, commitment = e
    return audit_final_export(root, freeze, context, ledger, registry, commitment, "b"*64)


def test_completed_export_recomputes_counts_and_keeps_rhino_and_rerun_blocked(evidence):
    result = audit(evidence)
    assert result["audit_passed"] is True
    assert result["independent_paired_statistics"]["sequence_exact"]["net_wins_lora_minus_base"] == 57
    assert result["new_run_allowed"] is False
    assert result["rhino_execution_authorized"] is False
    assert result["plaintext_or_raw_generations_read"] is False
    # Audit completion is separate from model quality; this synthetic base has
    # poor clarify/refuse and the frozen functions, not the audit, decide quality.
    assert result["overall_c5_decision"] == "pending_R_research_safety_and_C5_6"


@pytest.mark.parametrize("tamper", ["aggregate", "receipt_score", "model_hash", "plaintext",
                                    "duplicate_pair", "schema_drift", "new_run", "partial", "bool_type", "pair_prompt"])
def test_invalid_or_nonpublic_evidence_never_certified(evidence, tamper):
    root, files, _, _, _, _, _ = evidence
    rows = files["public-results.json"]["rows"]
    if tamper == "aggregate": files["public-report.json"]["offline"]["paired_metrics"]["sequence_exact"]["lora_correct"] -= 1
    elif tamper == "receipt_score": rows[0]["sequence_exact"] = False
    elif tamper == "model_hash": rows[0]["receipts"][0]["model_sha256"] = "0"*64
    elif tamper == "plaintext": rows[0]["receipts"][0]["raw"] = "synthetic forbidden content"
    elif tamper == "duplicate_pair": rows[1]["family_id"] = rows[0]["family_id"]
    elif tamper == "schema_drift": rows[0]["receipts"][0]["schema_sha256"] = "0"*64
    elif tamper == "new_run": files["resource-settlement.json"]["new_run_allowed"] = True
    elif tamper == "partial": files["public-progress.json"]["completed_route_family_pairs"] = 159
    elif tamper == "bool_type": rows[0]["parse_exact"] = 1
    elif tamper == "pair_prompt": rows[0]["receipts"][0]["prompt_sha256"] = "0"*64
    for name, content in files.items(): (root/name).write_text(json.dumps(content))
    with pytest.raises(FinalAuditError): audit(evidence)


def test_different_owner_run_or_failed_consumption_is_not_completed(evidence):
    root, _, _, _, ledger, _, _ = evidence
    ledger.write_text(ledger.read_text().replace("c5-final-"+"1"*24, "c5-final-"+"2"*24))
    with pytest.raises(FinalAuditError): audit(evidence)
    (root/"failed.json").write_text("{}")
    with pytest.raises(FinalAuditError): audit(evidence)


def test_private_generation_file_is_never_opened(evidence, monkeypatch):
    from pathlib import Path
    original = Path.read_text
    def read(path, *args, **kwargs):
        if path.name == "owner-private-generations.jsonl": raise AssertionError("private file opened")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    audit(evidence)
