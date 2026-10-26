"""Narrow new-study read handoff. No writes, output repair or authority creation.

The controller must already reparse the raw model response and authenticate
the actual native scene. Unlike the historical signer, this binds the new
input contract directly instead of substituting an old user-step hash.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import READS, digest, require, validate_native_arguments
from plugin.rhino_listener.c5_research_channel import publish_json
from training.c5_contract import parse_invocation, parse_selection
from training.c5_inventory import load_public_mcp_tools
from training.lora_development_wire import user_step


def issue_read(*, sent, observation, current, secret, schemas, max_reads, used_reads, state, clock=time.time):
    require(observation.get("status") == "schema_valid_not_authorized"
            and observation.get("repair_count") == observation.get("dispatch_count") == 0,
            "strict raw observation required")
    calls = observation["calls"]
    require(len(calls) == 2 and [c["stage"] for c in calls] == ["selector", "invocation"], "two-stage call required")
    tools = load_public_mcp_tools()
    selected = parse_selection(calls[0]["raw"], tools)
    parsed = parse_invocation(calls[1]["raw"], selected, tools)
    require(parsed == {"name": observation["name"], "arguments": observation["arguments"]}
            and all(c["parsed"] is True and c["output_sha256"] == hashlib.sha256(c["raw"].encode()).hexdigest()
                    for c in calls), "raw call differs")
    require(parsed["name"] in READS and type(max_reads) is int and type(used_reads) is int
            and 0 <= used_reads < max_reads <= 2, "read-only task policy denied")
    validate_native_arguments(parsed["name"], parsed["arguments"], schemas)
    from training.c5_modelbridge_joint_audit import semantic
    require(current.get("status") == "captured" and current["state"] == sent["binding"] == observation["scene_binding"]
            and semantic(current["native"]) == sent["scene"]
            and observation["user_step_sha256"] == hashlib.sha256(user_step(sent).encode()).hexdigest(),
            "actual scene or new input contract differs")
    if parsed["name"] == "get_bounding_box":
        require(parsed["arguments"]["object_id"] in {o["alias"] for o in sent["scene"]["objects"]}, "target absent")
    # Sign only after the actual reread and exclusive handoff claim. No expiry
    # is spent waiting for that reread, and failures cannot reissue this step.
    key = digest({"slot": sent["slot_id"], "step": sent["step_index"], "runtime": sent["runtime_sha256"]})
    publish_json(state, key + ".handoff.claim.json", {"request_sha256": digest(sent), "observation_sha256": digest(observation)})
    payload = {"version": 1, "request_id": secrets.token_urlsafe(24),
        "task_sha256": hashlib.sha256(sent["task"].encode()).hexdigest(), "owner_freeze_sha256": sent["runtime_sha256"],
        "expected": sent["binding"], "operation": parsed["name"], "arguments": parsed["arguments"],
        "consent_row_sha256": None, "expires_at": int(clock()) + 120}
    envelope = {"payload": payload, "signature": signature(secret, payload)}
    publish_json(state, key + ".handoff.json", envelope)
    return envelope
