#!/usr/bin/env python3
"""Audit an exported C5 training run; no weights loaded and no final data opened."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.c5_execution import (  # noqa: E402
    digest, execution_hashes, load_config, read_json, sha256_file,
    selection_key, verify_authorization, verify_checkpoint, write_json,
)


def audit(root: Path, authorization: Path) -> dict:
    """Only the three named development/formal runs are admissible."""
    auth = verify_authorization(authorization, load_config())
    events_path = root / "execution-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    starts = {e["segment_id"]: e for e in events if e["event"] == "start"}
    finishes = {e["segment_id"]: e for e in events if e["event"] == "finish"}
    if (len(starts) != sum(e["event"] == "start" for e in events)
        or len(finishes) != sum(e["event"] == "finish" for e in events)
        or starts.keys() != finishes.keys()):
        raise RuntimeError("duplicate/unsettled execution segment")
    if any(e["phase"] not in ("overfit", "system", "formal") for e in events):
        raise RuntimeError("export contains an out-of-scope execution phase")
    if not all(math.isfinite(float(e["seconds"])) and e["seconds"] >= 0 for e in finishes.values()):
        raise RuntimeError("invalid elapsed budget")
    hours = {phase: sum(e["seconds"] for e in finishes.values() if e["phase"] == phase) / 3600
             for phase in ("overfit", "system", "formal")}
    if hours["overfit"] + hours["system"] > 4 or hours["formal"] > 8 or sum(hours.values()) > 16:
        raise RuntimeError("budget exceeded")
    summaries = {}
    for phase, steps in (("overfit", 128), ("system", 26), ("formal", 132)):
        run = root / phase
        context = read_json(run / "context.json")
        result = read_json(run / "result.json")
        if (context["execution_sha256"] != execution_hashes()
            or context["config_sha256"] != digest(load_config())
            or context["cpu_report_sha256"] != sha256_file(ROOT / "eval/c5/c5-engineering-readiness.json")
            or context["dataset_manifest_sha256"] != sha256_file(ROOT / "eval/c5/dataset-v2-freeze-manifest.json")
            or context["authorization_sha256"] != digest(auth)
            or result["context_sha256"] != digest(context)
            or result["completed"] is not True or result["passed"] is not True
            or result["global_step"] != steps or result["final_holdout_rows_read"] != 0
            or context["final_holdout_rows_read"] != 0 or result["rhino_called"] is not False):
            raise RuntimeError("run context or completion mismatch: " + phase)
        metrics = [json.loads(line) for line in (run / "metrics.jsonl").read_text().splitlines()]
        step_rows = [r for r in metrics if "step" in r]
        if [r["step"] for r in step_rows] != list(range(1, steps + 1)):
            raise RuntimeError("non-contiguous optimizer ledger: " + phase)
        if not all(math.isfinite(float(r[k])) for r in step_rows for k in ("loss", "grad_norm", "learning_rate", "elapsed_seconds")):
            raise RuntimeError("non-finite metric: " + phase)
        checkpoints = {}
        for cp in sorted(run.glob("checkpoint-*")):
            verify_checkpoint(cp, digest(context))
            checkpoints[cp.name] = sha256_file(cp / "lineage.json")
        if not checkpoints or "checkpoint-" + str(steps) not in checkpoints:
            raise RuntimeError("final recovery checkpoint missing: " + phase)
        summaries[phase] = {"result": result, "context_sha256": digest(context),
            "optimizer_rows": len(step_rows), "verified_checkpoints": checkpoints,
            "loss_range": [min(r["loss"] for r in step_rows), max(r["loss"] for r in step_rows)],
            "grad_norm_range": [min(r["grad_norm"] for r in step_rows), max(r["grad_norm"] for r in step_rows)]}
    if summaries["overfit"]["result"]["resumed_from"] != 1 or "checkpoint-1" not in summaries["overfit"]["verified_checkpoints"]:
        raise RuntimeError("independent step-1 resume evidence missing")
    if summaries["system"]["result"]["training_families"] > 32:
        raise RuntimeError("system diagnostic exceeded family limit")
    registry = read_json(root / "formal/registry.json")
    if summaries["formal"]["result"]["training_records"] != 697 or summaries["formal"]["result"]["training_families"] != 320:
        raise RuntimeError("formal data scale drift")
    if registry != summaries["formal"]["result"]["registry"]:
        raise RuntimeError("registry/result disagreement")
    if registry["selected_checkpoint"] not in summaries["formal"]["verified_checkpoints"]:
        raise RuntimeError("selected checkpoint is outside verified export")
    if set(registry["files"]) != {"adapter_model.safetensors", "adapter_config.json"}:
        raise RuntimeError("unexpected registered adapter file")
    selected = root / "formal" / registry["selected_checkpoint"]
    if registry["files"] != {name: sha256_file(selected / name) for name in registry["files"]} or registry["adapter_sha256"] != digest(registry["files"]):
        raise RuntimeError("exported selected adapter differs from registry")
    if [r["step"] for r in registry["validation_candidates"]] != [44, 88, 132]:
        raise RuntimeError("formal selection candidates drift")
    best = max(registry["validation_candidates"], key=selection_key)
    if registry["selected_checkpoint"] != "checkpoint-" + str(best["step"]):
        raise RuntimeError("checkpoint violates frozen lexicographic/earliest selection")
    files = {p.relative_to(root).as_posix(): sha256_file(p)
             for phase in ("overfit", "system", "formal")
             for p in sorted((root / phase).rglob("*")) if p.is_file()}
    files["execution-events.jsonl"] = sha256_file(events_path)
    return {"schema_version": "1.0", "passed": True, "scope": "training/export integrity, not model quality",
        "experiment_id": registry["experiment_id"], "execution_revision": read_json(root / "formal/context.json")["source_revision"],
        "authorization_sha256": digest(auth), "gpu_hours": hours, "total_gpu_hours": sum(hours.values()),
        "stages": summaries, "exported_files": len(files), "exported_bytes": sum((root / name).stat().st_size for name in files),
        "export_file_manifest_sha256": digest(files), "files": files,
        "final_holdout_rows_read": 0, "rhino_called": False, "product_route_authorized": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-dir", type=Path, required=True)
    p.add_argument("--authorization", type=Path, default=ROOT / "eval/c5/c5-execution-authorization-v3.json")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = audit(a.artifact_dir, a.authorization)
    write_json(a.output, report, exclusive=True)
    print(json.dumps({k: v for k, v in report.items() if k not in ("stages", "files")}))


if __name__ == "__main__":
    main()
