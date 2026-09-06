from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.cluster import load_cluster_config, placeholder_paths, validate_cluster_config
from training.config import DEFAULT_CONFIG, ReadinessError, audit_readiness, load_config, project_path
from training.data import (
    load_samples,
    parse_generated_tool_calls,
    render_training_example,
    score_tool_generations,
)
from training.reporting import render_experiment_report, write_run_manifest
from training.runtime import latest_checkpoint, resolve_resume
from training.smoke import run_cpu_smoke


def test_locked_readiness_contract_and_real_a5_inputs_pass() -> None:
    if not project_path("data/training/a5/manifest.json").is_file():
        pytest.skip("private A5 artifacts are intentionally absent from a clean checkout")
    audit = audit_readiness()

    assert audit.passed, audit.findings
    assert audit.train_rows == 210
    assert audit.validation_rows == 45
    assert audit.status == "Training Ready — Waiting for School GPU Access"
    assert len(audit.config_sha256) == 64


def test_locked_static_readiness_contract_passes_without_private_data() -> None:
    audit = audit_readiness(require_data=False)

    assert audit.passed, audit.findings
    assert "data audit deferred" in audit.checks


def test_holdout_cannot_be_loaded_by_training_code(tmp_path: Path) -> None:
    target = tmp_path / "holdout" / "instruction_to_tool_call.jsonl"
    target.parent.mkdir()
    target.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ReadinessError, match="holdout"):
        load_samples(target, split="validation", view="instruction_to_tool_call")


def test_tool_call_parser_and_metrics_are_structural() -> None:
    sample = {
        "messages": [
            {"role": "user", "content": "box"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "create_box",
                            "arguments": '{"width": 2, "depth": 3, "height": 4}',
                        }
                    }
                ],
            },
        ]
    }
    text = '<tool_call>\n{"name":"create_box","arguments":{"depth":3,"height":4,"width":2}}\n</tool_call>'

    assert parse_generated_tool_calls(text) == [
        {"name": "create_box", "arguments": {"depth": 3, "height": 4, "width": 2}}
    ]
    metrics = score_tool_generations([sample], [text])
    assert metrics["tool_call_parse_rate"] == 1
    assert metrics["tool_sequence_exact_rate"] == 1


def test_training_renderer_decodes_serialized_arguments_for_qwen_template() -> None:
    class RecordingTokenizer:
        def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
            rendered = json.dumps(messages[:1], ensure_ascii=False, sort_keys=True) + "<assistant>"
            if len(messages) > 1:
                rendered += json.dumps(messages[1:], ensure_ascii=False, sort_keys=True)
            return rendered

    messages = [
        {"role": "user", "content": "box"},
        {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "create_box", "arguments": '{"width": 2}'}}
            ],
        },
    ]
    tokenizer = RecordingTokenizer()
    prompt, full = render_training_example(tokenizer, messages)

    assert prompt.endswith("<assistant>")
    assert '"arguments": {"width": 2}' in full
    assert messages[1]["tool_calls"][0]["function"]["arguments"] == '{"width": 2}'


def test_invalid_generated_tool_call_is_not_counted() -> None:
    sample = {
        "messages": [
            {"role": "user", "content": "sphere"},
            {"role": "assistant", "tool_calls": [{"function": {"name": "create_sphere", "arguments": "{}"}}]},
        ]
    }
    metrics = score_tool_generations([sample], ["not a tool call"])
    assert metrics["tool_call_parse_rate"] == 0
    assert metrics["tool_sequence_exact_rate"] == 0


def test_resume_discovers_highest_checkpoint_and_rejects_external_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    for step in (10, 30, 20):
        checkpoint = run_dir / f"checkpoint-{step}"
        checkpoint.mkdir(parents=True)
        (checkpoint / "trainer_state.json").write_text("{}", encoding="utf-8")

    assert latest_checkpoint(run_dir).name == "checkpoint-30"
    assert resolve_resume(run_dir, "auto").endswith("checkpoint-30")
    with pytest.raises(ReadinessError, match="inside"):
        resolve_resume(run_dir, str(tmp_path / "elsewhere"))
    with pytest.raises(ReadinessError, match="inside"):
        resolve_resume(run_dir, str(run_dir / ".." / "elsewhere"))


def test_run_manifest_refuses_config_drift(tmp_path: Path) -> None:
    config = load_config()
    write_run_manifest(tmp_path, config)
    changed = json.loads(json.dumps(config))
    changed["training"]["learning_rate"] = 0.1

    with pytest.raises(ReadinessError, match="config_sha256"):
        write_run_manifest(tmp_path, changed)


def test_cpu_smoke_trains_saves_resumes_and_evaluates(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    if not project_path("data/training/a5/manifest.json").is_file():
        pytest.skip("private A5 artifacts are intentionally absent from a clean checkout")
    result = run_cpu_smoke(output_dir=tmp_path / "smoke")

    assert result["passed"]
    assert result["steps"] == 2
    assert result["resumed_from_step"] == 1
    assert result["checkpoint_save"]
    assert result["checkpoint_restore"]
    assert result["adapter_only_trainable"]
    assert result["samples"] == {"train": 2, "validation": 1, "holdout": 0}
    assert (tmp_path / "smoke/checkpoint-step-0001/manifest.json").is_file()
    assert (tmp_path / "smoke/checkpoint-step-0002/manifest.json").is_file()
    assert (tmp_path / "smoke/smoke-report.json").is_file()


def test_school_gpu_template_is_complete_but_explicitly_awaiting_access() -> None:
    config = load_cluster_config("training/school_gpu.example.json")

    assert validate_cluster_config(config, allow_placeholders=True) == []
    assert placeholder_paths(config)
    strict = validate_cluster_config(config, allow_placeholders=False)
    assert any("unresolved access fields" in finding for finding in strict)


@pytest.mark.parametrize("scheduler_type", ["slurm", "pbs", "direct"])
def test_school_gpu_inventory_accepts_supported_scheduler_types(scheduler_type: str) -> None:
    raw = Path("training/school_gpu.example.json").read_text(encoding="utf-8")
    raw = raw.replace("REQUIRED_AT_ACCESS", "configured")
    raw = raw.replace("RECORD_AT_ACCESS", "recorded")
    raw = raw.replace("VERIFY_AT_ACCESS", "verified")
    config = json.loads(raw)
    config["scheduler"]["type"] = scheduler_type

    assert validate_cluster_config(config, allow_placeholders=False) == []


def test_experiment_report_handles_pretraining_state(tmp_path: Path) -> None:
    config = load_config(DEFAULT_CONFIG)
    text = render_experiment_report(tmp_path, config)

    assert "incomplete" in text
    assert config["base_model"]["revision"] in text
    assert "holdout" in text
