from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from training.c5_engineering import (
    C5CausalLMCollator,
    C5EngineeringError,
    C5TokenizedDataset,
    load_config,
    render_development_records,
    select_overfit_smoke,
    verify_development_splits,
)
from training.c5_freeze import sha256_file


def _family(split: str, family_id: str, records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_id": "rhinocoder-c5-dataset-v2",
        "contract_id": "qwen25-v4-selector-v3-json-invoker-c5-v1",
        "family_id": family_id,
        "split": split,
        "records": records,
        "review": {"status": "approved", "reviewer_1": "repository_owner"},
    }


def _write_split(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ), encoding="utf-8")


def test_development_loader_rejects_holdout_named_path(tmp_path: Path) -> None:
    with pytest.raises(C5EngineeringError, match="protected path"):
        verify_development_splits(
            tmp_path / "final-holdout",
            config=load_config(),
        )


def test_development_loader_checks_hashes_counts_and_disjoint_ids(tmp_path: Path) -> None:
    dataset = tmp_path / "accepted"
    dataset.mkdir()
    config = load_config()
    artifacts = []
    for split in ("train", "validation", "development"):
        row = _family(split, f"family-{split}", [{
            "record_id": f"record-{split}",
            "stage": "selector",
            "user_step": "创建宽 2、深 3、高 4 的长方体。",
            "selected_tool": "create_box",
        }])
        path = dataset / f"{split}.jsonl"
        _write_split(path, [row])
        digest = sha256_file(path)
        config["data"]["splits"][split] = {
            "families": 1, "records": 1, "sha256": digest,
        }
        artifacts.append({
            "path": path.name, "families": 1, "records": 1, "sha256": digest,
        })
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({
        "dataset_id": "rhinocoder-c5-dataset-v2",
        "formal_split_locked": True,
        "final_holdout_included": False,
        "final_holdout_rows_read": 0,
        "artifacts": artifacts,
    }), encoding="utf-8")
    result = verify_development_splits(dataset, config=config, freeze_manifest_path=freeze)
    assert {split: len(rows) for split, rows in result.items()} == {
        "train": 1, "validation": 1, "development": 1,
    }
    (dataset / "train.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(C5EngineeringError, match="locked hash"):
        verify_development_splits(dataset, config=config, freeze_manifest_path=freeze)


class _Tokenizer:
    pad_token_id = 0

    def __call__(self, text: str, **_kwargs):
        return {"input_ids": [ord(character) for character in text]}

    def apply_chat_template(self, messages, *, tokenize=False, add_generation_prompt=False, tools=None):
        assert tokenize is False
        prefix = "".join(f"{item['role']}:{item.get('content', '')}\n" for item in messages[:-1])
        last = messages[-1]
        if last["role"] != "assistant":
            prefix += f"{last['role']}:{last.get('content', '')}\nassistant:"
            return prefix
        if "tool_calls" in last:
            function = last["tool_calls"][0]["function"]
            target = json.dumps({
                "name": function["name"], "arguments": function["arguments"],
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        else:
            target = last["content"]
        return prefix + "assistant:" + target


def test_rendered_records_use_assistant_only_labels_and_deterministic_smoke() -> None:
    families = {split: [] for split in ("train", "validation", "development")}
    for split in families:
        for index in range(40 if split == "train" else 1):
            families[split].append(_family(split, f"{split}-{index}", [
                {
                    "record_id": f"{split}-selector-{index}",
                    "stage": "selector",
                    "user_step": "创建宽 2、深 3、高 4 的长方体。",
                    "selected_tool": "create_box",
                },
                {
                    "record_id": f"{split}-invocation-{index}",
                    "stage": "invocation",
                    "user_step": "创建宽 2、深 3、高 4 的长方体。",
                    "selected_tool": "create_box",
                    "arguments": {"width": 2, "depth": 3, "height": 4},
                },
            ]))
    records = render_development_records(families, _Tokenizer())
    smoke = select_overfit_smoke(records, total=64)
    assert len(smoke) == 64
    assert sum(record.stage == "selector" for record in smoke) == 32
    assert sum(record.stage == "invocation" for record in smoke) == 32
    assert [r.record_id for r in smoke] == [
        r.record_id for r in select_overfit_smoke(records, total=64)
    ]
    dataset = C5TokenizedDataset(smoke[:2])
    collated = C5CausalLMCollator(0)([dataset[0], dataset[1]])
    assert collated["input_ids"].shape[0] == 2
    for item, record in zip((dataset[0], dataset[1]), smoke[:2], strict=True):
        prompt_size = len(record.prompt_token_ids)
        assert item["labels"][:prompt_size].tolist() == [-100] * prompt_size
        assert all(value != -100 for value in item["labels"][prompt_size:].tolist())


def test_config_is_bound_to_expected_identity_and_smoke_fingerprint() -> None:
    config = load_config()
    assert config["experiment_id"] == "rhinocoder-qwen25-coder-7b-c5-contract-qlora-v2"
    assert config["diagnostics"]["overfit_samples"] == 64
    assert config["holdout_policy"]["content_read_allowed"] is False
    assert len(hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()) == 64
