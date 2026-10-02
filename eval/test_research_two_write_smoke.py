import copy

import pytest

from plugin.rhino_listener.research_safety import ResearchSafetyError, canonical_hash
from tools.r_research_two_write_smoke import SPEC, run, verify_owner_approval


def approval():
    return {"authorized_by": "repository_owner", "probe_spec_sha256": canonical_hash(SPEC), "approved": True,
            "authorization_basis": "explicit owner reply approving fixed two-write research safety probe"}


@pytest.mark.parametrize("field,value", [("authorized_by", "codex"), ("approved", False),
                                         ("probe_spec_sha256", "a"*64), ("authorization_basis", "agent thinks so")])
def test_agent_or_changed_spec_cannot_open_fixture(tmp_path, field, value):
    value_record = approval()
    value_record[field] = value
    with pytest.raises(ResearchSafetyError):
        run(tmp_path/"nonexistent-batch", tmp_path/"output", value_record)
    assert not (tmp_path/"output").exists()


def test_exact_external_approval_not_a_general_model_quality_grant():
    verify_owner_approval(approval())
    changed = copy.deepcopy(SPEC)
    changed["steps"][0]["width"] += 1
    with pytest.raises(ResearchSafetyError):
        verify_owner_approval({**approval(), "probe_spec_sha256": canonical_hash(changed)})
    assert SPEC["model_calls"] == 0 and SPEC["max_write_requests"] == 2 and not SPEC["formal_quality_claim"]


def test_attempted_a_id_cannot_be_replayed_even_with_valid_approval(tmp_path):
    with pytest.raises(ResearchSafetyError, match="retired"):
        run(tmp_path/"nonexistent-batch", tmp_path/"fresh-output", approval())
    assert not (tmp_path/"fresh-output").exists()


@pytest.mark.parametrize("bad_cleanup", [False, True])
def test_cpu_task_failure_is_distinct_from_verified_cleanup(tmp_path, monkeypatch, bad_cleanup):
    from tools import r_research_two_write_smoke as module
    from tools.r4_v5_ssh_no_write_session import _private_publish
    # Synthetic-only mocked lifecycle; no authorization for a real new probe.
    spec = {**SPEC, "probe_id": "RSDEV-CPU-MOCK"}
    monkeypatch.setattr(module, "SPEC", spec)
    batch = tmp_path/"batch"
    batch.mkdir(mode=0o700)
    digest = "a"*64
    _private_publish(batch, "bootstrap.json", {"version": 2, "model_invocation_allowed": False,
        "formal_quality_claim": False, "scope": spec["scope"], "initial_active_sha256": digest})
    _private_publish(batch, "source-inventory.json", {})
    monkeypatch.setattr(module, "verify_loaded_sources", lambda *args: None)
    def fail_write(*args):
        raise RuntimeError("synthetic task failure")
    monkeypatch.setattr(module, "write_steps", fail_write)
    calls = []
    def send(directory, seq, action, case_id, kind):
        calls.append(action)
        _private_publish(directory, "request-%03d.json" % seq, {
            "version": 2, "seq": seq, "action": action, "case_id": case_id, "fixture": kind})
        session = str(tmp_path/"synthetic-session")
        if action == "open":
            return {"status": "opened", "case_id": spec["probe_id"], "session_dir": session,
                    "fixture": "empty", "initial_active_sha256": digest}
        if action == "close":
            capture = {"case_id": spec["probe_id"], "session_dir": session, "on_rhino_main_thread": True,
                "capture_scope": "same_ui_callback_before_and_after_fixture_close", "close_seq": 2,
                "fixture_closed": True, "key_removed": True, "initial_active_sha256": digest,
                "before_close_active_sha256": digest, "after_close_active_sha256": "b"*64 if bad_cleanup else digest}
            _private_publish(batch, "final-active-002.json", capture)
            return {"status": "closed", "case_id": spec["probe_id"], "session_dir": session,
                    "key_removed": True, "final_active_capture": capture}
        return {"status": "stopped", "case_id": "RSDEV-END", "had_failure": False, "active_sha256_at_stop": digest}
    monkeypatch.setattr(module, "request", send)
    owner_record = {**approval(), "probe_spec_sha256": canonical_hash(spec)}
    result = module.run(batch, tmp_path/"output", owner_record)
    assert result["status"] == "two_write_research_safety_fail" and result["error"]
    assert result["cleanup_verified"] is (not bad_cleanup)
    assert calls == (["open", "close"] if bad_cleanup else ["open", "close", "stop"])
