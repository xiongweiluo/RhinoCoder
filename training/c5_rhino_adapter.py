"""C5-only strict live-step adapter, with no executor, loader or oracle labels.

Uses the original frozen 23-tool selector/full single-tool schema unchanged.
The trusted caller supplies actual alias-only readback and one-shot generation;
formal tasks/expected arguments never enter this API. No retry or output repair.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

from agent.privacy import PrivacyAction, classify_request
from training.c5_contract import (CONTRACT_ID, CORE_INVOCATION_TOOLS,
    parse_invocation, parse_selection, render_invocation, render_selection)
from training.c5_inventory import load_public_mcp_tools
from training.tool_contract_candidate import ContractError

GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def step_input(task, scene):
    """Normalize only real semantic state; omit physical IDs/revision/watermarks.

    Equivalent fresh base/LoRA fixtures consequently render the same initial
    input. Subsequent states must come from their own actual readbacks, not
    the scorer or a scripted expected next state.
    """
    if not isinstance(task, str) or not task.strip() or GUID.search(task):
        raise ContractError("nonempty GUID-free task required")
    if not isinstance(scene, dict) or set(scene) != {"unit", "objects", "groups"} or scene["unit"] != "Millimeters":
        raise ContractError("alias-only semantic scene required")
    objects = scene["objects"]
    if not isinstance(objects, list) or len(objects) > 16:
        raise ContractError("scene object budget exceeded")
    names = set()
    normalized = []
    for obj in objects:
        if not isinstance(obj, dict) or set(obj) != {"alias", "min", "max", "layer", "color", "groups"}:
            raise ContractError("unexpected semantic object field")
        alias = obj["alias"]
        if not isinstance(alias, str) or not 1 <= len(alias) <= 80 or alias in names or GUID.search(alias):
            raise ContractError("invalid/duplicate physical alias")
        names.add(alias)
        for key in ("min", "max"):
            v = obj[key]
            if not isinstance(v, list) or len(v) != 3 or not all(type(n) in (int, float) and math.isfinite(n) for n in v):
                raise ContractError("invalid semantic bounds")
        if any(a > b for a, b in zip(obj["min"], obj["max"])):
            raise ContractError("inverted semantic bounds")
        if not isinstance(obj["layer"], str) or not isinstance(obj["color"], list) or len(obj["color"]) != 3 or not all(
            type(n) is int and 0 <= n <= 255 for n in obj["color"]):
            raise ContractError("invalid semantic attributes")
        if not isinstance(obj["groups"], list) or any(not isinstance(s, str) for s in obj["groups"]) or len(set(obj["groups"])) != len(obj["groups"]):
            raise ContractError("invalid semantic groups")
        normalized.append({**obj, "groups": sorted(obj["groups"])})
    groups = scene["groups"]
    if not isinstance(groups, dict) or any(not isinstance(k, str) or not isinstance(v, list)
        or any(not isinstance(a, str) for a in v) or len(v) != len(set(v))
        or any(a not in names for a in v) for k, v in groups.items()):
        raise ContractError("invalid group membership")
    expected_groups = {k: sorted(o["alias"] for o in normalized if k in o["groups"]) for k in groups}
    if expected_groups != {k: sorted(v) for k, v in groups.items()} or any(g not in groups for o in normalized for g in o["groups"]):
        raise ContractError("object/group membership differs")
    value = {"unit": "Millimeters", "objects": sorted(normalized, key=lambda o: o["alias"]),
             "groups": {k: sorted(v) for k, v in groups.items()}}
    rendered = task.strip()+"\n当前只读安全场景（object_id 使用真实读回的唯一别名，不传物理 GUID）："+_json(value)
    if GUID.search(rendered):
        raise ContractError("physical ID in outbound scene")
    return rendered


def invoke_step(tokenizer, generate, user_step, *, scene_binding=None, privacy_guard=None):
    """Exactly one selector and, only if legal, one invocation generation.

    Returns the raw outputs for private research evidence. Does not grant
    consent, resolve GUIDs or dispatch. Operational errors are not retried.
    """
    if not isinstance(user_step,str):
        raise ContractError("string user step required")
    if scene_binding is not None:
        if (not isinstance(scene_binding,dict) or set(scene_binding)!={"document_key","revision","scene_sha256"}
            or type(scene_binding["revision"]) is not int or scene_binding["revision"] < 0
            or any(not isinstance(scene_binding[k],str) or re.fullmatch(r"[0-9a-f]{64}",scene_binding[k]) is None
                   for k in ("document_key","scene_sha256"))):
            raise ContractError("trusted pre-generation scene binding required")
        scene_binding = json.loads(_json(scene_binding))
    result = {"contract_id": CONTRACT_ID, "status": "not_started", "calls": [],
              "user_step_sha256":hashlib.sha256(user_step.encode()).hexdigest(), "scene_binding":scene_binding,
              "name": None, "arguments": None, "repair_count": 0, "dispatch_count": 0}
    if (classify_request(user_step).action is not PrivacyAction.ALLOW_CLOUD
            if privacy_guard is None else not privacy_guard(user_step)):
        return {**result, "status": "privacy_refused_no_generation"}
    tools = load_public_mcp_tools()
    selected = None
    for stage in ("selector", "invocation"):
        try:
            prompt = (render_selection(tokenizer, user_step, tools) if stage == "selector"
                      else render_invocation(tokenizer, user_step, tools, selected)).prompt
            # A receipt is entered before calling a potentially interruptible
            # generator; a trusted durable caller must likewise claim first.
            receipt = {"stage": stage, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                       "generation_attempted": True, "parsed": False}
            result["calls"].append(receipt)
            generated = generate(prompt, stage)
            if not isinstance(generated, dict) or not isinstance(generated.get("raw"), str):
                raise RuntimeError("generator missing raw output")
            receipt["raw"] = generated["raw"]
            receipt["output_sha256"] = hashlib.sha256(generated["raw"].encode()).hexdigest()
            for key in ("prompt_sha256", "output_sha256"):
                if key in generated and generated[key] != receipt[key]:
                    raise RuntimeError("generation receipt hash differs")
            if stage == "selector":
                selected = parse_selection(generated["raw"], tools)
                receipt["parsed"] = True
                if selected is None:
                    return {**result, "status": "abstained_no_dispatch"}
                if selected not in CORE_INVOCATION_TOOLS:
                    return {**result, "status": "unsupported_for_c5_no_dispatch", "name": selected}
            else:
                parsed = parse_invocation(generated["raw"], selected, tools)
                receipt["parsed"] = True
                return {**result, "status": "schema_valid_not_authorized", **parsed}
        except ContractError:
            return {**result, "status": stage+"_contract_failure_no_dispatch"}
        except Exception as exc:
            return {**result, "status": "operational_failure_no_retry", "error_type": type(exc).__name__}
    raise AssertionError("invalid adapter state")
