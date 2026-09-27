#!/usr/bin/env python3
"""One approved-model v5 result for authenticated SSH stdout; no consent/dispatch."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

from tools.r4_v3_model_probe import load_frozen_tools  # noqa: E402
from tools.r4_v5_target_free_probe import _freeze_check  # noqa: E402
from training.explicit_step_gate_candidate import before_invoker, preflight  # noqa: E402
from training.remote_result_v5_candidate import build_no_dispatch_result  # noqa: E402
from training.tool_controller_candidate import SceneState, compose_step_input  # noqa: E402
from training.tool_invocation_v5_candidate import render_invocation  # noqa: E402
from training.tool_local_gate_candidate import OfflineTransformersBackend, VerifiedSnapshot  # noqa: E402
from training.tool_selector_v4_candidate import render_selection  # noqa: E402
from training.tool_selector_v8_candidate import render_selection_v8  # noqa: E402


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


class GivenScene:
    def __init__(self, value):
        if not isinstance(value, dict) or set(value) != {"revision", "scene_sha256", "summary"}:
            raise ValueError("invalid_scene")
        summary = value["summary"]
        if not isinstance(summary, dict) or set(summary) != {"aliases", "object_count", "unit", "document_key"}:
            raise ValueError("invalid_scene_summary")
        aliases = summary["aliases"]
        if (not isinstance(aliases, list) or len(aliases) > 256
                or not all(isinstance(a, str) and _ALIAS.fullmatch(a) for a in aliases)
                or type(summary["object_count"]) is not int or not 0 <= summary["object_count"] <= 100000
                or summary["object_count"] < len(aliases)
                or not isinstance(summary["unit"], str) or not 1 <= len(summary["unit"]) <= 64
                or not isinstance(summary["document_key"], str)
                or not _HEX.fullmatch(summary["document_key"])
                or type(value["revision"]) is not int or value["revision"] < 0
                or not isinstance(value["scene_sha256"], str)
                or not _HEX.fullmatch(value["scene_sha256"])):
            raise ValueError("invalid_scene_values")
        self.state = SceneState(value["revision"], value["scene_sha256"], summary)

    def snapshot(self):
        return self.state


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--operator-approved-sha256", required=True)
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--emit-resource-metrics", action="store_true")
    parser.add_argument("--selector-json-prefix", action="store_true")
    parser.add_argument("--v8-selector-prompt", action="store_true")
    args = parser.parse_args()
    if len(args.input_json) > 10000:
        raise ValueError("input_too_large")
    request = json.loads(args.input_json, object_pairs_hook=_unique_pairs)
    if (not isinstance(request, dict) or
            set(request) not in ({"task", "scene", "challenge"},
                                 {"task", "scene", "challenge", "model_task"})):
        raise ValueError("invalid_request")
    task, scene = request["task"], GivenScene(request["scene"])
    model_task = request.get("model_task", task)
    if not isinstance(model_task, str) or not 0 < len(model_task) <= 4096:
        raise ValueError("invalid_model_task")
    if not isinstance(request["challenge"], str) or not _HEX.fullmatch(request["challenge"]):
        raise ValueError("invalid_challenge")
    _freeze_check()
    tools = load_frozen_tools(ROOT / "eval/r4_v3_public_tools.json")
    expected = preflight(task, scene=scene, tools=tools)
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"approved_root", "snapshot_dir", "file_sha256"}:
        raise ValueError("invalid_snapshot_manifest")
    manifest = VerifiedSnapshot(Path(payload["approved_root"]), Path(payload["snapshot_dir"]), payload["file_sha256"])

    import torch  # noqa: PLC0415

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_required")
    loaded_at = time.monotonic()
    backend = OfflineTransformersBackend.load(manifest, operator_approved_sha256=args.operator_approved_sha256)
    load_seconds = time.monotonic() - loaded_at
    load_peak_allocated = int(torch.cuda.max_memory_allocated())
    load_peak_reserved = int(torch.cuda.max_memory_reserved())
    torch.cuda.reset_peak_memory_stats()
    inference_at = time.monotonic()
    with torch.inference_mode():
        current = compose_step_input(model_task, scene.snapshot())
        selector_prompt = (render_selection_v8 if args.v8_selector_prompt else render_selection)(
            backend.tokenizer, current, tools).prompt
        if args.selector_json_prefix:
            # The prefix is part of the generated assistant message, not a
            # post-hoc repair. The strict parser still checks the entire JSON.
            selector = "{" + backend.complete("selector", selector_prompt + "{")
        else:
            selector = backend.complete("selector", selector_prompt)
        before_invoker(expected, selector, scene=scene, tools=tools)
        invocation = backend.invoke(render_invocation(backend.tokenizer, current, expected.tool_name, tools))
    if args.emit_resource_metrics:
        import resource  # noqa: PLC0415

        print("R4_V6_RESOURCE_METRICS " + json.dumps({
            "model_load_seconds": round(load_seconds, 4),
            "inference_seconds": round(time.monotonic() - inference_at, 4),
            "cuda_peak_allocated_bytes": max(load_peak_allocated, int(torch.cuda.max_memory_allocated())),
            "cuda_peak_reserved_bytes": max(load_peak_reserved, int(torch.cuda.max_memory_reserved())),
            "remote_peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        }, sort_keys=True, separators=(",", ":")), file=sys.stderr, flush=True)
    result = build_no_dispatch_result(
        task=task, scene=scene, tools=tools, challenge=request["challenge"],
        approved_manifest_sha256=args.operator_approved_sha256,
        selection_text=selector, invocation_text=invocation,
    )
    print("R4_V5_REMOTE_RESULT " + json.dumps(result, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")))


if __name__ == "__main__":
    main()
