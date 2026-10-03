from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from training.c5_engineering import load_config
from training.c5_execution import (
    ExecutionError, checkpoint_manifest, digest, finite, score_family,
    selection_key, verify_authorization, verify_checkpoint, write_json,
)


def test_validation_lexicographic_selection_not_loss_only():
    first = {"sequence_exact": .5, "arguments_exact": .5, "parse_exact": .9, "eval_loss": 1.0}
    second = {**first, "sequence_exact": .6, "eval_loss": 3.0}
    assert selection_key(second) > selection_key(first)
    assert selection_key({**first, "arguments_exact": .6}) > selection_key(first)
    assert selection_key({**first, "parse_exact": 1.0}) > selection_key(first)
    assert selection_key({**first, "eval_loss": .9}) > selection_key(first)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_stops(value):
    with pytest.raises(ExecutionError): finite(value, "loss")


def test_checkpoint_byte_tamper_and_context_rejected(tmp_path: Path):
    for name in ("adapter_model.safetensors", "adapter_config.json", "state.pt"):
        (tmp_path / name).write_bytes(b"synthetic")
    write_json(tmp_path / "progress.json", {"global_step": 1})
    write_json(tmp_path / "lineage.json", checkpoint_manifest(tmp_path, "context"))
    assert verify_checkpoint(tmp_path, "context")["global_step"] == 1
    with pytest.raises(ExecutionError): verify_checkpoint(tmp_path, "other")
    (tmp_path / "state.pt").write_bytes(b"tampered")
    with pytest.raises(ExecutionError): verify_checkpoint(tmp_path, "context")


def test_authorization_rejects_code_budget_or_owner_drift(tmp_path: Path):
    config = load_config()
    a = {"experiment_id": config["experiment_id"], "contract_id": config["contract_id"],
         "authorized_by": "repository_owner", "engineering_config_sha256": digest(config),
         "execution_sha256": {"fake": "hash"}, "diagnostic_gpu_hours_max": 4,
         "formal_gpu_hours_max": 8, "final_gpu_hours_max": 4, "total_gpu_hours_max": 16,
         "diagnostic_runs_max": 2, "lease_remaining_hours_reported": 48,
         "new_rental_allowed": False, "holdout_access_during_training": False,
         "formal_requires_engineering_pass": True, "conditional_formal_execution_authorized": True,
         "execution_deadline_epoch": 1800000000}
    path = tmp_path / "approval.json"
    with patch("training.c5_execution.execution_hashes", return_value={"fake": "hash"}):
        write_json(path, a)
        assert verify_authorization(path, config) == a
        for key, value in (("authorized_by", "agent"), ("total_gpu_hours_max", 20),
                           ("execution_sha256", {}), ("holdout_access_during_training", True)):
            write_json(path, {**a, key: value})
            with pytest.raises(ExecutionError): verify_authorization(path, config)


def _generator(raw):
    return {"raw": raw, "tokens": 4, "seconds": .1, "prompt_sha256": "a"*64,
            "output_sha256": "b"*64}


def test_wrong_selection_invokes_actual_single_schema_not_gold():
    family = {"family_id": "synthetic", "category": "core_invocation", "records": [
        {"record_id": "s", "stage": "selector", "user_step": "test", "selected_tool": "create_box"},
        {"record_id": "i", "stage": "invocation", "user_step": "test", "selected_tool": "create_box", "arguments": {}}]}
    class Rendered: prompt = "test"
    with patch("training.c5_execution.render_selection", return_value=Rendered()), \
         patch("training.c5_execution.parse_selection", return_value="create_sphere"), \
         patch("training.c5_execution.render_invocation", return_value=Rendered()) as render, \
         patch("training.c5_execution.parse_invocation", return_value={"arguments": {}}):
        row = score_family(family, lambda *_: _generator("{}"), None, [])
        assert render.call_args.args[3] == "create_sphere"
        assert row["parse_exact"] and not row["sequence_exact"]
        assert not row["tool_name_exact"] and not row["arguments_exact"]


def test_invalid_selector_fails_closed_without_invocation():
    from training.tool_contract_candidate import ContractError
    family = {"family_id": "synthetic", "category": "core_invocation", "records": [
        {"record_id": "s", "stage": "selector", "user_step": "test", "selected_tool": "create_box"},
        {"record_id": "i", "stage": "invocation", "user_step": "test", "selected_tool": "create_box", "arguments": {}}]}
    class Rendered: prompt = "test"
    with patch("training.c5_execution.render_selection", return_value=Rendered()), \
         patch("training.c5_execution.parse_selection", side_effect=ContractError("bad")), \
         patch("training.c5_execution.render_invocation") as render:
        row = score_family(family, lambda *_: _generator("bad"), None, [])
        assert not row["parse_exact"] and not row["sequence_exact"]
        assert row["receipts"][0]["output_sha256"] == "b"*64
        assert row["repair_count"] == row["dispatch_count"] == 0
        render.assert_not_called()


def test_output_reports_are_exclusive(tmp_path: Path):
    p = tmp_path / "result.json"
    write_json(p, {"passed": True}, exclusive=True)
    with pytest.raises(FileExistsError): write_json(p, {"passed": False}, exclusive=True)
    assert json.loads(p.read_text())["passed"] is True
