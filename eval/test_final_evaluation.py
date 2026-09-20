from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

import eval.final_evaluation as final_evaluation
from training.config import ReadinessError, canonical_json, sha256_file


def _sample(sample_id: str, argument: int) -> dict[str, Any]:
    return {
        "sample_id": sample_id,
        "split": "holdout",
        "view": "instruction_to_tool_call",
        "messages": [
            {"role": "user", "content": f"create box {argument}"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "create_box",
                            "arguments": {"size": argument},
                        }
                    }
                ],
            },
        ],
    }


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_paired_binary_statistics_are_exact_and_deterministic() -> None:
    left = {"a": True, "b": True, "c": False, "d": False}
    right = {"a": True, "b": False, "c": True, "d": True}

    first = final_evaluation.paired_binary_statistics(
        left, right, seed=17, resamples=500
    )
    second = final_evaluation.paired_binary_statistics(
        left, right, seed=17, resamples=500
    )

    assert first == second
    assert first["pairs"] == {
        "both_success": 1,
        "left_only": 1,
        "right_only": 2,
        "both_failure": 0,
    }
    assert first["difference_percentage_points"] == 25.0
    assert first["mcnemar_exact_two_sided_p"] == 1.0


def test_summary_rejects_incomplete_or_duplicate_pairing() -> None:
    row = {
        "route": "base",
        "sample_id": "one",
        "parse_success": True,
        "name_exact": True,
        "arguments_exact": True,
        "sequence_exact": True,
        "latency_ms": 1.0,
    }
    with pytest.raises(ReadinessError, match="complete base/LoRA pairing"):
        final_evaluation.summarize_generation_rows([row])
    with pytest.raises(ReadinessError, match="invalid route/sample pair"):
        final_evaluation.summarize_generation_rows([row, dict(row)])


def test_claim_is_append_only_and_refuses_a_second_new_run(tmp_path: Path) -> None:
    ledger = tmp_path / "holdout-consumption.jsonl"
    run_id, consumed_at = final_evaluation._claim_or_resume(
        ledger_path=ledger,
        experiment_id="experiment",
        freeze_sha256="a" * 64,
        resume_run_id=None,
    )

    events = final_evaluation._read_jsonl(ledger, "test ledger")
    assert events == [
        {
            "event_at": consumed_at,
            "experiment_id": "experiment",
            "freeze_manifest_sha256": "a" * 64,
            "holdout_consumed_at": consumed_at,
            "run_id": run_id,
            "schema_version": "1.0",
            "status": "started",
        }
    ]
    with pytest.raises(ReadinessError, match="second new run is forbidden"):
        final_evaluation._claim_or_resume(
            ledger_path=ledger,
            experiment_id="experiment",
            freeze_sha256="a" * 64,
            resume_run_id=None,
        )


def test_claimed_holdout_loader_enforces_hash_rows_and_split(tmp_path: Path) -> None:
    holdout = tmp_path / "holdout.jsonl"
    rows = [_sample("sample-a", 1), _sample("sample-b", 2)]
    _write_jsonl(holdout, rows)
    frozen = {
        "holdout": {
            "sha256_from_manifest": sha256_file(holdout),
            "rows": 2,
            "view": "instruction_to_tool_call",
        }
    }

    assert final_evaluation._load_claimed_holdout(holdout, frozen) == rows
    rows[1]["split"] = "validation"
    _write_jsonl(holdout, rows)
    frozen["holdout"]["sha256_from_manifest"] = sha256_file(holdout)
    with pytest.raises(ReadinessError, match="wrong split/view"):
        final_evaluation._load_claimed_holdout(holdout, frozen)


def test_wrong_confirmation_fails_before_consumption_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "freeze.json"
    manifest.write_text(json.dumps({"experiment_id": "experiment"}), encoding="utf-8")
    monkeypatch.setattr(
        final_evaluation,
        "audit_c3_freeze",
        lambda *args, **kwargs: {"freeze_manifest_sha256": "b" * 64},
    )

    def unexpected_claim(**kwargs: Any) -> tuple[str, str]:
        raise AssertionError("consumption must not be claimed")

    monkeypatch.setattr(final_evaluation, "_claim_or_resume", unexpected_claim)
    with pytest.raises(ReadinessError, match="exactly match"):
        final_evaluation.run_one_time_holdout(
            experiment_id="experiment",
            confirm_freeze_sha256="wrong",
            manifest_path=manifest,
            ledger_path=tmp_path / "ledger.jsonl",
            runs_root=tmp_path / "runs",
        )


