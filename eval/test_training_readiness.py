from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import training.preregistration as preregistration

from training.cluster import load_cluster_config, placeholder_paths, validate_cluster_config
from training.config import (
    DEFAULT_CONFIG,
    ReadinessError,
    audit_readiness,
    config_sha256,
    load_config,
    project_path,
    sha256_file,
)
from training.data import (
    load_samples,
    parse_generated_tool_calls,
    render_training_example,
    score_tool_generations,
)
from training.gpu_smoke import GPU_SMOKE_STEPS, gpu_smoke_output_dir
from training.model_cache import pretrained_load_kwargs
from training.preregistration import assert_formal_training_ready, build_freeze_payload
from training.reporting import render_experiment_report, write_run_manifest
from training.runtime import _load_base_model, _load_tokenizer, latest_checkpoint, resolve_resume
from training.smoke import run_cpu_smoke
from tools.freeze_preregistration import build_complete_payload


def test_locked_readiness_contract_and_real_a5_inputs_pass() -> None:
    if not project_path("data/training/a5/manifest.json").is_file():
        pytest.skip("private A5 artifacts are intentionally absent from a clean checkout")
    audit = audit_readiness()

    assert audit.passed, audit.findings
    assert audit.train_rows == 210
    assert audit.validation_rows == 45
    assert audit.status == "C0/C1 Passed — C2 Completed; C3 Freeze/Preflight Pending"
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


def test_model_cache_env_drives_online_and_strict_offline_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "hf-cache"
    monkeypatch.setenv("RHINOCODER_MODEL_CACHE", str(cache))
    monkeypatch.setenv("HF_TOKEN", "test-only-token")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    online = pretrained_load_kwargs()
    assert online["cache_dir"] == cache
    assert online["local_files_only"] is False
    assert online["token"] == "test-only-token"

    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    offline = pretrained_load_kwargs()
    assert offline["cache_dir"] == cache
    assert offline["local_files_only"] is True
    assert offline["token"] is None


def test_runtime_model_and_tokenizer_share_cache_and_offline_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "shared-cache"
    snapshot = (
        cache
        / "models--Qwen--Qwen2.5-Coder-7B-Instruct"
        / "snapshots"
        / "c03e6d358207e414f1eca0bb1891e29f1db0e242"
    )
    snapshot.mkdir(parents=True)
    monkeypatch.setenv("RHINOCODER_MODEL_CACHE", str(cache))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    calls: dict[str, dict] = {}

    class FakeTokenizer:
        pad_token_id = None
        eos_token = "<eos>"
        padding_side = "left"

        @property
        def pad_token(self):
            return None

        @pad_token.setter
        def pad_token(self, value):
            self.pad_token_id = 0

    class TokenizerLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["tokenizer"] = {"source": source, **kwargs}
            return FakeTokenizer()

    class ModelLoader:
        @staticmethod
        def from_pretrained(source, **kwargs):
            calls["model"] = {"source": source, **kwargs}
            return SimpleNamespace(config=SimpleNamespace(use_cache=True))

    stack = {
        "AutoTokenizer": TokenizerLoader,
        "AutoModelForCausalLM": ModelLoader,
        "BitsAndBytesConfig": lambda **kwargs: kwargs,
        "torch": SimpleNamespace(bfloat16="bf16"),
    }
    config = load_config()
    tokenizer = _load_tokenizer(stack, config)
    model = _load_base_model(stack, config)

    assert tokenizer.padding_side == "right"
    assert model.config.use_cache is False
    for kind in ("tokenizer", "model"):
        assert calls[kind]["cache_dir"] == cache
        assert calls[kind]["local_files_only"] is True
        assert calls[kind]["token"] is None
        assert calls[kind]["source"] == str(snapshot)
        assert calls[kind]["revision"] is None
    assert config["base_model"]["id"] == "Qwen/Qwen2.5-Coder-7B-Instruct"
    assert config["base_model"]["revision"] == "c03e6d358207e414f1eca0bb1891e29f1db0e242"


def test_formal_training_gate_requires_explicit_confirmation() -> None:
    with pytest.raises(ReadinessError, match="formal training is locked"):
        assert_formal_training_ready(load_config(), confirmed=False)


