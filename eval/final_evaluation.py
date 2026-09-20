"""Isolated C3 freeze, one-time A5 holdout gate, and paired statistics.

This module is intentionally independent from ``training.data.load_samples``.
The B-stage loader must continue rejecting holdout forever.  C3 first freezes
the completed C2 artifacts and evaluation protocol without opening holdout;
only an explicitly confirmed one-time run may claim and read the locked split.
"""

from __future__ import annotations

import gc
import json
import math
import os
import random
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    import fcntl
except ImportError:  # pragma: no cover - the locked C3 run is intentionally POSIX-only
    fcntl = None  # type: ignore[assignment]

from training.config import (
    DEFAULT_CONFIG,
    ReadinessError,
    canonical_json,
    config_sha256,
    load_config,
    project_path,
    sha256_bytes,
    sha256_file,
)
from training.preregistration import (
    DEFAULT_C1_REPORT,
    DEFAULT_FREEZE_MANIFEST,
    PROMPT_CONTRACT_FILES,
    TOOL_CONTRACT_FILES,
    TRACE_CONTRACT_FILES,
    _contract,
    _tracked_worktree_changes,
)
from training.reporting import atomic_json, directory_hashes, git_revision


DEFAULT_C3_FREEZE_MANIFEST = "data/training/c3/evaluation-freeze.json"
DEFAULT_C3_LEDGER = "data/training/c3/holdout-consumption.jsonl"
DEFAULT_C3_RUNS = "data/training/c3/runs"
DEFAULT_HOLDOUT_RELATIVE = "data/training/a5/holdout/instruction_to_tool_call.jsonl"
DEFAULT_MODEL_REGISTRY = "data/training/model-registry.jsonl"

P2_CONTRACT_FILES = (
    "eval/p2/freeze-manifest.json",
    "eval/p2/hard_tasks.jsonl",
    "eval/p2/fixtures.json",
    "eval/p2/statistics-protocol.json",
    "eval/p2/leakage-policy.json",
)
EVALUATION_IMPLEMENTATION_FILES = (
    "eval/final_evaluation.py",
    "training/runtime.py",
    "training/model_cache.py",
    "tools/run_final_evaluation.py",
)
ROUTES = ("base", "lora")
METRIC_FIELDS = ("parse_success", "name_exact", "arguments_exact", "sequence_exact")
TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
CHECKPOINT_RE = re.compile(r"^checkpoint-(\d+)$")
BOOTSTRAP_SEED = 20260917
BOOTSTRAP_RESAMPLES = 10_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"cannot load {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"{label} must be a JSON object: {path}")
    return value


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReadinessError(f"cannot load {label} {path}: {exc}") from exc
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReadinessError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ReadinessError(f"{path}:{line_no}: expected a JSON object")
        rows.append(value)
    return rows


