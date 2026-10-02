#!/usr/bin/env python3
"""Read-only source/snapshot/adapter recheck; no torch, training or evaluation.

The remote program reads only fixed source directories, the approved base
snapshot manifest and selected checkpoint. Never reads a final-run directory,
holdout, generation, or consumption ledger, and never writes on the GPU host.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.c5_final_audit import read_public, require  # noqa: E402

REMOTE = r'''
import hashlib,json,subprocess,sys
from pathlib import Path
spec=json.load(sys.stdin)
root=Path("/data/RhinoCoder-c5")
def check(ok, reason):
    if not ok: raise RuntimeError(reason)
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()
manifest=root/"base-snapshot-manifest.json"
m=json.loads(manifest.read_text())
snapshot=Path(m["snapshot_dir"])
approved=Path(m["approved_root"]).resolve()
check(sha(manifest)==spec["base_manifest_sha256"], "base manifest identity drift")
check(snapshot.name==spec["base_revision"] and len(m["file_sha256"])==14, "base revision/file count drift")
check(all((snapshot/n).resolve().is_relative_to(approved) and sha(snapshot/n)==h for n,h in m["file_sha256"].items()), "base snapshot bytes drift")
check(all(sha(root/n)==h for n,h in spec["implementation_sha256"].items()), "frozen execution source drift")
adapter=Path("/data/c5-runs-20261001/formal/checkpoint-132")
actual_adapter={n:sha(adapter/n) for n in spec["adapter_files"]}
check(actual_adapter==spec["adapter_files"], "adapter bytes drift")
inventory={}
for folder in ("agent","training","tools","plugin","data_pipeline"):
    for p in sorted((root/folder).rglob("*.py")):
        check(p.resolve().is_relative_to(root.resolve()) and not p.is_symlink(), "source inventory boundary drift")
        inventory[p.relative_to(root).as_posix()]=sha(p)
for n in ("requirements.txt","requirements-training.txt","requirements-lock.txt"):
    if (root/n).is_file(): inventory[n]=sha(root/n)
gpu=subprocess.check_output(["nvidia-smi","--query-gpu=name,memory.total,memory.used,utilization.gpu","--format=csv,noheader"],text=True).strip()
result={"status":"readonly_assets_verified_not_study_authorization","source_revision_label":(root/"SOURCE_REVISION").read_text().strip(),
"frozen_implementation_files_verified":len(spec["implementation_sha256"]),"source_inventory":inventory,
"base_revision":snapshot.name,"base_snapshot_files_verified":14,"base_manifest_sha256":sha(manifest),
"adapter_files":actual_adapter,"selected_checkpoint":"checkpoint-132","gpu_observation":gpu,
"model_loaded":False,"remote_writes":0,"holdout_rows_read":0,"evaluation_started":False,"c5_6_authorized":False}
print(json.dumps(result,sort_keys=True))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-control", type=Path, required=True)
    parser.add_argument("--ssh-target", required=True)
    parser.add_argument("--ssh-port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(args.ssh_control.is_socket(), "existing authenticated SSH master required")
    freeze = read_public(ROOT/"eval/c5/c5-final-evaluation-freeze.json")
    registry = read_public(ROOT/"eval/c5/gpu-formal-registry-20261001.json")
    base_manifest_sha256 = read_public(ROOT/"eval/c5/gpu-overfit-context-20261001.json")["snapshot"]["manifest_sha256"]
    spec = {"base_revision": registry["base_revision"], "implementation_sha256": freeze["implementation_sha256"],
            "adapter_files": registry["files"], "base_manifest_sha256": base_manifest_sha256}
    import shlex
    command = "/data/conda-envs/rhinocoder/bin/python -c "+shlex.quote(REMOTE)
    completed = subprocess.run([
        "ssh", "-T", "-S", str(args.ssh_control), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "HostKeyAlgorithms=ssh-ed25519", "-p", str(args.ssh_port), args.ssh_target, command,
    ], input=json.dumps(spec), text=True, capture_output=True, timeout=180)
    require(completed.returncode == 0, "read-only remote asset check failed: "+completed.stderr[-1000:])
    value = json.loads(completed.stdout)
    require(value["adapter_files"] == registry["files"] and value["frozen_implementation_files_verified"] == 28
            and value["base_manifest_sha256"] == base_manifest_sha256 and value["base_revision"] == registry["base_revision"]
            and value["status"] == "readonly_assets_verified_not_study_authorization"
            and all(value[k] is False for k in ("model_loaded", "evaluation_started", "c5_6_authorized"))
            and type(value["remote_writes"]) is int and value["remote_writes"] == 0
            and type(value["holdout_rows_read"]) is int and value["holdout_rows_read"] == 0,
            "remote receipt identity differs")
    with args.output.open("x") as output:
        output.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n")
    print(json.dumps({k: value[k] for k in ("status", "base_snapshot_files_verified", "frozen_implementation_files_verified", "c5_6_authorized")}))


if __name__ == "__main__":
    main()
