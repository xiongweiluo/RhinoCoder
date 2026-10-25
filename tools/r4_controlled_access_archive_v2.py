#!/usr/bin/env python3
"""Versioned archive for a *closed* disposable R fixture.

The 2026-09-26 probe runner is deliberately frozen for historical auditing.
Future batches must use this archiver, which includes committed WAL entries
through SQLite's backup API rather than copying the database main file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.r4_v5_ssh_no_write_session import (
    _private_directory, _private_publish_bytes, _private_read,
)

_CASE_ID = re.compile(r"[A-Z][A-Z0-9-]{1,63}\Z")
_MAX_AUDIT_JSON = 1024 * 1024


class ArchiveError(RuntimeError):
    pass


def _ledger_rows(database: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        return dict(db.execute(
            "SELECT state, COUNT(*) FROM candidate_write GROUP BY state"
        ))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_bytes(source: Path) -> bytes:
    parent_fd = _private_directory(source.parent)
    try:
        fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or not 1 <= info.st_size <= _MAX_AUDIT_JSON):
                raise ArchiveError("unsafe_audit_source:" + source.name)
            raw = os.read(fd, info.st_size + 1)
            if len(raw) != info.st_size:
                raise ArchiveError("audit_source_changed:" + source.name)
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _selected_json(session: Path) -> list[Path]:
    selected = [session / "initial.json"]
    selected += sorted(path for path in session.glob("execute-*.json")
                       if not path.name.startswith("execute-response-"))
    selected += sorted(session.glob("execute-response-*.json"))
    selected += sorted(session.glob("formal-drift-request-*.json"))
    selected += sorted(session.glob("formal-drift-response-*.json"))
    selected += sorted(session.glob("capture-response-*.json"))[-1:]
    for plan in sorted(session.glob("v6-plan-*")):
        selected += sorted(plan.glob("receipt.json"))
        for step in sorted(plan.glob("step-*")):
            selected += [path for name in (
                "remote-result.json", "resource-metrics.json", "record.json",
                "remote-failure-diagnostic.json",
            ) if (path := step / name).is_file()]
    for loss_dir in sorted(session.glob("v6-lost-receipt-*")):
        selected += [path for name in (
            "remote-result.json", "resource-metrics.json", "receipt.json",
            "withheld-rhino-response.json",
        ) if (path := loss_dir / name).is_file()]
    return selected


def _backup_ledger(source: Path, destination: Path, *,
                   expected: dict[str, int] | None = None) -> dict[str, int]:
    """Publish a complete non-overwriting 0600 SQLite snapshot or no final name."""
    parent_fd = _private_directory(destination.parent)
    temporary = None
    try:
        source_info = source.lstat()
        if (not stat.S_ISREG(source_info.st_mode)
                or stat.S_IMODE(source_info.st_mode) != 0o600
                or source_info.st_uid != os.getuid()):
            raise ArchiveError("unsafe_ledger_source")
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            before = dict(origin.execute(
                "SELECT state, COUNT(*) FROM candidate_write GROUP BY state"))
            fd, temporary = tempfile.mkstemp(prefix=".sqlite-backup-",
                                              dir=destination.parent)
            os.close(fd)
            with closing(sqlite3.connect(temporary)) as snapshot:
                origin.backup(snapshot)
                snapshot.execute("PRAGMA journal_mode=DELETE")
                if snapshot.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ArchiveError("snapshot_integrity_failed")
                copied = dict(snapshot.execute(
                    "SELECT state, COUNT(*) FROM candidate_write GROUP BY state"))
            after = dict(origin.execute(
                "SELECT state, COUNT(*) FROM candidate_write GROUP BY state"))
            if copied != before or after != before:
                raise ArchiveError("ledger_changed_during_backup")
            if expected is not None and copied != expected:
                raise ArchiveError("archived_ledger_disagrees_with_run")
        for suffix in ("-wal", "-shm"):
            if (Path(temporary + suffix)).exists():
                raise ArchiveError("snapshot_sidecar_present")
        fd = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(Path(temporary).name, destination.name,
                src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
        os.fsync(parent_fd)
        return copied
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def archive_closed_case(session: Path, output: Path, case_id: str,
                        close_receipt: dict, *, expected_ledger: dict[str, int] | None = None) -> dict:
    """Archive a closed fixture into a fresh case directory.

    An exception leaves any partial destination for diagnosis; callers must
    fail closed, never reuse or silently overwrite it.
    """
    session = session.resolve(strict=True)
    if (not _CASE_ID.fullmatch(case_id)
            or close_receipt.get("status") != "closed"
            or close_receipt.get("case_id") != case_id
            or close_receipt.get("key_removed") is not True
            or Path(close_receipt.get("session_dir", "")).resolve() != session
            or (session / "channel/secret").exists()):
        raise ArchiveError("fixture_not_verified_closed")
    if (not isinstance(expected_ledger, dict)
            or not all(isinstance(key, str) and type(value) is int and value > 0
                       for key, value in expected_ledger.items())):
        raise ArchiveError("independent_expected_ledger_required")
    session_fd = _private_directory(session)
    os.close(session_fd)
    output_fd = _private_directory(output)
    os.close(output_fd)
    cases = output / "cases"
    try:
        os.mkdir(cases, 0o700)
    except FileExistsError:
        pass
    cases_fd = _private_directory(cases)
    os.close(cases_fd)
    destination = cases / case_id
    os.mkdir(destination, 0o700)
    hashes = {}
    for source in _selected_json(session):
        name = (source.name if source.parent == session else
                source.parent.name + "-" + source.name)
        raw = _safe_bytes(source)
        _private_publish_bytes(destination, name, raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    ledger = destination / "fixture.sqlite3"
    rows = _backup_ledger(session / "fixture.sqlite3", ledger,
                          expected=expected_ledger)
    hashes[ledger.name] = _file_sha256(ledger)
    return {"case_id": case_id, "ledger": rows, "file_sha256": hashes,
            "archive_method": "sqlite_backup_v2"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--close-receipt", type=Path, required=True)
    parser.add_argument("--expected-ledger-json", required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected_ledger_json)
    if (not isinstance(expected, dict)
            or not all(isinstance(key, str) and type(value) is int and value > 0
                       for key, value in expected.items())):
        parser.error("expected ledger must be a state-to-positive-count object")
    receipt = _private_read(args.close_receipt)
    result = archive_closed_case(args.session_dir, args.output_dir, args.case_id,
                                 receipt, expected_ledger=expected)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
