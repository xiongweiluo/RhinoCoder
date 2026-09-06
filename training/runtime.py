"""GPU QLoRA train/evaluate runtime with safe resume and local registration."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from training.config import (
    DEFAULT_CONFIG,
    ReadinessError,
    audit_readiness,
    config_sha256,
    load_config,
    project_path,
)
from training.data import (
    CausalLMCollator,
    ConversationDataset,
    add_loss_metrics,
    load_samples,
    score_tool_generations,
)
from training.reporting import (
    append_jsonl,
    atomic_json,
    environment_snapshot,
    register_adapter,
    render_experiment_report,
    write_run_manifest,
)


CHECKPOINT_RE = re.compile(r"^checkpoint-(\d+)$")


def _require_training_stack() -> dict[str, Any]:
    try:
        import torch
        import transformers
        from peft import (  # type: ignore[import-not-found]
            LoraConfig,
            PeftModel,
            TaskType,
            get_peft_model,
            prepare_model_for_kbit_training,
        )
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            Trainer,
            TrainerCallback,
            TrainingArguments,
        )
    except ImportError as exc:
        raise ReadinessError(
            "training dependencies are incomplete; install requirements-training.txt"
        ) from exc
    return {
        "torch": torch,
        "transformers": transformers,
        "LoraConfig": LoraConfig,
        "PeftModel": PeftModel,
        "TaskType": TaskType,
        "get_peft_model": get_peft_model,
        "prepare_model_for_kbit_training": prepare_model_for_kbit_training,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "Trainer": Trainer,
        "TrainerCallback": TrainerCallback,
        "TrainingArguments": TrainingArguments,
    }


def require_gpu(torch: Any, config: Mapping[str, Any]) -> None:
    if not torch.cuda.is_available():
        raise ReadinessError("formal LoRA training requires an NVIDIA CUDA GPU; use the CPU smoke command locally")
    minimum = int(config["base_model"]["expected_vram_gb"]["minimum"])
    available = torch.cuda.get_device_properties(torch.cuda.current_device()).total_memory / (1024**3)
    if available < minimum:
        raise ReadinessError(f"GPU has {available:.1f} GiB; locked experiment requires at least {minimum} GiB")
    if config["training"]["bf16"] and not torch.cuda.is_bf16_supported():
        raise ReadinessError("locked experiment requires a GPU with bfloat16 support")


def latest_checkpoint(run_dir: Path) -> Path | None:
    candidates: list[tuple[int, Path]] = []
    if not run_dir.is_dir():
        return None
    for path in run_dir.iterdir():
        match = CHECKPOINT_RE.fullmatch(path.name)
        if path.is_dir() and match and (path / "trainer_state.json").is_file():
            candidates.append((int(match.group(1)), path))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def resolve_resume(run_dir: Path, requested: str) -> str | None:
    if requested == "none":
        if latest_checkpoint(run_dir) is not None:
            raise ReadinessError("checkpoints already exist; refusing to overwrite without --resume auto")
        return None
    if requested == "auto":
        checkpoint = latest_checkpoint(run_dir)
        return str(checkpoint) if checkpoint else None
    checkpoint = project_path(requested).resolve()
    try:
        checkpoint.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise ReadinessError("resume checkpoint must be inside the locked experiment run directory") from exc
    if not (checkpoint / "trainer_state.json").is_file():
        raise ReadinessError(f"invalid trainer checkpoint: {checkpoint}")
    return str(checkpoint)


def _load_tokenizer(stack: Mapping[str, Any], config: Mapping[str, Any]) -> Any:
    tokenizer_config = config["base_model"]["tokenizer"]
    tokenizer = stack["AutoTokenizer"].from_pretrained(
        tokenizer_config["id"],
        revision=tokenizer_config["revision"],
        trust_remote_code=False,
        token=os.getenv("HF_TOKEN") or None,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def _quantization(stack: Mapping[str, Any], config: Mapping[str, Any]) -> Any:
    torch = stack["torch"]
    quant = config["lora"]["quantization"]
    return stack["BitsAndBytesConfig"](
        load_in_4bit=quant["bits"] == 4,
        bnb_4bit_quant_type=quant["type"],
        bnb_4bit_use_double_quant=bool(quant["double_quant"]),
        bnb_4bit_compute_dtype=torch.bfloat16,
    )


def _load_base_model(stack: Mapping[str, Any], config: Mapping[str, Any]) -> Any:
    torch = stack["torch"]
    local_rank = int(os.getenv("LOCAL_RANK", "0"))
    model = stack["AutoModelForCausalLM"].from_pretrained(
        config["base_model"]["id"],
        revision=config["base_model"]["revision"],
        trust_remote_code=False,
        token=os.getenv("HF_TOKEN") or None,
        quantization_config=_quantization(stack, config),
        dtype=torch.bfloat16,
        device_map={"": local_rank},
    )
    model.config.use_cache = False
    return model


def _attach_lora(stack: Mapping[str, Any], model: Any, config: Mapping[str, Any]) -> Any:
    lora = config["lora"]
    model = stack["prepare_model_for_kbit_training"](
        model,
        use_gradient_checkpointing=bool(config["training"]["gradient_checkpointing"]),
    )
    adapter = stack["LoraConfig"](
        task_type=stack["TaskType"].CAUSAL_LM,
        r=int(lora["rank"]),
        lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora["dropout"]),
        bias=str(lora["bias"]),
        target_modules=list(lora["target_modules"]),
    )
    return stack["get_peft_model"](model, adapter)


def _datasets(config: Mapping[str, Any], tokenizer: Any) -> tuple[Any, Any, list[dict[str, Any]]]:
    data = config["data"]
    view = str(data["view"])
    train_samples = load_samples(data["train"]["path"], split="train", view=view)
    validation_samples = load_samples(data["validation"]["path"], split="validation", view=view)
    maximum = int(config["training"]["max_sequence_length"])
    return (
        ConversationDataset(train_samples, tokenizer, maximum),
        ConversationDataset(validation_samples, tokenizer, maximum),
        validation_samples,
    )


def _trainer(
    stack: Mapping[str, Any],
    config: Mapping[str, Any],
    run_dir: Path,
    model: Any,
    tokenizer: Any,
    train_dataset: Any,
    validation_dataset: Any,
) -> Any:
    training = config["training"]
    checkpoint = config["checkpoint"]
    metrics_path = run_dir / str(config["logging"]["metrics_file"])
    callback_base = stack["TrainerCallback"]

    # Transformers is an optional training dependency loaded at runtime, so
    # static analysis cannot resolve this base class in the normal app env.
    class JsonlMetricsCallback(callback_base):  # type: ignore[valid-type,misc]
        def on_log(self, args: Any, state: Any, control: Any, logs: Any = None, **kwargs: Any) -> None:
            if logs and state.is_world_process_zero:
                append_jsonl(metrics_path, {"step": state.global_step, **dict(logs)})

    arguments = stack["TrainingArguments"](
        output_dir=str(run_dir),
        per_device_train_batch_size=int(training["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(training["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(training["gradient_accumulation_steps"]),
        learning_rate=float(training["learning_rate"]),
        num_train_epochs=float(training["epochs"]),
        warmup_ratio=float(training["warmup_ratio"]),
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
        logging_steps=int(training["logging_steps"]),
        logging_first_step=True,
        eval_strategy="steps",
        eval_steps=int(training["evaluation_steps"]),
        save_strategy="steps",
        save_steps=int(checkpoint["save_steps"]),
        save_total_limit=int(checkpoint["save_total_limit"]),
        load_best_model_at_end=True,
        metric_for_best_model=str(checkpoint["selection_metric"]),
        greater_is_better=bool(checkpoint["greater_is_better"]),
        report_to="none",
        remove_unused_columns=False,
    )
    return stack["Trainer"](
        model=model,
        args=arguments,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=CausalLMCollator(tokenizer.pad_token_id),
        processing_class=tokenizer,
        callbacks=[JsonlMetricsCallback()],
    )


def evaluate_generations(
    model: Any,
    tokenizer: Any,
    samples: Sequence[Mapping[str, Any]],
    *,
    max_new_tokens: int,
) -> dict[str, float | int]:
    generated: list[str] = []
    for sample in samples:
        prompt = tokenizer.apply_chat_template(
            list(sample["messages"][:-1]),
            tokenize=False,
            add_generation_prompt=True,
        )
        encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        encoded = {key: value.to(model.device) for key, value in encoded.items()}
        output = model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
        continuation = output[0, encoded["input_ids"].shape[1] :]
        generated.append(tokenizer.decode(continuation, skip_special_tokens=False))
    return score_tool_generations(samples, generated)


def train(config_path: str | Path = DEFAULT_CONFIG, *, resume: str = "auto") -> dict[str, Any]:
    config = load_config(config_path)
    audit = audit_readiness(config_path)
    if not audit.passed:
        raise ReadinessError("training readiness audit failed: " + "; ".join(audit.findings))
    stack = _require_training_stack()
    require_gpu(stack["torch"], config)
    run_dir = project_path(config["checkpoint"]["root"]).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    write_run_manifest(run_dir, config)
    atomic_json(run_dir / str(config["logging"]["environment_file"]), environment_snapshot())
    resume_from = resolve_resume(run_dir, resume)
    tokenizer = _load_tokenizer(stack, config)
    train_dataset, validation_dataset, validation_samples = _datasets(config, tokenizer)
    model = _attach_lora(stack, _load_base_model(stack, config), config)
    model.print_trainable_parameters()
    trainer = _trainer(
        stack, config, run_dir, model, tokenizer, train_dataset, validation_dataset
    )
    train_result = trainer.train(resume_from_checkpoint=resume_from)
    loss_metrics = add_loss_metrics(trainer.evaluate())
    generation_metrics = evaluate_generations(
        trainer.model,
        tokenizer,
        validation_samples,
        max_new_tokens=int(config["evaluation"]["generation_max_new_tokens"]),
    )
    evaluation = {
        **loss_metrics,
        **generation_metrics,
        "train_metrics": dict(train_result.metrics),
        "config_sha256": config_sha256(config),
        "split": "validation",
        "holdout_read": False,
    }
    atomic_json(run_dir / "evaluation.json", evaluation)
    adapter_dir = run_dir / str(config["checkpoint"]["adapter_directory"])
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    registration = register_adapter(config, adapter_dir, evaluation)
    return {"run_dir": str(run_dir), "evaluation": evaluation, "registration": registration}


def evaluate_adapter(
    adapter_path: str | Path,
    config_path: str | Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    config = load_config(config_path)
    audit = audit_readiness(config_path)
    if not audit.passed:
        raise ReadinessError("training readiness audit failed: " + "; ".join(audit.findings))
    stack = _require_training_stack()
    require_gpu(stack["torch"], config)
    tokenizer = _load_tokenizer(stack, config)
    base = _load_base_model(stack, config)
    adapter = project_path(adapter_path).resolve()
    if not (adapter / "adapter_config.json").is_file():
        raise ReadinessError(f"adapter_config.json not found in {adapter}")
    model = stack["PeftModel"].from_pretrained(base, str(adapter), is_trainable=False)
    _, validation_dataset, validation_samples = _datasets(config, tokenizer)
    trainer = _trainer(stack, config, adapter.parent, model, tokenizer, validation_dataset, validation_dataset)
    metrics = add_loss_metrics(trainer.evaluate())
    metrics.update(
        evaluate_generations(
            model,
            tokenizer,
            validation_samples,
            max_new_tokens=int(config["evaluation"]["generation_max_new_tokens"]),
        )
    )
    metrics.update({"split": "validation", "holdout_read": False})
    atomic_json(adapter.parent / "evaluation.json", metrics)
    return metrics


def write_report(
    run_dir: str | Path,
    output: str | Path,
    config_path: str | Path = DEFAULT_CONFIG,
) -> Path:
    config = load_config(config_path)
    target = project_path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_experiment_report(project_path(run_dir), config),
        encoding="utf-8",
    )
    return target
