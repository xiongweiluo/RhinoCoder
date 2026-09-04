from __future__ import annotations

import json
import stat
import tarfile
from pathlib import Path

import pytest

from tools.freeze_golden_set import FreezeError, freeze_golden_set


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path, *, duplicate_task: bool = False) -> Path:
    root = tmp_path / "repo"
    (root / "data/traces").mkdir(parents=True)
    (root / "data/review_batches/batch-01").mkdir(parents=True)
    (root / "data/collection_reports").mkdir(parents=True)
    (root / "eval/collection").mkdir(parents=True)
    (root / ".env").write_text(
        "API_KEY=sk-do-not-back-this-up\n",  # secret-scan: allow -- exclusion fixture
        encoding="utf-8",
    )

    golden_rows = []
    feedback_rows = []
    reviewed_rows = []
    for index in range(2):
        run_id = f"run-{index}"
        task_id = "task-0" if duplicate_task else f"task-{index}"
        golden_rows.append(
            {
                "run_id": run_id,
                "metadata": {
                    "task": {"campaign_id": "fixture", "task_id": task_id}
                },
            }
        )
        feedback_rows.append({"run_id": run_id, "label": "accepted"})
        screenshot = Path(f"data/review_batches/batch-01/task-{index}.png")
        (root / screenshot).write_bytes(b"PNG fixture")
        reviewed_rows.append(
            {
                "run_id": run_id,
                "feedback": {"review": {"visual_evidence": screenshot.as_posix()}},
            }
        )
        (root / f"data/traces/{run_id}.json").write_text(
            json.dumps({"run_id": run_id}), encoding="utf-8"
        )

    _write_jsonl(root / "data/golden_traces_v2.jsonl", golden_rows)
    _write_jsonl(root / "data/feedback.jsonl", feedback_rows)
    _write_jsonl(root / "data/ai_reviewed_candidates.jsonl", reviewed_rows)
    (root / "data/collection_reports/fixture-quality.json").write_text(
        "{}\n", encoding="utf-8"
    )
    for name in ("phase1_30.json", "phase2_100.json", "phase3_300.json"):
        (root / "eval/collection" / name).write_text("{}\n", encoding="utf-8")

    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    return root


def test_freeze_creates_secret_free_restorable_backup(tmp_path):
    root = _fixture(tmp_path)
    output = root / "data/backups/golden-set-300"

    summary = freeze_golden_set(root, output, expected_count=2)

    assert summary.golden_records == 2
    assert summary.unique_task_ids == 2
    assert summary.trace_files == 2
    assert summary.unique_screenshot_files == 2
    assert summary.secret_scan_passed
    assert summary.restore_verification_passed
    assert (output / "ARCHIVE.sha256").is_file()
    assert (output / "RESTORE_VERIFICATION.json").is_file()
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "golden-set-300.tar.gz").stat().st_mode) == 0o600
    with tarfile.open(output / "golden-set-300.tar.gz", "r:gz") as archive:
        names = archive.getnames()
    assert ".env" not in names
    assert "SHA256SUMS" in names
    assert "MANIFEST.json" in names


def test_freeze_rejects_duplicate_campaign_task_ids(tmp_path):
    root = _fixture(tmp_path, duplicate_task=True)

    with pytest.raises(FreezeError, match="task IDs are not unique"):
        freeze_golden_set(
            root,
            root / "data/backups/golden-set-300",
            expected_count=2,
        )


def test_freeze_rejects_secret_in_selected_artifact(tmp_path):
    root = _fixture(tmp_path)
    report = root / "data/collection_reports/fixture-quality.json"
    report.write_text(
        '{"api_key": "sk-this-secret-must-not-enter-the-backup"}\n',  # secret-scan: allow -- rejection fixture
        encoding="utf-8",
    )

    with pytest.raises(FreezeError, match="Potential secrets detected"):
        freeze_golden_set(
            root,
            root / "data/backups/golden-set-300",
            expected_count=2,
        )


def test_freeze_rejects_output_outside_backup_directory(tmp_path):
    root = _fixture(tmp_path)

    with pytest.raises(FreezeError, match="must be a child"):
        freeze_golden_set(root, root / "unsafe-output", expected_count=2)
