#!/usr/bin/env python3
"""Opt-in v6 real-model multi-step probe in one unsaved headless Rhino document.

All steps compile before any model/consent/write. Every step gets a fresh Rhino
UI-thread scene, authenticated approved-model result, and Mac-side recheck.
Each write gets its own scoped delegated consent, signed handoff, durable Rhino
reservation, and geometry readback. Any uncertainty stops without retry.
This is a development probe, not the formal 60-task quality evaluator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.privacy import PrivacyAction, classify_request  # noqa: E402
from plugin.rhino_listener.candidate_file_channel import load_private_secret, publish_signed_envelope  # noqa: E402
from plugin.rhino_listener.candidate_v6_live_session import verify_postwrite  # noqa: E402
from tools.r4_v5_live_human_write import LiveRunError, _remote_result, _wait_private  # noqa: E402
from tools.r4_v5_one_step_remote_probe import GivenScene  # noqa: E402
from tools.r4_v5_ssh_no_write_session import _private_publish, _private_read  # noqa: E402
from training.consent_candidate import DELEGATED_HEADLESS_SCOPE, ConsentStore  # noqa: E402
from training.consent_handoff_v5_candidate import issue_signed_handoff  # noqa: E402
from training.controlled_v6_plan import PlanError, _SPLIT, clarification_prompt, compile_task  # noqa: E402
from training.remote_result_v5_candidate import verify_no_dispatch_result  # noqa: E402
from training.tool_controller_candidate import SceneState, compose_step_input  # noqa: E402
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402


_HEX = set("0123456789abcdef")


@dataclass(frozen=True)
class Capture:
    state: SceneState
    objects: tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]
    selected_aliases: tuple[str, ...]

    def geometry_view(self):
        return {"objects": [{"alias": alias, "min": list(low), "max": list(high)}
                            for alias, low, high in self.objects]}


def _capture_value(value):
    if not isinstance(value, dict) or set(value) != {
        "revision", "scene_sha256", "summary", "objects", "selected_aliases",
    }:
        raise LiveRunError("invalid_v6_capture")
    state = GivenScene({key: value[key] for key in ("revision", "scene_sha256", "summary")}).snapshot()
    rows = value["objects"]
    selected = value["selected_aliases"]
    if not isinstance(rows, list) or len(rows) > 256 or not isinstance(selected, list):
        raise LiveRunError("invalid_v6_capture")
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"alias", "min", "max"}:
            raise LiveRunError("invalid_v6_capture")
        alias, lo, hi = row["alias"], row["min"], row["max"]
        if (not isinstance(alias, str) or alias not in state.summary["aliases"]
                or not isinstance(lo, list) or not isinstance(hi, list)
                or len(lo) != 3 or len(hi) != 3
                or not all(type(x) in (int, float) and math.isfinite(x) for x in (*lo, *hi))
                or any(a > b for a, b in zip(lo, hi))):
            raise LiveRunError("invalid_v6_capture")
        normalized.append((alias, tuple(float(x) for x in lo), tuple(float(x) for x in hi)))
    aliases = [row[0] for row in normalized]
    if (len(set(aliases)) != len(aliases) or sorted(aliases) != sorted(state.summary["aliases"])
            or len(rows) != state.summary["object_count"]
            or not all(isinstance(alias, str) and alias in aliases for alias in selected)
            or len(set(selected)) != len(selected)):
        raise LiveRunError("invalid_v6_capture")
    return Capture(state, tuple(sorted(normalized)), tuple(sorted(selected)))


class V6Scene:
    def __init__(self, directory):
        self.directory = Path(directory)

    def capture(self):
        nonce = secrets.token_hex(32)
        _private_publish(self.directory, "capture-" + nonce + ".json", {
            "version": 1, "nonce": nonce,
        })
        result = _wait_private(self.directory / ("capture-response-" + nonce + ".json"),
                               self.directory, 20)
        if (not isinstance(result, dict) or set(result) != {"version", "nonce", "scene"}
                or type(result["version"]) is not int or result["version"] != 1
                or result["nonce"] != nonce):
            raise LiveRunError("invalid_v6_capture_response")
        return _capture_value(result["scene"])

    def snapshot(self):
        return self.capture().state


def _initial(directory):
    value = _private_read(directory / "initial.json")
    if (not isinstance(value, dict) or set(value) != {
            "version", "fixture", "scene", "active_document_content_sha256",
    } or value["version"] != 1 or type(value["version"]) is not int
            or value["fixture"] != "empty_headless_mm"
            or not isinstance(value["active_document_content_sha256"], str)
            or len(value["active_document_content_sha256"]) != 64
            or not set(value["active_document_content_sha256"]) <= _HEX):
        raise LiveRunError("invalid_v6_initial")
    capture = _capture_value(value["scene"])
    if (capture.state.summary["object_count"] != 0 or capture.objects
            or capture.state.summary["unit"] != "Millimeters"):
        raise LiveRunError("unexpected_v6_fixture")
    return capture


def _validate_plan_targets(plan, initial):
    aliases = set(initial.state.summary["aliases"])
    next_count = initial.state.summary["object_count"]
    latest = None
    for step in plan.steps:
        if step.operation == "create_box":
            next_count += 1
            latest = "box-" + str(next_count)
            if latest in aliases:
                raise LiveRunError("predicted_alias_conflict")
            aliases.add(latest)
        elif step.operation == "move_object":
            arguments = dict(step.arguments)
            alias = latest if step.target_ref == "last_created" else arguments.get("alias")
            if alias not in aliases:
                raise LiveRunError("target_unavailable_before_write")


def _execute(directory, request_id):
    nonce = secrets.token_hex(32)
    _private_publish(directory, "execute-" + nonce + ".json", {
        "version": 1, "nonce": nonce, "request_id": request_id,
    })
    return _wait_private(directory / ("execute-response-" + nonce + ".json"), directory, 30)


def _geometry_args(explicit):
    if explicit["op"] == "move_object":
        return {"alias": explicit["alias"], "translate_x": explicit["dx"],
                "translate_y": explicit["dy"], "translate_z": explicit["dz"]}
    return {axis: explicit[axis] for axis in ("width", "depth", "height")}


def _inject_formal_scene_drift(directory, case_id, expected_write_attempts):
    if (not isinstance(case_id, str)
            or (not case_id.startswith(("R6-E", "R7-E", "R8-E"))
                and case_id != "DEV8-DRIFT"
                and case_id != "DEV9-DRIFT"
                and case_id not in {"RCA-OLD-E10", "RCA-NEW-DRIFT"}
                and re.fullmatch(r"DEV8-DRIFT-[A-Z]", case_id) is None)):
        raise LiveRunError("formal_drift_case_invalid")
    nonce = secrets.token_hex(32)
    _private_publish(directory, "formal-drift-request-" + nonce + ".json", {
        "version": 1, "case_id": case_id, "nonce": nonce,
        "expected_write_attempts": expected_write_attempts,
    })
    response = _wait_private(directory / ("formal-drift-response-" + nonce + ".json"),
                             directory, 20)
    if (not isinstance(response, dict) or response.get("version") != 1
            or response.get("nonce") != nonce or response.get("case_id") != case_id
            or response.get("active_document_unchanged") is not True):
        raise LiveRunError("formal_drift_response_invalid")


def run(args):
    directory = args.session_dir.resolve()
    bootstrap = _initial(directory)
    scene = V6Scene(directory)
    initial = scene.capture()
    fixture_name = getattr(args, "fixture_name", "empty")
    if fixture_name == "empty":
        if (initial.state.summary != bootstrap.state.summary
                or initial.state.revision < bootstrap.state.revision or initial.objects):
            raise LiveRunError("unexpected_baseline_change")
    else:
        fixture_path = Path(getattr(args, "fixture_path", ROOT / "eval/r4_v6_formal_fixtures.json"))
        fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))["fixtures"]
        expected = fixtures.get(fixture_name)
        if (expected is None or initial.state.revision <= bootstrap.state.revision
                or initial.state.summary["unit"] != "Millimeters"
                or initial.state.summary["object_count"] != len(expected["objects"])
                or initial.geometry_view()["objects"] != expected["objects"]
                or list(initial.selected_aliases) != expected["selected_aliases"]
                or not (directory / "formal-seed-receipt.json").is_file()):
            raise LiveRunError("unexpected_seeded_baseline")
    try:
        plan = compile_task(args.task)
    except PlanError as exc:
        return None, {"status": "clarification_required" if clarification_prompt(exc) else "task_rejected",
                      "code": exc.code, "question": clarification_prompt(exc),
                      "model_calls": 0, "rhino_execute_requests": 0}
    action = classify_request(compose_step_input(args.task, initial.state)).action
    if action not in {PrivacyAction.ALLOW_CLOUD, PrivacyAction.MINIMIZE_CLOUD, PrivacyAction.FORCE_LOCAL}:
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
        remote, hashes, challenge = _remote_result(
            args, directory, before.state, step_dir, **remote_kwargs,
        )
        if getattr(args, "formal_drift_step", None) == index:
            _inject_formal_scene_drift(directory, args.formal_case_id,
                                       sum(item["operation"] in {"create_box", "move_object"}
                                           for item in records))
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
                request_id = publish_signed_envelope(directory / "channel", envelope)
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
    receipt = {
        "status": "v6_development_plan_completed_not_formal_quality",
        "source_kind": plan.source_kind, "original_task_sha256": plan.original_task_sha256,
        "steps": records, "step_count": len(records), "elapsed_seconds": round(time.monotonic() - started, 3),
        "approved_manifest_sha256": args.approved_manifest_sha256,
        "host_key_sha256": args.expected_host_key_sha256,
        "active_document_unchanged": True,
    }
    _private_publish(run_dir, "receipt.json", receipt)
    return run_dir, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--expected-host-key-sha256", required=True)
    parser.add_argument("--approved-manifest-sha256", required=True)
    parser.add_argument("--control-socket", type=Path, required=True)
    parser.add_argument("--delegated-headless-approval", action="store_true")
    parser.add_argument("--fixture-name", default="empty",
                        choices=("empty", "seeded_one", "seeded_selected", "seeded_two",
                                 "read_two_shifted", "read_two_selected", "read_three",
                                 "read_one_shifted_selected", "read_four",
                                 "read_one_unselected_offset"))
    args = parser.parse_args()
    try:
        run_dir, receipt = run(args)
    except LiveRunError as exc:
        print("R4_V6_LIVE_STOPPED " + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2) from None
    print("R4_V6_LIVE_RESULT " + json.dumps(
        {"run_dir": None if run_dir is None else str(run_dir), **receipt},
        ensure_ascii=False, sort_keys=True,
    ), flush=True)


if __name__ == "__main__":
    main()
