"""New-study wire, native receipt binding and unchanged raw-output reparse.

No socket, process, loader, Rhino API, corpus or grant access. Host signatures
must originate in the separately frozen host entry. Request/response hashes
are bindings, not owner approval. All model routes use the same validation.
"""
from __future__ import annotations

import hashlib
import math

from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_contract import DECODE_CONFIG
from training.c5_formal20_privacy import allowed
from training.c5_modelbridge_joint_audit import semantic
from training.c5_rhino_adapter import invoke_step, step_input
from training.lora_dev_feedback import read_progress, render_progress
from training.lora_development_scope import STUDY, _sha

from plugin.rhino_listener.lora_development_channel import (
    PROTOCOL, detached, host_response, verify_host)


def validate_request(value, model_views, runtime):
    value = detached(value)
    require(type(value) is dict and set(value) == {"protocol", "study_id", "runtime_sha256", "slot_id",
        "route", "system", "step_index", "task", "scene", "binding", "progress", "host_evidence_sha256"},
        "exact model request required")
    require(value["protocol"] == PROTOCOL and value["study_id"] == STUDY
            and value["runtime_sha256"] == _sha(runtime), "new development runtime required")
    plan = model_views.get(value["slot_id"])
    require(plan is not None and all(value[k] == plan[k] for k in ("route", "system", "task"))
            and type(value["step_index"]) is int and 0 <= value["step_index"] < plan["max_steps"],
            "model request outside frozen public plan")
    b = value["binding"]
    require(type(b) is dict and set(b) == {"document_key", "revision", "scene_sha256"}
            and type(b["revision"]) is int and b["revision"] >= 0, "actual scene binding required")
    _sha(b["document_key"]); _sha(b["scene_sha256"]); _sha(value["host_evidence_sha256"])
    # Validate projected facts for both systems; only the candidate renders them.
    render_progress(value["task"], value["scene"], value["progress"])
    require((value["step_index"] == 0) == (value["progress"]["status"] == "no_previous_step"),
            "progress step differs")
    require(allowed(value["task"], value["scene"]), "public task/scene privacy refused")
    return value


def user_step(sent):
    return (step_input(sent["task"], sent["scene"]) if sent["system"] == "original" else
            render_progress(sent["task"], sent["scene"], sent["progress"]))


def request_from_host(*, model_views, runtime, slot, step_index, secret, capture, capture_request,
                      capture_sequence, previous=None):
    """Validate host origin before projecting a minimal model-side input.

    previous contains the immediately previous already-reparsed observation
    and signed host execution exchange, never expected/scorer operations.
    """
    plan = model_views[slot]
    require(capture_request.get("action") == "capture", "actual capture exchange required")
    current = verify_host(capture, secret=secret, runtime=runtime, slot=slot,
                          sequence=capture_sequence, request=capture_request)
    require(current.get("status") == "captured", "host capture not complete")
    scene, binding = semantic(current["native"]), current["state"]
    prior = None
    if step_index:
        require(type(previous) is dict and set(previous) == {"step_index", "observation", "envelope", "request", "sequence"}
                and previous["step_index"] == step_index - 1 and previous["sequence"] < capture_sequence
                and previous["request"].get("action") == "execute", "immediate prior execution exchange required")
        receipt = verify_host(previous["envelope"], secret=secret, runtime=runtime, slot=slot,
                              sequence=previous["sequence"], request=previous["request"])
        require(previous["request"].get("envelope", {}).get("payload") == receipt.get("payload"),
                "host executed another payload")
        p = receipt["payload"]
        require(p.get("owner_freeze_sha256") == runtime
                and p.get("task_sha256") == hashlib.sha256(plan["task"].encode()).hexdigest(),
                "previous native task/runtime differs")
        require(receipt.get("result_sha256") == digest(receipt.get("result")), "native result hash differs")
        prior = {"step_index": previous["step_index"], "policy_denied": False,
                 "observation": previous["observation"], "receipt": receipt}
    else:
        require(previous is None, "first step cannot contain predecessor")
    facts = read_progress(scene, step_index=step_index, previous_step=prior, current_binding=binding)
    value = {"protocol": PROTOCOL, "study_id": STUDY, "runtime_sha256": runtime, "slot_id": slot,
        "route": plan["route"], "system": plan["system"], "step_index": step_index, "task": plan["task"],
        "scene": scene, "binding": binding, "progress": facts,
        "host_evidence_sha256": digest({"capture": capture, "previous": previous})}
    return validate_request(value, model_views, runtime)


def check_predecessor(sent, previous_request, previous_observation):
    """Worker verifies progress agrees with its own preceding model output."""
    if sent["step_index"] == 0:
        require(previous_request is None and previous_observation is None, "unexpected worker predecessor")
        return
    require(type(previous_request) is dict and type(previous_observation) is dict
            and previous_request["step_index"] + 1 == sent["step_index"]
            and all(previous_request[k] == sent[k] for k in
                    ("slot_id", "route", "system", "task", "scene", "binding", "runtime_sha256"))
            and previous_observation["status"] == "schema_valid_not_authorized", "worker predecessor differs")
    args = previous_observation["arguments"]
    require(sent["progress"] == {"status": "done", "operation": previous_observation["name"],
            "target_alias": args.get("object_id")}, "progress does not match previous model operation")


def model_response(sent, observation, generations, identity):
    return detached({"protocol": PROTOCOL, "request_sha256": digest(sent), "model_identity_sha256": _sha(identity),
                     "observation": observation, "generations": generations})


def reparse_response(value, sent, *, model_views, runtime, identity, tokenizer):
    sent = validate_request(sent, model_views, runtime)
    value = detached(value)
    require(set(value) == {"protocol", "request_sha256", "model_identity_sha256", "observation", "generations"}
            and value["protocol"] == PROTOCOL and value["request_sha256"] == digest(sent)
            and value["model_identity_sha256"] == _sha(identity), "response model/request differs")
    rows = value["generations"]
    require(type(rows) is list and 1 <= len(rows) <= 2, "one-shot generation population required")
    cursor = 0
    def replay(prompt, stage):
        nonlocal cursor
        require(cursor < len(rows), "missing raw generation")
        row = rows[cursor]; cursor += 1
        require(type(row) is dict and set(row) == {"stage", "raw", "tokens", "seconds", "prompt_sha256", "output_sha256"}
                and row["stage"] == stage and type(row["raw"]) is str
                and type(row["tokens"]) is int and 0 <= row["tokens"] <= DECODE_CONFIG[stage + "_max_new_tokens"]
                and type(row["seconds"]) in (int, float) and math.isfinite(row["seconds"]) and row["seconds"] >= 0
                and row["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
                and row["output_sha256"] == hashlib.sha256(row["raw"].encode()).hexdigest(), "raw generation receipt differs")
        return row
    rendered = user_step(sent)
    observed = invoke_step(tokenizer, replay, rendered, scene_binding=sent["binding"],
                           privacy_guard=lambda text: text == rendered and allowed(sent["task"], sent["scene"]))
    require(cursor == len(rows) and digest(observed) == digest(value["observation"])
            and observed["status"] != "operational_failure_no_retry", "unchanged raw output reparse failed")
    return observed
