"""C0 freeze manifest and C1 gate for the formal LoRA run."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

from training.config import (
    DEFAULT_CONFIG,
    ReadinessError,
    audit_readiness,
    canonical_json,
    config_sha256,
    load_config,
    project_path,
    sha256_bytes,
    sha256_file,
)
from training.reporting import git_revision, utc_now


DEFAULT_PREREGISTRATION = "docs/training-preregistration.md"
DEFAULT_FREEZE_MANIFEST = "data/training/c0/preregistration-freeze.json"
DEFAULT_C1_REPORT = "data/training/gpu-smoke/rhinocoder-qwen25-coder-7b-itc-lora-v1/smoke-report.json"

PROMPT_CONTRACT_FILES = ("agent/version.py", "agent/llm.py")
TOOL_CONTRACT_FILES = (
    "plugin/mcp_server/main.py",
    "plugin/mcp_server/schemas_geometry.py",
    "plugin/mcp_server/schemas_perception.py",
    "plugin/mcp_server/schemas_property.py",
    "plugin/mcp_server/schemas_transform.py",
)
TRACE_CONTRACT_FILES = ("agent/version.py", "agent/runtime.py", "agent/trace_store.py")


def _tracked_worktree_changes() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=project_path("."),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReadinessError(f"cannot inspect Git worktree: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _file_hashes(paths: tuple[str, ...] | list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in paths:
        path = project_path(relative)
        if not path.is_file():
            raise ReadinessError(f"freeze input is missing: {relative}")
        hashes[relative] = sha256_file(path)
    return hashes


def _contract(files: tuple[str, ...]) -> dict[str, Any]:
    hashes = _file_hashes(files)
    return {
        "files": hashes,
        "aggregate_sha256": sha256_bytes(canonical_json(hashes).encode("utf-8")),
    }


def _manifest_artifact(a5_manifest: Mapping[str, Any], suffix: str) -> Mapping[str, Any]:
    matches = [
        item
        for item in a5_manifest.get("artifacts") or []
        if str(item.get("path") or "") == suffix
    ]
    if len(matches) != 1:
        raise ReadinessError(f"A5 manifest must contain exactly one {suffix!r} artifact")
    return matches[0]


def build_freeze_payload(
    config_path: str | Path = DEFAULT_CONFIG,
    preregistration_path: str | Path = DEFAULT_PREREGISTRATION,
) -> dict[str, Any]:
    """Build the external freeze payload without reading the holdout file."""

    audit = audit_readiness(config_path)
    if not audit.passed:
        raise ReadinessError("readiness audit failed: " + "; ".join(audit.findings))
    preregistration = project_path(preregistration_path)
    text = preregistration.read_text(encoding="utf-8")
    if "FREEZE READY" not in text or "DRAFT — DO NOT START FORMAL TRAINING" in text:
        raise ReadinessError("formal preregistration is not marked FREEZE READY")

    config = load_config(config_path)
    a5_manifest_path = project_path(config["data"]["manifest"])
    a5_manifest = json.loads(a5_manifest_path.read_text(encoding="utf-8"))
    holdout = _manifest_artifact(a5_manifest, "holdout/instruction_to_tool_call.jsonl")
    version_manifest = json.loads(project_path("docs/version-manifest.json").read_text(encoding="utf-8"))
    interfaces = version_manifest["interfaces"]

    return {
        "schema_version": "1.0",
        "kind": "external-c0-preregistration-freeze",
        "status": "freeze_candidate",
        "created_at": utc_now(),
        "experiment_id": config["experiment_id"],
        "git_revision": git_revision(),
        "preregistration": {
            "path": preregistration.relative_to(project_path(".")).as_posix(),
            "sha256": sha256_file(preregistration),
            "self_hash_policy": "document hash lives only in this external manifest",
        },
        "base_model": {
            "id": config["base_model"]["id"],
            "revision": config["base_model"]["revision"],
        },
        "configuration": {
            "path": project_path(config_path).relative_to(project_path(".")).as_posix(),
            "canonical_sha256": config_sha256(config),
            "file_sha256": sha256_file(project_path(config_path)),
        },
        "a5": {
            "manifest_path": config["data"]["manifest"],
            "manifest_sha256": sha256_file(a5_manifest_path),
            "train": config["data"]["train"],
            "validation": config["data"]["validation"],
            "holdout": {
                "rows": holdout.get("rows"),
                "sha256_from_manifest": holdout.get("sha256"),
                "file_read": False,
                "loader_policy": "forbidden_until_c3_one_time_entry",
            },
        },
        "contracts": {
            "versions": {
                "prompt": interfaces["prompt"],
                "tool_schema": interfaces["tool_schema"],
                "trace_schema": interfaces["trace_schema"],
                "mcp_tool_count": interfaces["mcp_tool_count"],
            },
            "prompt": _contract(PROMPT_CONTRACT_FILES),
            "tools": _contract(TOOL_CONTRACT_FILES),
            "trace": _contract(TRACE_CONTRACT_FILES),
        },
        "gates": {
            "c0_frozen": True,
            "c1_gpu_smoke_resume_required": True,
            "c2_formal_training_started": False,
            "holdout_read": False,
        },
    }


def audit_preregistration_freeze(
    manifest_path: str | Path = DEFAULT_FREEZE_MANIFEST,
    *,
    require_clean_git: bool = True,
) -> dict[str, Any]:
    target = project_path(manifest_path)
    try:
        frozen = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"cannot load C0 freeze manifest {target}: {exc}") from exc
    if frozen.get("status") != "frozen" or frozen.get("kind") != "external-c0-preregistration-freeze":
        raise ReadinessError("invalid C0 freeze manifest status/kind")
    if require_clean_git and _tracked_worktree_changes():
        raise ReadinessError("formal training requires a clean tracked worktree")
    if frozen.get("git_revision") != git_revision():
        raise ReadinessError("C0 freeze Git revision does not match the current checkout")
    p2 = (frozen.get("evaluation_contracts") or {}).get("p2") or {}
    if len(str(p2.get("aggregate_sha256") or "")) != 64 or not p2.get("files"):
        raise ReadinessError("C0 freeze manifest lacks the independently frozen P2 contract hashes")
    config_path = frozen.get("configuration", {}).get("path")
    if not config_path:
        raise ReadinessError("C0 freeze manifest lacks the configuration path")
    current = build_freeze_payload(config_path, frozen["preregistration"]["path"])
    for key in ("experiment_id", "git_revision", "preregistration", "base_model", "configuration", "a5", "contracts", "gates"):
        if frozen.get(key) != current.get(key):
            raise ReadinessError(f"C0 freeze drift detected at {key}")
    return {
        "passed": True,
        "experiment_id": frozen["experiment_id"],
        "git_revision": frozen["git_revision"],
        "freeze_manifest_sha256": sha256_file(target),
        "holdout_read": False,
    }


def assert_formal_training_ready(
    config: Mapping[str, Any],
    *,
    confirmed: bool,
    freeze_manifest_path: str | Path = DEFAULT_FREEZE_MANIFEST,
    c1_report_path: str | Path = DEFAULT_C1_REPORT,
) -> dict[str, Any]:
    """Refuse C2 unless the operator explicitly confirms valid C0 and C1 artifacts."""

    if not confirmed:
        raise ReadinessError(
            "formal training is locked; complete C0/C1 and pass --confirm-formal-training"
        )
    c0 = audit_preregistration_freeze(freeze_manifest_path)
    report_path = project_path(c1_report_path)
    try:
        c1 = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"cannot load completed C1 GPU smoke report {report_path}: {exc}") from exc
    expected = {
        "experiment_id": config["experiment_id"],
        "config_sha256": config_sha256(config),
        "git_revision": c0["git_revision"],
        "c0_freeze_manifest_sha256": c0["freeze_manifest_sha256"],
    }
    for key, value in expected.items():
        if c1.get(key) != value:
            raise ReadinessError(f"C1 GPU smoke report differs at {key}")
    required = {
        "passed": True,
        "status": "complete",
        "device": "cuda",
        "checkpoint_save": True,
        "checkpoint_restore": True,
        "optimizer_step": True,
        "formal_run_directory_written": False,
        "model_registry_written": False,
        "holdout_read": False,
        "non_finite_detected": False,
    }
    for key, value in required.items():
        if c1.get(key) != value:
            raise ReadinessError(f"C1 GPU smoke gate is not satisfied at {key}")
    if int(c1.get("steps") or 0) != 2 or int(c1.get("resumed_from_step") or 0) != 1:
        raise ReadinessError("C1 GPU smoke must prove step-1 save and step-2 resume")
    if (c1.get("samples") or {}).get("holdout") != 0 or c1.get("p2_read") is not False:
        raise ReadinessError("C1 GPU smoke report must prove zero holdout/P2 reads")
    if (c1.get("smoke_limits") or {}).get("maximum_optimizer_steps") != 2:
        raise ReadinessError("C1 GPU smoke report exceeds or omits the two-step safety limit")
    checkpoint = (report_path.parent / str(c1.get("checkpoint") or "")).resolve()
    if checkpoint.parent != report_path.parent.resolve():
        raise ReadinessError("C1 checkpoint is outside the isolated smoke directory")
    expected_files = c1.get("checkpoint_files") or {}
    if not expected_files or not isinstance(expected_files, dict):
        raise ReadinessError("C1 GPU smoke report lacks checkpoint hashes")
    if not any(str(relative).startswith("optimizer") for relative in expected_files):
        raise ReadinessError("C1 GPU smoke report lacks optimizer-state lineage")
    for relative, expected_hash in expected_files.items():
        item = checkpoint / str(relative)
        if not item.is_file() or sha256_file(item) != expected_hash:
            raise ReadinessError(f"C1 checkpoint hash mismatch: {relative}")
    try:
        trainer_state = json.loads((checkpoint / "trainer_state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError("cannot verify C1 trainer state") from exc
    if int(trainer_state.get("global_step") or 0) != 2:
        raise ReadinessError("C1 checkpoint does not contain global step 2")
    return {"c0": c0, "c1_report_sha256": sha256_file(report_path)}
