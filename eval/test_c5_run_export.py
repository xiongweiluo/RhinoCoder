"""Synthetic export-integrity fixtures; never a real holdout or model loader."""
from pathlib import Path

import pytest

from tools.audit_c5_run_export import ROOT, audit
from training.c5_execution import (
    checkpoint_manifest, digest, execution_hashes, load_config, read_json,
    sha256_file, write_json,
)


def _fixture(root: Path):
    authorization = ROOT / "eval/c5/c5-execution-authorization-v3.json"
    events = []
    for phase, steps in (("overfit", 128), ("system", 26), ("formal", 132)):
        run = root / phase
        run.mkdir()
        context = {"execution_sha256": execution_hashes(), "authorization_sha256": digest(read_json(authorization)),
            "config_sha256": digest(load_config()), "cpu_report_sha256": sha256_file(ROOT / "eval/c5/c5-engineering-readiness.json"),
            "dataset_manifest_sha256": sha256_file(ROOT / "eval/c5/dataset-v2-freeze-manifest.json"),
            "final_holdout_rows_read": 0, "source_revision": "synthetic"}
        write_json(run / "context.json", context)
        result = {"completed": True, "passed": True, "global_step": steps, "final_holdout_rows_read": 0,
            "rhino_called": False, "context_sha256": digest(context), "resumed_from": 1 if phase == "overfit" else None,
            "training_records": 697 if phase == "formal" else 64, "training_families": 320 if phase == "formal" else 32}
        for step in ({1, steps} if phase == "overfit" else {steps}):
            cp = run / f"checkpoint-{step}"
            cp.mkdir()
            for name in ("adapter_model.safetensors", "adapter_config.json", "state.pt"):
                (cp / name).write_bytes(b"synthetic, not a model")
            write_json(cp / "progress.json", {"global_step": step})
            write_json(cp / "lineage.json", checkpoint_manifest(cp, digest(context)))
        (run / "metrics.jsonl").write_text("".join(
            '{"step":%d,"loss":0.1,"grad_norm":0.2,"learning_rate":0.001,"elapsed_seconds":1}\n' % step
            for step in range(1, steps + 1)))
        if phase == "formal":
            files = {name: sha256_file(run / "checkpoint-132" / name)
                     for name in ("adapter_model.safetensors", "adapter_config.json")}
            registry = {"experiment_id": "synthetic", "selected_checkpoint": "checkpoint-132",
                "files": files, "adapter_sha256": digest(files), "validation_candidates": [
                    {"step": s, "sequence_exact": s / 132, "arguments_exact": 1, "parse_exact": 1, "eval_loss": .1}
                    for s in (44, 88, 132)]}
            result["registry"] = registry
            write_json(run / "registry.json", registry)
        write_json(run / "result.json", result)
        events.extend([{"event": "start", "segment_id": phase, "phase": phase},
                       {"event": "finish", "segment_id": phase, "phase": phase, "seconds": 1}])
    import json
    (root / "execution-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return authorization


def test_export_checks_all_bytes_without_opening_final(tmp_path):
    auth = _fixture(tmp_path)
    final = tmp_path / "final"
    final.mkdir()
    (final / "private.jsonl").write_bytes(b"\xffnot admissible input")
    report = audit(tmp_path, auth)
    assert report["passed"] and report["final_holdout_rows_read"] == 0
    assert not any(name.startswith("final/") for name in report["files"])
    (tmp_path / "formal/checkpoint-132/state.pt").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="checkpoint lineage"):
        audit(tmp_path, auth)


def test_export_rejects_noncontiguous_steps_and_unsettled_budget(tmp_path):
    auth = _fixture(tmp_path)
    p = tmp_path / "execution-events.jsonl"
    original = p.read_text()
    p.write_text("\n".join(original.splitlines()[:-1]) + "\n")
    with pytest.raises(RuntimeError, match="unsettled"):
        audit(tmp_path, auth)
    p.write_text(original)
    p = tmp_path / "system/metrics.jsonl"
    p.write_text("\n".join(p.read_text().splitlines()[1:]) + "\n")
    with pytest.raises(RuntimeError, match="non-contiguous"):
        audit(tmp_path, auth)
