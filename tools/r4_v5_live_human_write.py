#!/usr/bin/env python3
"""One explicit SSH/model → scoped approval → disposable Rhino write.

Run only with a fresh Rhino live Idle session. SSH asks the operator for its
password on the terminal; this program never receives, stores, or logs it.
The human review page is local-only and optional only when the operator has
explicitly delegated this isolated headless scope to Codex. Both paths use
one signed handoff and one Rhino execution attempt, with no automatic retry.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.rhino_listener.candidate_file_channel import load_private_secret, publish_signed_envelope  # noqa: E402
from tools.r4_v5_one_step_remote_probe import GivenScene  # noqa: E402
from tools.r4_v5_ssh_no_write_session import (  # noqa: E402
    _REMOTE_MANIFEST, _REMOTE_PYTHON, _REMOTE_ROOT, _SOURCE_FILES,
    _pinned_host_key, _private_publish, _private_publish_bytes, _private_read, _ssh_output,
)
from training.consent_candidate import (  # noqa: E402
    DELEGATED_HEADLESS_SCOPE, ConsentStore, start_local_consent_ui,
)
from training.consent_handoff_v5_candidate import issue_signed_handoff  # noqa: E402
from training.remote_result_v5_candidate import verify_no_dispatch_result  # noqa: E402
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TASK = '{"op":"create_box","width":13,"depth":17,"height":19}'
_SAFE_REMOTE_CODES = {
    "duplicate_key", "non_finite_number", "missing_or_invalid_parameter",
    "out_of_range_parameter", "untrusted_or_oversized_command", "invalid_json_command",
    "invalid_command_shape", "unsupported_command", "missing_or_extra_parameter",
    "invalid_target_alias", "target_not_unique", "scene_unavailable", "scene_changed",
    "privacy_rejected", "tool_unavailable", "preflight_rejected",
    "invalid_selection_output", "selection_mismatch", "invalid_invocation_output",
    "argument_mismatch", "invalid_challenge", "invalid_manifest_digest",
    "invalid_model_text", "invalid_result_shape", "invalid_result_status",
    "challenge_mismatch", "manifest_mismatch", "binding_mismatch",
    "invalid_request",
}
_SAFE_REMOTE_EXCEPTION_CLASSES = {
    "ContractError", "ExplicitStepError", "LocalGateError", "RemoteResultError",
    "ValueError", "RuntimeError", "KeyError", "TypeError", "AssertionError",
    "FileNotFoundError", "OSError", "OutOfMemoryError",
}
_SAFE_REMOTE_PHASES = (
    ("_freeze_check", "remote_source_freeze"),
    ("preflight", "remote_preflight"),
    ("VerifiedSnapshot", "snapshot_verification"),
    ("OfflineTransformersBackend.load", "model_load"),
    ("render_selection", "selector_prompt"),
    ("backend.complete", "selector_inference"),
    ("before_invoker", "selector_gate"),
    ("render_invocation", "invoker_prompt"),
    ("backend.invoke", "invoker_inference"),
    ("build_no_dispatch_result", "remote_result_contract"),
)


class LiveRunError(RuntimeError):
    pass


def _record_remote_failure(run_dir, *, returncode, stdout, stderr, timed_out=False):
    """Persist bounded diagnostics without retaining remote stderr or task text."""

    output = stdout if isinstance(stdout, bytes) else (stdout or "").encode("utf-8", "replace")
    error = stderr if isinstance(stderr, bytes) else (stderr or "").encode("utf-8", "replace")
    complete_hash_lines = sum(
        len(line) >= 66 and all(letter in b"0123456789abcdef" for letter in line[:64])
        and line[64:66] == b"  "
        for line in output.splitlines()
    )
    if timed_out:
        category = "subprocess_deadline"
    elif returncode == 255:
        category = "ssh_transport_or_auth"
    elif complete_hash_lines >= len(_SOURCE_FILES):
        category = "remote_probe_process"
    else:
        category = "remote_source_check_or_probe"
    structured_code = None
    exception_class = None
    phase = None
    if not isinstance(stderr, bytes):
        lines = (stderr or "").splitlines()
        for line in reversed(lines[-16:]):
            match = re.fullmatch(
                r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*"
                r"(?:ExplicitStepError|RemoteResultError|ValueError): ([a-z_]+)",
                                 line.strip())
            if match and match.group(1) in _SAFE_REMOTE_CODES:
                structured_code = match.group(1)
                break
        # Only allowlisted class and phase labels leave this process. The
        # traceback, model output, and task text are never persisted.
        for line in reversed(lines[-16:]):
            match = re.match(r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)*"
                             r"([A-Za-z_][A-Za-z0-9_]*):", line.strip())
            if match and match.group(1) in _SAFE_REMOTE_EXCEPTION_CLASSES:
                exception_class = match.group(1)
                break
        for marker, safe_phase in _SAFE_REMOTE_PHASES:
            if marker in (stderr or ""):
                phase = safe_phase
    _private_publish(run_dir, "remote-failure-diagnostic.json", {
        "version": 1, "category": category, "exit_status": returncode,
        "timed_out": bool(timed_out),
        "source_hash_lines": min(complete_hash_lines, len(_SOURCE_FILES)),
        "stdout_length": len(output), "stdout_sha256": hashlib.sha256(output).hexdigest(),
        "stderr_length": len(error), "stderr_sha256": hashlib.sha256(error).hexdigest(),
        "structured_error_code": structured_code,
        "exception_class": exception_class, "phase_hint": phase,
        "raw_output_retained": False,
    })


def _wait_private(path, directory, timeout):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if (directory / "failure.json").exists():
            raise LiveRunError("rhino_session_failed")
        if time.monotonic() >= deadline:
            raise LiveRunError("rhino_response_timeout")
        time.sleep(0.1)
    return _private_read(path)


class LiveScene:
    def __init__(self, directory, initial):
        self.directory = Path(directory)
        self.initial = initial

    def capture(self):
        nonce = secrets.token_hex(32)
        _private_publish(self.directory, "capture-" + nonce + ".json", {
            "version": 1, "nonce": nonce,
        })
        value = _wait_private(self.directory / ("capture-response-" + nonce + ".json"),
                              self.directory, 20)
        if (not isinstance(value, dict) or set(value) != {"version", "nonce", "scene"}
                or type(value["version"]) is not int or value["version"] != 1
                or value["nonce"] != nonce):
            raise LiveRunError("invalid_rhino_capture")
        return GivenScene(value["scene"]).snapshot()

    def snapshot(self):
        state = self.capture()
        if state != self.initial:
            raise LiveRunError("write_grade_scene_changed")
        return state


def _initial(directory):
    value = _private_read(directory / "initial.json")
    if (not isinstance(value, dict) or set(value) != {
            "version", "fixture", "scene", "active_document_content_sha256",
    } or type(value["version"]) is not int or value["version"] != 1
            or value["fixture"] != "empty_headless_mm"
            or not isinstance(value["active_document_content_sha256"], str)
            or not _HEX.fullmatch(value["active_document_content_sha256"])):
        raise LiveRunError("invalid_live_session")
    state = GivenScene(value["scene"]).snapshot()
    if state.summary["aliases"] != [] or state.summary["object_count"] != 0 or state.summary["unit"] != "Millimeters":
        raise LiveRunError("unexpected_fixture")
    return state


def _checked_control_socket(path):
    if path is None:
        return None
    path = Path(path)
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise LiveRunError("unsafe_ssh_control_socket")
    try:
        parent = path.parent.lstat()
        entry = path.lstat()
    except OSError as exc:
        raise LiveRunError("unsafe_ssh_control_socket") from exc
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != os.getuid()):
        raise LiveRunError("unsafe_ssh_control_socket")
    return str(path)


def _remote_result(args, directory, initial, run_dir, *, task=_TASK, model_task=None):
    if not _HEX.fullmatch(args.approved_manifest_sha256):
        raise LiveRunError("invalid_manifest_digest")
    pinned = _pinned_host_key(args.host, args.port, args.known_hosts,
                              args.expected_host_key_sha256)
    _private_publish_bytes(run_dir, "known_hosts", (pinned + "\n").encode())
    challenge = secrets.token_hex(32)
    request_value = {
        "task": task, "scene": {"revision": initial.revision,
                                  "scene_sha256": initial.scene_sha256,
                                  "summary": initial.summary}, "challenge": challenge,
    }
    if model_task is not None:
        if not isinstance(model_task, str) or not 0 < len(model_task) <= 4096:
            raise LiveRunError("invalid_model_task")
        request_value["model_task"] = model_task
    request = json.dumps(request_value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    remote = (
        "cd " + shlex.quote(_REMOTE_ROOT) + " && "
        + "sha256sum " + " ".join(shlex.quote(file) for file in _SOURCE_FILES)
        + " && env PYTHONPATH=.r4deps " + shlex.quote(_REMOTE_PYTHON)
        + " tools/r4_v5_one_step_remote_probe.py"
        + " --manifest " + shlex.quote(_REMOTE_MANIFEST)
        + " --operator-approved-sha256 " + shlex.quote(args.approved_manifest_sha256)
        + " --input-json " + shlex.quote(request)
        + (" --emit-resource-metrics" if getattr(args, "collect_resource_metrics", False) else "")
        + (" --selector-json-prefix" if getattr(args, "selector_json_prefix", False) else "")
        + (" --v8-selector-prompt" if getattr(args, "v8_selector_prompt", False) else "")
    )
    control_socket = _checked_control_socket(getattr(args, "control_socket", None))
    if control_socket is None:
        print("SSH_PASSWORD_PROMPT_IN_THIS_TERMINAL", flush=True)
    ssh_args = ["ssh", "-T", "-o", "StrictHostKeyChecking=yes",
                "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "GlobalKnownHostsFile=/dev/null",
                "-o", "UserKnownHostsFile=" + str(run_dir / "known_hosts"),
                "-o", "NumberOfPasswordPrompts=1", "-o", "ConnectTimeout=10",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2"]
    if control_socket is not None:
        ssh_args += ["-S", control_socket, "-o", "BatchMode=yes"]
    ssh_args += ["-p", str(args.port), f"{args.user}@{args.host}", remote]
    remote_started = time.monotonic()
    try:
        ssh = subprocess.run(
            ssh_args,
            # Includes the operator's interactive password-entry time plus a
            # cold offline CUDA/model load. The remote command still has SSH
            # keepalives and one password prompt; no write permission exists.
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired as exc:
        _record_remote_failure(run_dir, returncode=None, stdout=exc.stdout,
                               stderr=exc.stderr, timed_out=True)
        raise LiveRunError("ssh_authentication_or_model_timeout") from exc
    if ssh.returncode != 0:
        _record_remote_failure(run_dir, returncode=ssh.returncode,
                               stdout=ssh.stdout, stderr=ssh.stderr)
        if "CUDA out of memory" in ssh.stderr or "OutOfMemoryError" in ssh.stderr:
            raise LiveRunError("remote_cuda_oom")
        raise LiveRunError("ssh_or_model_failed")
    result, hashes = _ssh_output(ssh.stdout)
    if getattr(args, "collect_resource_metrics", False):
        import resource  # noqa: PLC0415

        prefix = "R4_V6_RESOURCE_METRICS "
        rows = [line[len(prefix):] for line in ssh.stderr.splitlines() if line.startswith(prefix)]
        if len(rows) != 1:
            raise LiveRunError("remote_resource_metrics_missing")
        metrics = json.loads(rows[0])
        if (not isinstance(metrics, dict) or set(metrics) != {
                "model_load_seconds", "inference_seconds", "cuda_peak_allocated_bytes",
                "cuda_peak_reserved_bytes", "remote_peak_rss_kib",
        } or any(type(value) not in (int, float) or value < 0 for value in metrics.values())):
            raise LiveRunError("remote_resource_metrics_invalid")
        _private_publish(run_dir, "resource-metrics.json", {
            **metrics,
            "model_roundtrip_seconds": round(time.monotonic() - remote_started, 4),
            "mac_process_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        })
    _private_publish(run_dir, "remote-result.json", result)
    return result, hashes, challenge


async def _review_and_execute(directory, run_dir, scene, checked, tools, hashes, args):
    consent = ConsentStore(run_dir / "review.sqlite3", tools)
    note = (
        "仅向一次性、未保存的 Rhino headless 测试文档写入：在空白毫米场景中创建 "
        "13 × 17 × 19 mm 长方体。活动文档不写入；批准后受控运行器立即尝试一次，失败不自动重试。"
    )
    delegated = bool(args.delegated_headless_approval)
    link = consent.prepare(
        _TASK, "create_box", checked.model_arguments,
        scene=scene, ttl_seconds=300, review_note=note,
        delegated_scope=DELEGATED_HEADLESS_SCOPE if delegated else "",
    )
    runner = None
    try:
        if delegated:
            # `_initial` and the strict live scene already proved an empty,
            # unsaved headless millimetre fixture. The delegate method checks
            # expiry/session/current Rhino scene again and leaves a distinct
            # durable audit reason, never a synthetic human click.
            status = consent.approve_delegated_headless(link)
            print("CODEX_DELEGATED_HEADLESS_DECISION " + status, flush=True)
        else:
            runner, base = await start_local_consent_ui(consent)
            print("HUMAN_REVIEW_URL " + base + link.path, flush=True)
            print("WAITING_FOR_PERSONAL_APPROVAL_OR_REVOCATION", flush=True)
            deadline = time.monotonic() + 305
            while True:
                if consent.status_for_runner(link) != "pending":
                    break
                if time.monotonic() >= deadline:
                    break
                await asyncio.sleep(0.5)
            status = consent.inspect(link)[0]["status"]
        if status != "approved":
            consent.abort_without_human(link)
            raise LiveRunError("approval_" + status)
        envelope = issue_signed_handoff(
            task=_TASK, checked=checked, link=link, scene=scene,
            consent=consent, tools=tools,
            secret=load_private_secret(directory / "channel"),
        )
        request_id = publish_signed_envelope(directory / "channel", envelope)
        nonce = secrets.token_hex(32)
        _private_publish(directory, "execute-" + nonce + ".json", {
            "version": 1, "nonce": nonce, "request_id": request_id,
        })
        result = await asyncio.to_thread(
            _wait_private, directory / ("execute-response-" + nonce + ".json"),
            directory, 30,
        )
        if (not isinstance(result, dict) or result.get("status") != "done"
                or result.get("ledger_state") != "done"
                or result.get("headless_object_count") != 1
                or result.get("active_document_unchanged") is not True
                or result.get("box_dimensions_mm") != [13.0, 17.0, 19.0]):
            raise LiveRunError("rhino_execution_not_verified_manual_review")
        audit = consent.audit_events(link.request_id)
        events = [event["event_type"] for event in audit]
        if events != ["requested", "approved", "consumed", "signed_handoff_issued"]:
            raise LiveRunError("unexpected_consent_audit")
        approval_reason = audit[1]["reason_code"]
        if approval_reason != ("codex_delegated_headless" if delegated else "human_action"):
            raise LiveRunError("unexpected_approval_actor")
        receipt = {
            "status": ("delegated_approved_disposable_rhino_write_verified" if delegated
                       else "human_approved_disposable_rhino_write_verified"),
            "approval_mode": "codex_delegated_headless" if delegated else "human_click",
            "human_approved": not delegated, "codex_delegated_approved": delegated,
            "authorization_scope": DELEGATED_HEADLESS_SCOPE if delegated else "one_human_click",
            "consent_approval_reason": approval_reason,
            "consent_consumed": True,
            "remote_model_contract_verified": True,
            "scene_sha256": scene.initial.scene_sha256,
            "task_sha256": hashlib.sha256(_TASK.encode()).hexdigest(),
            "tool": checked.name, "headless_object_count": 1,
            "box_dimensions_mm": result["box_dimensions_mm"],
            "ledger_state": result["ledger_state"],
            "active_document_unchanged": True,
            "consent_events": events,
            "remote_result_sha256": hashlib.sha256(
                (run_dir / "remote-result.json").read_bytes()).hexdigest(),
            "remote_code_sha256": hashes,
            "host_key_sha256": args.expected_host_key_sha256,
            "approved_manifest_sha256": args.approved_manifest_sha256,
        }
        _private_publish(run_dir, "receipt.json", receipt)
        return receipt
    finally:
        if runner is not None:
            await runner.cleanup()


async def _run(args):
    directory = args.session_dir.resolve()
    bootstrap = _initial(directory)
    initial = LiveScene(directory, bootstrap).capture()
    # Rhino may advance a process-global serial once immediately after the
    # Script Editor command returns. Establish the executable baseline only
    # from a later Idle capture, while requiring the same empty fixture and
    # gate-bound document identity. All subsequent captures remain exact.
    if (initial.summary != bootstrap.summary or initial.revision < bootstrap.revision
            or initial.scene_sha256 == ""):
        raise LiveRunError("unexpected_baseline_change")
    scene = LiveScene(directory, initial)
    scene.snapshot()
    run_dir = directory / ("run-" + secrets.token_hex(24))
    os.mkdir(run_dir, 0o700)
    result, hashes, challenge = await asyncio.to_thread(
        _remote_result, args, directory, initial, run_dir,
    )
    scene.snapshot()  # Fresh Rhino UI-thread strict state after remote inference.
    tools = load_public_mcp_tools()
    checked = verify_no_dispatch_result(
        result, task=_TASK, scene=scene, tools=tools, challenge=challenge,
        approved_manifest_sha256=args.approved_manifest_sha256,
    )
    if checked.name != "create_box" or checked.target_alias is not None:
        raise LiveRunError("unexpected_model_operation")
    receipt = await _review_and_execute(directory, run_dir, scene, checked, tools, hashes, args)
    return run_dir, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--expected-host-key-sha256", required=True)
    parser.add_argument("--approved-manifest-sha256", required=True)
    parser.add_argument("--control-socket", type=Path,
                        help="pre-authenticated SSH master socket in an owner-only directory")
    parser.add_argument("--delegated-headless-approval", action="store_true",
                        help="Codex-delegated approval for this disposable headless fixture only")
    args = parser.parse_args()
    try:
        run_dir, receipt = asyncio.run(_run(args))
    except LiveRunError as exc:
        print("R4_V5_LIVE_STOPPED " + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2) from None
    print("R4_V5_LIVE_RESULT " + json.dumps({"run_dir": str(run_dir), **receipt},
                                            ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
