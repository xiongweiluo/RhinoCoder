"""Locked B1/B2 experiment configuration and readiness audit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "training/configs/rhinocoder-qwen25-coder-7b-itc-lora-v1.json"
TRAINING_REQUIREMENTS = PROJECT_ROOT / "requirements-training.txt"
EXPECTED_MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"
EXPECTED_MODEL_REVISION = "c03e6d358207e414f1eca0bb1891e29f1db0e242"
EXPECTED_VIEW = "instruction_to_tool_call"
REQUIRED_TRAINING_PINS = {
    "torch": "2.10.0",
    "transformers": "5.2.0",
    "peft": "0.18.1",
    "accelerate": "1.12.0",
    "bitsandbytes": "0.49.2",
    "safetensors": "0.7.0",
}


class ReadinessError(RuntimeError):
    """Raised when a locked training invariant is violated."""


@dataclass(slots=True)
class ReadinessAudit:
    passed: bool = True
    status: str = "Training Ready — Waiting for School GPU Access"
    config_sha256: str = ""
    train_rows: int = 0
    validation_rows: int = 0
    checks: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.findings.append(message)
        self.passed = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    target = project_path(path)
    try:
        config = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"cannot load training config {target}: {exc}") from exc
    if not isinstance(config, dict):
        raise ReadinessError("training config must be a JSON object")
    return config


def config_sha256(config: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(config).encode("utf-8"))


def _read_jsonl(path: Path, audit: ReadinessAudit) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        audit.add(f"missing training artifact {path}: {exc}")
        return rows
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            audit.add(f"{path}:{line_no}: invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            audit.add(f"{path}:{line_no}: row must be an object")
            continue
        rows.append(row)
    return rows


def _require_equal(audit: ReadinessAudit, actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        audit.add(f"{label}: expected {expected!r}, found {actual!r}")
    else:
        audit.checks.append(label)


def _validate_static_config(config: Mapping[str, Any], audit: ReadinessAudit) -> None:
    scope = config.get("scope") or {}
    model = config.get("base_model") or {}
    tokenizer = model.get("tokenizer") or {}
    data = config.get("data") or {}
    lora = config.get("lora") or {}
    train = config.get("training") or {}
    checkpoint = config.get("checkpoint") or {}
    evaluation = config.get("evaluation") or {}

    _require_equal(audit, config.get("schema_version"), "1.0", "schema version")
    _require_equal(audit, config.get("status"), "locked_pre_gpu", "pre-GPU lock")
    _require_equal(audit, scope.get("base_model_count"), 1, "single base model")
    _require_equal(audit, scope.get("training_view"), EXPECTED_VIEW, "single primary view")
    _require_equal(audit, scope.get("hyperparameter_variants"), 1, "single hyperparameter variant")
    _require_equal(audit, scope.get("holdout_policy"), "forbidden", "holdout policy")
    _require_equal(audit, model.get("id"), EXPECTED_MODEL_ID, "base model id")
    _require_equal(audit, model.get("revision"), EXPECTED_MODEL_REVISION, "base model revision")
    _require_equal(audit, model.get("license"), "Apache-2.0", "base model license")
    _require_equal(audit, tokenizer.get("id"), EXPECTED_MODEL_ID, "tokenizer id")
    _require_equal(audit, tokenizer.get("revision"), EXPECTED_MODEL_REVISION, "tokenizer revision")
    _require_equal(audit, data.get("view"), EXPECTED_VIEW, "dataset view")
    _require_equal(audit, lora.get("method"), "QLoRA", "adapter method")

    numeric_positive = {
        "LoRA rank": lora.get("rank"),
        "LoRA alpha": lora.get("alpha"),
        "max sequence length": train.get("max_sequence_length"),
        "train batch size": train.get("per_device_train_batch_size"),
        "gradient accumulation": train.get("gradient_accumulation_steps"),
        "learning rate": train.get("learning_rate"),
        "epochs": train.get("epochs"),
        "seed": train.get("seed"),
        "evaluation frequency": train.get("evaluation_steps"),
        "checkpoint frequency": checkpoint.get("save_steps"),
    }
    for label, value in numeric_positive.items():
        if not isinstance(value, (int, float)) or value <= 0:
            audit.add(f"{label} must be positive")
        else:
            audit.checks.append(label)
    if train.get("evaluation_steps") != checkpoint.get("save_steps"):
        audit.add("evaluation_steps and save_steps must match for best-checkpoint selection")
    if checkpoint.get("selection_metric") != "eval_loss" or checkpoint.get("greater_is_better") is not False:
        audit.add("best checkpoint must minimize eval_loss")
    if evaluation.get("split") != "validation" or evaluation.get("holdout_allowed") is not False:
        audit.add("automatic evaluation must use validation and forbid holdout")
    for split in ("train", "validation"):
        path = str((data.get(split) or {}).get("path") or "")
        if "holdout" in path.lower():
            audit.add(f"{split} path illegally references holdout")
    if len(list((PROJECT_ROOT / "training/configs").glob("*.json"))) != 1:
        audit.add("B1/B2 permits exactly one locked experiment config")


def _validate_requirements(audit: ReadinessAudit) -> None:
    try:
        lines = TRAINING_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        audit.add(f"cannot read {TRAINING_REQUIREMENTS}: {exc}")
        return
    pins = {}
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#") or "==" not in value:
            continue
        name, version = value.split("==", 1)
        pins[name.strip()] = version.strip()
    for package, version in REQUIRED_TRAINING_PINS.items():
        _require_equal(audit, pins.get(package), version, f"dependency pin {package}")


def _validate_data(config: Mapping[str, Any], audit: ReadinessAudit) -> None:
    data = config.get("data") or {}
    manifest_path = project_path(str(data.get("manifest") or ""))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        audit.add(f"cannot load A5 manifest {manifest_path}: {exc}")
        return
    _require_equal(audit, manifest.get("pipeline_version"), data.get("pipeline_version"), "A5 pipeline version")
    artifacts = {str(item.get("path")): item for item in manifest.get("artifacts") or []}
    for split in ("train", "validation"):
        expected = data.get(split) or {}
        path = project_path(str(expected.get("path") or ""))
        relative = path.relative_to(manifest_path.parent).as_posix()
        artifact = artifacts.get(relative)
        if not artifact:
            audit.add(f"A5 manifest does not contain {relative}")
            continue
        rows = _read_jsonl(path, audit)
        if split == "train":
            audit.train_rows = len(rows)
        else:
            audit.validation_rows = len(rows)
        _require_equal(audit, len(rows), expected.get("rows"), f"{split} row count")
        if path.is_file():
            _require_equal(audit, sha256_file(path), expected.get("sha256"), f"{split} file hash")
        _require_equal(audit, artifact.get("sha256"), expected.get("sha256"), f"{split} manifest hash")
        for index, row in enumerate(rows, 1):
            if row.get("split") != split or row.get("view") != EXPECTED_VIEW:
                audit.add(f"{path}:{index}: split/view does not match locked experiment")
            messages = row.get("messages")
            if not isinstance(messages, list) or len(messages) != 2:
                audit.add(f"{path}:{index}: instruction-to-tool-call sample must contain two messages")
            elif messages[0].get("role") != "user" or not (messages[1].get("tool_calls") or []):
                audit.add(f"{path}:{index}: sample lacks user prompt or assistant tool call target")


def audit_readiness(config_path: str | Path = DEFAULT_CONFIG, *, require_data: bool = True) -> ReadinessAudit:
    config = load_config(config_path)
    audit = ReadinessAudit(config_sha256=config_sha256(config))
    _validate_static_config(config, audit)
    _validate_requirements(audit)
    if require_data:
        _validate_data(config, audit)
    else:
        audit.checks.append("data audit deferred")
    return audit
