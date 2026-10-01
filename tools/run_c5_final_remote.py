#!/usr/bin/env python3
"""Custodian-triggered, single-use GPU final job; stdin is never logged.

Do not invoke this tool from a development/diagnostic session. The owner-side
client claims and decrypts the committed artifact; only its private process
sends the exact committed families over authenticated SSH.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import fcntl
import json
import os
import random
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.umask(0o077)

from training.c5_execution import (  # noqa: E402
    digest, evaluate_families, generation, load_config, load_pinned_tokenizer,
    read_json, score_family, sha256_file, verify_authorization, verify_checkpoint,
    verify_snapshot, write_json, append_event,
)
from training.c5_final_evaluation import controller_report, verify_sealed_plaintext  # noqa: E402
from training.c5_holdout import summarize_offline_results  # noqa: E402
from training.c5_inventory import load_public_mcp_tools  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--snapshot-manifest", type=Path, required=True)
    p.add_argument("--authorization", type=Path, required=True)
    p.add_argument("--final-freeze", type=Path, required=True)
    p.add_argument("--preflight", action="store_true")
    a = p.parse_args()
    # Check all preconditions and model identity before accepting any plaintext.
    import torch
    from peft import PeftModel, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    auth = verify_authorization(a.authorization, load_config())
    freeze = read_json(a.final_freeze)
    lock = (a.run_root / "execution.lock").open("a+")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    for name, expected in freeze["implementation_sha256"].items():
        if sha256_file(ROOT / name) != expected:
            raise RuntimeError("final evaluation code differs from freeze")
    registry = read_json(a.run_root / "formal/registry.json")
    if (sha256_file(a.run_root / "formal/registry.json") != freeze["registry_sha256"]
        or sha256_file(a.run_root / "formal/result.json") != freeze["formal_result_sha256"]
        or sha256_file(ROOT / "eval/c5/offline-freeze-spec.json") != freeze["thresholds_sha256"]
        or digest(read_json(ROOT / "eval/c5/final-holdout-commitment.json")) != freeze["commitment_sha256"]):
        raise RuntimeError("final preregistration/result/registry/commitment drift")
    if registry["adapter_sha256"] != freeze["adapter_sha256"]:
        raise RuntimeError("final adapter freeze mismatch")
    context = read_json(a.run_root / "formal/context.json")
    if registry["context_sha256"] != digest(context):
        raise RuntimeError("formal registration context drift")
    verify_checkpoint(a.run_root / "formal" / registry["selected_checkpoint"], digest(context))
    for phase in ("overfit", "system", "formal"):
        if read_json(a.run_root / phase / "result.json")["passed"] is not True:
            raise RuntimeError("earlier stage not passed")
    verify_snapshot(a.snapshot, a.snapshot_manifest)
    load_public_mcp_tools()  # Require the original schema before any claim/plaintext.
    events = [json.loads(x) for x in (a.run_root / "execution-events.jsonl").read_text().splitlines()]
    starts = {e["segment_id"] for e in events if e["event"] == "start"}
    finishes = {e["segment_id"] for e in events if e["event"] == "finish"}
    if starts != finishes:
        raise RuntimeError("unsettled GPU budget; no final consumption allowed")
    used = sum(e["seconds"] for e in events if e["event"] == "finish")
    budget = min(4*3600, 16*3600-used, auth["execution_deadline_epoch"]-time.time()-900)
    if budget <= 0: raise RuntimeError("final evaluation budget exhausted")
    final = a.run_root / "final"
    if final.exists():
        raise RuntimeError("final execution already exists; no new ID or rerun")
    if a.preflight:
        print(json.dumps({"ready":True,"adapter_sha256":registry["adapter_sha256"],
                          "budget_seconds_remaining":budget,"final_freeze_sha256":digest(freeze),
                          "final_holdout_rows_read":0,"consumption_claim_executed":False}))
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()
        return
    final.mkdir(mode=0o700)  # Exclusive global final directory: no rerun under a new run ID.
    start = time.monotonic()
    def stop(*_): raise RuntimeError("final GPU budget stop")
    signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, budget)
    try:
        payload = json.load(sys.stdin)
        if (payload["custodian_identity"] != "repository_owner"
            or payload["adapter_sha256"] != freeze["adapter_sha256"]
            or payload["thresholds_sha256"] != freeze["thresholds_sha256"]
            or payload["commitment_sha256"] != freeze["commitment_sha256"]
            or payload["code_revision"] != freeze["code_revision"]):
            raise RuntimeError("owner claim or final freeze mismatch")
        commitment = read_json(ROOT / "eval/c5/final-holdout-commitment.json")
        verify_sealed_plaintext(payload["families"], commitment)
        write_json(final / "consumption-receipt.json", {k:v for k,v in payload.items() if k != "families"}, exclusive=True)
        tokenizer = load_pinned_tokenizer(a.snapshot, config=load_config())
        random.seed(20260928); torch.manual_seed(20260928); torch.cuda.manual_seed_all(20260928)
        torch.backends.cuda.matmul.allow_tf32 = True  # Same frozen formal-validation execution flag.
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
        base = AutoModelForCausalLM.from_pretrained(a.snapshot, local_files_only=True,
            trust_remote_code=False, quantization_config=quant, dtype=torch.bfloat16, device_map={"":0})
        # Match formal validation's FP32 unquantized embedding/head/norm casts.
        # No backward/checkpoint hooks in this inference-only process. Both
        # routes share this identical base; NF4 matmul compute remains BF16.
        base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
        base.config.use_cache = False
        model = PeftModel.from_pretrained(base, a.run_root / "formal" / registry["selected_checkpoint"],
                                       local_files_only=True, is_trainable=False)
        model.eval(); torch.cuda.reset_peak_memory_stats()
        tools = load_public_mcp_tools()
        parser_hash = digest({name: sha256_file(ROOT / name) for name in
            ("training/c5_contract.py", "training/tool_contract_candidate.py", "training/tool_contract_v3_candidate.py", "training/tool_selector_v4_candidate.py")})
        rows = []
        order = list(payload["families"]); random.Random(20260927).shuffle(order)
        for ordinal, family in enumerate(order):
            # Counterbalanced pair order; no retry, repair, prompt editing or oracle tool forcing.
            routes = ("base", "lora") if ordinal % 2 == 0 else ("lora", "base")
            for route in routes:
                manager = model.disable_adapter() if route == "base" else contextlib.nullcontext()
                with manager:
                    def generate(prompt, stage):
                        result = generation(model, tokenizer, prompt, stage)
                        append_event(final / "owner-private-generations.jsonl", {
                            "family_id_sha256": hashlib.sha256(family["family_id"].encode()).hexdigest(),
                            "route": route, "stage": stage, **result})
                        return result
                    row = score_family(family, generate, tokenizer, tools)
                row["route"] = route
                row["family_id"] = hashlib.sha256(row["family_id"].encode()).hexdigest()
                for receipt in row["receipts"]:
                    receipt["record_id"] = hashlib.sha256(receipt["record_id"].encode()).hexdigest()
                    receipt.update(model_sha256=freeze["adapter_sha256"] if route == "lora" else digest(context["snapshot"]),
                                   schema_sha256=digest(tools), parser_sha256=parser_hash)
                rows.append(row)
                write_json(final / "public-progress.json", {"completed_route_family_pairs": len(rows), "run_id": payload["run_id"]})
        summary = summarize_offline_results(rows)
        compatibility = controller_report(rows, summary["offline_gate_passed"])
        report = {"run_id": payload["run_id"], "offline": summary, "controller": compatibility,
                  "adapter_sha256": freeze["adapter_sha256"], "final_freeze_sha256": digest(freeze),
                  "seconds": time.monotonic()-start, "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                  "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                  "final_holdout_families_consumed":80, "default_route_changed":False,
                  "rhino_called":False, "development_agent_plaintext_access":False}
        write_json(final / "public-results.json", {"rows": rows}, exclusive=True)
        write_json(final / "public-report.json", report, exclusive=True)
        print(json.dumps(report, ensure_ascii=False))
    except BaseException as exc:
        write_json(final / "failed.json", {"status":"failed_consumption_no_rerun", "error_type":type(exc).__name__})
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        write_json(final / "resource-settlement.json", {"seconds":time.monotonic()-start,
                   "final_budget_seconds_max":budget, "new_run_allowed":False})
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()


if __name__ == "__main__":
    main()
