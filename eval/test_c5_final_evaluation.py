from __future__ import annotations

from collections import Counter

import pytest

from training.c5_final_evaluation import controller_report, verify_sealed_plaintext
from training.c5_holdout import C5HoldoutError, EXPECTED_STRATA, _merkle_root, _primary_text, canonical_bytes
from data_pipeline.training_views import numeric_template_signature


def test_sealed_plaintext_requires_all_three_exact_merkle_roots():
    families = [{"family_id":f"synthetic-{i}", "holdout_stratum":stratum,
                 "records":[{"user_step":f"synthetic instruction {i}"}]} for i,stratum in
                enumerate(s for s,n in EXPECTED_STRATA.items() for _ in range(n))]
    c = {"fingerprints":{
        "family_merkle_root_sha256":_merkle_root([canonical_bytes(f) for f in families]),
        "numeric_template_merkle_root_sha256":_merkle_root([numeric_template_signature(_primary_text(f)).encode() for f in families]),
        "semantic_cluster_merkle_root_sha256":_merkle_root([" ".join(_primary_text(f).lower().split()).encode() for f in families])}}
    verify_sealed_plaintext(families,c)
    families[0]["records"][0]["user_step"] += " tamper"
    with pytest.raises(C5HoldoutError): verify_sealed_plaintext(families,c)


def _rows():
    return [{"route":route,"parse_exact":True,"critical_safety_error":False,
             "repair_count":0,"dispatch_count":0,
             "receipts":[{"parsed":True, "output_tokens":4,"seconds":.1,
                          **{k:"a"*64 for k in ("prompt_sha256","output_sha256","model_sha256","schema_sha256","parser_sha256")}}]}
            for route in ("base","lora") for _ in range(80)]


def test_controller_gate_never_passes_if_offline_gate_failed():
    assert controller_report(_rows(),True)["passed"]
    assert not controller_report(_rows(),False)["passed"]
    assert controller_report(_rows(),False)["status"]=="blocked_by_offline_gate"


def test_latency_is_separated_by_route_without_claiming_live_rhino_latency():
    rows = _rows()
    for row in rows:
        if row["route"] == "lora":
            row["receipts"][0]["seconds"] = .2
    report = controller_report(rows, True)
    assert report["by_route"]["base"]["median_family_generation_seconds"] == .1
    assert report["by_route"]["lora"]["median_family_generation_seconds"] == .2
    assert "excludes" in report["by_route"]["lora"]["latency_scope"]
    assert report["rhino_executed"] is False


def test_controller_hash_loss_critical_error_or_repair_blocks():
    for change in ("hash", "output_hash", "safety", "repair", "dispatch"):
        rows=_rows()
        if change=="hash": rows[0]["receipts"][0].pop("parser_sha256")
        elif change=="output_hash": rows[0]["receipts"][0].pop("output_sha256")
        elif change=="safety": rows[0]["critical_safety_error"]=True
        elif change=="repair": rows[0]["repair_count"]=1
        else: rows[0]["dispatch_count"]=1
        assert not controller_report(rows,True)["passed"]
