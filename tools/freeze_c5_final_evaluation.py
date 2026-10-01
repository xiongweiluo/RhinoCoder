#!/usr/bin/env python3
"""Freeze a completed C5 formal adapter and owner-only final code, without holdout access."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from training.c5_execution import digest,read_json,sha256_file,write_json  # noqa: E402

FILES=("tools/run_c5_owner_final.py","tools/run_c5_final_remote.py",
       "training/c5_final_evaluation.py","training/c5_execution.py","training/c5_inventory.py",
       "training/c5_contract.py","training/tool_contract_candidate.py",
       "training/tool_contract_v3_candidate.py","training/tool_selector_v4_candidate.py",
       "training/c5_holdout.py")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--formal-result",type=Path,required=True)
    p.add_argument("--registry",type=Path,required=True)
    p.add_argument("--output",type=Path,default=ROOT/"eval/c5/c5-final-evaluation-freeze.json")
    a=p.parse_args()
    result=read_json(a.formal_result);registry=read_json(a.registry)
    if not result.get("completed") or result.get("passed") is not True or result.get("registry")!=registry:
        raise RuntimeError("formal adapter registration not complete")
    revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    spec=ROOT/"eval/c5/offline-freeze-spec.json"
    freeze={"schema_version":"1.0","experiment_id":registry["experiment_id"],
            "contract_id":registry["contract_id"],"code_revision":revision,
            "adapter_sha256":registry["adapter_sha256"],
            "selected_checkpoint":registry["selected_checkpoint"],
            "formal_result_sha256":sha256_file(a.formal_result),"registry_sha256":sha256_file(a.registry),
            "thresholds_sha256":sha256_file(spec),
            "commitment_sha256":digest(read_json(ROOT/"eval/c5/final-holdout-commitment.json")),
            "implementation_sha256":{name:sha256_file(ROOT/name) for name in FILES},
            "data_unlock_allowed_only_to":"repository_owner",
            "final_holdout_rows_read":0,"consumption_claim_executed":False,
            "raw_outputs_private_to_custodian":True,"new_final_runs_max":1,
            "selection_and_hyperparameter_changes_after_claim_allowed":False,
            "comparison":"paired same frozen base NF4/BF16; LoRA disabled/enabled on same model; counterbalanced family order",
            "numeric_loading":"same prepare_model_for_kbit_training FP32 nonquantized casts and allow_tf32=true as formal validation; seed 20260928; no gradient checkpointing/backward; shared base with adapter disabled/enabled",
            "safety_scoring":"refusal stratum choosing a tool is a conservative critical prediction error even though no dispatch occurs",
            "metric_scope":"family-level complete strict sequence under supplied step contexts; not Rhino geometry success",
            "c5_5_requires_offline_gate_pass":True,"product_route_authorized":False}
    write_json(a.output,freeze,exclusive=True)
    print("Final evaluation freeze SHA-256: "+digest(freeze))


if __name__=="__main__":main()
