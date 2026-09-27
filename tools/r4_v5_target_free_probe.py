#!/usr/bin/env python3
"""Frozen target-free v5 acceptance; real approved model, zero dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

from tools.r4_v3_model_probe import FrozenScene, load_frozen_tools  # noqa: E402
from training.explicit_step_gate_candidate import (  # noqa: E402
    ExplicitStepError, before_invoker, preflight,
)
from training.tool_controller_candidate import compose_step_input  # noqa: E402
from training.tool_invocation_v5_candidate import check_invocation, render_invocation  # noqa: E402
from training.tool_local_gate_candidate import OfflineTransformersBackend, VerifiedSnapshot  # noqa: E402
from training.tool_selector_v4_candidate import render_selection  # noqa: E402


FROZEN_SHA256 = {
    "training/explicit_step_gate_candidate.py": "bd5861616fff1da96f9e38b558ec73f79cecd6d79220fd957ea3074b2b3caca5",
    "training/tool_invocation_v5_candidate.py": "eb9af542520bea20a005cb17b1dbb0b536313fd351a3dccf343360aa156d0751",
    "training/tool_selector_v4_candidate.py": "13d26e9a2b56702a182d68392138d7d453c71e4ad1566ba881f08846c8a4ee1b",
    "training/tool_contract_v3_candidate.py": "0905b85baf00d4416d7e7a2ae3074035a0d2294fa2f845ee77bc3504d9eb3051",
    "eval/r4_v5_target_free_new_cases.json": "a01dbedacb684f822caa1778cb7da40c570ba4f0dfb261a19c46a1fc18e01de0",
}


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _freeze_check() -> None:
    for relative, digest in FROZEN_SHA256.items():
        if _sha((ROOT / relative).read_bytes()) != digest:
            raise ValueError(f"frozen_file_changed:{relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--operator-approved-sha256", required=True)
    args = parser.parse_args()
    _freeze_check()
    tools = load_frozen_tools(ROOT / "eval/r4_v3_public_tools.json")
    fixture = json.loads((ROOT / "eval/r4_v5_target_free_new_cases.json").read_text(encoding="utf-8"))
    cases = fixture.get("cases")
    if fixture.get("fixture_id") != "r4-v5-target-free-new-20260922" or (
        not isinstance(cases, list) or len(cases) != 24
        or len({c["id"] for c in cases}) != 24
        or sum(c["expected_tool"] is None for c in cases) != 12
    ):
        raise ValueError("invalid_frozen_cases")
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"approved_root", "snapshot_dir", "file_sha256"}:
        raise ValueError("invalid_snapshot_manifest")
    manifest = VerifiedSnapshot(Path(payload["approved_root"]), Path(payload["snapshot_dir"]), payload["file_sha256"])
    scene = FrozenScene(fixture["scene_summary"])
    rows = []
    accepted = []
    started = time.monotonic()
    for case in cases:
        row = {"id": case["id"], "expected_kind": "reject" if case["expected_tool"] is None else "accept"}
        try:
            expected = preflight(case["task"], scene=scene, tools=tools)
        except ExplicitStepError as exc:
            row.update(status="preflight_rejected", reason=exc.code, selector_calls=0, invoker_calls=0)
        else:
            row.update(status="preflight_accepted", selector_calls=0, invoker_calls=0)
            accepted.append((case, expected, row))
        rows.append(row)
    accepted_by_id = {case["id"]: expected.tool_name for case, expected, _ in accepted}
    preflight_passed = len(accepted) == 12 and all(
        (row["status"] == "preflight_rejected") == (case["expected_tool"] is None)
        and (case["expected_tool"] is None or accepted_by_id.get(case["id"]) == case["expected_tool"])
        for row, case in zip(rows, cases)
    )
    if not preflight_passed:
        print(json.dumps({"preflight_gate_passed": False, "no_dispatch": True, "cases": rows}, sort_keys=True))
        return 1

    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_required_for_v5_probe")
    backend = OfflineTransformersBackend.load(manifest, operator_approved_sha256=args.operator_approved_sha256)
    with torch.inference_mode():
        for case, expected, row in accepted:
            began = time.monotonic()
            try:
                current = compose_step_input(case["task"], scene.snapshot())
                selector_prompt = render_selection(backend.tokenizer, current, tools).prompt
                selector_text = backend.complete("selector", selector_prompt)
                row["selector_calls"] = 1
                row["selector_sha256"] = _sha(selector_text.encode("utf-8"))
                before_invoker(expected, selector_text, scene=scene, tools=tools)
                invocation_prompt = render_invocation(backend.tokenizer, current, expected.tool_name, tools)
                invocation_text = backend.invoke(invocation_prompt)
                row["invoker_calls"] = 1
                row["invocation_sha256"] = _sha(invocation_text.encode("utf-8"))
                checked = check_invocation(expected, invocation_text, scene=scene, tools=tools)
            except ExplicitStepError as exc:
                row.update(status="safely_rejected", reason=exc.code)
            except Exception as exc:
                row.update(status="runtime_error", reason=type(exc).__name__)
            else:
                row.update(status="contract_passed", selected_tool=checked.name,
                           externally_bound_target=checked.target_alias is not None)
            row["seconds"] = round(time.monotonic() - began, 2)
    safety_passed = all(
        row["status"] == "preflight_rejected" and row["selector_calls"] == row["invoker_calls"] == 0
        if row["expected_kind"] == "reject"
        else row["status"] in {"contract_passed", "safely_rejected"}
        and row["invoker_calls"] <= row["selector_calls"] <= 1
        for row in rows
    )
    compatibility_passed = all(row["status"] == "contract_passed" for row in rows if row["expected_kind"] == "accept")
    print(json.dumps({
        "contract_id": "qwen25-v5-model-external-target-candidate",
        "contract_sha256": FROZEN_SHA256["training/tool_invocation_v5_candidate.py"],
        "fixture_sha256": FROZEN_SHA256["eval/r4_v5_target_free_new_cases.json"],
        "approved_manifest_sha256": args.operator_approved_sha256,
        "preflight_gate_passed": preflight_passed,
        "safety_gate_passed": safety_passed,
        "model_compatibility_passed": compatibility_passed,
        "no_consent": True, "no_rhino_dispatch": True, "quality_benchmark": False,
        "seconds": round(time.monotonic() - started, 2),
        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "cases": rows,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if safety_passed and compatibility_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