def _append_jsonl_fsync(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json(payload) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _exclusive_ledger_lock(path: Path) -> Iterable[None]:
    if fcntl is None:
        raise ReadinessError(
            "C3 one-time consumption requires POSIX advisory file locking"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    with lock_path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _file_contract(paths: Sequence[str]) -> dict[str, Any]:
    files: dict[str, str] = {}
    for relative in paths:
        target = project_path(relative)
        if not target.is_file():
            raise ReadinessError(f"C3 freeze input is missing: {relative}")
        files[relative] = sha256_file(target)
    return {
        "files": files,
        "aggregate_sha256": sha256_bytes(canonical_json(files).encode("utf-8")),
    }


def _manifest_artifact(manifest: Mapping[str, Any], relative: str) -> dict[str, Any]:
    matches = [
        item
        for item in manifest.get("artifacts") or []
        if isinstance(item, dict) and item.get("path") == relative
    ]
    if len(matches) != 1:
        raise ReadinessError(
            f"A5 manifest must contain exactly one {relative!r} artifact"
        )
    return dict(matches[0])


def _latest_checkpoint(run_dir: Path) -> tuple[int, Path]:
    candidates: list[tuple[int, Path]] = []
    if run_dir.is_dir():
        for item in run_dir.iterdir():
            match = CHECKPOINT_RE.fullmatch(item.name)
            if item.is_dir() and match and (item / "trainer_state.json").is_file():
                candidates.append((int(match.group(1)), item))
    if not candidates:
        raise ReadinessError(
            f"completed C2 run has no recoverable checkpoint: {run_dir}"
        )
    return max(candidates, key=lambda entry: entry[0])


def _aggregate_hashes(files: Mapping[str, str]) -> str:
    return sha256_bytes(canonical_json(dict(files)).encode("utf-8"))


def _find_registration(
    registry_path: Path,
    *,
    experiment_id: str,
    expected_adapter: Path,
    expected_config_sha256: str,
) -> dict[str, Any]:
    matches = []
    for row in _read_jsonl(registry_path, "model registry"):
        adapter = Path(str(row.get("adapter_path") or "")).resolve()
        if (
            row.get("experiment_id") == experiment_id
            and row.get("config_sha256") == expected_config_sha256
            and adapter == expected_adapter.resolve()
        ):
            matches.append(row)
    if len(matches) != 1:
        raise ReadinessError(
            "C3 freeze requires exactly one matching registered C2 adapter"
        )
    return matches[0]


def _validate_c0_manifest(c0: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    if (
        c0.get("kind") != "external-c0-preregistration-freeze"
        or c0.get("status") != "frozen"
    ):
        raise ReadinessError("invalid C0 freeze manifest status/kind")
    if c0.get("experiment_id") != config["experiment_id"]:
        raise ReadinessError("C0 experiment ID differs from the locked configuration")
    if (c0.get("configuration") or {}).get("canonical_sha256") != config_sha256(config):
        raise ReadinessError(
            "C0 configuration hash differs from the locked configuration"
        )
    if (c0.get("gates") or {}).get("holdout_read") is not False:
        raise ReadinessError("C0 manifest does not prove holdout_read=false")


def build_c3_freeze_payload(
    config_path: str | Path = DEFAULT_CONFIG,
    *,
    c0_manifest_path: str | Path = DEFAULT_FREEZE_MANIFEST,
    c1_report_path: str | Path = DEFAULT_C1_REPORT,
) -> dict[str, Any]:
    """Build a C3 freeze candidate without opening the holdout file."""

    config = load_config(config_path)
    config_hash = config_sha256(config)
    experiment_id = str(config["experiment_id"])

    c0_path = project_path(c0_manifest_path)
    c0 = _read_json(c0_path, "C0 freeze manifest")
    _validate_c0_manifest(c0, config)

    c1_path = project_path(c1_report_path)
    c1 = _read_json(c1_path, "C1 report")
    if c1.get("experiment_id") != experiment_id or c1.get("passed") is not True:
        raise ReadinessError(
            "C1 report is not the completed report for this experiment"
        )
    if c1.get("holdout_read") is not False or c1.get("p2_read") is not False:
        raise ReadinessError("C1 report does not prove zero holdout/P2 reads")

    run_dir = project_path(str(config["checkpoint"]["root"])).resolve()
    run_manifest_path = run_dir / str(config["logging"]["run_manifest"])
    evaluation_path = run_dir / "evaluation.json"
    environment_path = run_dir / str(config["logging"]["environment_file"])
    metrics_path = run_dir / str(config["logging"]["metrics_file"])
    run_manifest = _read_json(run_manifest_path, "C2 run manifest")
    evaluation = _read_json(evaluation_path, "C2 evaluation")
    environment = _read_json(environment_path, "C2 environment")
    if run_manifest.get("experiment_id") != experiment_id:
        raise ReadinessError("C2 run manifest experiment ID drift")
    if run_manifest.get("config_sha256") != config_hash:
        raise ReadinessError("C2 run manifest configuration hash drift")
    if (run_manifest.get("data") or {}).get("holdout_read") is not False:
        raise ReadinessError("C2 run manifest does not prove holdout_read=false")
    if (
        evaluation.get("holdout_read") is not False
        or evaluation.get("split") != "validation"
    ):
        raise ReadinessError(
            "C2 evaluation must be validation-only with holdout_read=false"
        )
    if evaluation.get("config_sha256") != config_hash:
        raise ReadinessError("C2 evaluation configuration hash drift")

    adapter_dir = run_dir / str(config["checkpoint"]["adapter_directory"])
    if not (adapter_dir / "adapter_config.json").is_file():
        raise ReadinessError(f"registered C2 adapter is missing: {adapter_dir}")
    adapter_hashes = directory_hashes(adapter_dir)
    registration = _find_registration(
        project_path(
            str(config["logging"].get("model_registry") or DEFAULT_MODEL_REGISTRY)
        ),
        experiment_id=experiment_id,
        expected_adapter=adapter_dir,
        expected_config_sha256=config_hash,
    )
    if registration.get("adapter_files") != adapter_hashes:
        raise ReadinessError(
            "registered adapter hashes differ from the C2 adapter directory"
        )
    if (registration.get("evaluation") or {}).get("holdout_read") is not False:
        raise ReadinessError(
            "registered C2 evaluation does not prove holdout_read=false"
        )

    checkpoint_step, checkpoint_dir = _latest_checkpoint(run_dir)
    checkpoint_hashes = directory_hashes(checkpoint_dir)
    trainer_state = _read_json(
        checkpoint_dir / "trainer_state.json", "C2 trainer state"
    )
    if int(trainer_state.get("global_step") or -1) != checkpoint_step:
        raise ReadinessError(
            "latest C2 checkpoint trainer state has the wrong global step"
        )

    a5_manifest_path = project_path(str(config["data"]["manifest"]))
    a5_manifest = _read_json(a5_manifest_path, "A5 manifest")
    holdout_artifact = _manifest_artifact(
        a5_manifest, "holdout/instruction_to_tool_call.jsonl"
    )
    frozen_holdout = (c0.get("a5") or {}).get("holdout") or {}
    if holdout_artifact.get("sha256") != frozen_holdout.get(
        "sha256_from_manifest"
    ) or holdout_artifact.get("rows") != frozen_holdout.get("rows"):
        raise ReadinessError("A5 holdout metadata drifted from the C0 manifest")
    if sha256_file(a5_manifest_path) != (c0.get("a5") or {}).get("manifest_sha256"):
        raise ReadinessError("A5 manifest drifted from C0")

    prompt_contract = _contract(PROMPT_CONTRACT_FILES)
    tool_contract = _contract(TOOL_CONTRACT_FILES)
    trace_contract = _contract(TRACE_CONTRACT_FILES)
    frozen_contracts = c0.get("contracts") or {}
    for name, current in (
        ("prompt", prompt_contract),
        ("tools", tool_contract),
        ("trace", trace_contract),
    ):
        if frozen_contracts.get(name) != current:
            raise ReadinessError(f"{name} contract drifted after C0")

    p2_contract = _file_contract(P2_CONTRACT_FILES)
    frozen_p2 = (c0.get("evaluation_contracts") or {}).get("p2") or {}
    if (
        frozen_p2.get("files") != p2_contract["files"]
        or frozen_p2.get("aggregate_sha256") != p2_contract["aggregate_sha256"]
    ):
        raise ReadinessError("P2 evaluation contract drifted after C0")

    current_git = git_revision()
    return {
        "schema_version": "1.0",
        "kind": "c3-final-evaluation-freeze",
        "status": "freeze_candidate",
        "experiment_id": experiment_id,
        "lineage": {
            "c0_manifest_path": str(Path(c0_manifest_path)),
            "c0_manifest_sha256": sha256_file(c0_path),
            "c0_git_revision": c0.get("git_revision"),
            "c1_report_path": str(Path(c1_report_path)),
            "c1_report_sha256": sha256_file(c1_path),
            "training_git_revision": run_manifest.get("git_revision"),
            "evaluation_git_revision": current_git,
            "config_path": str(Path(config_path)),
            "config_sha256": config_hash,
            "base_model": {
                "id": config["base_model"]["id"],
                "revision": config["base_model"]["revision"],
            },
            "tokenizer": dict(config["base_model"]["tokenizer"]),
        },
        "c2": {
            "run_directory": str(run_dir),
            "run_manifest_sha256": sha256_file(run_manifest_path),
            "environment_sha256": sha256_file(environment_path),
            "metrics_sha256": sha256_file(metrics_path),
            "evaluation_sha256": sha256_file(evaluation_path),
            "evaluation": evaluation,
            "environment": environment,
            "registration_id": registration.get("registration_id"),
            "registration_sha256": sha256_bytes(
                canonical_json(registration).encode("utf-8")
            ),
            "adapter": {
                "path": str(adapter_dir),
                "files": adapter_hashes,
                "aggregate_sha256": _aggregate_hashes(adapter_hashes),
            },
            "last_checkpoint": {
                "path": str(checkpoint_dir),
                "step": checkpoint_step,
                "files": checkpoint_hashes,
                "aggregate_sha256": _aggregate_hashes(checkpoint_hashes),
            },
        },
        "holdout": {
            "path": DEFAULT_HOLDOUT_RELATIVE,
            "manifest_path": str(config["data"]["manifest"]),
            "manifest_sha256": sha256_file(a5_manifest_path),
            "rows": holdout_artifact.get("rows"),
            "sha256_from_manifest": holdout_artifact.get("sha256"),
            "view": str(config["data"]["view"]),
            "file_read": False,
            "one_time": True,
        },
        "p2": {
            **p2_contract,
            "role": "external_hard_regression_set_not_blind_holdout",
            "content_parsed_by_c3_freeze": False,
            "files_hashed_for_lineage": True,
        },
        "contracts": {
            "versions": frozen_contracts.get("versions"),
            "prompt": prompt_contract,
            "tools": tool_contract,
            "trace": trace_contract,
        },
        "inference": {
            "routes": list(ROUTES),
            "do_sample": False,
            "max_new_tokens": int(config["evaluation"]["generation_max_new_tokens"]),
            "batch_size": 1,
            "chat_template": "pinned upstream tokenizer chat template",
            "special_tokens": "pinned tokenizer values; pad falls back to eos only when absent",
            "seed": int(config["training"]["seed"]),
        },
        "statistics": {
            "a5_primary": "full tool-call sequence exact rate, LoRA minus base",
            "paired_binary": "two-sided exact McNemar",
            "bootstrap": {
                "method": "paired percentile",
                "seed": BOOTSTRAP_SEED,
                "resamples": BOOTSTRAP_RESAMPLES,
                "confidence": 0.95,
            },
            "layers_reported_separately": ["a5", "p2"],
        },
        "implementation": _file_contract(EVALUATION_IMPLEMENTATION_FILES),
        "gates": {
            "c2_completed": True,
            "holdout_read": False,
            "holdout_consumption_requires_exact_freeze_sha": True,
            "repeated_new_run_forbidden": True,
            "same_run_resume_limit": 1,
        },
    }


def freeze_c3_evaluation(
    config_path: str | Path = DEFAULT_CONFIG,
    *,
    output_path: str | Path = DEFAULT_C3_FREEZE_MANIFEST,
    c0_manifest_path: str | Path = DEFAULT_FREEZE_MANIFEST,
    c1_report_path: str | Path = DEFAULT_C1_REPORT,
) -> dict[str, Any]:
    if _tracked_worktree_changes():
        raise ReadinessError(
            "C3 freeze requires a clean worktree; commit reviewed evaluation code first"
        )
    target = project_path(output_path)
    if target.exists():
        raise ReadinessError(
            f"C3 freeze manifest already exists and is immutable: {target}"
        )
    payload = build_c3_freeze_payload(
        config_path,
        c0_manifest_path=c0_manifest_path,
        c1_report_path=c1_report_path,
    )
    payload["status"] = "frozen"
    payload["created_at"] = _now()
    atomic_json(target, payload)
    return {
        **payload,
        "freeze_manifest_sha256": sha256_file(target),
        "output": str(target),
    }


def audit_c3_freeze(
    manifest_path: str | Path = DEFAULT_C3_FREEZE_MANIFEST,
    *,
    require_clean_git: bool = True,
) -> dict[str, Any]:
    target = project_path(manifest_path)
    frozen = _read_json(target, "C3 freeze manifest")
    if (
        frozen.get("kind") != "c3-final-evaluation-freeze"
        or frozen.get("status") != "frozen"
    ):
        raise ReadinessError("invalid C3 freeze manifest status/kind")
    if require_clean_git and _tracked_worktree_changes():
        raise ReadinessError("C3 evaluation requires a clean worktree")
    current = build_c3_freeze_payload(
        frozen["lineage"]["config_path"],
        c0_manifest_path=frozen["lineage"]["c0_manifest_path"],
        c1_report_path=frozen["lineage"]["c1_report_path"],
    )
    for key, value in current.items():
        if key in {"status", "created_at"}:
            continue
        if frozen.get(key) != value:
            raise ReadinessError(f"C3 freeze drift detected at {key}")
    return {
        "passed": True,
        "experiment_id": frozen["experiment_id"],
        "evaluation_git_revision": frozen["lineage"]["evaluation_git_revision"],
        "freeze_manifest_sha256": sha256_file(target),
        "holdout_read": False,
    }


def c3_preflight(
    manifest_path: str | Path = DEFAULT_C3_FREEZE_MANIFEST,
    *,
    ledger_path: str | Path = DEFAULT_C3_LEDGER,
) -> dict[str, Any]:
    audit = audit_c3_freeze(manifest_path)
    frozen = _read_json(project_path(manifest_path), "C3 freeze manifest")
    ledger = _read_jsonl(project_path(ledger_path), "C3 holdout ledger")
    events = [
        row for row in ledger if row.get("experiment_id") == frozen["experiment_id"]
    ]
    return {
        **audit,
        "holdout_path_present": project_path(frozen["holdout"]["path"]).is_file(),
        "holdout_file_opened": False,
        "consumption_events": len(events),
        "new_run_allowed": not events,
        "resume_run_ids": sorted(
            {
                str(row["run_id"])
                for row in events
                if row.get("status")
                in {"started", "dataset_verified", "route_complete", "resumed"}
            }
            - {
                str(row["run_id"])
                for row in events
                if row.get("status") in {"complete", "failed_before_generation"}
            }
        ),
    }


def _normalized_call(value: Mapping[str, Any]) -> dict[str, Any] | None:
    function = (
        value.get("function") if isinstance(value.get("function"), Mapping) else value
    )
    name = str((function or {}).get("name") or "").strip()
    arguments = (function or {}).get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if not name or not isinstance(arguments, dict):
        return None
    return {"name": name, "arguments": arguments}


def _expected_calls(sample: Mapping[str, Any]) -> list[dict[str, Any]]:
    messages = sample.get("messages") or []
    raw_calls = (messages[-1] if messages else {}).get("tool_calls") or []
    calls: list[dict[str, Any]] = []
    for value in raw_calls:
        if not isinstance(value, Mapping):
            raise ReadinessError(
                f"holdout sample {sample.get('sample_id')} has invalid tool-call target"
            )
        normalized = _normalized_call(value)
        if normalized is None:
            raise ReadinessError(
                f"holdout sample {sample.get('sample_id')} has invalid tool-call target"
            )
        calls.append(normalized)
    if not calls:
        raise ReadinessError(
            f"holdout sample {sample.get('sample_id')} has no tool-call target"
        )
    return calls


def _parse_generated_calls(text: str) -> list[dict[str, Any]] | None:
    matches = TOOL_CALL_RE.findall(text)
    if not matches:
        return None
    calls: list[dict[str, Any]] = []
    for raw in matches:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(value, dict):
            return None
        normalized = _normalized_call(value)
        if normalized is None:
            return None
        calls.append(normalized)
    return calls


def _load_claimed_holdout(
    path: Path, frozen: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Open holdout only after an append-only consumption claim exists."""

    expected_hash = str(frozen["holdout"]["sha256_from_manifest"])
    if sha256_file(path) != expected_hash:
        raise ReadinessError("A5 holdout hash differs from the C3 freeze manifest")
    rows = _read_jsonl(path, "claimed A5 holdout")
    expected_rows = int(frozen["holdout"]["rows"])
    if len(rows) != expected_rows:
        raise ReadinessError(
            f"A5 holdout has {len(rows)} rows; expected {expected_rows}"
        )
    seen: set[str] = set()
    for line_no, row in enumerate(rows, 1):
        if (
            row.get("split") != "holdout"
            or row.get("view") != frozen["holdout"]["view"]
        ):
            raise ReadinessError(f"A5 holdout row {line_no} has the wrong split/view")
        sample_id = str(row.get("sample_id") or "")
        if not sample_id or sample_id in seen:
            raise ReadinessError(
                f"A5 holdout row {line_no} has a missing/duplicate sample_id"
            )
        messages = row.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise ReadinessError(f"A5 holdout row {line_no} has incomplete messages")
        if messages[0].get("role") != "user" or messages[-1].get("role") != "assistant":
            raise ReadinessError(
                f"A5 holdout row {line_no} has an invalid conversation boundary"
            )
        _expected_calls(row)
        seen.add(sample_id)
    return rows


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _exact_mcnemar_p(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if discordant == 0:
        return 1.0
    tail = min(left_only, right_only)
    probability = sum(math.comb(discordant, value) for value in range(tail + 1)) / (
        2**discordant
    )
    return min(1.0, 2.0 * probability)


def paired_binary_statistics(
    left: Mapping[str, bool],
    right: Mapping[str, bool],
    *,
    seed: int = BOOTSTRAP_SEED,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, Any]:
    if set(left) != set(right) or not left:
        raise ReadinessError("paired statistics require the same non-empty task IDs")
    task_ids = sorted(left)
    both = sum(bool(left[item]) and bool(right[item]) for item in task_ids)
    left_only = sum(bool(left[item]) and not bool(right[item]) for item in task_ids)
    right_only = sum(not bool(left[item]) and bool(right[item]) for item in task_ids)
    neither = len(task_ids) - both - left_only - right_only
    differences = [int(bool(right[item])) - int(bool(left[item])) for item in task_ids]
    rng = random.Random(seed)
    bootstrap = []
    for _ in range(resamples):
        bootstrap.append(
            100.0
            * sum(differences[rng.randrange(len(differences))] for _ in task_ids)
            / len(task_ids)
        )
    return {
        "tasks": len(task_ids),
        "left_rate": sum(bool(left[item]) for item in task_ids) / len(task_ids),
        "right_rate": sum(bool(right[item]) for item in task_ids) / len(task_ids),
        "difference_percentage_points": 100.0 * sum(differences) / len(task_ids),
        "pairs": {
            "both_success": both,
            "left_only": left_only,
            "right_only": right_only,
            "both_failure": neither,
        },
        "net_wins_right_minus_left": right_only - left_only,
        "mcnemar_exact_two_sided_p": _exact_mcnemar_p(left_only, right_only),
        "paired_bootstrap_95ci_percentage_points": {
            "low": _percentile(bootstrap, 0.025),
            "high": _percentile(bootstrap, 0.975),
            "seed": seed,
            "resamples": resamples,
        },
    }


def summarize_generation_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_route: dict[str, dict[str, Mapping[str, Any]]] = {route: {} for route in ROUTES}
    for row in rows:
        route = str(row.get("route") or "")
        sample_id = str(row.get("sample_id") or "")
        if route not in by_route or not sample_id or sample_id in by_route[route]:
            raise ReadinessError(
                "raw C3 generations contain an invalid route/sample pair"
            )
        by_route[route][sample_id] = row
    if set(by_route["base"]) != set(by_route["lora"]) or not by_route["base"]:
        raise ReadinessError("C3 raw generations are not a complete base/LoRA pairing")

    route_metrics: dict[str, Any] = {}
    paired: dict[str, Any] = {}
    for route in ROUTES:
        route_rows = by_route[route]
        route_metrics[route] = {
            "samples": len(route_rows),
            **{
                field: sum(bool(row.get(field)) for row in route_rows.values())
                / len(route_rows)
                for field in METRIC_FIELDS
            },
            "latency_ms_median": _percentile(
                [float(row.get("latency_ms") or 0.0) for row in route_rows.values()],
                0.5,
            ),
            "latency_ms_p95": _percentile(
                [float(row.get("latency_ms") or 0.0) for row in route_rows.values()],
                0.95,
            ),
        }
    for field in METRIC_FIELDS:
        paired[field] = paired_binary_statistics(
            {sample: bool(row.get(field)) for sample, row in by_route["base"].items()},
            {sample: bool(row.get(field)) for sample, row in by_route["lora"].items()},
        )
    return {
        "routes": route_metrics,
        "paired_lora_minus_base": paired,
        "primary_metric": paired["sequence_exact"],
    }


def _score_generation(
    *,
    run_id: str,
    route: str,
    sample: Mapping[str, Any],
    generated_text: str,
    generated_token_ids: Sequence[int],
    latency_ms: float,
) -> dict[str, Any]:
    expected = _expected_calls(sample)
    actual = _parse_generated_calls(generated_text)
    parsed = actual is not None
    actual_calls = actual or []
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "sample_id": sample["sample_id"],
        "route": route,
        "generated_at": _now(),
        "generated_text": generated_text,
        "generated_token_ids": list(generated_token_ids),
        "expected_tool_calls": expected,
        "actual_tool_calls": actual,
        "parse_success": parsed,
        "name_exact": parsed
        and [item["name"] for item in actual_calls]
        == [item["name"] for item in expected],
        "arguments_exact": parsed
        and [item["arguments"] for item in actual_calls]
        == [item["arguments"] for item in expected],
        "sequence_exact": parsed and actual_calls == expected,
        "latency_ms": latency_ms,
    }


def _generate_route(
    route: str,
    samples: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    frozen: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Imported lazily so local audits/tests do not require the GPU stack.  This
    # reuses model loading only; it never calls training.data.load_samples.
    from training.runtime import (
        _load_base_model,
        _load_tokenizer,
        _require_training_stack,
    )

    stack = _require_training_stack()
    torch = stack["torch"]
    if not torch.cuda.is_available():
        raise ReadinessError("C3 base/LoRA generation requires CUDA")
    torch.manual_seed(int(frozen["inference"]["seed"]))
    torch.cuda.manual_seed_all(int(frozen["inference"]["seed"]))
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    model = None
    try:
        tokenizer = _load_tokenizer(stack, config)
        model = _load_base_model(stack, config)
        if route == "lora":
            model = stack["PeftModel"].from_pretrained(
                model,
                str(frozen["c2"]["adapter"]["path"]),
                is_trainable=False,
            )
        model.eval()
        model.config.use_cache = True
        torch.cuda.reset_peak_memory_stats()
        for sample in samples:
            prompt = tokenizer.apply_chat_template(
                list(sample["messages"][:-1]),
                tokenize=False,
                add_generation_prompt=True,
            )
            encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
            encoded = {key: value.to(model.device) for key, value in encoded.items()}
            sample_started = time.monotonic()
            with torch.inference_mode():
                output = model.generate(
                    **encoded,
                    max_new_tokens=int(frozen["inference"]["max_new_tokens"]),
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )
            continuation = output[0, encoded["input_ids"].shape[1] :]
            rows.append(
                _score_generation(
                    run_id=run_id,
                    route=route,
                    sample=sample,
                    generated_text=tokenizer.decode(
                        continuation, skip_special_tokens=False
                    ),
                    generated_token_ids=continuation.tolist(),
                    latency_ms=(time.monotonic() - sample_started) * 1000.0,
                )
            )
        resources = {
            "walltime_seconds": time.monotonic() - started,
            "peak_memory_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_memory_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        }
    finally:
        if model is not None:
            del model
        gc.collect()
        torch.cuda.empty_cache()
    return rows, resources


def _run_events(
    ledger: Sequence[Mapping[str, Any]], experiment_id: str
) -> list[dict[str, Any]]:
    return [dict(row) for row in ledger if row.get("experiment_id") == experiment_id]


def _summarize_resource_events(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    freeze_sha256: str,
) -> dict[str, Any]:
    summarized: dict[str, Any] = {}
    for route in ROUTES:
        events = []
        for row in rows:
            if (
                row.get("run_id") != run_id
                or row.get("freeze_manifest_sha256") != freeze_sha256
                or row.get("route") not in ROUTES
            ):
                raise ReadinessError("C3 resource event has invalid lineage")
            if row.get("route") == route:
                sample_ids = row.get("sample_ids")
                resources = row.get("resources")
                if not isinstance(sample_ids, list) or not isinstance(resources, dict):
                    raise ReadinessError("C3 resource event has an invalid payload")
                events.append(dict(row))
        if not events:
            raise ReadinessError(f"C3 {route} route has no resource evidence")
        summarized[route] = {
            "segments": len(events),
            "attempted_samples": sum(len(row["sample_ids"]) for row in events),
            "walltime_seconds": sum(
                float((row.get("resources") or {}).get("walltime_seconds") or 0.0)
                for row in events
            ),
            "peak_memory_allocated_bytes": max(
                int(
                    (row.get("resources") or {}).get("peak_memory_allocated_bytes") or 0
                )
                for row in events
            ),
            "peak_memory_reserved_bytes": max(
                int((row.get("resources") or {}).get("peak_memory_reserved_bytes") or 0)
                for row in events
            ),
            "events": events,
        }
    return summarized


def _claim_or_resume(
    *,
    ledger_path: Path,
    experiment_id: str,
    freeze_sha256: str,
    resume_run_id: str | None,
) -> tuple[str, str]:
    with _exclusive_ledger_lock(ledger_path):
        events = _run_events(
            _read_jsonl(ledger_path, "C3 holdout ledger"), experiment_id
        )
        if resume_run_id is None:
            if events:
                raise ReadinessError(
                    "A5 holdout already has a consumption record; a second new run is forbidden"
                )
            run_id = f"c3-{uuid.uuid4().hex}"
            consumed_at = _now()
            _append_jsonl_fsync(
                ledger_path,
                {
                    "schema_version": "1.0",
                    "status": "started",
                    "event_at": consumed_at,
                    "holdout_consumed_at": consumed_at,
                    "experiment_id": experiment_id,
                    "run_id": run_id,
                    "freeze_manifest_sha256": freeze_sha256,
                },
            )
            return run_id, consumed_at

        matching = [row for row in events if row.get("run_id") == resume_run_id]
        if not matching or any(row.get("status") == "complete" for row in matching):
            raise ReadinessError("C3 resume requires the same incomplete run ID")
        if any(row.get("status") == "failed_before_generation" for row in matching):
            raise ReadinessError(
                "C3 run failed before a verified dataset; fail-closed policy forbids reopening"
            )
        if not any(row.get("status") == "dataset_verified" for row in matching):
            raise ReadinessError("C3 resume requires a prior dataset_verified event")
        if sum(row.get("status") == "resumed" for row in matching) >= 1:
            raise ReadinessError("C3 same-run resume limit of one has been exhausted")
        if any(row.get("freeze_manifest_sha256") != freeze_sha256 for row in matching):
            raise ReadinessError("C3 resume freeze hash differs from the original run")
        consumed_at = str(
            matching[0].get("holdout_consumed_at") or matching[0]["event_at"]
        )
        _append_jsonl_fsync(
            ledger_path,
            {
                "schema_version": "1.0",
                "status": "resumed",
                "event_at": _now(),
                "holdout_consumed_at": consumed_at,
                "experiment_id": experiment_id,
                "run_id": resume_run_id,
                "freeze_manifest_sha256": freeze_sha256,
            },
        )
        return resume_run_id, consumed_at


RouteGenerator = Callable[
    [str, Sequence[Mapping[str, Any]], str],
    tuple[list[dict[str, Any]], dict[str, Any]],
]


def run_one_time_holdout(
    *,
    experiment_id: str,
    confirm_freeze_sha256: str,
    manifest_path: str | Path = DEFAULT_C3_FREEZE_MANIFEST,
    ledger_path: str | Path = DEFAULT_C3_LEDGER,
    runs_root: str | Path = DEFAULT_C3_RUNS,
    resume_run_id: str | None = None,
    route_generator: RouteGenerator | None = None,
) -> dict[str, Any]:
    audit = audit_c3_freeze(manifest_path)
    frozen_path = project_path(manifest_path)
    frozen = _read_json(frozen_path, "C3 freeze manifest")
    freeze_hash = audit["freeze_manifest_sha256"]
    if experiment_id != frozen["experiment_id"]:
        raise ReadinessError(
            "explicit C3 experiment ID does not match the freeze manifest"
        )
    if confirm_freeze_sha256 != freeze_hash:
        raise ReadinessError(
            "--confirm-freeze-sha256 must exactly match the audited C3 freeze manifest"
        )

    ledger = project_path(ledger_path)
    run_id, consumed_at = _claim_or_resume(
        ledger_path=ledger,
        experiment_id=experiment_id,
        freeze_sha256=freeze_hash,
        resume_run_id=resume_run_id,
    )
    run_dir = project_path(runs_root) / run_id
    raw_path = run_dir / "raw-generations.jsonl"
    resource_path = run_dir / "resource-events.jsonl"
    summary_path = run_dir / "summary.json"
    if resume_run_id is None and run_dir.exists():
        raise ReadinessError("new C3 run directory unexpectedly already exists")
    if summary_path.exists():
        raise ReadinessError(
            "C3 run summary already exists; completed evidence is immutable"
        )
    existing = _read_jsonl(raw_path, "C3 raw generations")
    existing_keys = {(row.get("route"), row.get("sample_id")) for row in existing}
    if len(existing_keys) != len(existing):
        raise ReadinessError("C3 raw generations contain duplicate route/sample rows")

    try:
        samples = _load_claimed_holdout(project_path(frozen["holdout"]["path"]), frozen)
    except Exception:
        if resume_run_id is None:
            _append_jsonl_fsync(
                ledger,
                {
                    "schema_version": "1.0",
                    "status": "failed_before_generation",
                    "event_at": _now(),
                    "holdout_consumed_at": consumed_at,
                    "experiment_id": experiment_id,
                    "run_id": run_id,
                    "freeze_manifest_sha256": freeze_hash,
                },
            )
        raise
    if not any(
        row.get("run_id") == run_id and row.get("status") == "dataset_verified"
        for row in _read_jsonl(ledger, "C3 holdout ledger")
    ):
        _append_jsonl_fsync(
            ledger,
            {
                "schema_version": "1.0",
                "status": "dataset_verified",
                "event_at": _now(),
                "holdout_consumed_at": consumed_at,
                "experiment_id": experiment_id,
                "run_id": run_id,
                "freeze_manifest_sha256": freeze_hash,
                "holdout_sha256": frozen["holdout"]["sha256_from_manifest"],
                "rows": len(samples),
            },
        )

    config = load_config(frozen["lineage"]["config_path"])
    for route in ROUTES:
        missing = [
            sample
            for sample in samples
            if (route, sample["sample_id"]) not in existing_keys
        ]
        if missing:
            if route_generator is None:
                generated, route_resources = _generate_route(
                    route,
                    missing,
                    run_id=run_id,
                    frozen=frozen,
                    config=config,
                )
            else:
                generated, route_resources = route_generator(route, missing, run_id)
            expected_ids = [sample["sample_id"] for sample in missing]
            if [row.get("sample_id") for row in generated] != expected_ids:
                raise ReadinessError(
                    f"C3 {route} generator returned rows out of order or with wrong IDs"
                )
            _append_jsonl_fsync(
                resource_path,
                {
                    "schema_version": "1.0",
                    "event_at": _now(),
                    "experiment_id": experiment_id,
                    "run_id": run_id,
                    "freeze_manifest_sha256": freeze_hash,
                    "route": route,
                    "sample_ids": expected_ids,
                    "resources": route_resources,
                },
            )
            for row in generated:
                if row.get("route") != route or row.get("run_id") != run_id:
                    raise ReadinessError(
                        f"C3 {route} generator returned invalid lineage"
                    )
                _append_jsonl_fsync(raw_path, row)
                existing_keys.add((route, row["sample_id"]))
        route_already_complete = any(
            row.get("run_id") == run_id
            and row.get("status") == "route_complete"
            and row.get("route") == route
            for row in _read_jsonl(ledger, "C3 holdout ledger")
        )
        if not route_already_complete:
            _append_jsonl_fsync(
                ledger,
                {
                    "schema_version": "1.0",
                    "status": "route_complete",
                    "event_at": _now(),
                    "holdout_consumed_at": consumed_at,
                    "experiment_id": experiment_id,
                    "run_id": run_id,
                    "freeze_manifest_sha256": freeze_hash,
                    "route": route,
                },
            )

    final_rows = _read_jsonl(raw_path, "C3 raw generations")
    expected_count = int(frozen["holdout"]["rows"]) * len(ROUTES)
    if len(final_rows) != expected_count:
        raise ReadinessError(
            f"C3 raw output has {len(final_rows)} rows; expected {expected_count}"
        )
    resource_events = _read_jsonl(resource_path, "C3 resource events")
    resources = _summarize_resource_events(
        resource_events,
        run_id=run_id,
        freeze_sha256=freeze_hash,
    )
    results = summarize_generation_rows(final_rows)
    raw_hash = sha256_file(raw_path)
    resource_hash = sha256_file(resource_path)
    summary = {
        "schema_version": "1.0",
        "kind": "c3-a5-holdout-base-lora-evaluation",
        "status": "complete",
        "completed_at": _now(),
        "holdout_consumed_at": consumed_at,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "freeze_manifest_sha256": freeze_hash,
        "evaluation_git_revision": frozen["lineage"]["evaluation_git_revision"],
        "training_git_revision": frozen["lineage"]["training_git_revision"],
        "adapter_aggregate_sha256": frozen["c2"]["adapter"]["aggregate_sha256"],
        "holdout_read": True,
        "holdout_rows": int(frozen["holdout"]["rows"]),
        "raw_output_path": str(raw_path),
        "raw_output_sha256": raw_hash,
        "resource_output_path": str(resource_path),
        "resource_output_sha256": resource_hash,
        "resources": resources,
        "results": results,
        "decision_scope": "A5 base-vs-LoRA tool generation only; P2/cloud/hybrid remain separate",
    }
    atomic_json(summary_path, summary)
    summary_hash = sha256_file(summary_path)
    _append_jsonl_fsync(
        ledger,
        {
            "schema_version": "1.0",
            "status": "complete",
            "event_at": _now(),
            "holdout_consumed_at": consumed_at,
            "experiment_id": experiment_id,
            "run_id": run_id,
            "freeze_manifest_sha256": freeze_hash,
            "raw_output_path": str(raw_path),
            "raw_output_sha256": raw_hash,
            "resource_output_path": str(resource_path),
            "resource_output_sha256": resource_hash,
            "summary_path": str(summary_path),
            "summary_sha256": summary_hash,
        },
    )
    return {
        **summary,
        "summary_path": str(summary_path),
        "summary_sha256": summary_hash,
    }


def audit_completed_c3_run(
    run_id: str,
    *,
    manifest_path: str | Path = DEFAULT_C3_FREEZE_MANIFEST,
    ledger_path: str | Path = DEFAULT_C3_LEDGER,
    runs_root: str | Path = DEFAULT_C3_RUNS,
) -> dict[str, Any]:
    freeze = audit_c3_freeze(manifest_path)
    frozen = _read_json(project_path(manifest_path), "C3 freeze manifest")
    events = [
        row
        for row in _read_jsonl(project_path(ledger_path), "C3 holdout ledger")
        if row.get("experiment_id") == frozen["experiment_id"]
        and row.get("run_id") == run_id
    ]
    completed = [row for row in events if row.get("status") == "complete"]
    if len(completed) != 1:
        raise ReadinessError(
            "C3 run audit requires exactly one append-only complete event"
        )
    if any(
        row.get("freeze_manifest_sha256") != freeze["freeze_manifest_sha256"]
        for row in events
    ):
        raise ReadinessError("C3 ledger contains mixed freeze-manifest lineage")
    if sum(row.get("status") == "started" for row in events) != 1:
        raise ReadinessError(
            "C3 run audit requires exactly one initial consumption claim"
        )
    if sum(row.get("status") == "dataset_verified" for row in events) != 1:
        raise ReadinessError(
            "C3 run audit requires exactly one dataset verification event"
        )
    if sum(row.get("status") == "resumed" for row in events) > 1:
        raise ReadinessError("C3 run exceeded the same-run resume limit")
    completed_routes = [
        str(row.get("route")) for row in events if row.get("status") == "route_complete"
    ]
    if sorted(completed_routes) != sorted(ROUTES):
        raise ReadinessError("C3 run audit requires one completion event per route")
    allowed_statuses = {
        "started",
        "dataset_verified",
        "route_complete",
        "resumed",
        "complete",
    }
    if any(row.get("status") not in allowed_statuses for row in events):
        raise ReadinessError("completed C3 ledger contains an invalid status")
    event = completed[0]
    run_dir = project_path(runs_root) / run_id
    raw_path = run_dir / "raw-generations.jsonl"
    resource_path = run_dir / "resource-events.jsonl"
    summary_path = run_dir / "summary.json"
    if sha256_file(raw_path) != event.get("raw_output_sha256"):
        raise ReadinessError("C3 raw output hash differs from the append-only ledger")
    if sha256_file(summary_path) != event.get("summary_sha256"):
        raise ReadinessError("C3 summary hash differs from the append-only ledger")
    if sha256_file(resource_path) != event.get("resource_output_sha256"):
        raise ReadinessError(
            "C3 resource evidence hash differs from the append-only ledger"
        )
    summary = _read_json(summary_path, "C3 summary")
    if (
        summary.get("run_id") != run_id
        or summary.get("experiment_id") != frozen["experiment_id"]
        or summary.get("freeze_manifest_sha256") != freeze["freeze_manifest_sha256"]
        or summary.get("holdout_read") is not True
        or summary.get("raw_output_sha256") != event.get("raw_output_sha256")
        or summary.get("resource_output_sha256") != event.get("resource_output_sha256")
    ):
        raise ReadinessError("C3 summary lineage is invalid")
    rows = _read_jsonl(raw_path, "C3 raw generations")
    expected_rows = int(frozen["holdout"]["rows"]) * len(ROUTES)
    if len(rows) != expected_rows or any(row.get("run_id") != run_id for row in rows):
        raise ReadinessError("C3 raw generations have invalid count or run lineage")
    recomputed = summarize_generation_rows(rows)
    if summary.get("results") != recomputed:
        raise ReadinessError(
            "C3 paired statistics differ from the immutable raw outputs"
        )
    resource_rows = _read_jsonl(resource_path, "C3 resource events")
    recomputed_resources = _summarize_resource_events(
        resource_rows,
        run_id=run_id,
        freeze_sha256=freeze["freeze_manifest_sha256"],
    )
    if summary.get("resources") != recomputed_resources:
        raise ReadinessError(
            "C3 resource summary differs from the immutable resource events"
        )
    return {
        "passed": True,
        "experiment_id": frozen["experiment_id"],
        "run_id": run_id,
        "freeze_manifest_sha256": freeze["freeze_manifest_sha256"],
        "raw_output_sha256": event["raw_output_sha256"],
        "resource_output_sha256": event["resource_output_sha256"],
        "summary_sha256": event["summary_sha256"],
        "holdout_read": True,
        "new_run_allowed": False,
    }
