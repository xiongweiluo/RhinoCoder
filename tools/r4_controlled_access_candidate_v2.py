#!/usr/bin/env python3
"""Versioned isolated R runner: interactive opt-in and per-step outbound guard.

The 2026-09-26 runner is sealed by evidence hashes. This fork deliberately
preserves its geometry, consent, and readback behavior while changing only the
entry, privacy, and stop boundaries. It is not the default product route.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time

from agent.privacy import PrivacyAction, classify_request
from tools.r4_controlled_access_optin_v2 import OptInError, OptInLease
from tools.r4_controlled_access_remote_guard_v2 import guarded_remote_result
from tools.r4_v6_live_multistep import (
    LiveRunError, V6Scene, _execute, _geometry_args, _initial,
    _private_publish, _validate_plan_targets,
    load_private_secret, publish_signed_envelope, verify_postwrite,
)
from training.consent_candidate import DELEGATED_HEADLESS_SCOPE, ConsentStore
from training.consent_handoff_v5_candidate import issue_signed_handoff
from training.controlled_v6_plan import PlanError, _SPLIT, clarification_prompt, compile_task
from training.remote_result_v5_candidate import verify_no_dispatch_result
from training.tool_controller_candidate import compose_step_input
from training.tool_schema_inventory import load_public_mcp_tools


def run(args, lease: OptInLease):
    lease.claim(args)
    if getattr(args, "fixture_name", None) != "empty":
        raise OptInError("disposable_empty_fixture_required")
    directory = args.session_dir.resolve()
    bootstrap = _initial(directory)
    scene = V6Scene(directory)
    initial = scene.capture()
    if (initial.state.summary != bootstrap.state.summary
            or initial.state.revision < bootstrap.state.revision or initial.objects):
        raise LiveRunError("unexpected_baseline_change")
    try:
        plan = compile_task(args.task)
    except PlanError as exc:
        return None, {"status": "clarification_required" if clarification_prompt(exc) else "task_rejected",
                      "code": exc.code, "question": clarification_prompt(exc),
                      "model_calls": 0, "rhino_execute_requests": 0}
    action = classify_request(compose_step_input(args.task, initial.state)).action
    if action is not PrivacyAction.ALLOW_CLOUD:
        return None, {"status": "privacy_rejected", "model_calls": 0,
                      "rhino_execute_requests": 0}
    _validate_plan_targets(plan, initial)
    if any(step.operation in {"create_box", "move_object"} for step in plan.steps) and not args.delegated_headless_approval:
        raise LiveRunError("write_approval_scope_required")
    if list(directory.glob("execute-*.json")):
        raise LiveRunError("fixture_not_pristine")
    run_dir = directory / ("v6-plan-" + secrets.token_hex(24))
    os.mkdir(run_dir, 0o700)
    tools = load_public_mcp_tools()
    consent = ConsentStore(run_dir / "review.sqlite3", tools)
    records = []
    created_alias = None
    natural_segments = (_SPLIT.split(args.task.strip()) if plan.source_kind == "bounded_natural_language"
                        else None)
    if natural_segments is not None and len(natural_segments) != len(plan.steps):
        raise LiveRunError("natural_segments_changed")
    started = time.monotonic()
    for index, step in enumerate(plan.steps, 1):
        lease.check(args)
        step_started = time.monotonic()
        before = scene.capture()
        explicit_task = step.explicit_task(created_alias=created_alias)
        model_task = None
        if natural_segments is not None and getattr(args, "formal_model_original_language", False):
            model_task = natural_segments[index - 1].strip()
            if hashlib.sha256(model_task.encode()).hexdigest() != step.source_segment_sha256:
                raise LiveRunError("natural_segment_hash_mismatch")
        step_dir = run_dir / ("step-" + str(index))
        os.mkdir(step_dir, 0o700)
        remote_kwargs = {"task": explicit_task}
        if model_task is not None:
            remote_kwargs["model_task"] = model_task
        lease.check(args)
        remote, hashes, challenge = guarded_remote_result(
            args, directory, before.state, step_dir, **remote_kwargs,
        )
        lease.check(args)
        if scene.capture() != before:
            raise LiveRunError("write_grade_scene_changed")
        checked = verify_no_dispatch_result(
            remote, task=explicit_task, scene=scene, tools=tools,
            challenge=challenge, approved_manifest_sha256=args.approved_manifest_sha256,
        )
        if checked.name != step.operation:
            raise LiveRunError("model_tool_mismatch")
        if scene.capture() != before:
            raise LiveRunError("write_grade_scene_changed")
        record = {
            "index": index, "operation": step.operation,
            "source_segment_sha256": step.source_segment_sha256,
            "explicit_task_sha256": hashlib.sha256(explicit_task.encode()).hexdigest(),
            "before_scene_sha256": before.state.scene_sha256,
            "remote_result_sha256": hashlib.sha256((step_dir / "remote-result.json").read_bytes()).hexdigest(),
            "remote_code_sha256": hashes,
        }
        if step.operation in {"get_scene_summary", "get_selected_objects"}:
            after = scene.capture()
            if after != before:
                raise LiveRunError("read_scene_changed")
            record["tool_result"] = (dict(after.state.summary) if step.operation == "get_scene_summary"
                                     else list(after.selected_aliases))
            record["readback_verified"] = True
        else:
            lease.check(args)
            link = consent.prepare(
                explicit_task, checked.name,
                {**checked.model_arguments, **({"object_id": checked.target_alias}
                                             if checked.target_alias is not None else {})},
                scene=scene, delegated_scope=DELEGATED_HEADLESS_SCOPE, ttl_seconds=300,
            )
            try:
                if consent.approve_delegated_headless(link) != "approved":
                    raise LiveRunError("delegated_approval_rejected")
                envelope = issue_signed_handoff(
                    task=explicit_task, checked=checked, link=link, scene=scene,
                    consent=consent, tools=tools,
                    secret=load_private_secret(directory / "channel"),
                )
                lease.check(args)
                request_id = publish_signed_envelope(directory / "channel", envelope)
                lease.check(args)
                response = _execute(directory, request_id)
                if (not isinstance(response, dict) or response.get("status") != "done"
                        or response.get("ledger_state") != "done"
                        or response.get("operation") != step.operation
                        or response.get("active_document_unchanged") is not True):
                    raise LiveRunError("rhino_execution_not_verified_manual_review")
                after = scene.capture()
                explicit = json.loads(explicit_task)
                geometry_args = _geometry_args(explicit)
                alias = verify_postwrite(step.operation, geometry_args,
                                         before.geometry_view(), after.geometry_view())
                if (response.get("alias") != alias
                        or response.get("before_scene_sha256") != before.state.scene_sha256
                        or response.get("after_scene_sha256") != after.state.scene_sha256
                        or response.get("headless_object_count") != after.state.summary["object_count"]):
                    raise LiveRunError("rhino_readback_mismatch_manual_review")
                events = consent.audit_events(link.request_id)
                if ([item["event_type"] for item in events] != [
                        "requested", "approved", "consumed", "signed_handoff_issued",
                ] or events[1]["reason_code"] != "codex_delegated_headless"):
                    raise LiveRunError("unexpected_consent_audit")
                record.update({
                    "approval_mode": "codex_delegated_headless", "consent_events": [item["event_type"] for item in events],
                    "ledger_state": "done", "alias": alias, "after_scene_sha256": after.state.scene_sha256,
                    "geometry_readback": after.geometry_view(), "readback_verified": True,
                })
                if step.operation == "create_box":
                    created_alias = alias
            finally:
                # Only pending/approved records are revoked; a consumed write
                # stays consumed and must never be retried after uncertainty.
                consent.abort_without_human(link)
        record["elapsed_seconds"] = round(time.monotonic() - step_started, 4)
        records.append(record)
        _private_publish(step_dir, "record.json", record)
    lease.check(args)
    receipt = {
        "status": "controlled_access_candidate_v2_completed_not_formal_quality",
        "source_kind": plan.source_kind, "original_task_sha256": plan.original_task_sha256,
        "steps": records, "step_count": len(records), "elapsed_seconds": round(time.monotonic() - started, 3),
        "approved_manifest_sha256": args.approved_manifest_sha256,
        "host_key_sha256": args.expected_host_key_sha256,
        "operator_opt_in_grant_sha256": hashlib.sha256(
            (lease.control_dir / "grant.json").read_bytes()).hexdigest(),
        "active_document_unchanged": True,
    }
    _private_publish(run_dir, "receipt.json", receipt)
    return run_dir, receipt
