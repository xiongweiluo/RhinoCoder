#!/usr/bin/env python3
"""Read-only public C5-6 freeze preparation; deliberately cannot admit a run.

No private task input, owner approval, decryption, GPU, Rhino, network or state
directory is opened. A future formal entry needs a *new* complete runtime
freeze, real adapter/import closure and exact owner approval; this inventory
is merely a reproducible preparation snapshot.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.c5_contract import BASE_MODEL_REVISION, CONTRACT_ID, CORE_INVOCATION_TOOLS
from training.c5_formal20_plan import STUDY_ID, STRATA


SOURCE_FOLDERS = ("agent", "training", "tools", "plugin", "data_pipeline")
PUBLIC_FILES = (
    "eval/c5/rhino-formal20-spec-draft.json",
    "eval/c5/rhino-runtime-schema-v1.json",
    "eval/c5/gpu-formal-registry-20261001.json",
    "eval/c5/c5-engineering-config.json",
    "requirements-training.txt", "requirements.txt",
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def report() -> dict:
    draft = json.loads((ROOT / PUBLIC_FILES[0]).read_text(encoding="utf-8"))
    registry = json.loads((ROOT / PUBLIC_FILES[2]).read_text(encoding="utf-8"))
    if (draft.get("study_id") != STUDY_ID or draft.get("execution_ready") is not False
            or draft.get("owner_approval_received") is not False
            or draft.get("contract_id") != CONTRACT_ID
            or draft.get("base_revision") != BASE_MODEL_REVISION
            or draft.get("strata_counts") != STRATA
            or draft.get("family_count") != 20 or draft.get("route_slots") != 40
            or draft.get("original_final_entry_allowed") is not False
            or draft.get("default_route_change_allowed") is not False):
        raise ValueError("formal20 public draft boundary changed")
    if (registry.get("selected_checkpoint") != "checkpoint-132"
            or draft.get("adapter_sha256") != registry.get("adapter_sha256")
            or len(CORE_INVOCATION_TOOLS) != 12):
        raise ValueError("original base/adapter/core-tool identity changed")
    source = {path.relative_to(ROOT).as_posix(): _sha(path)
              for folder in SOURCE_FOLDERS for path in sorted((ROOT / folder).rglob("*.py"))}
    public = {name: _sha(ROOT / name) for name in PUBLIC_FILES}
    if not source or len(public) != len(PUBLIC_FILES):
        raise ValueError("public/source inventory incomplete")
    return {
        "status": "public_freeze_preparation_only_not_execution_ready",
        "study_id": STUDY_ID,
        "draft_spec_file_sha256": public[PUBLIC_FILES[0]],
        "source_file_count": len(source),
        "source_inventory_sha256": hashlib.sha256(_canonical(source)).hexdigest(),
        "public_file_sha256": public,
        "contract_id": CONTRACT_ID,
        "core_tool_count": 12,
        "base_revision": BASE_MODEL_REVISION,
        "adapter_sha256": registry["adapter_sha256"],
        "execution_ready": False,
        "owner_approval_received": False,
        "private_task_files_opened": 0,
        "original80_rows_read": 0,
        "formal_route_slots_consumed": 0,
        "gpu_model_calls": 0,
        "real_rhino_calls": 0,
        "actual_mac_rhino_gpu_import_closure_verified": False,
        "remaining": list(draft["pending_before_execution"]),
    }


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, sort_keys=True, indent=2))
