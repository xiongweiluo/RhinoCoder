"""Validated conversation loading, tokenization and tool-call evaluation."""

from __future__ import annotations

import json
import math
import os
import re
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

from training.config import ReadinessError, project_path


TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)


def load_samples(path: str | Path, *, split: str, view: str) -> list[dict[str, Any]]:
    target = project_path(path)
    if "holdout" in target.parts or split == "holdout":
        raise ReadinessError("holdout data is locked and cannot be loaded by B-stage training code")
    rows: list[dict[str, Any]] = []
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReadinessError(f"cannot read dataset {target}: {exc}") from exc
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReadinessError(f"{target}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict) or row.get("split") != split or row.get("view") != view:
            raise ReadinessError(f"{target}:{line_no}: sample split/view mismatch")
        messages = row.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise ReadinessError(f"{target}:{line_no}: messages are incomplete")
        if messages[0].get("role") != "user" or messages[-1].get("role") != "assistant":
            raise ReadinessError(f"{target}:{line_no}: expected user-to-assistant conversation")
        rows.append(row)
    if not rows:
        raise ReadinessError(f"dataset is empty: {target}")
    return rows


def render_training_example(tokenizer: Any, messages: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    """Render the full target and prompt prefix using the pinned chat template."""

    normalized = json.loads(json.dumps(list(messages), ensure_ascii=False))
    for message in normalized:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    function["arguments"] = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise ReadinessError("tool-call target contains invalid argument JSON") from exc
    prompt = tokenizer.apply_chat_template(
        normalized[:-1],
        tokenize=False,
        add_generation_prompt=True,
    )
    full = tokenizer.apply_chat_template(
        normalized,
        tokenize=False,
        add_generation_prompt=False,
    )
    if not isinstance(prompt, str) or not isinstance(full, str) or not full.startswith(prompt):
        raise ReadinessError("tokenizer chat template does not preserve the assistant prompt prefix")
    return prompt, full


class ConversationDataset:
    """Small eager tokenized dataset with assistant-only labels."""

    def __init__(self, samples: Sequence[Mapping[str, Any]], tokenizer: Any, max_length: int) -> None:
        import torch

        self._torch = torch
        self._items: list[dict[str, Any]] = []
        for sample in samples:
            prompt, full = render_training_example(tokenizer, sample["messages"])
            prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
            full_ids = tokenizer(full, add_special_tokens=False)["input_ids"]
            if full_ids[: len(prompt_ids)] != prompt_ids:
                raise ReadinessError(
                    f"sample {sample.get('sample_id')} token prefix differs from rendered prompt"
                )
            if len(full_ids) > max_length:
                raise ReadinessError(
                    f"sample {sample.get('sample_id')} has {len(full_ids)} tokens, exceeds locked "
                    f"max_sequence_length={max_length}; overflow_policy=reject"
                )
            labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids) :]
            if not any(token != -100 for token in labels):
                raise ReadinessError(f"sample {sample.get('sample_id')} has no assistant target tokens")
            self._items.append(
                {
                    "input_ids": torch.tensor(full_ids, dtype=torch.long),
                    "attention_mask": torch.ones(len(full_ids), dtype=torch.long),
                    "labels": torch.tensor(labels, dtype=torch.long),
                }
            )

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self._items[index]


