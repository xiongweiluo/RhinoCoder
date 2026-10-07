"""Independent completion timing replay; never imports producer timers."""
import hashlib
import json
import math


def digest(v):
    return hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def audit_phase(value, *, role, sequence, freeze_sha, request, response, cap):
    require(set(value) == {"version", "role", "sequence", "runtime_freeze_sha256", "request_sha256",
        "response_sha256", "cap_seconds", "elapsed_seconds", "events", "completed_in_budget",
        "hard_preemption_proven", "execution_success_claimed"} and type(value["version"]) is int
        and value["version"] == 1 and type(value["sequence"]) is int and value["sequence"] == sequence
        and value["role"] == role and value["runtime_freeze_sha256"] == freeze_sha
        and value["request_sha256"] == digest(request) and value["response_sha256"] == digest(response),
        "raw timing phase binding differs")
    require(type(value["cap_seconds"]) is int and value["cap_seconds"] == cap
        and value["completed_in_budget"] is True and value["hard_preemption_proven"] is False
        and value["execution_success_claimed"] is False, "timing cannot grant success or preemption")
    events = value["events"]
    require(type(events) is list and 2 <= len(events) <= 64
        and events[0] == {"event": "started", "elapsed_seconds": 0.0}
        and events[-1]["event"] == ("response-written" if role in {"hub", "native", "settle"} else "response-validated"),
        "complete raw phase boundaries required")
    previous = -1
    for row in events:
        require(set(row) == {"event", "elapsed_seconds"} and type(row["event"]) is str
                and row["event"].isascii() and 0 < len(row["event"]) <= 64, "raw phase event malformed")
        t = row["elapsed_seconds"]
        require(type(t) in (int, float) and math.isfinite(t) and previous <= t < cap,
                "raw phase deadline/clock differs")
        previous = t
    require(type(value["elapsed_seconds"]) in (int, float)
        and value["elapsed_seconds"] == previous, "phase final elapsed differs")
    return {"raw_phase_verified": True, "elapsed_seconds": previous, "execution_authority": False}
