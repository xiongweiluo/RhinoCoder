#!/usr/bin/env python3
"""Fixed B development probe: frozen source, owner approval and permanent claim.

No model, GPU, holdout, formal score or automatic retry. The default historic
entry remains retired A. This entry deliberately exposes no custom task/spec,
state-directory or output-directory command-line switches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.rhino_listener.research_safety import (canonical_hash, require,
    source_inventory, verify_loaded_sources)  # noqa: E402
from tools.r4_v5_ssh_no_write_session import (_private_directory, _private_publish,
    _private_read, _unique_pairs)  # noqa: E402
from tools.r_research_two_write_smoke import run as run_engine, verify_owner_approval  # noqa: E402

SPEC = {
    "probe_id": "RSDEV-TWO-WRITE-20261002-B", "scope": "isolated_unsaved_headless_mm",
    "steps": [{"op": "create_box", "width": 347, "depth": 353, "height": 359},
              {"op": "move_object", "alias": "box-1", "dx": 7, "dy": -11, "dz": 13}],
    "max_write_requests": 2, "model_calls": 0, "formal_quality_claim": False,
}
POLICY = {
    "version": 2, "fixtures": 1, "fixture": "empty", "unit": "Millimeters",
    "lifecycle": ["open", "close", "stop"], "write_retries": 0, "model_calls": 0,
    "gpu_hours": 0, "holdout_reads": 0, "quality_claim": False,
    "claim_before_open": True, "claim_permanent_even_on_interruption": True,
    "engine_claim_before_open": True,
    "geometry_checks": "independent exact box bounds and translation, entire object set",
    "permission_checks": "two consumed permissions, eight bound events and two done ledger rows",
    "cleanup_checks": "same UI callback active digests, exact session close, key absence and controller stop",
    "timeout_policy": "bounded existing RPCs; no kill or retry; unknown identity requires manual cleanup",
    "lifecycle_rpc_seconds": 30, "scene_rpc_seconds": 20, "execute_rpc_seconds": 30,
    "pass_authorizes": "two-tool research subset only, not full R gate or C5-6",
}
FREEZE_PATH = ROOT/"eval/r_research/two-write-B-freeze-20261002.json"
STATE_DIR = Path("/Users/xiongweiluo/RhinoCoder/data/training/c5/research-probe-state")
CLAIM_NAME = SPEC["probe_id"]+".claim.json"
ENGINE_NAME = SPEC["probe_id"]+".engine-started.json"
OUTPUT_NAME = SPEC["probe_id"]+"-output"


def read_freeze():
    require(FREEZE_PATH.resolve() == FREEZE_PATH and not FREEZE_PATH.is_symlink(), "unsafe freeze path")
    fd = os.open(FREEZE_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= 256*1024, "unsafe freeze file")
        raw = os.read(fd, 256*1024+1)
        require(len(raw) == info.st_size, "freeze changed during read")
    finally:
        os.close(fd)
    return json.loads(raw, object_pairs_hook=_unique_pairs)


def verify_freeze(freeze):
    require(isinstance(freeze, dict) and set(freeze) == {
        "schema_version", "probe_spec", "probe_spec_sha256", "policy", "source_revision",
        "source_inventory", "source_inventory_sha256"}, "freeze schema differs")
    require(type(freeze["schema_version"]) is int and freeze["schema_version"] == 2
            and canonical_hash(freeze["probe_spec"]) == canonical_hash(SPEC)
            and freeze["probe_spec_sha256"] == canonical_hash(SPEC)
            and canonical_hash(freeze["policy"]) == canonical_hash(POLICY), "fixed B scope/policy differs")
    revision = freeze["source_revision"]
    require(isinstance(revision, str) and len(revision) == 40
            and all(c in "0123456789abcdef" for c in revision), "source revision invalid")
    inventory = freeze["source_inventory"]
    require(inventory == source_inventory(ROOT)
            and freeze["source_inventory_sha256"] == canonical_hash(inventory), "source inventory incomplete/drifted")
    # Freeze is committed after its source commit; verify that every frozen
    # file actually belongs to that immutable commit, not just a Git label.
    for name, digest in inventory.items():
        raw = subprocess.check_output(["git", "show", revision+":"+name], cwd=ROOT)
        require(hashlib.sha256(raw).hexdigest() == digest, "source commit bytes differ")
    verify_loaded_sources(ROOT, inventory, tuple(sys.modules.values()))
    return canonical_hash(freeze)


def verify_approval(approval, freeze):
    digest = verify_freeze(freeze)
    verify_owner_approval(approval, spec=SPEC)
    require(approval.get("runtime_freeze_sha256") == digest, "owner approval does not bind runtime freeze")
    return digest


def verify_fresh_batch(batch, freeze):
    bootstrap = _private_read(batch/"bootstrap.json")
    require(bootstrap.get("version") == 2 and bootstrap.get("scope") == SPEC["scope"]
            and bootstrap.get("model_invocation_allowed") is False
            and bootstrap.get("formal_quality_claim") is False, "controller scope differs")
    require(_private_read(batch/"source-inventory.json") == freeze["source_inventory"], "controller source drift")
    require(not any(list(batch.glob(pattern)) for pattern in
                    ("request-*.json", "response-*.json", "failure-*.json", "final-active-*.json")),
            "controller already attempted; fresh controller required")


def claim_value(batch, approval, digest):
    return {"schema_version": 2, "probe_id": SPEC["probe_id"],
        "probe_spec_sha256": canonical_hash(SPEC), "runtime_freeze_sha256": digest,
        "batch_dir": str(batch.resolve()), "output_dir": str(STATE_DIR/OUTPUT_NAME),
        "owner_approval_sha256": canonical_hash(approval), "state": "claimed_permanently_before_open"}


def begin_engine(batch, output, approval, spec):
    require(canonical_hash(spec) == canonical_hash(SPEC), "only fixed B may use this engine admission")
    freeze = read_freeze()
    digest = verify_approval(approval, freeze)
    verify_fresh_batch(batch, freeze)
    require(output == STATE_DIR/OUTPUT_NAME and STATE_DIR.resolve() == STATE_DIR, "engine output/state differs")
    claim = _private_read(STATE_DIR/CLAIM_NAME)
    require(claim == claim_value(batch, approval, digest), "engine lacks exact permanent admission")
    # Also reject direct shared-engine calls after interruption before mkdir.
    _private_publish(STATE_DIR, ENGINE_NAME, {"schema_version": 2,
        "probe_id": SPEC["probe_id"], "claim_sha256": canonical_hash(claim),
        "state": "engine_started_once_before_open"})


def run(batch, approval):
    freeze = read_freeze()
    digest = verify_approval(approval, freeze)
    verify_fresh_batch(batch, freeze)
    require(STATE_DIR.is_dir() and STATE_DIR.resolve() == STATE_DIR, "owner private state directory required")
    fd = _private_directory(STATE_DIR)
    os.close(fd)
    output = STATE_DIR/OUTPUT_NAME
    require(not output.exists() and not output.is_symlink(), "B output exists; never replay")
    # Atomic exclusive publication arbitrates concurrent processes. A claim
    # is never removed or replaced, even if the process dies before open.
    claim = claim_value(batch, approval, digest)
    _private_publish(STATE_DIR, CLAIM_NAME, claim)
    return run_engine(batch, output, approval, spec=SPEC)


def audit(batch):
    from tools.audit_r_research_two_write import audit as audit_receipts
    freeze = read_freeze()
    digest = verify_freeze(freeze)
    claim = _private_read(STATE_DIR/CLAIM_NAME)
    output = STATE_DIR/OUTPUT_NAME
    approval = _private_read(output/"owner-approval.json")
    verify_approval(approval, freeze)
    require(claim == claim_value(batch, approval, digest),
        "permanent claim identity differs")
    engine_claim = _private_read(STATE_DIR/ENGINE_NAME)
    require(engine_claim == {"schema_version": 2, "probe_id": SPEC["probe_id"],
        "claim_sha256": canonical_hash(claim), "state": "engine_started_once_before_open"},
        "single engine admission differs")
    value = audit_receipts(batch, output/"result.json", spec=SPEC)
    value.update({"runtime_freeze_sha256": digest, "permanent_claim_sha256": canonical_hash(claim),
                  "engine_claim_sha256": canonical_hash(engine_claim),
                  "permanent_claim_verified": True, "historic_A_retired": True})
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "audit"))
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--owner-approval", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        require(args.owner_approval is not None and args.report is None, "run requires owner receipt only")
        value = run(args.batch_dir, _private_read(args.owner_approval))
        print(json.dumps({k: value[k] for k in ("status", "error", "cleanup_verified", "c5_6_authorized")}))
        raise SystemExit(0 if value["error"] is None else 1)
    require(args.report is not None and args.owner_approval is None, "audit requires public report only")
    value = audit(args.batch_dir)
    with args.report.open("x") as destination:
        destination.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n")
    print(json.dumps({k: value[k] for k in ("status", "probe_id", "c5_6_authorized")}))


if __name__ == "__main__":
    main()
