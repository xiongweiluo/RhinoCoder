"""Pure diagnostic timing replay. No producer, model, Rhino or file imports.

Intervals are journal checkpoint gaps, NOT exclusive source/hash durations.
File mtimes do not prove when a driver observed a reply or clock agreement.
Nothing here grants execution, changes thresholds or reclassifies retired C.
"""
import hashlib
import json
import math

C_ID = "C5DEV-HOSTASSURANCE-20261007-C"
C_FREEZE = "bbbbca84474d5cd397f2e011775cb17b50f6f4a7328c6cee339a4aedf13090d1"
EMPTY = {"groups": {}, "objects": [], "unit": "Millimeters"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def replay_timing(rows, request, response, binding, *, request_mtime_ns,
                  response_mtime_ns, native_ack_seconds=25):
    require(type(native_ack_seconds) in (int, float) and math.isfinite(native_ack_seconds)
            and native_ack_seconds == 25, "retired native deadline must remain25")
    require(type(request_mtime_ns) is int and type(response_mtime_ns) is int
            and 0 < request_mtime_ns <= response_mtime_ns, "ordered integer file mtimes required")
    require(type(binding["host_sequence"]) is int and 0 <= binding["host_sequence"] < len(rows)
            and binding["runtime_freeze_sha256"] == C_FREEZE
            and binding["request_sha256"] == digest(request), "exact request/checkpoint binding required")
    previous = -1
    for n, row in enumerate(rows):
        t = row["elapsed_seconds"]
        require(type(t) in (int, float) and math.isfinite(t) and t >= previous
                and type(row["sequence"]) is int and row["sequence"] == n
                and row["study_id"] == C_ID and row["runtime_freeze_sha256"] == C_FREEZE
                and row["record_sha256"] == digest({k: v for k, v in row.items() if k != "record_sha256"}),
                "monotonic raw journal record identity differs")
        if n:
            require(row["previous_sha256"] == rows[n-1]["record_sha256"], "raw journal link differs")
        previous = t
    start = binding["host_sequence"]
    anchor = rows[start]
    require(binding["host_record_sha256"] == anchor["record_sha256"]
            and anchor["kind"] == "checkpoint"
            and anchor["payload"]["continuity_error_type"] is None, "successful anchored dispatch guard required")
    require(request["kind"] == "execute" and response["status"] == "done"
            and response["payload"] == request["envelope"]["payload"]
            and response["payload"]["operation"] == "get_scene_summary"
            and response["payload"]["arguments"] == {}, "only completed historical read diagnostic allowed")
    require(type(response["stable_idle_samples"]) is int and response["stable_idle_samples"] == 3
            and len(response["settling_samples"]) == 3
            and all(v == response["settling_samples"][0] for v in response["settling_samples"])
            and all(response[k] == EMPTY for k in ("before", "after", "immediate_after", "result"))
            and response["result_sha256"] == digest(EMPTY), "raw empty three-stable read evidence differs")
    # Take only the contiguous successful checkpoint suffix after the anchor.
    # Lifecycle/detach records are never included as request service time.
    suffix = []
    for row in rows[start+1:]:
        if row["kind"] != "checkpoint":
            break
        require(row["payload"]["continuity_error_type"] is None, "post-anchor checkpoint failed")
        suffix.append(row)
    require(len(suffix) == 3, "retired read must have exactly three post-anchor checkpoints")
    points = [anchor] + suffix
    gaps = [points[n+1]["elapsed_seconds"]-points[n]["elapsed_seconds"] for n in range(3)]
    lag = (response_mtime_ns-request_mtime_ns)/1_000_000_000
    return {
        "study_id": C_ID, "status": "RETIRED_DEVELOPMENT_TIMING_DIAGNOSTIC_NOT_NEW_GATE",
        "request_anchor_sequence": start, "post_anchor_checkpoint_sequences": [r["sequence"] for r in suffix],
        "checkpoint_gap_seconds": gaps, "checkpoint_span_seconds": sum(gaps),
        "same_filesystem_request_to_response_mtime_seconds": lag,
        "frozen_native_ack_seconds": native_ack_seconds, "mtime_lag_exceeds_frozen_window": lag > native_ack_seconds,
        "mtime_excess_seconds": max(0, lag-native_ack_seconds),
        "source_guard_exclusive_cost_measured": False,
        "settle_deadline_actual_start_or_completion_proven": False,
        "driver_reply_observation_time_proven": False,
        "mtime_clock_integrity_independently_proven": False,
        "unique_causal_root_proven": False, "late_reply_reclassified_as_timely": False,
        "original_C_remains_failure": True, "execution_authority": False,
        "new_model_gpu_rhino_holdout_calls": 0,
    }
