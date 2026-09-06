"""School GPU configuration validation and non-secret environment inventory."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from training.config import ReadinessError, project_path
from training.reporting import utc_now


PLACEHOLDER_MARKERS = ("REQUIRED_AT_ACCESS", "RECORD_AT_ACCESS", "VERIFY_AT_ACCESS")


def load_cluster_config(path: str | Path) -> dict[str, Any]:
    target = project_path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"cannot load cluster config {target}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError("cluster config must be an object")
    return value


def placeholder_paths(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(placeholder_paths(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(placeholder_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, str) and any(marker in value for marker in PLACEHOLDER_MARKERS):
        found.append(prefix)
    return found


def validate_cluster_config(config: dict[str, Any], *, allow_placeholders: bool) -> list[str]:
    findings: list[str] = []
    required_sections = ("login", "scheduler", "compute", "storage", "network", "secrets")
    for section in required_sections:
        if not isinstance(config.get(section), dict):
            findings.append(f"missing section: {section}")
    scheduler_type = str((config.get("scheduler") or {}).get("type") or "")
    if not allow_placeholders and scheduler_type not in {"slurm", "pbs", "direct"}:
        findings.append("scheduler.type must be slurm, pbs, or direct")
    if int((config.get("compute") or {}).get("minimum_vram_gb") or 0) < 16:
        findings.append("minimum_vram_gb must be at least 16")
    placeholders = placeholder_paths(config)
    if placeholders and not allow_placeholders:
        findings.append("unresolved access fields: " + ", ".join(placeholders))
    return findings


def _command(command: list[str]) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if not executable:
        return {"available": False, "command": command[0]}
    result = subprocess.run(
        [executable, *command[1:]],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": result.stdout.strip()[:4000],
        "stderr": result.stderr.strip()[:2000],
    }


def inventory_cluster(config_path: str | Path) -> dict[str, Any]:
    config = load_cluster_config(config_path)
    findings = validate_cluster_config(config, allow_placeholders=False)
    if findings:
        raise ReadinessError("cluster config is incomplete: " + "; ".join(findings))
    cache_name = str(config["storage"]["model_cache_environment_variable"])
    token_name = str(config["secrets"]["huggingface_token_environment_variable"])
    scheduler_type = str(config["scheduler"]["type"])
    scheduler_command = {
        "slurm": ["sinfo", "--version"],
        "pbs": ["qstat", "--version"],
        "direct": ["true"],
    }[scheduler_type]
    return {
        "schema_version": "1.0",
        "captured_at": utc_now(),
        "config_path": str(project_path(config_path)),
        "commands": {
            "nvidia_smi": _command(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader",
                ]
            ),
            "cuda_compiler": _command(["nvcc", "--version"]),
            "scheduler": {"type": scheduler_type, **_command(scheduler_command)},
            "quota": _command(["quota", "-s"]),
            "storage": _command(["df", "-h", "."]),
        },
        "environment_presence": {
            cache_name: bool(os.getenv(cache_name)),
            token_name: bool(os.getenv(token_name)),
        },
        "secret_values_recorded": False,
    }
