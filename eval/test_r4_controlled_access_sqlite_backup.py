"""Regression: a raw SQLite copy can miss a committed WAL transaction."""

import shutil
import sqlite3
import stat
from contextlib import closing

import pytest

from tools import r4_controlled_access_archive_v2 as archive
from tools.r4_v5_ssh_no_write_session import _private_publish


def test_sqlite_backup_includes_committed_uncheckpointed_wal(tmp_path):
    source = tmp_path / "source.sqlite3"
    with closing(sqlite3.connect(source)) as db:
        db.execute("CREATE TABLE ledger(state TEXT)")
        db.commit()
    with closing(sqlite3.connect(source)) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        db.execute("INSERT INTO ledger VALUES ('done')")
        db.commit()

        stale = tmp_path / "raw-copy.sqlite3"
        shutil.copyfile(source, stale)
        with closing(sqlite3.connect(stale)) as copied:
            assert copied.execute("SELECT state FROM ledger").fetchall() == []

        consistent = tmp_path / "backup.sqlite3"
        with closing(sqlite3.connect(consistent)) as snapshot:
            db.backup(snapshot)
        with closing(sqlite3.connect(consistent)) as restored:
            assert restored.execute("SELECT state FROM ledger").fetchall() == [("done",)]


def _fixture(tmp_path):
    session = tmp_path / "session"
    session.mkdir(mode=0o700)
    (session / "channel").mkdir(mode=0o700)
    _private_publish(session, "initial.json", {"fixture": "empty"})
    ledger = session / "fixture.sqlite3"
    with closing(sqlite3.connect(ledger)) as db:
        db.execute("CREATE TABLE candidate_write(state TEXT)")
        db.commit()
    ledger.chmod(0o600)
    output = tmp_path / "archive"
    output.mkdir(mode=0o700)
    close = {"status": "closed", "case_id": "RCA-TEST",
             "session_dir": str(session), "key_removed": True}
    return session, ledger, output, close


def test_closed_case_archiver_captures_wal_and_keeps_private_files(tmp_path):
    session, ledger, output, close = _fixture(tmp_path)
    with closing(sqlite3.connect(ledger)) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        db.execute("INSERT INTO candidate_write VALUES ('done')")
        db.commit()
        result = archive.archive_closed_case(
            session, output, "RCA-TEST", close, expected_ledger={"done": 1})
        assert result["archive_method"] == "sqlite_backup_v2"
        assert result["ledger"] == {"done": 1}
        saved = output / "cases/RCA-TEST/fixture.sqlite3"
        assert archive._ledger_rows(saved) == {"done": 1}
        assert stat.S_IMODE(saved.stat().st_mode) == 0o600
        assert not list(saved.parent.glob(".sqlite-backup-*"))
        assert (saved.parent / "initial.json").read_bytes() == (
            session / "initial.json").read_bytes()
        assert archive._ledger_rows(ledger) == {"done": 1}


@pytest.mark.parametrize("fault", ("wrong_case", "key_present", "secret_present"))
def test_archiver_rejects_unverified_closure(tmp_path, fault):
    session, _ledger, output, close = _fixture(tmp_path)
    if fault == "wrong_case":
        close["case_id"] = "RCA-OTHER"
    elif fault == "key_present":
        close["key_removed"] = False
    else:
        (session / "channel/secret").write_text("test-only")
    with pytest.raises(archive.ArchiveError, match="fixture_not_verified_closed"):
        archive.archive_closed_case(session, output, "RCA-TEST", close)
    assert not (output / "cases").exists()


def test_archiver_rejects_mismatched_ledger_without_ready_database(tmp_path):
    session, _ledger, output, close = _fixture(tmp_path)
    with pytest.raises(archive.ArchiveError, match="archived_ledger_disagrees_with_run"):
        archive.archive_closed_case(
            session, output, "RCA-TEST", close, expected_ledger={"done": 1})
    dest = output / "cases/RCA-TEST"
    assert not (dest / "fixture.sqlite3").exists()
    assert not list(dest.glob(".sqlite-backup-*"))


def test_archiver_requires_independent_expected_ledger_before_creating_case(tmp_path):
    session, _ledger, output, close = _fixture(tmp_path)
    with pytest.raises(archive.ArchiveError,
                       match="independent_expected_ledger_required"):
        archive.archive_closed_case(session, output, "RCA-TEST", close)
    assert not (output / "cases").exists()


def test_archiver_never_overwrites_existing_case(tmp_path):
    session, _ledger, output, close = _fixture(tmp_path)
    first = archive.archive_closed_case(session, output, "RCA-TEST", close,
                                        expected_ledger={})
    with pytest.raises(FileExistsError):
        archive.archive_closed_case(session, output, "RCA-TEST", close,
                                    expected_ledger={})
    assert archive._ledger_rows(output / "cases/RCA-TEST/fixture.sqlite3") == {}
    assert first["file_sha256"]["fixture.sqlite3"] == archive._file_sha256(
        output / "cases/RCA-TEST/fixture.sqlite3")


def test_ledger_backup_never_replaces_existing_final_name(tmp_path):
    _session, source, output, _close = _fixture(tmp_path)
    existing = output / "fixture.sqlite3"
    existing.write_bytes(b"sentinel")
    existing.chmod(0o600)
    with pytest.raises(FileExistsError):
        archive._backup_ledger(source, existing, expected={})
    assert existing.read_bytes() == b"sentinel"
    assert not list(output.glob(".sqlite-backup-*"))


def test_ledger_backup_rejects_symlink_source(tmp_path):
    _session, source, output, _close = _fixture(tmp_path)
    link = tmp_path / "source-link.sqlite3"
    link.symlink_to(source)
    with pytest.raises(archive.ArchiveError, match="unsafe_ledger_source"):
        archive._backup_ledger(link, output / "fixture.sqlite3")
    assert not (output / "fixture.sqlite3").exists()


def test_ledger_backup_publish_failure_leaves_no_final_or_temp(tmp_path, monkeypatch):
    _session, source, output, _close = _fixture(tmp_path)

    def fail_publish(*_args, **_kwargs):
        raise OSError("injected_publish_failure")

    monkeypatch.setattr(archive.os, "link", fail_publish)
    with pytest.raises(OSError, match="injected_publish_failure"):
        archive._backup_ledger(source, output / "fixture.sqlite3", expected={})
    assert not (output / "fixture.sqlite3").exists()
    assert not list(output.glob(".sqlite-backup-*"))
