"""Synthetic failed-A forensic receipts; no Rhino, model, or real probe replay."""
import json
import shutil
import sqlite3
from contextlib import closing

import pytest

from eval.test_research_two_write_audit import fixture, mutate, put
from plugin.rhino_listener.research_safety import ResearchSafetyError, require
from tools import audit_r_research_two_write_incident as module


def failed_archive(tmp_path, monkeypatch):
    batch, output, session = fixture(tmp_path, monkeypatch)
    result = json.loads((output/"result.json").read_text())
    first, second = result["records"]
    # Keep only the first synthetic operation from an existing CPU fixture.
    for filename in ("execute-"+"5"*64+".json", "execute-response-"+"5"*64+".json",
                     "capture-"+"3"*64+".json", "capture-response-"+"3"*64+".json"):
        (session/filename).unlink()
    (session/"channel"/(second["request_id"]+".json")).unlink()
    for name in ("step-1.json", "step-2.json"):
        (output/name).unlink()
    for path in (session/"fixture.sqlite3", output/"fixture.sqlite3"):
        with closing(sqlite3.connect(path)) as db:
            db.execute("DELETE FROM candidate_write WHERE idempotency_key=?", (second["ledger_row"]["idempotency_key"],))
            db.commit()
    with closing(sqlite3.connect(output/"consent.sqlite3")) as db:
        db.execute("DELETE FROM consent_requests WHERE request_id=?", (second["request_id"],))
        db.execute("DELETE FROM consent_events WHERE request_id=?", (second["request_id"],))
        db.commit()
    result.update(status="two_write_research_safety_fail", error="ResearchSafetyError:pre-scene chain differs",
                  cleanup_verified=False, records=[])
    put(output/"result.json", result)
    output.rename(tmp_path/"client")
    shutil.copytree(session, tmp_path/"fixture")
    # Mock only immutable Git-object lookup. Actual field audit checks the
    # complete 128-file ae74b0e manifest against real local Git objects.
    inventory = result["source_inventory"]
    monkeypatch.setattr(module, "verify_frozen_inventory", lambda actual: require(actual == inventory, "source differs"))
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: b'record["before_revision"] >= 1')
    return tmp_path, session


def test_posthoc_cleanup_does_not_promote_original_failure(tmp_path, monkeypatch):
    archive, session = failed_archive(tmp_path, monkeypatch)
    original = (archive/"client"/"result.json").read_bytes()
    value = module.audit(archive)
    assert value["original_status"] == "two_write_research_safety_fail"
    assert value["original_cleanup_verified_flag"] is False
    assert value["fixture_closed_verified"] and value["controller_stopped_verified"]
    assert value["actual_before_revision"] == 0 and value["actual_after_revision"] == 1
    assert value["write_attempts"] == 1 and value["second_write_attempts"] == 0
    assert not value["two_write_gate_passed"] and not value["full_R_research_safety_gate_passed"] and not value["c5_6_authorized"]
    assert str(tmp_path) not in json.dumps(value)
    assert (archive/"client"/"result.json").read_bytes() == original


@pytest.mark.parametrize("tamper", ["original_replay", "geometry", "consent", "cleanup", "promoted_result"])
def test_failed_attempt_forensic_audit_rejects_tampering(tmp_path, monkeypatch, tamper):
    archive, session = failed_archive(tmp_path, monkeypatch)
    if tamper == "original_replay":
        put(session/("execute-"+"9"*64+".json"), {"version": 1})
    elif tamper == "geometry":
        for directory in (session, archive/"fixture"):
            mutate(directory/("capture-response-"+"2"*64+".json"),
                   lambda v: v["scene"]["objects"][0]["max"].__setitem__(0, 999))
    elif tamper == "consent":
        with closing(sqlite3.connect(archive/"client"/"consent.sqlite3")) as db:
            db.execute("UPDATE consent_requests SET status='approved'"); db.commit()
    elif tamper == "cleanup":
        mutate(archive/"batch"/"final-active-002.json", lambda v: v.update(after_close_active_sha256="f"*64))
    elif tamper == "promoted_result":
        mutate(archive/"client"/"result.json", lambda v: v.update(status="two_write_research_safety_pass_not_model_quality"))
    with pytest.raises(ResearchSafetyError): module.audit(archive)
