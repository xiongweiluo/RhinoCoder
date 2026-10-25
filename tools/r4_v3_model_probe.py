#!/usr/bin/env python3
"""Frozen, no-dispatch v3 model contract probe on new synthetic tasks.

This is not a quality benchmark and cannot contact Rhino or issue consent.
All model input is in the committed fixture, with no A5/P2 task access.
"""

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

from training.tool_contract_candidate import (  # noqa: E402
    ContractError, validate_arguments, validate_inventory,
)
from training.tool_contract_v3_candidate import parse_invocation, render_invocation  # noqa: E402
from training.tool_controller_candidate import SceneState, compose_step_input  # noqa: E402
from training.tool_local_gate_candidate import (  # noqa: E402
    LocalSelectionGate, OfflineTransformersBackend, VerifiedSnapshot,
)


FIXTURE_SHA256 = "3479349a8973dc17386e5a4bc5084d0c27b8bd546a0bc532ce9efa764adf7600"
CONTRACT_SHA256 = "0905b85baf00d4416d7e7a2ae3074035a0d2294fa2f845ee77bc3504d9eb3051"
TOOL_SCHEMA_SHA256 = "151c5453bf92f83343e93e53013bfc8f3518e5b6a7e9e2fc49e97ba863b0637d"
PUBLIC_TOOLS_FILE_SHA256 = "3938b46835c7ae1ea20a3cc0e3b6dad0d175a5245ddf230b6da0363157cf57d1"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_frozen_tools(path: Path) -> list[dict]:
    if _sha_bytes(path.read_bytes()) != PUBLIC_TOOLS_FILE_SHA256:
        raise ValueError("public_tool_file_changed_after_preregistration")
    tools = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(tools, list) or len(tools) != 23 or len(validate_inventory(tools)) != 23:
        raise ValueError("invalid_public_tool_inventory")
    canonical_digest = _sha_bytes(json.dumps(
        tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))
    if canonical_digest != TOOL_SCHEMA_SHA256:
        raise ValueError("public_tool_schema_changed")
    return tools


def load_frozen_fixture(path: Path, tools: list[dict]) -> dict:
    if _sha_bytes(path.read_bytes()) != FIXTURE_SHA256:
        raise ValueError("fixture_changed_after_preregistration")
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("fixture_id") != "r4-v3-contract-safety-new-20260921":
        raise ValueError("wrong_fixture_id")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != 10:
        raise ValueError("wrong_case_count")
    inventory = {tool["function"]["name"]: tool for tool in tools}
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "id", "task", "expected_tool", "expected_arguments",
        } or case["id"] in seen or not isinstance(case["task"], str) or not case["task"].strip():
            raise ValueError("invalid_case")
        seen.add(case["id"])
        name = case["expected_tool"]
        if name is None:
            if case["expected_arguments"] is not None:
                raise ValueError("abstention_has_arguments")
        elif name not in inventory:
            raise ValueError("unknown_expected_tool")
        else:
            validate_arguments(name, case["expected_arguments"], inventory[name])
    return fixture


class FrozenScene:
    def __init__(self, summary: dict) -> None:
        digest = _sha_bytes(json.dumps(
            summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8"))
        self.state = SceneState(0, digest, summary)

    def snapshot(self) -> SceneState:
        return self.state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--operator-approved-sha256", required=True)
    parser.add_argument("--fixture", type=Path, default=ROOT / "eval/r4_v3_new_cases.json")
    args = parser.parse_args()

    if _sha_bytes((ROOT / "training/tool_contract_v3_candidate.py").read_bytes()) != CONTRACT_SHA256:
        raise ValueError("contract_changed_after_preregistration")
    tools = load_frozen_tools(ROOT / "eval/r4_v3_public_tools.json")
    fixture = load_frozen_fixture(args.fixture, tools)
    manifest_payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest_payload, dict) or set(manifest_payload) != {
        "approved_root", "snapshot_dir", "file_sha256",
    } or not isinstance(manifest_payload["file_sha256"], dict):
        raise ValueError("invalid_snapshot_manifest")
    snapshot = VerifiedSnapshot(
        Path(manifest_payload["approved_root"]), Path(manifest_payload["snapshot_dir"]),
        manifest_payload["file_sha256"],
    )
    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_required_for_frozen_model_probe")
    started = time.monotonic()
    backend = OfflineTransformersBackend.load(
        snapshot, operator_approved_sha256=args.operator_approved_sha256,
    )
    scene = FrozenScene(fixture["scene_summary"])
    gate = LocalSelectionGate(tools)
    outcomes = []
    with torch.inference_mode():
        for case in fixture["cases"]:
            case_started = time.monotonic()
            choice = gate.probe(case["task"], scene=scene, backend=backend)
            row = {
                "id": case["id"], "selection_status": choice.status,
                "selected_tool": choice.selected_tool,
                "selection_expected": (
                    choice.status == "needs_clarification" if case["expected_tool"] is None
                    else choice.status == "selection_observed" and choice.selected_tool == case["expected_tool"]
                ),
            }
            if row["selection_expected"] and case["expected_tool"] is not None:
                raw = None
                try:
                    prompt = render_invocation(
                        backend.tokenizer,
                        compose_step_input(case["task"], scene.snapshot()),
                        tools, case["expected_tool"],
                    ).prompt
                    raw = backend.invoke(prompt)
                    call = parse_invocation(raw, case["expected_tool"], tools)
                except (ContractError, TypeError, AttributeError):
                    row["invocation_status"] = "strict_parse_rejected"
                    if isinstance(raw, str):
                        row["raw_sha256"] = _sha_bytes(raw.encode("utf-8"))
                except Exception:
                    row["invocation_status"] = "model_or_runtime_unavailable"
                else:
                    row["invocation_status"] = "strict_parse_passed"
                    row["arguments_expected"] = call["arguments"] == case["expected_arguments"]
                    row["arguments_sha256"] = _sha_bytes(json.dumps(
                        call["arguments"], ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False,
                    ).encode("utf-8"))
            row["seconds"] = round(time.monotonic() - case_started, 2)
            outcomes.append(row)
    valid = [row for row, case in zip(outcomes, fixture["cases"]) if case["expected_tool"] is not None]
    ambiguous = [row for row, case in zip(outcomes, fixture["cases"]) if case["expected_tool"] is None]
    passed = (
        all(row["selection_expected"] and row.get("invocation_status") == "strict_parse_passed"
            and row.get("arguments_expected") for row in valid)
        and all(row["selection_expected"] for row in ambiguous)
    )
    print(json.dumps({
        "fixture_id": fixture["fixture_id"], "fixture_sha256": FIXTURE_SHA256,
        "contract_sha256": CONTRACT_SHA256, "tool_schema_sha256": TOOL_SCHEMA_SHA256,
        "approved_manifest_sha256": args.operator_approved_sha256,
        "case_count": len(outcomes), "valid_case_count": len(valid),
        "ambiguous_case_count": len(ambiguous),
        "contract_compatibility_passed": passed,
        "no_dispatch": True, "quality_benchmark": False,
        "total_seconds": round(time.monotonic() - started, 2),
        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "cases": outcomes,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
