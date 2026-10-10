"""C5-2 development-data loader, contract renderer, and CPU engineering gate.

This module is intentionally separate from the C0-C4 A5 training runtime. It
only accepts the three hash-locked C5 development splits, renders every record
through :mod:`training.c5_contract`, and never knows a final-holdout path or
decryption key.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from training.c5_contract import (
    BASE_MODEL,
    BASE_MODEL_REVISION,
    CONTRACT_ID,
    EXPERIMENT_ID,
    MAX_SEQUENCE_TOKENS,
    parse_invocation,
    parse_selection,
    render_invocation,
    render_selection,
)
from training.c5_dataset import DATASET_ID, DEVELOPMENT_SPLITS
from training.c5_freeze import canonical_bytes, sha256_file
from training.tool_contract_candidate import ContractError
from training.c5_inventory import load_public_mcp_tools


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "eval/c5/c5-engineering-config.json"
DEFAULT_FREEZE_MANIFEST = ROOT / "eval/c5/dataset-v2-freeze-manifest.json"
FORBIDDEN_PATH_MARKERS = ("holdout", "final-holdout", "final_holdout", "a5", "/p2/")


class C5EngineeringError(RuntimeError):
    """A C5-2 lineage, isolation, rendering, or token invariant failed."""


@dataclass(frozen=True, slots=True)
class RenderedTrainingRecord:
    split: str
    family_id: str
    record_id: str
    stage: str
    selected_tool: str | None
    prompt: str
    full: str
    target: str
    prompt_tokens: int
    full_tokens: int
    prompt_token_ids: tuple[int, ...]
    full_token_ids: tuple[int, ...]

    @property
    def label_token_count(self) -> int:
        return len(self.full_token_ids) - len(self.prompt_token_ids)


class C5TokenizedDataset:
    """Eager assistant-only dataset accepted by the Hugging Face Trainer."""

    def __init__(self, records: Sequence[RenderedTrainingRecord]) -> None:
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - optional training dependency
            raise C5EngineeringError("tokenized dataset requires torch") from exc
        self._items = []
        for record in records:
            prompt_size = len(record.prompt_token_ids)
            labels = [-100] * prompt_size + list(record.full_token_ids[prompt_size:])
            if not labels or all(value == -100 for value in labels):
                raise C5EngineeringError(f"{record.record_id}: assistant target is empty")
            self._items.append({
                "input_ids": torch.tensor(record.full_token_ids, dtype=torch.long),
                "attention_mask": torch.ones(len(record.full_token_ids), dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long),
            })

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self._items[index]


class C5CausalLMCollator:
    def __init__(self, pad_token_id: int) -> None:
        self.pad_token_id = pad_token_id

    def __call__(self, features: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        import torch

        width = max(int(item["input_ids"].shape[0]) for item in features)

        def pad(name: str, value: int) -> Any:
            return torch.stack([
                torch.nn.functional.pad(
                    item[name], (0, width - item[name].shape[0]), value=value
                )
                for item in features
            ])

        return {
            "input_ids": pad("input_ids", self.pad_token_id),
            "attention_mask": pad("attention_mask", 0),
            "labels": pad("labels", -100),
        }


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise C5EngineeringError(f"cannot load C5 engineering config: {exc}") from exc
    if not isinstance(value, dict):
        raise C5EngineeringError("C5 engineering config must be an object")
    return value


def _assert_safe_development_path(path: Path) -> None:
    lowered = "/" + path.resolve().as_posix().lower().strip("/") + "/"
    if any(marker in lowered for marker in FORBIDDEN_PATH_MARKERS):
        raise C5EngineeringError(f"development loader refuses protected path: {path}")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise C5EngineeringError(f"cannot read development split {path}: {exc}") from exc
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise C5EngineeringError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(value, dict):
            raise C5EngineeringError(f"{path}:{line_number}: family must be an object")
        rows.append(value)
    return rows


def verify_development_splits(
    dataset_dir: Path,
    *,
    config: Mapping[str, Any],
    freeze_manifest_path: Path = DEFAULT_FREEZE_MANIFEST,
) -> dict[str, list[dict[str, Any]]]:
    """Load exactly train/validation/development after byte-level verification."""

    _assert_safe_development_path(dataset_dir)
    try:
        freeze = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise C5EngineeringError(f"cannot load dataset freeze manifest: {exc}") from exc
    if freeze.get("dataset_id") != DATASET_ID or freeze.get("formal_split_locked") is not True:
        raise C5EngineeringError("dataset freeze is not the locked C5 development set")
    if freeze.get("final_holdout_included") is not False or freeze.get("final_holdout_rows_read") != 0:
        raise C5EngineeringError("dataset freeze has an unsafe final-holdout declaration")
    manifest_artifacts = {
        str(item.get("path") or ""): item for item in freeze.get("artifacts") or []
    }
    configured = (config.get("data") or {}).get("splits") or {}
    if set(configured) != set(DEVELOPMENT_SPLITS):
        raise C5EngineeringError("config must name exactly the three development splits")

    result: dict[str, list[dict[str, Any]]] = {}
    seen_families: set[str] = set()
    seen_records: set[str] = set()
    for split in DEVELOPMENT_SPLITS:
        filename = f"{split}.jsonl"
        expected = configured[split]
        public = manifest_artifacts.get(filename)
        if public is None or any(public.get(key) != expected.get(key) for key in (
            "sha256", "families", "records"
        )):
            raise C5EngineeringError(f"{split}: config differs from public dataset freeze")
        path = dataset_dir / filename
        _assert_safe_development_path(path)
        if not path.is_file() or sha256_file(path) != expected["sha256"]:
            raise C5EngineeringError(f"{split}: split bytes differ from the locked hash")
        families = _load_jsonl(path)
        if len(families) != int(expected["families"]):
            raise C5EngineeringError(f"{split}: family count differs from freeze")
        record_count = 0
        for family in families:
            family_id = str(family.get("family_id") or "")
            if (
                not family_id
                or family_id in seen_families
                or family.get("split") != split
                or family.get("dataset_id") != DATASET_ID
                or family.get("contract_id") != CONTRACT_ID
                or (family.get("review") or {}).get("status") != "approved"
                or (family.get("review") or {}).get("reviewer_1") != "repository_owner"
            ):
                raise C5EngineeringError(f"{split}: family identity/review invariant failed")
            seen_families.add(family_id)
            records = family.get("records") or []
            if not isinstance(records, list) or not records:
                raise C5EngineeringError(f"{family_id}: no training records")
            record_count += len(records)
            for record in records:
                record_id = str(record.get("record_id") or "")
                if not record_id or record_id in seen_records:
                    raise C5EngineeringError(f"{family_id}: duplicate or missing record ID")
                seen_records.add(record_id)
        if record_count != int(expected["records"]):
            raise C5EngineeringError(f"{split}: record count differs from freeze")
        result[split] = families
    return result


def load_pinned_tokenizer(snapshot: Path, *, config: Mapping[str, Any]) -> Any:
    """Load one explicit local snapshot; network fallback is never allowed."""

    if not snapshot.is_dir() or snapshot.name != BASE_MODEL_REVISION:
        raise C5EngineeringError("tokenizer snapshot path is absent or has the wrong revision")
    tokenizer_config = snapshot / "tokenizer_config.json"
    expected = config["base_model"]["tokenizer"]["tokenizer_config_sha256"]
    if not tokenizer_config.is_file() or sha256_file(tokenizer_config) != expected:
        raise C5EngineeringError("tokenizer_config.json differs from the C5 freeze")
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise C5EngineeringError("transformers is required for the C5 token audit") from exc
    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def _token_ids(tokenizer: Any, text: str) -> tuple[int, ...]:
    return tuple(tokenizer(text, add_special_tokens=False)["input_ids"])


def render_development_records(
    families_by_split: Mapping[str, Sequence[Mapping[str, Any]]],
    tokenizer: Any,
) -> list[RenderedTrainingRecord]:
    tools = load_public_mcp_tools()
    rendered: list[RenderedTrainingRecord] = []
    for split in DEVELOPMENT_SPLITS:
        for family in families_by_split[split]:
            family_id = str(family["family_id"])
            for record in family["records"]:
                stage = str(record.get("stage") or "")
                selected = record.get("selected_tool")
                try:
                    if stage == "selector":
                        value = render_selection(
                            tokenizer,
                            str(record["user_step"]),
                            tools,
                            selected_tool=selected,
                        )
                    elif stage == "invocation":
                        if not isinstance(selected, str):
                            raise C5EngineeringError(f"{record['record_id']}: invocation lacks tool")
                        value = render_invocation(
                            tokenizer,
                            str(record["user_step"]),
                            tools,
                            selected,
                            arguments=dict(record.get("arguments") or {}),
                        )
                    else:
                        raise C5EngineeringError(f"{record['record_id']}: unknown stage {stage}")
                except (ContractError, KeyError, TypeError) as exc:
                    raise C5EngineeringError(
                        f"{record.get('record_id')}: contract rendering failed: {exc}"
                    ) from exc
                if value.full is None or value.full_tokens is None or not value.full.startswith(value.prompt):
                    raise C5EngineeringError(f"{record['record_id']}: target rendering is incomplete")
                target = value.full[len(value.prompt):]
                if stage == "selector":
                    if parse_selection(target, tools) != selected:
                        raise C5EngineeringError(f"{record['record_id']}: selector round-trip drift")
                else:
                    parsed = parse_invocation(target, str(selected), tools)
                    if parsed["arguments"] != record.get("arguments"):
                        raise C5EngineeringError(f"{record['record_id']}: invocation round-trip drift")
                prompt_ids = _token_ids(tokenizer, value.prompt)
                full_ids = _token_ids(tokenizer, value.full)
                if full_ids[:len(prompt_ids)] != prompt_ids:
                    raise C5EngineeringError(f"{record['record_id']}: token prefix drift")
                if len(full_ids) > MAX_SEQUENCE_TOKENS or len(full_ids) <= len(prompt_ids):
                    raise C5EngineeringError(f"{record['record_id']}: invalid target token budget")
                rendered.append(RenderedTrainingRecord(
                    split=split,
                    family_id=family_id,
                    record_id=str(record["record_id"]),
                    stage=stage,
                    selected_tool=selected if isinstance(selected, str) else None,
                    prompt=value.prompt,
                    full=value.full,
                    target=target,
                    prompt_tokens=len(prompt_ids),
                    full_tokens=len(full_ids),
                    prompt_token_ids=prompt_ids,
                    full_token_ids=full_ids,
                ))
    return rendered


def _stable_key(value: str) -> str:
    return hashlib.sha256(f"c5-engineering-smoke-v1:{value}".encode()).hexdigest()


def select_overfit_smoke(
    records: Sequence[RenderedTrainingRecord], *, total: int = 64
) -> list[RenderedTrainingRecord]:
    """Deterministically select a balanced train-only 32-64 record smoke set."""

    if total < 32 or total > 64 or total % 2:
        raise C5EngineeringError("overfit smoke must contain an even 32-64 records")
    train = [record for record in records if record.split == "train"]
    selectors = sorted((r for r in train if r.stage == "selector"), key=lambda r: _stable_key(r.record_id))
    invocations = [r for r in train if r.stage == "invocation"]
    per_stage = total // 2
    by_tool: dict[str, list[RenderedTrainingRecord]] = defaultdict(list)
    for record in invocations:
        by_tool[str(record.selected_tool)].append(record)
    chosen_invocations: list[RenderedTrainingRecord] = []
    for tool in sorted(by_tool):
        by_tool[tool].sort(key=lambda r: _stable_key(r.record_id))
        chosen_invocations.append(by_tool[tool][0])
    remaining = sorted(
        (r for r in invocations if r not in chosen_invocations),
        key=lambda r: _stable_key(r.record_id),
    )
    chosen_invocations.extend(remaining[:per_stage - len(chosen_invocations)])
    chosen = selectors[:per_stage] + chosen_invocations
    if len(chosen) != total or len({r.record_id for r in chosen}) != total:
        raise C5EngineeringError("cannot build the frozen overfit smoke set")
    return sorted(chosen, key=lambda r: _stable_key(r.record_id))


def audit_engineering_gate(
    dataset_dir: Path,
    tokenizer_snapshot: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    config = load_config(config_path)
    if (
        config.get("experiment_id") != EXPERIMENT_ID
        or config.get("contract_id") != CONTRACT_ID
        or config.get("base_model", {}).get("id") != BASE_MODEL
        or config.get("base_model", {}).get("revision") != BASE_MODEL_REVISION
        or config.get("data", {}).get("dataset_id") != DATASET_ID
        or config.get("training", {}).get("max_sequence_length") != MAX_SEQUENCE_TOKENS
        or config.get("training", {}).get("overflow_policy") != "reject"
    ):
        raise C5EngineeringError("C5 engineering config identity or token policy drifted")
    holdout = config.get("holdout_policy") or {}
    if holdout != {
        "claim_allowed": False,
        "content_read_allowed": False,
        "final_holdout_rows_read": 0,
    }:
        raise C5EngineeringError("C5 engineering config has an unsafe holdout policy")
    diagnostics = config.get("diagnostics") or {}
    if (
        config.get("status") != "c5_2_cpu_authorized_gpu_pending"
        or diagnostics.get("gpu_authorized") is not False
        or diagnostics.get("development_runs_max") != 2
        or diagnostics.get("gpu_hours_max") != 4
        or not 32 <= int(diagnostics.get("overfit_samples") or 0) <= 64
        or int(diagnostics.get("system_diagnostic_train_families_max") or 0) > 32
        or int(diagnostics.get("system_diagnostic_max_optimizer_steps") or 0) > 26
        or config.get("formal_training_authorized") is not False
    ):
        raise C5EngineeringError("C5 diagnostic budget or authorization boundary drifted")
    families = verify_development_splits(dataset_dir, config=config)
    tokenizer = load_pinned_tokenizer(tokenizer_snapshot, config=config)
    records = render_development_records(families, tokenizer)
    public_tools = load_public_mcp_tools()
    smoke = select_overfit_smoke(records, total=int(config["diagnostics"]["overfit_samples"]))
    split_records = Counter(record.split for record in records)
    split_families = {split: len(families[split]) for split in DEVELOPMENT_SPLITS}
    stage_counts = Counter(record.stage for record in records)
    prompt_lengths = [record.prompt_tokens for record in records]
    full_lengths = [record.full_tokens for record in records]
    label_lengths = [record.label_token_count for record in records]
    smoke_tools = Counter(str(r.selected_tool) for r in smoke if r.stage == "invocation")
    lineage_payload = [
        {
            "record_id": record.record_id,
            "split": record.split,
            "stage": record.stage,
            "prompt_sha256": hashlib.sha256(record.prompt.encode()).hexdigest(),
            "target_sha256": hashlib.sha256(record.target.encode()).hexdigest(),
            "full_tokens": record.full_tokens,
        }
        for record in records
    ]
    return {
        "schema_version": "1.0",
        "status": "cpu_contract_and_data_gate_passed_gpu_diagnostics_pending",
        "passed": True,
        "experiment_id": EXPERIMENT_ID,
        "contract_id": CONTRACT_ID,
        "dataset_id": DATASET_ID,
        "config_sha256": hashlib.sha256(canonical_bytes(config)).hexdigest(),
        "dataset_freeze_manifest_sha256": sha256_file(DEFAULT_FREEZE_MANIFEST),
        "public_tool_schema_sha256": hashlib.sha256(canonical_bytes(public_tools)).hexdigest(),
        "implementation_sha256": {
            "training/c5_engineering.py": sha256_file(ROOT / "training/c5_engineering.py"),
            "tools/run_c5_engineering.py": sha256_file(ROOT / "tools/run_c5_engineering.py"),
            "eval/test_c5_engineering.py": sha256_file(ROOT / "eval/test_c5_engineering.py"),
        },
        "tokenizer_revision": BASE_MODEL_REVISION,
        "tokenizer_config_sha256": sha256_file(tokenizer_snapshot / "tokenizer_config.json"),
        "families": split_families,
        "records": dict(sorted(split_records.items())),
        "stage_records": dict(sorted(stage_counts.items())),
        "tokens": {
            "max_sequence_length": MAX_SEQUENCE_TOKENS,
            "overflow_policy": "reject",
            "prompt_min": min(prompt_lengths),
            "prompt_median": statistics.median(prompt_lengths),
            "prompt_max": max(prompt_lengths),
            "full_min": min(full_lengths),
            "full_median": statistics.median(full_lengths),
            "full_max": max(full_lengths),
            "label_min": min(label_lengths),
            "label_median": statistics.median(label_lengths),
            "label_max": max(label_lengths),
            "overflow_records": 0,
        },
        "strict_roundtrip_records": len(records),
        "assistant_only_labels_verified": len(records),
        "rendered_lineage_sha256": hashlib.sha256(canonical_bytes(lineage_payload)).hexdigest(),
        "overfit_smoke": {
            "records": len(smoke),
            "selector_records": sum(r.stage == "selector" for r in smoke),
            "invocation_records": sum(r.stage == "invocation" for r in smoke),
            "invocation_tool_counts": dict(sorted(smoke_tools.items())),
            "record_ids_sha256": hashlib.sha256(canonical_bytes(
                [record.record_id for record in smoke]
            )).hexdigest(),
            "executed": False,
        },
        "gpu_used": False,
        "model_weights_loaded": False,
        "rhino_contacted": False,
        "final_holdout_rows_read": 0,
        "single_use_claim_executed": False,
        "formal_training_authorized": False,
    }


__all__ = [
    "C5CausalLMCollator",
    "C5EngineeringError",
    "C5TokenizedDataset",
    "DEFAULT_CONFIG",
    "RenderedTrainingRecord",
    "audit_engineering_gate",
    "load_config",
    "load_pinned_tokenizer",
    "render_development_records",
    "select_overfit_smoke",
    "verify_development_splits",
]
