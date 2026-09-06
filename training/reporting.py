"""Training metric logging, model registration and experiment reports."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from training.config import ReadinessError, canonical_json, config_sha256, project_path, sha256_file


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical_json(payload) + "\n")


def git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_path("."),
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def environment_snapshot() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for name in ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "safetensors"):
        try:
            module = __import__(name)
            packages[name] = str(getattr(module, "__version__", "unknown"))
        except ImportError:
            packages[name] = "not-installed"
    snapshot: dict[str, Any] = {
        "captured_at": utc_now(),
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": git_revision(),
        "packages": packages,
    }
    try:
        import torch

        snapshot["cuda_available"] = torch.cuda.is_available()
        snapshot["cuda_version"] = torch.version.cuda
        snapshot["cudnn_version"] = torch.backends.cudnn.version()
        snapshot["gpus"] = [
            {
                "index": index,
                "name": torch.cuda.get_device_name(index),
                "total_memory_bytes": torch.cuda.get_device_properties(index).total_memory,
            }
            for index in range(torch.cuda.device_count())
        ]
    except ImportError:
        snapshot["cuda_available"] = False
        snapshot["gpus"] = []
    return snapshot


def write_run_manifest(run_dir: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    data = config["data"]
    payload = {
        "schema_version": "1.0",
        "experiment_id": config["experiment_id"],
        "created_at": utc_now(),
        "config_sha256": config_sha256(config),
        "base_model": config["base_model"],
        "data": {
            "view": data["view"],
            "train": data["train"],
            "validation": data["validation"],
            "holdout_read": False,
        },
        "git_revision": git_revision(),
    }
    path = run_dir / str(config["logging"]["run_manifest"])
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        for key in ("experiment_id", "config_sha256", "base_model", "data"):
            if existing.get(key) != payload.get(key):
                raise ReadinessError(f"existing run manifest differs at {key}; refusing unsafe resume")
        return existing
    atomic_json(path, payload)
    return payload


def directory_hashes(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): sha256_file(item)
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def register_adapter(
    config: Mapping[str, Any],
    adapter_dir: Path,
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    hashes = directory_hashes(adapter_dir)
    payload = {
        "schema_version": "1.0",
        "registered_at": utc_now(),
        "experiment_id": config["experiment_id"],
        "config_sha256": config_sha256(config),
        "base_model_id": config["base_model"]["id"],
        "base_model_revision": config["base_model"]["revision"],
        "adapter_path": adapter_dir.as_posix(),
        "adapter_files": hashes,
        "evaluation": dict(evaluation),
        "holdout_read": False,
        "git_revision": git_revision(),
    }
    payload["registration_id"] = config_sha256(payload)[:24]
    registry = project_path(str(config["logging"]["model_registry"]))
    existing = []
    if registry.is_file():
        existing = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not any(row.get("registration_id") == payload["registration_id"] for row in existing):
        append_jsonl(registry, payload)
    return payload


def parse_metrics(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReadinessError(f"{path}:{line_no}: invalid metric JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ReadinessError(f"{path}:{line_no}: metric must be an object")
        rows.append(row)
    return rows


def render_experiment_report(run_dir: Path, config: Mapping[str, Any]) -> str:
    manifest_path = run_dir / str(config["logging"]["run_manifest"])
    environment_path = run_dir / str(config["logging"]["environment_file"])
    evaluation_path = run_dir / "evaluation.json"
    metrics_path = run_dir / str(config["logging"]["metrics_file"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    environment = json.loads(environment_path.read_text(encoding="utf-8")) if environment_path.is_file() else {}
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8")) if evaluation_path.is_file() else {}
    metrics = parse_metrics(metrics_path)
    best = min(
        (row for row in metrics if isinstance(row.get("eval_loss"), (int, float))),
        key=lambda row: row["eval_loss"],
        default={},
    )
    status = "completed" if evaluation else "incomplete"
    return "\n".join(
        [
            f"# LoRA 实验报告：{config['experiment_id']}",
            "",
            f"状态：**{status}**",
            "",
            "## 血缘",
            "",
            f"- 配置 SHA-256：`{manifest.get('config_sha256', config_sha256(config))}`",
            f"- 基座：`{config['base_model']['id']}@{config['base_model']['revision']}`",
            f"- 数据视图：`{config['data']['view']}`；holdout 读取：`{manifest.get('data', {}).get('holdout_read', False)}`",
            f"- Git：`{manifest.get('git_revision', 'unavailable')}`",
            "",
            "## 环境",
            "",
            f"- Python：`{environment.get('python', 'not captured')}`",
            f"- CUDA：`{environment.get('cuda_version', 'not captured')}`",
            f"- GPU：`{json.dumps(environment.get('gpus', []), ensure_ascii=False)}`",
            "",
            "## 训练与验证",
            "",
            f"- 最佳日志指标：`{json.dumps(best, ensure_ascii=False, sort_keys=True)}`",
            f"- 自动评测：`{json.dumps(evaluation, ensure_ascii=False, sort_keys=True)}`",
            "",
            "## 决策",
            "",
            "- [ ] loss 正常下降且无 NaN/Inf。",
            "- [ ] validation 工具调用结构指标优于无微调基座。",
            "- [ ] checkpoint 恢复结果与连续训练一致。",
            "- [ ] 仅在 C 阶段最终锁定配置后运行 holdout。",
            "- [ ] 根据统一四路评测决定是否部署，不因已训练而默认上线。",
            "",
        ]
    )
