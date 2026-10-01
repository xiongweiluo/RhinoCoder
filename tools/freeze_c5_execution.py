#!/usr/bin/env python3
"""Materialize the repository owner's explicitly granted conditional execution authorization.

This does not approve a PR on behalf of its owner and cannot expand any budget.
The authorization is bound to the code/data config actually executed.
"""
from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.c5_engineering import load_config  # noqa: E402
from training.c5_execution import digest, execution_hashes, write_json  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm-owner-request", required=True,
                   choices=["2026-10-01-two-days-complete-1-through-5"])
    p.add_argument("--output", type=Path, default=ROOT / "eval/c5/c5-execution-authorization.json")
    args = p.parse_args()
    c = load_config(); now = time.time()
    a = {"schema_version": "1.0", "experiment_id": c["experiment_id"], "contract_id": c["contract_id"],
         "authorized_by": "repository_owner", "authorization_recorded_epoch": now,
         "authorization_basis": "Owner message: 实际租期有两天，帮我把1-5依次全部完整高质量完成",
         "lease_remaining_hours_reported": 48, "execution_deadline_epoch": now + 47 * 3600,
         "lease_expiry_precision": "owner reports two days; conservative 47-hour execution ceiling, not provider billing verification",
         "hourly_price_verified": False, "new_rental_allowed": False,
         "diagnostic_gpu_hours_max": 4, "formal_gpu_hours_max": 8,
         "final_gpu_hours_max": 4, "total_gpu_hours_max": 16, "diagnostic_runs_max": 2,
         "formal_requires_engineering_pass": True, "conditional_formal_execution_authorized": True,
         "holdout_access_during_training": False, "final_claim_requires_owner_custody_execution": True,
         "engineering_config_sha256": digest(c), "execution_sha256": execution_hashes(),
         "validation_candidates": "epoch checkpoints 44/88/132 only; periodic recovery checkpoints are not candidates",
         "selection_order": ["sequence_exact", "arguments_exact", "parse_exact", "eval_loss"],
         "selection_tie_break": "earliest_checkpoint", "stop_export_reserve_seconds": 900,
         "operational_failure_policy": "stop, preserve report and complete checkpoints; no automatic configuration changes or extra diagnostic runs",
         "product_route_switch_authorized": False}
    write_json(args.output, a, exclusive=True)
    print("Frozen conditional C5 execution authorization: " + digest(a))


if __name__ == "__main__":
    main()
