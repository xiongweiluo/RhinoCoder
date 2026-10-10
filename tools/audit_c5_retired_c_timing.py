"""CPU-only fixed retired-C development audit; never accepts a private path."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.c5_retired_dev_timing_audit import replay_timing
from training.c5_host_assurance_audit import audit_host_continuity, audit_request_checkpoint_bindings

STATE = Path("/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-state-20261007-C")
FIXED = {
    "result.json": "6093aa3ae6e25f31ecaaad551c368a919d499ff2e6c8aa57d674910295b3c3a9",
    "read-lora/request-0009.json": "2a0d1290bb61b07cc223ad5be7c8f5c0f3aef1bdc28eda8104b827f6cc1d2b9d",
    "read-lora/response-0009.json": "13f8482467023c45b6ba729fe5ddaf3cd0f6aee8f113a2569ea8834c242052e3",
    "c-cleanup-b-ui-receipt-observed.json": "c375d62491e0770ce3fbce73dc1c690b79aca0b4ccd66baf73963dcc0f1bad15",
}


def read(name):
    allowed = set(FIXED) | {"read-lora/host-check-0009.json"} | {
        "host-continuity-%04d.json" % n for n in range(58)}
    if type(name) is not str or name not in allowed:
        raise ValueError("only fixed non-key retired development evidence allowed")
    path = STATE/name
    if path.resolve() != path or not path.is_file() or not 0 < path.stat().st_size <= 4194304:
        raise ValueError("fixed bounded regular development file required")
    data = path.read_bytes()
    if name in FIXED and hashlib.sha256(data).hexdigest() != FIXED[name]:
        raise ValueError("retired evidence bytes differ")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("duplicate development JSON field")
            result[k] = v
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite evidence")))


def audit():
    original = read("result.json")
    if original["status"] != "modelbridge_fail_retired_no_replay":
        raise ValueError("original C failure must remain")
    ui = read("c-cleanup-b-ui-receipt-observed.json")
    external = ui["host_receipt"]
    if external["record_count"] != 58:
        raise ValueError("exact sealed retired record population differs")
    host = audit_host_continuity(STATE, "C5DEV-HOSTASSURANCE-20261007-C",
        "bbbbca84474d5cd397f2e011775cb17b50f6f4a7328c6cee339a4aedf13090d1",
        "bd9594c703bf953f5638ba4436a78b20164a6440510de25f64d1077e9c849672", external["seal_sha256"])
    bindings = audit_request_checkpoint_bindings(STATE, ["write-base", "write-lora", "read-lora"],
        "bbbbca84474d5cd397f2e011775cb17b50f6f4a7328c6cee339a4aedf13090d1")
    request_name, response_name = "read-lora/request-0009.json", "read-lora/response-0009.json"
    result = replay_timing([read("host-continuity-%04d.json" % n) for n in range(58)],
        read(request_name), read(response_name), read("read-lora/host-check-0009.json"),
        request_mtime_ns=(STATE/request_name).stat().st_mtime_ns,
        response_mtime_ns=(STATE/response_name).stat().st_mtime_ns)
    return {**result, "raw_host_audit": host, "request_binding_audit": bindings,
        "fixed_file_sha256": FIXED, "key_file_reads": 0, "formal20_reads": 0,
        "new_subscriptions": 0, "retired_entry_replay": False}


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Fixed retired-development audit accepts no arguments or private paths")
    print(json.dumps(audit(), sort_keys=True, allow_nan=False))
