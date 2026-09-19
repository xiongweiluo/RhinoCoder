"""Isolated two-process CUDA QLoRA smoke with checkpoint lineage verification."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    CausalLMCollator,
    ConversationDataset,
    load_samples,
    render_training_example,
)
from training.preregistration import (
    DEFAULT_FREEZE_MANIFEST,
    assert_formal_training_ready,
    audit_preregistration_freeze,
)
from training.reporting import atomic_json, environment_snapshot, git_revision, utc_now
from training.runtime import (
    _attach_lora,
    _load_base_model,
    _load_tokenizer,
    _require_training_stack,
    latest_checkpoint,
    require_gpu,
)


DEFAULT_GPU_SMOKE_ROOT = "data/training/gpu-smoke"
GPU_SMOKE_STEPS = 2
GPU_SMOKE_TRAIN_SAMPLES = 2
GPU_SMOKE_VALIDATION_SAMPLES = 1


def gpu_smoke_output_dir(config: Mapping[str, Any], output_dir: str | Path | None = None) -> Path:
    target = project_path(
        output_dir or Path(DEFAULT_GPU_SMOKE_ROOT) / str(config["experiment_id"])
    ).resolve()
    formal_root = project_path(config["checkpoint"]["root"]).resolve()
    formal_runs_root = project_path("data/training/runs").resolve()
    if target == formal_root or formal_root in target.parents:
        raise ReadinessError("GPU smoke output must not be inside the formal C2 run directory")
    if target == formal_runs_root or formal_runs_root in target.parents:
        raise ReadinessError("GPU smoke output must not be inside data/training/runs")
    if "holdout" in {part.lower() for part in target.parts}:
        raise ReadinessError("GPU smoke output path must not reference holdout")
    return target


def _select_shortest(
    samples: Sequence[Mapping[str, Any]], tokenizer: Any, count: int
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for source in samples:
        sample = dict(source)
        _prompt, full = render_training_example(tokenizer, sample["messages"])
        length = len(tokenizer(full, add_special_tokens=False)["input_ids"])
        ranked.append((length, str(sample.get("sample_id") or ""), sample))
    ranked.sort(key=lambda item: (item[0], item[1]))
    if len(ranked) < count:
        raise ReadinessError(f"GPU smoke needs {count} samples, found {len(ranked)}")
    return [item[2] for item in ranked[:count]]


def _selected_samples(
    config: Mapping[str, Any], tokenizer: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = config["data"]
    view = str(data["view"])
    train = load_samples(data["train"]["path"], split="train", view=view)
    validation = load_samples(data["validation"]["path"], split="validation", view=view)
    return (
        _select_shortest(train, tokenizer, GPU_SMOKE_TRAIN_SAMPLES),
        _select_shortest(validation, tokenizer, GPU_SMOKE_VALIDATION_SAMPLES),
    )


def _sample_ids(samples: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(sample.get("sample_id") or "") for sample in samples]


def _checkpoint_hashes(path: Path) -> dict[str, str]:
    if not (path / "trainer_state.json").is_file():
        raise ReadinessError(f"GPU smoke checkpoint lacks trainer_state.json: {path}")
    hashes = {
        item.relative_to(path).as_posix(): sha256_file(item)
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }
    if not any(name.startswith("optimizer") for name in hashes):
        raise ReadinessError("GPU smoke checkpoint does not contain optimizer state")
    return hashes


def _verify_hashes(path: Path, expected: Mapping[str, str]) -> None:
    actual = _checkpoint_hashes(path)
    if dict(expected) != actual:
        raise ReadinessError("GPU smoke checkpoint files changed before resume")


def _read_global_step(path: Path) -> int:
    state = json.loads((path / "trainer_state.json").read_text(encoding="utf-8"))
    return int(state.get("global_step") or 0)


def _build_trainer(
    stack: Mapping[str, Any],
    config: Mapping[str, Any],
    output_dir: Path,
    model: Any,
    tokenizer: Any,
    train_dataset: Any,
    validation_dataset: Any,
    *,
    phase: str,
) -> Any:
    training = config["training"]
    callback_base = stack["TrainerCallback"]

    class StopAfterCheckpointCallback(callback_base):  # type: ignore[valid-type,misc]
        def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> Any:
            if phase == "initial" and int(state.global_step) >= 1:
                control.should_save = True
                control.should_training_stop = True
            return control

    arguments = stack["TrainingArguments"](
        output_dir=str(output_dir),
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=float(training["learning_rate"]),
        max_steps=GPU_SMOKE_STEPS,
        warmup_ratio=0.0,
        weight_decay=float(training["weight_decay"]),
        max_grad_norm=float(training["max_grad_norm"]),
        lr_scheduler_type=str(training["lr_scheduler"]),
        optim=str(training["optimizer"]),
        gradient_checkpointing=bool(training["gradient_checkpointing"]),
        bf16=bool(training["bf16"]),
        tf32=bool(training["tf32"]),
        seed=int(training["seed"]),
        data_seed=int(training["data_seed"]),
        logging_strategy="steps",
        logging_steps=1,
        logging_first_step=True,
        eval_strategy="no",
        save_strategy="steps",
        save_steps=1,
        save_total_limit=2,
        report_to="none",
        remove_unused_columns=False,
        dataloader_num_workers=0,
    )
    return stack["Trainer"](
        model=model,
        args=arguments,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=CausalLMCollator(tokenizer.pad_token_id),
        processing_class=tokenizer,
        callbacks=[StopAfterCheckpointCallback()],
    )


def _base_lineage(config: Mapping[str, Any], c0: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "c1-gpu-smoke-resume",
        "experiment_id": config["experiment_id"],
        "config_sha256": config_sha256(config),
        "git_revision": git_revision(),
        "c0_freeze_manifest_sha256": c0["freeze_manifest_sha256"],
        "base_model": {
            "id": config["base_model"]["id"],
            "revision": config["base_model"]["revision"],
        },
        "data": {
            "train_sha256": config["data"]["train"]["sha256"],
            "validation_sha256": config["data"]["validation"]["sha256"],
            "view": config["data"]["view"],
        },
        "holdout_read": False,
        "p2_read": False,
        "formal_run_directory_written": False,
        "model_registry_written": False,
    }


def _load_state(
    target: Path, config: Mapping[str, Any], c0: Mapping[str, Any]
) -> dict[str, Any]:
    state_path = target / "smoke-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"cannot load initial GPU smoke state {state_path}: {exc}") from exc
    expected = _base_lineage(config, c0)
    for key in (
        "experiment_id",
        "config_sha256",
        "git_revision",
        "c0_freeze_manifest_sha256",
        "base_model",
        "data",
        "holdout_read",
        "p2_read",
    ):
        if state.get(key) != expected.get(key):
            raise ReadinessError(f"GPU smoke state lineage differs at {key}")
    checkpoint = target / str(state.get("checkpoint") or "")
    if checkpoint.parent != target:
        raise ReadinessError("GPU smoke checkpoint must be a direct child of the isolated output directory")
    if _read_global_step(checkpoint) != 1:
        raise ReadinessError("GPU smoke resume requires the step-1 checkpoint")
    _verify_hashes(checkpoint, state.get("checkpoint_files") or {})
    return state


def run_gpu_smoke(
    config_path: str | Path = DEFAULT_CONFIG,
    *,
    phase: str,
    output_dir: str | Path | None = None,
    freeze_manifest: str | Path = DEFAULT_FREEZE_MANIFEST,
) -> dict[str, Any]:
    """Run step 1 or resume step 2; never call the formal trainer or model registry."""

    if phase not in {"initial", "resume"}:
        raise ReadinessError("GPU smoke phase must be 'initial' or 'resume'")
    audit = audit_readiness(config_path)
    if not audit.passed:
        raise ReadinessError("readiness audit failed: " + "; ".join(audit.findings))
    config = load_config(config_path)
    c0 = audit_preregistration_freeze(freeze_manifest)
    target = gpu_smoke_output_dir(config, output_dir)
    if phase == "initial" and target.exists() and any(target.iterdir()):
        raise ReadinessError("initial GPU smoke refuses a non-empty output directory")
    if phase == "resume" and not target.is_dir():
        raise ReadinessError("resume GPU smoke requires a completed initial phase")
    target.mkdir(parents=True, exist_ok=True)
    lineage = _base_lineage(config, c0)
    started = time.monotonic()
    stack = _require_training_stack()
    torch = stack["torch"]
    require_gpu(torch, config)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    try:
        tokenizer = _load_tokenizer(stack, config)
        selected_train, selected_validation = _selected_samples(config, tokenizer)
        state = None
        if phase == "resume":
            state = _load_state(target, config, c0)
            if state.get("train_sample_ids") != _sample_ids(selected_train):
                raise ReadinessError("GPU smoke train sample selection changed before resume")
            if state.get("validation_sample_ids") != _sample_ids(selected_validation):
                raise ReadinessError("GPU smoke validation sample selection changed before resume")

        maximum = int(config["training"]["max_sequence_length"])
        train_dataset = ConversationDataset(selected_train, tokenizer, maximum)
        validation_dataset = ConversationDataset(selected_validation, tokenizer, maximum)
        model = _attach_lora(stack, _load_base_model(stack, config), config)
        trainable_parameters = sum(p.numel() for p in model.parameters() if p.requires_grad)
        all_parameters = sum(p.numel() for p in model.parameters())
        trainer = _build_trainer(
            stack,
            config,
            target,
            model,
            tokenizer,
            train_dataset,
            validation_dataset,
            phase=phase,
        )
        resume_checkpoint = str(target / state["checkpoint"]) if state else None
        train_result = trainer.train(resume_from_checkpoint=resume_checkpoint)
        torch.cuda.synchronize()
        checkpoint = latest_checkpoint(target)
        expected_step = 1 if phase == "initial" else GPU_SMOKE_STEPS
        if checkpoint is None or _read_global_step(checkpoint) != expected_step:
            raise ReadinessError(f"GPU smoke expected checkpoint step {expected_step}")
        checkpoint_hashes = _checkpoint_hashes(checkpoint)
        losses = [
            float(row["loss"])
            for row in trainer.state.log_history
            if isinstance(row.get("loss"), (int, float))
        ]
        validation_metrics: dict[str, Any] = {}
        if phase == "resume":
            validation_metrics = dict(trainer.evaluate(eval_dataset=validation_dataset))
        numeric = losses + [
            float(value)
            for key, value in validation_metrics.items()
            if key == "eval_loss" and isinstance(value, (int, float))
        ]
        non_finite = not numeric or any(not math.isfinite(value) for value in numeric)
        report = {
            **lineage,
            "status": "initial_complete" if phase == "initial" else "complete",
            "passed": phase == "resume" and not non_finite,
            "phase": phase,
            "device": "cuda",
            "created_at": utc_now(),
            "samples": {
                "train": len(selected_train),
                "validation": len(selected_validation),
                "holdout": 0,
            },
            "train_sample_ids": _sample_ids(selected_train),
            "validation_sample_ids": _sample_ids(selected_validation),
            "steps": expected_step,
            "resumed_from_step": 1 if phase == "resume" else 0,
            "optimizer_step": expected_step >= 1,
            "checkpoint_save": True,
            "checkpoint_restore": phase == "resume",
            "checkpoint": checkpoint.name,
            "checkpoint_files": checkpoint_hashes,
            "losses": losses,
            "validation": validation_metrics,
            "non_finite_detected": non_finite,
            "walltime_seconds": time.monotonic() - started,
            "peak_memory_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_memory_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            "trainable_parameters": trainable_parameters,
            "all_parameters": all_parameters,
            "trainable_percent": (100.0 * trainable_parameters / all_parameters),
            "environment": environment_snapshot(),
            "smoke_limits": {
                "maximum_optimizer_steps": GPU_SMOKE_STEPS,
                "gradient_accumulation_steps": 1,
                "formal_epochs": False,
            },
        }
        if phase == "initial":
            atomic_json(target / "smoke-state.json", report)
        atomic_json(target / "smoke-report.json", report)
        return report
    except Exception as exc:
        failure = {
            **lineage,
            "status": "failed",
            "passed": False,
            "phase": phase,
            "failed_at": utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "walltime_seconds": time.monotonic() - started,
            "non_finite_detected": "nan" in str(exc).lower() or "inf" in str(exc).lower(),
            "environment": environment_snapshot(),
        }
        atomic_json(target / "smoke-failure.json", failure)
        raise


def audit_gpu_smoke(
    config_path: str | Path = DEFAULT_CONFIG,
    *,
    output_dir: str | Path | None = None,
    freeze_manifest: str | Path = DEFAULT_FREEZE_MANIFEST,
) -> dict[str, Any]:
    """Audit the completed C1 artifact without launching formal training."""

    config = load_config(config_path)
    target = gpu_smoke_output_dir(config, output_dir)
    gate = assert_formal_training_ready(
        config,
        confirmed=True,
        freeze_manifest_path=freeze_manifest,
        c1_report_path=target / "smoke-report.json",
    )
    return {
        "passed": True,
        "status": "complete",
        "experiment_id": config["experiment_id"],
        "c0": gate["c0"],
        "c1_report_sha256": gate["c1_report_sha256"],
        "formal_training_started": False,
        "holdout_read": False,
    }