def test_formal_training_gate_verifies_completed_c1_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config()
    checkpoint = tmp_path / "checkpoint-2"
    checkpoint.mkdir()
    trainer_state = checkpoint / "trainer_state.json"
    optimizer_state = checkpoint / "optimizer.pt"
    trainer_state.write_text('{"global_step": 2}\n', encoding="utf-8")
    optimizer_state.write_bytes(b"optimizer-state")
    revision = "a" * 40
    monkeypatch.setattr(
        preregistration,
        "audit_preregistration_freeze",
        lambda _path: {
            "passed": True,
            "experiment_id": config["experiment_id"],
            "git_revision": revision,
            "freeze_manifest_sha256": "b" * 64,
            "holdout_read": False,
        },
    )
    report = {
        "experiment_id": config["experiment_id"],
        "config_sha256": config_sha256(config),
        "git_revision": revision,
        "c0_freeze_manifest_sha256": "b" * 64,
        "passed": True,
        "status": "complete",
        "device": "cuda",
        "checkpoint_save": True,
        "checkpoint_restore": True,
        "optimizer_step": True,
        "formal_run_directory_written": False,
        "model_registry_written": False,
        "holdout_read": False,
        "p2_read": False,
        "non_finite_detected": False,
        "steps": 2,
        "resumed_from_step": 1,
        "samples": {"train": 2, "validation": 1, "holdout": 0},
        "smoke_limits": {"maximum_optimizer_steps": 2},
        "checkpoint": checkpoint.name,
        "checkpoint_files": {
            "trainer_state.json": sha256_file(trainer_state),
            "optimizer.pt": sha256_file(optimizer_state),
        },
    }
    report_path = tmp_path / "smoke-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = assert_formal_training_ready(
        config,
        confirmed=True,
        freeze_manifest_path=tmp_path / "unused-freeze.json",
        c1_report_path=report_path,
    )

    assert result["c0"]["git_revision"] == revision
    optimizer_state.write_bytes(b"changed")
    with pytest.raises(ReadinessError, match="hash mismatch"):
        assert_formal_training_ready(
            config,
            confirmed=True,
            freeze_manifest_path=tmp_path / "unused-freeze.json",
            c1_report_path=report_path,
        )


def test_gpu_smoke_directory_isolated_from_formal_runs(tmp_path: Path) -> None:
    config = load_config()
    assert GPU_SMOKE_STEPS == 2
    target = gpu_smoke_output_dir(config, tmp_path / "gpu-smoke")
    assert target == (tmp_path / "gpu-smoke").resolve()
    with pytest.raises(ReadinessError, match="formal C2"):
        gpu_smoke_output_dir(config, config["checkpoint"]["root"])
    with pytest.raises(ReadinessError, match="data/training/runs"):
        gpu_smoke_output_dir(config, "data/training/runs/unsafe-smoke")


def test_c0_payload_uses_manifest_hash_without_reading_holdout() -> None:
    if not project_path("data/training/a5/manifest.json").is_file():
        pytest.skip("private A5 manifest is intentionally absent from a clean checkout")
    payload = build_freeze_payload()

    assert payload["status"] == "freeze_candidate"
    assert payload["a5"]["holdout"]["file_read"] is False
    assert payload["a5"]["holdout"]["sha256_from_manifest"] == (
        "cdafcaa1a5f19fe748260b1f78ddee38c63e78d3959a326504e60e8fc585390e"
    )
    assert payload["gates"]["c2_formal_training_started"] is False

    complete = build_complete_payload()
    assert complete["evaluation_contracts"]["p2"]["role"] == (
        "evaluation_only_not_a_training_consumer"
    )
    assert len(complete["evaluation_contracts"]["p2"]["aggregate_sha256"]) == 64


def test_formal_preregistration_is_freeze_ready_and_externalized() -> None:
    text = Path("docs/training-preregistration.md").read_text(encoding="utf-8")

    assert "FREEZE READY" in text
    assert "EXTERNAL MANIFEST NOT YET CREATED" in text
    assert "ae38f0e158dc166940e90e2e335953914e969f841546b3d67e8a1a023ce4bcb1" in text
    assert "本文件不记录自身 SHA-256" in text
    assert "validation 表现差" in text
    assert "GO" in text and "MORE-DATA" in text and "NO-GO" in text


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


def test_gpu_host_template_is_complete_but_requires_local_values() -> None:
    config = load_cluster_config("training/school_gpu.example.json")

    assert validate_cluster_config(config, allow_placeholders=True) == []
    assert config["status"] == "template_requires_local_values"
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
