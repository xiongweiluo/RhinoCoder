import copy
import pytest
from training.c5_retired_dev_timing_audit import C_ID, C_FREEZE, EMPTY, digest, replay_timing


def fixture():
    request = {"kind": "execute", "envelope": {"payload": {"operation": "get_scene_summary", "arguments": {}}}}
    sample = {"native": EMPTY, "state": {"revision": 0}, "active_sha256": "a"*64}
    response = {"status": "done", "payload": request["envelope"]["payload"], "stable_idle_samples": 3,
                "settling_samples": [copy.deepcopy(sample) for _ in range(3)],
                "before": EMPTY, "after": EMPTY, "immediate_after": EMPTY, "result": EMPTY, "result_sha256": digest(EMPTY)}
    rows = []
    for n, t in enumerate([0, 6.4, 12.8, 19.2, 1000]):
        row = {"study_id": C_ID, "runtime_freeze_sha256": C_FREEZE, "sequence": n,
               "elapsed_seconds": t, "kind": "checkpoint" if n < 4 else "detach_attempt",
               "payload": {"continuity_error_type": None}, "previous_sha256": rows[-1]["record_sha256"] if rows else "b"*64}
        row["record_sha256"] = digest(row)
        rows.append(row)
    binding = {"host_sequence": 0, "runtime_freeze_sha256": C_FREEZE, "request_sha256": digest(request),
               "host_record_sha256": rows[0]["record_sha256"]}
    return rows, request, response, binding


def run(parts, **kwargs):
    return replay_timing(*parts, request_mtime_ns=1_000_000_000, response_mtime_ns=26_600_000_000, **kwargs)


def rehash(rows):
    for i, row in enumerate(rows):
        if i:
            row["previous_sha256"] = rows[i-1]["record_sha256"]
        row["record_sha256"] = digest({k: v for k, v in row.items() if k != "record_sha256"})


def test_checkpoint_gaps_not_causal_cost_or_gate_pass():
    result = run(fixture())
    assert result["checkpoint_span_seconds"] == pytest.approx(19.2)
    assert result["mtime_excess_seconds"] == pytest.approx(.6)
    for k in ["source_guard_exclusive_cost_measured", "driver_reply_observation_time_proven",
              "unique_causal_root_proven", "late_reply_reclassified_as_timely", "execution_authority"]:
        assert result[k] is False
    assert result["original_C_remains_failure"] is True


@pytest.mark.parametrize("which,value", [
    ("host_sequence", True), ("host_sequence", -1), ("host_sequence", 100),
    ("runtime_freeze_sha256", "x"*64), ("request_sha256", "x"*64), ("host_record_sha256", "x"*64)])
def test_wrong_binding_rejected(which, value):
    parts = fixture(); parts[3][which] = value
    with pytest.raises(ValueError):
        run(parts)


@pytest.mark.parametrize("field,value", [("elapsed_seconds", True), ("elapsed_seconds", -1),
    ("elapsed_seconds", float("nan")), ("sequence", True), ("study_id", "new-D"),
    ("runtime_freeze_sha256", "x"*64), ("record_sha256", "x"*64)])
def test_tampered_or_nonmonotonic_records_rejected(field, value):
    parts = fixture(); parts[0][1][field] = value
    with pytest.raises((ValueError, TypeError)):
        run(parts)


def test_rehashed_decreasing_clock_rejected():
    parts = fixture();parts[0][2]["elapsed_seconds"] = 1; rehash(parts[0])
    with pytest.raises(ValueError):
        run(parts)


@pytest.mark.parametrize("deadline", [24, 26, True, float("inf"), float("nan")])
def test_retired_deadline_cannot_be_changed(deadline):
    with pytest.raises(ValueError):
        run(fixture(), native_ack_seconds=deadline)


@pytest.mark.parametrize("field,value", [("status", "failed_no_retry"), ("stable_idle_samples", True),
    ("stable_idle_samples", 2), ("result_sha256", "x"*64), ("after", {"objects": [1]})])
def test_failed_or_unstable_reply_rejected(field, value):
    parts = fixture(); parts[2][field] = value
    with pytest.raises(ValueError):
        run(parts)


def test_divergent_sample_rejected():
    parts = fixture();parts[2]["settling_samples"][1]["state"]["revision"] = 1
    with pytest.raises(ValueError):
        run(parts)


def test_control_not_timing_diagnostic():
    parts = fixture();parts[1]["kind"] = "control";parts[3]["request_sha256"] = digest(parts[1])
    with pytest.raises(ValueError):
        run(parts)


@pytest.mark.parametrize("count", [2, 4])
def test_missing_extra_post_anchor_checkpoints_rejected(count):
    parts = list(fixture())
    parts[0] = parts[0][:count+1]
    if count == 4:
        parts[0][4]["kind"] = "checkpoint"; rehash(parts[0])
    with pytest.raises(ValueError):
        run(parts)


def test_mtime_bool_or_backward_rejected():
    for start, end in [(True, 1), (2, 1), (0, 2)]:
        with pytest.raises(ValueError):
            replay_timing(*fixture(), request_mtime_ns=start, response_mtime_ns=end)


def test_fixed_audit_rejects_keys_and_arbitrary_names_before_io(monkeypatch):
    from pathlib import Path
    from tools.audit_c5_retired_c_timing import read
    def forbidden(*args, **kwargs):
        raise AssertionError("no IO permitted before fixed name validation")
    monkeypatch.setattr(Path, "resolve", forbidden)
    for name in ["hub.key", "read-lora/handoff.key", "../../holdout.jsonl", "private.jsonl", None]:
        with pytest.raises(ValueError):
            read(name)


def test_cli_private_path_argument_rejected_before_fixed_evidence_read():
    import subprocess
    import sys
    from pathlib import Path
    tool = Path(__file__).resolve().parents[1]/"tools/audit_c5_retired_c_timing.py"
    result = subprocess.run([sys.executable, str(tool), "/synthetic/private20.jsonl"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "accepts no arguments or private paths" in result.stderr
    assert "Traceback" not in result.stderr
