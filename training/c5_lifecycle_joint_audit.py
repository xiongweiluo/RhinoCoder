"""Independent raw timing population/binding audit. No producer import."""
from pathlib import Path
from plugin.rhino_listener.c5_research_channel import read_json
from training.c5_lifecycle_timing_audit import audit_phase, require


def audit_native_timing(directory, freeze_sha, *, hub=False):
    prefix = "hub-" if hub else ""
    requests = sorted(directory.glob(prefix+"request-*.json"))
    names = {p.name[len(prefix+"request-"):] for p in requests}
    require(names and {p.name[len(prefix+"service-time-"):] for p in directory.glob(prefix+"service-time-*.json")} == names
        and {p.name[len(prefix+"client-time-"):] for p in directory.glob(prefix+"client-time-*.json")} == names,
        "missing/extra complete native timing sidecar population")
    settles, count = set(), 0
    for path in requests:
        n = path.name[len(prefix+"request-"):]
        require(n == "%04d.json" % (count+1), "timing request sequence differs")
        seq = count+1
        request, response = read_json(directory, path.name), read_json(directory, prefix+"response-"+n)
        audit_phase(read_json(directory, prefix+"service-time-"+n), role="hub" if hub else "native",
                    sequence=seq, freeze_sha=freeze_sha, request=request, response=response, cap=120)
        audit_phase(read_json(directory, prefix+"client-time-"+n), role="client",
                    sequence=seq, freeze_sha=freeze_sha, request=request, response=response, cap=120)
        if not hub and request.get("kind") == "execute" and response.get("status") == "done":
            settles.add("settle-time-"+n)
            audit_phase(read_json(directory, "settle-time-"+n), role="settle",
                        sequence=seq, freeze_sha=freeze_sha, request=request, response=response, cap=60)
        count += 1
    require(hub or {p.name for p in directory.glob("settle-time-*.json")} == settles,
            "extra/missing execute settling timing proof")
    return {"native_requests_with_complete_timing": count, "execution_authority": False}


def audit_model_timing(state, order, freeze_sha):
    ready = read_json(state, "worker-startup-ready.json")
    audit_phase(read_json(state, "startup-time.json"), role="startup", sequence=0,
                freeze_sha=freeze_sha, request=None, response=ready, cap=180)
    for seq, slot in enumerate(order, 1):
        directory = state/slot
        audit_phase(read_json(directory, "model-time.json"), role="model", sequence=seq,
            freeze_sha=freeze_sha, request=read_json(directory, "model-request.json"),
            response=read_json(directory, "model-response.json"), cap=180)
    return {"model_requests_with_complete_timing": len(order), "startup_timing_verified": True,
            "execution_authority": False}
