#!/usr/bin/env python3
"""Freeze the local golden dataset into a checksummed, restorable backup."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_secrets import PATTERNS  # noqa: E402


DEFAULT_OUTPUT = ROOT / "data" / "backups" / "golden-set-300"
GOLDEN_FILE = Path("data/golden_traces_v2.jsonl")
FEEDBACK_FILE = Path("data/feedback.jsonl")
AI_REVIEWED_FILE = Path("data/ai_reviewed_candidates.jsonl")
CAMPAIGN_MANIFESTS = (
    Path("eval/collection/phase1_30.json"),
    Path("eval/collection/phase2_100.json"),
    Path("eval/collection/phase3_300.json"),
)


class FreezeError(RuntimeError):
    """Raised when the golden dataset cannot be safely frozen."""


@dataclass(frozen=True)
class FreezeSummary:
    schema_version: str
    milestone: str
    created_at: str
    source_revision: str
    golden_records: int
    unique_run_ids: int
    unique_task_ids: int
    trace_files: int
    screenshot_references: int
    unique_screenshot_files: int
    accepted_feedback_run_ids: int
    collection_report_files: int
    campaign_manifest_files: int
    artifact_files: int
    artifact_bytes: int
    secret_scan_passed: bool
    archive_path: str
    archive_sha256: str
    restore_verification_passed: bool


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FreezeError(f"Required JSONL file is missing: {path}")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FreezeError(f"Invalid JSON in {path}:{line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise FreezeError(f"Expected a JSON object in {path}:{line_no}")
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _task_key(row: dict[str, Any]) -> tuple[str, str]:
    task = (row.get("metadata") or {}).get("task") or {}
    campaign_id = str(task.get("campaign_id") or "")
    task_id = str(task.get("task_id") or "")
    if not campaign_id or not task_id:
        raise FreezeError(f"Golden record {row.get('run_id')!r} has no campaign/task ID")
    return campaign_id, task_id


def _safe_project_file(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise FreezeError(f"Artifact path must remain inside the project: {relative}")
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise FreezeError(f"Artifact file is missing or outside the project: {relative}")
    if resolved.is_symlink():
        raise FreezeError(f"Symlinked artifacts are not allowed: {relative}")
    return resolved


def _collect_artifacts(
    root: Path, expected_count: int
) -> tuple[list[Path], dict[str, int]]:
    golden_rows = _read_jsonl(root / GOLDEN_FILE)
    if len(golden_rows) != expected_count:
        raise FreezeError(
            f"Expected {expected_count} golden records, found {len(golden_rows)}"
        )

    run_ids = [str(row.get("run_id") or "") for row in golden_rows]
    if any(not run_id for run_id in run_ids):
        raise FreezeError("Every golden record must have a run_id")
    if len(set(run_ids)) != expected_count:
        raise FreezeError("Golden run IDs are not unique")

    task_keys = [_task_key(row) for row in golden_rows]
    if len(set(task_keys)) != expected_count:
        raise FreezeError("Golden campaign/task IDs are not unique")
    task_ids = [task_id for _campaign_id, task_id in task_keys]
    if len(set(task_ids)) != expected_count:
        raise FreezeError("Golden task IDs are not unique")

    feedback_rows = _read_jsonl(root / FEEDBACK_FILE)
    accepted_feedback_run_ids = {
        str(row.get("run_id") or "")
        for row in feedback_rows
        if row.get("label") == "accepted"
    }
    missing_feedback = sorted(set(run_ids) - accepted_feedback_run_ids)
    if missing_feedback:
        raise FreezeError(
            f"Golden runs without accepted feedback: {', '.join(missing_feedback)}"
        )

    reviewed_rows = _read_jsonl(root / AI_REVIEWED_FILE)
    screenshot_refs: list[Path] = []
    for row in reviewed_rows:
        review = ((row.get("feedback") or {}).get("review") or {})
        visual_evidence = str(review.get("visual_evidence") or "").strip()
        if visual_evidence:
            screenshot_refs.append(Path(visual_evidence))
    unique_screenshots = sorted(set(screenshot_refs), key=lambda path: path.as_posix())

    trace_paths = [Path("data/traces") / f"{run_id}.json" for run_id in run_ids]
    report_dir = root / "data" / "collection_reports"
    report_paths = sorted(
        (path.relative_to(root) for path in report_dir.iterdir() if path.is_file()),
        key=lambda path: path.as_posix(),
    )
    if not any("quality" in path.name for path in report_paths):
        raise FreezeError("No golden dataset quality report was found")

    relative_paths = {
        GOLDEN_FILE,
        FEEDBACK_FILE,
        AI_REVIEWED_FILE,
        *CAMPAIGN_MANIFESTS,
        *trace_paths,
        *unique_screenshots,
        *report_paths,
    }
    for relative in relative_paths:
        if relative.name == ".env" or relative.name.startswith(".env."):
            raise FreezeError(f"Environment files cannot enter the backup: {relative}")
        _safe_project_file(root, relative)

    artifacts = sorted(relative_paths, key=lambda path: path.as_posix())
    return artifacts, {
        "golden_records": len(golden_rows),
        "unique_run_ids": len(set(run_ids)),
        "unique_task_ids": len(set(task_ids)),
        "trace_files": len(trace_paths),
        "screenshot_references": len(screenshot_refs),
        "unique_screenshot_files": len(unique_screenshots),
        "accepted_feedback_run_ids": len(set(run_ids) & accepted_feedback_run_ids),
        "collection_report_files": len(report_paths),
        "campaign_manifest_files": len(CAMPAIGN_MANIFESTS),
    }


def _scan_for_secrets(root: Path, artifacts: Iterable[Path]) -> None:
    findings: list[str] = []
    text_suffixes = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}
    for relative in artifacts:
        path = root / relative
        if path.suffix.lower() not in text_suffixes:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise FreezeError(f"Text artifact is not valid UTF-8: {relative}") from exc
        for line_no, line in enumerate(content.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{relative.as_posix()}:{line_no}: {label}")
    if findings:
        details = "\n".join(findings[:20])
        raise FreezeError(f"Potential secrets detected in backup artifacts:\n{details}")


def _write_hash_manifest(root: Path, artifacts: Iterable[Path], destination: Path) -> None:
    lines = [f"{_sha256(root / relative)}  {relative.as_posix()}" for relative in artifacts]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_archive(
    root: Path,
    artifacts: Iterable[Path],
    hash_manifest: Path,
    metadata: Path,
    archive: Path,
) -> None:
    with archive.open("wb") as raw_stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_stream, mtime=0) as gz_stream:
            with tarfile.open(fileobj=gz_stream, mode="w") as tar:
                for relative in artifacts:
                    info = tar.gettarinfo(str(root / relative), arcname=relative.as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    info.mode = 0o600
                    with (root / relative).open("rb") as source:
                        tar.addfile(info, source)
                for path, arcname in (
                    (hash_manifest, "SHA256SUMS"),
                    (metadata, "MANIFEST.json"),
                ):
                    info = tar.gettarinfo(str(path), arcname=arcname)
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    info.mode = 0o600
                    with path.open("rb") as source:
                        tar.addfile(info, source)


def _safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar.getmembers():
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise FreezeError(f"Unsafe archive member: {member.name}")
            if not member.isfile():
                raise FreezeError(f"Backup may only contain regular files: {member.name}")
        tar.extractall(destination, filter="data")


def _verify_restored(
    root: Path, artifacts: Iterable[Path], hash_manifest: Path, archive: Path
) -> dict[str, Any]:
    expected = {
        relative.as_posix(): _sha256(root / relative) for relative in artifacts
    }
    with tempfile.TemporaryDirectory(prefix="rhinocoder-golden-restore-") as temp_dir:
        restored_root = Path(temp_dir)
        _safe_extract(archive, restored_root)
        restored_manifest = restored_root / "SHA256SUMS"
        if restored_manifest.read_bytes() != hash_manifest.read_bytes():
            raise FreezeError("Restored SHA256SUMS differs from the source manifest")
        mismatches = [
            relative
            for relative, digest in expected.items()
            if not (restored_root / relative).is_file()
            or _sha256(restored_root / relative) != digest
        ]
        if mismatches:
            raise FreezeError(
                "Restored artifacts differ from their source hashes: "
                + ", ".join(mismatches[:20])
            )
    return {
        "passed": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "artifact_files": len(expected),
        "archive_sha256": _sha256(archive),
        "sha256_manifest_sha256": _sha256(hash_manifest),
        "source_and_restored_hashes_match": True,
    }


def freeze_golden_set(
    root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    expected_count: int = 300,
    overwrite: bool = False,
) -> FreezeSummary:
    root = root.resolve()
    output_dir = output_dir.resolve()
    allowed_output_root = (root / "data" / "backups").resolve()
    if output_dir == allowed_output_root or not output_dir.is_relative_to(allowed_output_root):
        raise FreezeError(
            f"Backup destination must be a child of {allowed_output_root}: {output_dir}"
        )
    if output_dir.exists():
        if not overwrite:
            raise FreezeError(f"Backup destination already exists: {output_dir}")

    artifacts, counts = _collect_artifacts(root, expected_count)
    _scan_for_secrets(root, artifacts)
    allowed_output_root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=".golden-set-300-", dir=allowed_output_root)
    )
    try:
        hash_manifest = staging_dir / "SHA256SUMS"
        _write_hash_manifest(root, artifacts, hash_manifest)

        created_at = datetime.now(timezone.utc).isoformat()
        archive = staging_dir / "golden-set-300.tar.gz"
        pre_archive_manifest = {
            "schema_version": "1.0",
            "milestone": "golden-set-300",
            "created_at": created_at,
            "source_revision": _git_revision(root),
            **counts,
            "artifact_files": len(artifacts),
            "artifact_bytes": sum((root / path).stat().st_size for path in artifacts),
            "secret_scan_passed": True,
        }
        manifest_path = staging_dir / "MANIFEST.json"
        manifest_path.write_text(
            json.dumps(pre_archive_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _create_archive(root, artifacts, hash_manifest, manifest_path, archive)
        verification = _verify_restored(root, artifacts, hash_manifest, archive)
        verification_path = staging_dir / "RESTORE_VERIFICATION.json"
        verification_path.write_text(
            json.dumps(verification, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        archive_digest = _sha256(archive)
        (staging_dir / "ARCHIVE.sha256").write_text(
            f"{archive_digest}  {archive.name}\n", encoding="utf-8"
        )

        summary = FreezeSummary(
            **pre_archive_manifest,
            archive_path=(output_dir / archive.name).relative_to(root).as_posix(),
            archive_sha256=archive_digest,
            restore_verification_passed=bool(verification["passed"]),
        )
        (staging_dir / "FREEZE_SUMMARY.json").write_text(
            json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for path in staging_dir.iterdir():
            path.chmod(0o600)
        staging_dir.chmod(0o700)

        if output_dir.exists():
            shutil.rmtree(output_dir)
        staging_dir.replace(output_dir)
        return summary
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-count", type=int, default=300)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        summary = freeze_golden_set(
            args.root,
            args.output_dir,
            expected_count=args.expected_count,
            overwrite=args.overwrite,
        )
    except (FreezeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Golden set freeze failed: {exc}")
        return 1
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