class CausalLMCollator:
    def __init__(self, pad_token_id: int) -> None:
        self.pad_token_id = pad_token_id

    def __call__(self, features: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        import torch

        width = max(int(item["input_ids"].shape[0]) for item in features)

        def padded(name: str, value: int) -> Any:
            rows = []
            for item in features:
                tensor = item[name]
                rows.append(torch.nn.functional.pad(tensor, (0, width - tensor.shape[0]), value=value))
            return torch.stack(rows)

        return {
            "input_ids": padded("input_ids", self.pad_token_id),
            "attention_mask": padded("attention_mask", 0),
            "labels": padded("labels", -100),
        }


def _normalized_call(value: Mapping[str, Any]) -> dict[str, Any] | None:
    function = value.get("function") if isinstance(value.get("function"), Mapping) else value
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


def expected_tool_calls(sample: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = []
    for value in (sample.get("messages") or [])[-1].get("tool_calls") or []:
        normalized = _normalized_call(value)
        if normalized is None:
            raise ReadinessError(f"sample {sample.get('sample_id')} has an invalid tool-call target")
        calls.append(normalized)
    return calls


def parse_generated_tool_calls(text: str) -> list[dict[str, Any]] | None:
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


def score_tool_generations(
    samples: Sequence[Mapping[str, Any]], generated: Sequence[str]
) -> dict[str, float | int]:
    if len(samples) != len(generated):
        raise ReadinessError("generated output count does not match validation samples")
    parsed_count = name_exact = arguments_exact = sequence_exact = 0
    for sample, text in zip(samples, generated, strict=True):
        expected = expected_tool_calls(sample)
        actual = parse_generated_tool_calls(text)
        if actual is None:
            continue
        parsed_count += 1
        if [item["name"] for item in actual] == [item["name"] for item in expected]:
            name_exact += 1
        if [item["arguments"] for item in actual] == [item["arguments"] for item in expected]:
            arguments_exact += 1
        if actual == expected:
            sequence_exact += 1
    total = len(samples)
    return {
        "samples": total,
        "tool_call_parse_rate": parsed_count / total,
        "tool_name_exact_rate": name_exact / total,
        "tool_arguments_exact_rate": arguments_exact / total,
        "tool_sequence_exact_rate": sequence_exact / total,
    }


def add_loss_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(metrics)
    loss = result.get("eval_loss")
    if isinstance(loss, (int, float)) and math.isfinite(float(loss)):
        result["perplexity"] = math.exp(min(float(loss), 20.0))
    return result


def audit_official_tokenizer(
    config: Mapping[str, Any],
    *,
    cache_dir: str | Path,
    local_files_only: bool = False,
) -> dict[str, Any]:
    """Download only the pinned tokenizer and verify every train/validation length."""

    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise ReadinessError("tokenizer audit requires transformers") from exc
    tokenizer_config = config["base_model"]["tokenizer"]
    cache_path = project_path(cache_dir)
    source = tokenizer_config["id"]
    revision = tokenizer_config["revision"]
    if local_files_only:
        repository_cache = "models--" + str(source).replace("/", "--")
        snapshot = cache_path / repository_cache / "snapshots" / str(revision)
        if not snapshot.is_dir():
            raise ReadinessError(f"pinned tokenizer snapshot is not cached: {snapshot}")
        source = str(snapshot)
        revision = None
    tokenizer = AutoTokenizer.from_pretrained(
        source,
        revision=revision,
        trust_remote_code=False,
        token=None if local_files_only else os.getenv("HF_TOKEN") or None,
        cache_dir=cache_path,
        local_files_only=local_files_only,
    )
    maximum = int(config["training"]["max_sequence_length"])
    view = str(config["data"]["view"])
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "tokenizer_id": tokenizer_config["id"],
        "tokenizer_revision": tokenizer_config["revision"],
        "max_sequence_length": maximum,
        "overflow_policy": config["training"]["overflow_policy"],
        "splits": {},
        "overflow_sample_ids": [],
        "holdout_read": False,
    }
    for split in ("train", "validation"):
        samples = load_samples(config["data"][split]["path"], split=split, view=view)
        lengths = []
        for sample in samples:
            _prompt, full = render_training_example(tokenizer, sample["messages"])
            length = len(tokenizer(full, add_special_tokens=False)["input_ids"])
            lengths.append(length)
            if length > maximum:
                result["overflow_sample_ids"].append(sample.get("sample_id"))
        ordered = sorted(lengths)
        p95_index = max(math.ceil(len(ordered) * 0.95) - 1, 0)
        result["splits"][split] = {
            "samples": len(lengths),
            "minimum_tokens": min(lengths),
            "median_tokens": statistics.median(lengths),
            "p95_tokens": ordered[p95_index],
            "maximum_tokens": max(lengths),
        }
    result["passed"] = not result["overflow_sample_ids"]
    return result
