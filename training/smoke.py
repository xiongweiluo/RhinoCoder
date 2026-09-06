"""Network-free CPU LoRA smoke covering save, resume and evaluation."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from training.config import DEFAULT_CONFIG, ReadinessError, audit_readiness, config_sha256, load_config, project_path, sha256_file
from training.data import load_samples
from training.reporting import atomic_json, environment_snapshot, utc_now


def _encode_sample(sample: Mapping[str, Any], *, limit: int = 384) -> list[int]:
    payload = json.dumps(sample["messages"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    encoded = list(payload.encode("utf-8"))[:limit]
    if len(encoded) < 2:
        raise ReadinessError("CPU smoke sample is too short")
    return encoded


def _build_model(torch: Any, *, rank: int, alpha: int, seed: int) -> Any:
    torch.manual_seed(seed)

    class TinyAdapterLM(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            width = 32
            self.embedding = torch.nn.Embedding(256, width)
            self.base_head = torch.nn.Linear(width, 256, bias=False)
            self.lora_a = torch.nn.Parameter(torch.empty(rank, width))
            self.lora_b = torch.nn.Parameter(torch.zeros(256, rank))
            torch.nn.init.kaiming_uniform_(self.lora_a, a=math.sqrt(5))
            for parameter in self.embedding.parameters():
                parameter.requires_grad = False
            for parameter in self.base_head.parameters():
                parameter.requires_grad = False
            self.scale = alpha / rank

        def forward(self, token_ids: Any) -> Any:
            hidden = self.embedding(token_ids)
            base = self.base_head(hidden)
            adapter = (hidden @ self.lora_a.T) @ self.lora_b.T
            return base + adapter * self.scale

    return TinyAdapterLM()


def _batch(torch: Any, samples: Sequence[Mapping[str, Any]]) -> tuple[Any, Any]:
    encoded = [_encode_sample(sample) for sample in samples]
    width = min(len(value) for value in encoded) - 1
    inputs = torch.tensor([value[:width] for value in encoded], dtype=torch.long)
    labels = torch.tensor([value[1 : width + 1] for value in encoded], dtype=torch.long)
    return inputs, labels


def _step(torch: Any, model: Any, optimizer: Any, inputs: Any, labels: Any) -> float:
    model.train()
    optimizer.zero_grad(set_to_none=True)
    logits = model(inputs)
    loss = torch.nn.functional.cross_entropy(logits.reshape(-1, 256), labels.reshape(-1))
    if not torch.isfinite(loss):
        raise ReadinessError("CPU smoke produced a non-finite loss")
    loss.backward()
    optimizer.step()
    return float(loss.detach())


def _evaluate(torch: Any, model: Any, inputs: Any, labels: Any) -> float:
    model.eval()
    with torch.no_grad():
        logits = model(inputs)
        loss = torch.nn.functional.cross_entropy(logits.reshape(-1, 256), labels.reshape(-1))
    return float(loss)


def _save_checkpoint(
    torch: Any,
    path: Path,
    *,
    model: Any,
    optimizer: Any,
    step: int,
    loss: float,
    config_hash: str,
    data_hash: str,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    state_path = path / "adapter-state.pt"
    temporary = state_path.with_suffix(".pt.tmp")
    torch.save(
        {
            "step": step,
            "lora_a": model.lora_a.detach(),
            "lora_b": model.lora_b.detach(),
            "optimizer": optimizer.state_dict(),
            "config_sha256": config_hash,
            "data_sha256": data_hash,
        },
        temporary,
    )
    os.replace(temporary, state_path)
    atomic_json(
        path / "manifest.json",
        {
            "schema_version": "1.0",
            "kind": "cpu-smoke-adapter-only",
            "step": step,
            "loss": loss,
            "config_sha256": config_hash,
            "data_sha256": data_hash,
            "state_sha256": sha256_file(state_path),
            "created_at": utc_now(),
        },
    )


def _restore(torch: Any, path: Path, model: Any, optimizer: Any, config_hash: str, data_hash: str) -> int:
    state = torch.load(path / "adapter-state.pt", map_location="cpu", weights_only=True)
    if state.get("config_sha256") != config_hash or state.get("data_sha256") != data_hash:
        raise ReadinessError("CPU smoke checkpoint lineage does not match config/data")
    with torch.no_grad():
        model.lora_a.copy_(state["lora_a"])
        model.lora_b.copy_(state["lora_b"])
    optimizer.load_state_dict(state["optimizer"])
    return int(state["step"])


def run_cpu_smoke(
    config_path: str | Path = DEFAULT_CONFIG,
    output_dir: str | Path = "data/training/smoke",
) -> dict[str, Any]:
    audit = audit_readiness(config_path)
    if not audit.passed:
        raise ReadinessError("readiness audit failed: " + "; ".join(audit.findings))
    try:
        import torch
    except ImportError as exc:
        raise ReadinessError("CPU smoke requires PyTorch") from exc
    config = load_config(config_path)
    data = config["data"]
    train_samples = load_samples(data["train"]["path"], split="train", view=data["view"])[:2]
    validation_samples = load_samples(
        data["validation"]["path"], split="validation", view=data["view"]
    )[:1]
    train_inputs, train_labels = _batch(torch, train_samples)
    validation_inputs, validation_labels = _batch(torch, validation_samples)
    rank = int(config["lora"]["rank"])
    alpha = int(config["lora"]["alpha"])
    seed = int(config["training"]["seed"])
    config_hash = config_sha256(config)
    data_hash = str(data["train"]["sha256"])
    target = project_path(output_dir)

    first_model = _build_model(torch, rank=rank, alpha=alpha, seed=seed)
    first_optimizer = torch.optim.AdamW(
        [first_model.lora_a, first_model.lora_b],
        lr=float(config["training"]["learning_rate"]),
    )
    frozen_before = {
        "embedding": first_model.embedding.weight.detach().clone(),
        "base_head": first_model.base_head.weight.detach().clone(),
    }
    first_loss = _step(torch, first_model, first_optimizer, train_inputs, train_labels)
    checkpoint_one = target / "checkpoint-step-0001"
    _save_checkpoint(
        torch,
        checkpoint_one,
        model=first_model,
        optimizer=first_optimizer,
        step=1,
        loss=first_loss,
        config_hash=config_hash,
        data_hash=data_hash,
    )
    if not torch.equal(frozen_before["embedding"], first_model.embedding.weight):
        raise ReadinessError("CPU smoke changed frozen embedding weights")
    if not torch.equal(frozen_before["base_head"], first_model.base_head.weight):
        raise ReadinessError("CPU smoke changed frozen base weights")

    resumed_model = _build_model(torch, rank=rank, alpha=alpha, seed=seed)
    resumed_optimizer = torch.optim.AdamW(
        [resumed_model.lora_a, resumed_model.lora_b],
        lr=float(config["training"]["learning_rate"]),
    )
    resumed_step = _restore(
        torch, checkpoint_one, resumed_model, resumed_optimizer, config_hash, data_hash
    )
    second_loss = _step(torch, resumed_model, resumed_optimizer, train_inputs, train_labels)
    checkpoint_two = target / "checkpoint-step-0002"
    _save_checkpoint(
        torch,
        checkpoint_two,
        model=resumed_model,
        optimizer=resumed_optimizer,
        step=resumed_step + 1,
        loss=second_loss,
        config_hash=config_hash,
        data_hash=data_hash,
    )
    validation_loss = _evaluate(torch, resumed_model, validation_inputs, validation_labels)
    report = {
        "schema_version": "1.0",
        "passed": all(math.isfinite(value) for value in (first_loss, second_loss, validation_loss)),
        "device": "cpu",
        "network_used": False,
        "base_model_downloaded": False,
        "samples": {"train": 2, "validation": 1, "holdout": 0},
        "steps": 2,
        "resumed_from_step": resumed_step,
        "loss": {"step_1": first_loss, "step_2": second_loss, "validation": validation_loss},
        "checkpoint_save": True,
        "checkpoint_restore": resumed_step == 1,
        "adapter_only_trainable": True,
        "config_sha256": config_hash,
        "data_sha256": data_hash,
        "environment": environment_snapshot(),
    }
    atomic_json(target / "smoke-report.json", report)
    return report
