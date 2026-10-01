#!/usr/bin/env python3
"""Independent custodian's terminal-only C5 final invocation.

Never run this from an agent tool call. Ciphertext/key paths are entered by
the owner in their own terminal, never recorded in source or public reports.
The authoritative owner ledger is fixed in the explicitly selected private
state directory; use the same directory for all invocations.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.umask(0o077)

from training.c5_execution import digest, read_json, sha256_file, write_json  # noqa: E402
from training.c5_final_evaluation import verify_sealed_plaintext  # noqa: E402
from training.c5_holdout import claim_encrypted_artifact  # noqa: E402


def outside_repo(path):
    if path.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError("custodian artifact/state/identity must remain outside the repository")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner-state-dir", type=Path, required=True)
    p.add_argument("--final-freeze", type=Path, required=True)
    p.add_argument("--ssh-control", type=Path)
    a = p.parse_args()
    if not sys.stdin.isatty():
        raise RuntimeError("owner final tool requires the custodian's interactive terminal")
    age = shutil.which("age")
    if not age:
        raise RuntimeError("age is unavailable; install/verify it before any consumption")
    outside_repo(a.owner_state_dir)
    freeze = read_json(a.final_freeze)
    for name, expected in freeze["implementation_sha256"].items():
        if sha256_file(ROOT / name) != expected:
            raise RuntimeError("local final evaluation code differs from freeze")
    ciphertext = Path(input("Encrypted artifact path (private, not logged): ").strip()).expanduser()
    identity = Path(input("age identity file path (private, not logged): ").strip()).expanduser()
    outside_repo(ciphertext); outside_repo(identity)
    if not ciphertext.is_file() or not identity.is_file():
        raise RuntimeError("custodian files unavailable; no claim made")
    commitment = read_json(ROOT / "eval/c5/final-holdout-commitment.json")
    expected_commitment = digest(commitment)
    confirmation = input("To consume ONCE, enter commitment SHA-256 " + expected_commitment + ": ").strip()
    if confirmation != expected_commitment or confirmation != freeze["commitment_sha256"]:
        raise RuntimeError("explicit custodian confirmation mismatch; no claim made")
    a.owner_state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if a.owner_state_dir.stat().st_mode & 0o077:
        raise RuntimeError("custodian state directory must be mode 0700")
    remote_args = ["/data/conda-envs/rhinocoder/bin/python", "tools/run_c5_final_remote.py",
        "--run-root", "/data/c5-runs-20261001", "--snapshot",
        "/data/hf-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/c03e6d358207e414f1eca0bb1891e29f1db0e242",
        "--snapshot-manifest", "/data/RhinoCoder-c5/base-snapshot-manifest.json",
        "--authorization", "/data/RhinoCoder-c5/eval/c5/c5-execution-authorization-v3.json",
        "--final-freeze", "/data/RhinoCoder-c5/eval/c5/c5-final-evaluation-freeze.json"]
    ssh = ["ssh", "-T", "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlgorithms=ssh-ed25519"]
    if a.ssh_control: ssh += ["-S", str(a.ssh_control)]
    ssh += ["-p", "22134", "linux@175.155.64.171",
            "cd /data/RhinoCoder-c5 && " + shlex.join(remote_args)]
    ready = subprocess.run(ssh[:-1]+[ssh[-1]+" --preflight"], text=True,
                           capture_output=True, check=True, timeout=300)
    preflight = json.loads(ready.stdout)
    if preflight.get("ready") is not True or preflight["final_freeze_sha256"] != digest(freeze):
        raise RuntimeError("remote final preflight mismatch; no claim made")
    # Do not move/remove/reset this authoritative ledger or choose a new state directory for a retry.
    claim = claim_encrypted_artifact(commitment, ciphertext,
        a.owner_state_dir / "c5-holdout-consumption.jsonl",
        confirm_commitment_sha256=confirmation, code_revision=freeze["code_revision"],
        adapter_sha256=freeze["adapter_sha256"], thresholds_sha256=freeze["thresholds_sha256"],
        expected_exclusion_sha256=sha256_file(ROOT / "eval/c5/historical-exclusions.json"),
        expected_dataset_freeze_sha256=sha256_file(ROOT / "eval/c5/dataset-v2-freeze-manifest.json"))
    try:
        plain = subprocess.run([age, "--decrypt", "-i", str(identity), str(ciphertext)],
                               capture_output=True, check=True).stdout
        families = [json.loads(line) for line in plain.decode("utf-8").splitlines() if line.strip()]
        del plain
        verify_sealed_plaintext(families, commitment)
        payload = {"custodian_identity":"repository_owner", "run_id":claim["run_id"],
                   "holdout_consumed_at":claim["holdout_consumed_at"], "families":families,
                   "commitment_sha256":confirmation, "adapter_sha256":freeze["adapter_sha256"],
                   "thresholds_sha256":freeze["thresholds_sha256"], "code_revision":freeze["code_revision"]}
        # Private stdin only; neither prompts nor targets occur in shell arguments/logs.
        result = subprocess.run(ssh, input=json.dumps(payload, ensure_ascii=False),
                                text=True, capture_output=True, timeout=4*3600+120)
        if result.returncode != 0:
            raise RuntimeError("final remote execution failed after consumption; no automatic rerun")
        report = json.loads(result.stdout)
        write_json(a.owner_state_dir / "c5-public-final-report.json", report, exclusive=True)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except BaseException as exc:
        write_json(a.owner_state_dir / "c5-failed-consumption.json", {
            "run_id":claim["run_id"], "error_type":type(exc).__name__, "new_run_allowed":False}, exclusive=True)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("C5 owner evaluation stopped: " + type(exc).__name__ + ". Consult the private ledger; do not rerun after a claim.", file=sys.stderr)
        raise SystemExit(1)