def test_preflight_checks_presence_without_opening_holdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holdout = tmp_path / "holdout.jsonl"
    holdout.touch()
    manifest = tmp_path / "freeze.json"
    manifest.write_text(
        json.dumps(
            {
                "experiment_id": "experiment",
                "holdout": {"path": str(holdout)},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        final_evaluation,
        "audit_c3_freeze",
        lambda *args, **kwargs: {
            "passed": True,
            "freeze_manifest_sha256": "c" * 64,
            "holdout_read": False,
        },
    )

    result = final_evaluation.c3_preflight(
        manifest, ledger_path=tmp_path / "ledger.jsonl"
    )

    assert result["passed"] is True
    assert result["holdout_path_present"] is True
    assert result["holdout_file_opened"] is False
    assert result["new_run_allowed"] is True


def test_synthetic_one_time_run_and_audit_never_allow_a_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    samples = [_sample("sample-a", 1), _sample("sample-b", 2)]
    holdout = tmp_path / "holdout.jsonl"
    _write_jsonl(holdout, samples)
    freeze_hash = "d" * 64
    manifest = tmp_path / "freeze.json"
    manifest.write_text(
        json.dumps(
            {
                "experiment_id": "experiment",
                "lineage": {
                    "config_path": "unused-test-config.json",
                    "evaluation_git_revision": "evaluation-revision",
                    "training_git_revision": "training-revision",
                },
                "holdout": {
                    "path": str(holdout),
                    "sha256_from_manifest": sha256_file(holdout),
                    "rows": len(samples),
                    "view": "instruction_to_tool_call",
                },
                "c2": {"adapter": {"aggregate_sha256": "adapter-hash"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        final_evaluation,
        "audit_c3_freeze",
        lambda *args, **kwargs: {
            "passed": True,
            "experiment_id": "experiment",
            "freeze_manifest_sha256": freeze_hash,
            "holdout_read": False,
        },
    )
    monkeypatch.setattr(final_evaluation, "load_config", lambda path: {})

    def generator(
        route: str, route_samples: Sequence[Mapping[str, Any]], run_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        generated = []
        for sample in route_samples:
            call = {
                "name": "create_box",
                "arguments": {
                    "size": sample["messages"][-1]["tool_calls"][0]["function"][
                        "arguments"
                    ]["size"]
                },
            }
            if route == "base" and sample["sample_id"] == "sample-b":
                call["arguments"] = {"size": 999}
            generated.append(
                final_evaluation._score_generation(
                    run_id=run_id,
                    route=route,
                    sample=sample,
                    generated_text=f"<tool_call>{json.dumps(call)}</tool_call>",
                    generated_token_ids=[1, 2, 3],
                    latency_ms=1.0,
                )
            )
        return generated, {"walltime_seconds": 0.01}

    ledger = tmp_path / "ledger.jsonl"
    runs = tmp_path / "runs"
    result = final_evaluation.run_one_time_holdout(
        experiment_id="experiment",
        confirm_freeze_sha256=freeze_hash,
        manifest_path=manifest,
        ledger_path=ledger,
        runs_root=runs,
        route_generator=generator,
    )

    assert result["status"] == "complete"
    assert result["holdout_read"] is True
    assert result["results"]["routes"]["base"]["sequence_exact"] == 0.5
    assert result["results"]["routes"]["lora"]["sequence_exact"] == 1.0
    assert result["results"]["primary_metric"]["net_wins_right_minus_left"] == 1
    assert (
        final_evaluation.audit_completed_c3_run(
            result["run_id"],
            manifest_path=manifest,
            ledger_path=ledger,
            runs_root=runs,
        )["passed"]
        is True
    )

    def reopened_holdout(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise AssertionError("a second run must fail before reopening holdout")

    monkeypatch.setattr(final_evaluation, "_load_claimed_holdout", reopened_holdout)
    with pytest.raises(ReadinessError, match="second new run is forbidden"):
        final_evaluation.run_one_time_holdout(
            experiment_id="experiment",
            confirm_freeze_sha256=freeze_hash,
            manifest_path=manifest,
            ledger_path=ledger,
            runs_root=runs,
            route_generator=generator,
        )
    final_evaluation._append_jsonl_fsync(
        ledger,
        {
            "schema_version": "1.0",
            "status": "route_complete",
            "event_at": "tampered",
            "experiment_id": "experiment",
            "run_id": result["run_id"],
            "freeze_manifest_sha256": "wrong-freeze",
            "route": "base",
        },
    )
    with pytest.raises(ReadinessError, match="mixed freeze-manifest lineage"):
        final_evaluation.audit_completed_c3_run(
            result["run_id"],
            manifest_path=manifest,
            ledger_path=ledger,
            runs_root=runs,
        )


def test_incomplete_run_resumes_same_lineage_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    samples = [_sample("sample-a", 1)]
    holdout = tmp_path / "holdout.jsonl"
    _write_jsonl(holdout, samples)
    freeze_hash = "e" * 64
    manifest = tmp_path / "freeze.json"
    manifest.write_text(
        json.dumps(
            {
                "experiment_id": "experiment",
                "lineage": {
                    "config_path": "unused-test-config.json",
                    "evaluation_git_revision": "evaluation-revision",
                    "training_git_revision": "training-revision",
                },
                "holdout": {
                    "path": str(holdout),
                    "sha256_from_manifest": sha256_file(holdout),
                    "rows": 1,
                    "view": "instruction_to_tool_call",
                },
                "c2": {"adapter": {"aggregate_sha256": "adapter-hash"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        final_evaluation,
        "audit_c3_freeze",
        lambda *args, **kwargs: {
            "passed": True,
            "experiment_id": "experiment",
            "freeze_manifest_sha256": freeze_hash,
            "holdout_read": False,
        },
    )
    monkeypatch.setattr(final_evaluation, "load_config", lambda path: {})
    calls: list[str] = []
    interrupt_lora = True

    def interrupted_generator(
        route: str, route_samples: Sequence[Mapping[str, Any]], run_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        nonlocal interrupt_lora
        calls.append(route)
        if route == "lora" and interrupt_lora:
            interrupt_lora = False
            raise RuntimeError("simulated interruption")
        call = {"name": "create_box", "arguments": {"size": 1}}
        return [
            final_evaluation._score_generation(
                run_id=run_id,
                route=route,
                sample=route_samples[0],
                generated_text=f"<tool_call>{json.dumps(call)}</tool_call>",
                generated_token_ids=[1],
                latency_ms=1.0,
            )
        ], {"walltime_seconds": 0.01}

    ledger = tmp_path / "ledger.jsonl"
    runs = tmp_path / "runs"
    with pytest.raises(RuntimeError, match="simulated interruption"):
        final_evaluation.run_one_time_holdout(
            experiment_id="experiment",
            confirm_freeze_sha256=freeze_hash,
            manifest_path=manifest,
            ledger_path=ledger,
            runs_root=runs,
            route_generator=interrupted_generator,
        )
    events = final_evaluation._read_jsonl(ledger, "test ledger")
    run_id = str(events[0]["run_id"])
    assert calls == ["base", "lora"]

    calls.clear()
    result = final_evaluation.run_one_time_holdout(
        experiment_id="experiment",
        confirm_freeze_sha256=freeze_hash,
        manifest_path=manifest,
        ledger_path=ledger,
        runs_root=runs,
        resume_run_id=run_id,
        route_generator=interrupted_generator,
    )

    assert result["status"] == "complete"
    assert calls == ["lora"]
    statuses = [
        row["status"] for row in final_evaluation._read_jsonl(ledger, "test ledger")
    ]
    assert statuses.count("resumed") == 1
    assert statuses.count("route_complete") == 2
    assert statuses.count("complete") == 1
    assert result["resources"]["base"]["segments"] == 1
    assert result["resources"]["lora"]["segments"] == 1


def test_c3_is_separate_from_training_entry_and_loader() -> None:
    module_source = Path(final_evaluation.__file__).read_text(encoding="utf-8")
    training_entry = Path(__file__).resolve().parents[1] / "tools" / "run_training.py"

    assert "from training.data import" not in module_source
    assert "import training.data" not in module_source
    assert "holdout-run" not in training_entry.read_text(encoding="utf-8")
