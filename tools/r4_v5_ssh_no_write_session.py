#!/usr/bin/env python3
"""Repeatable SSH→Rhino-idle v5 smoke, stopping at revoked pending review.

Requires an already-rented GPU and a pre-existing, independently trusted SSH
host-key fingerprint. SSH requests an interactive password from the operator's
TTY; no password, approval capability, or signing key is persisted here. The
Rhino side is a read-only idle session with no dispatcher. On success a
pending record is observed and immediately revoked; no UI is served.
"""

from __future__ import annotations

import argparse
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

from tools.r4_v5_one_step_remote_probe import GivenScene  # noqa: E402
from tools.r4_v5_rhino_idle_request import submit  # noqa: E402
from training.consent_candidate import ConsentStore  # noqa: E402
from training.remote_result_v5_candidate import verify_no_dispatch_result  # noqa: E402
from training.tool_controller_candidate import SceneState  # noqa: E402
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}\Z")
_MARKER = "R4_V5_REMOTE_RESULT "
_REMOTE_ROOT = "/data/RhinoCoder-r4-gate"
_REMOTE_MANIFEST = "data/training/r4/model-snapshot-candidate.json"
_REMOTE_PYTHON = "/data/conda-envs/rhinocoder/bin/python"
_SOURCE_FILES = (
    "tools/r4_v5_one_step_remote_probe.py",
    "training/remote_result_v5_candidate.py",
)


class SessionError(RuntimeError):
    pass


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SessionError("duplicate_json_key")
        value[key] = item
    return value


def _private_directory(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        os.close(fd)
        raise SessionError("unsafe_directory")
    return fd


def _private_read(path, *, limit=16384):
    fd = _private_directory(path.parent)
    try:
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            info = os.fstat(file_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > limit):
                raise SessionError("unsafe_file")
            raw = os.read(file_fd, limit + 1)
            if len(raw) != info.st_size:
                raise SessionError("file_changed")
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)
    return json.loads(raw, object_pairs_hook=_unique_pairs)


def _private_publish_bytes(directory, name, raw):
    fd = _private_directory(directory)
    temporary = ".publish-" + secrets.token_hex(24)
    file_fd = None
    try:
        file_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=fd)
        try:
            if os.write(file_fd, raw) != len(raw):
                raise SessionError("short_write")
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
            file_fd = None
        # The final name is the readiness signal. Never expose it before the
        # bytes are complete, and never replace an existing one.
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass
        os.close(fd)
    return hashlib.sha256(raw).hexdigest()


def _private_publish(directory, name, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode()
    return _private_publish_bytes(directory, name, raw)


def _pinned_host_key(host, port, known_hosts, expected):
    if not _FINGERPRINT.fullmatch(expected):
        raise SessionError("invalid_host_fingerprint")
    lookup = subprocess.run(
        ["ssh-keygen", "-F", f"[{host}]:{port}", "-f", str(known_hosts)],
        capture_output=True, text=True, check=True, timeout=10,
    )
    matches = []
    for line in lookup.stdout.splitlines():
        if line.startswith("#") or " ssh-ed25519 " not in line:
            continue
        fingerprint = subprocess.run(
            ["ssh-keygen", "-lf", "-"], input=line + "\n", capture_output=True,
            text=True, check=True, timeout=10,
        ).stdout
        if expected in fingerprint.split():
            matches.append(line)
    if len(matches) != 1:
        raise SessionError("host_key_not_independently_pinned")
    return matches[0]


def _ssh_output(output):
    lines = output.splitlines()
    hashes = {}
    results = []
    for line in lines:
        if line.startswith(_MARKER):
            results.append(json.loads(line[len(_MARKER):], object_pairs_hook=_unique_pairs))
            continue
        pieces = line.split("  ", 1)
        if len(pieces) == 2 and pieces[1] in _SOURCE_FILES and _HEX.fullmatch(pieces[0]):
            if pieces[1] in hashes:
                raise SessionError("duplicate_remote_hash")
            hashes[pieces[1]] = pieces[0]
        elif line.strip():
            raise SessionError("unexpected_remote_stdout")
    if len(results) != 1 or set(hashes) != set(_SOURCE_FILES):
        raise SessionError("incomplete_remote_result")
    for file, digest in hashes.items():
        if hashlib.sha256((ROOT / file).read_bytes()).hexdigest() != digest:
            raise SessionError("remote_code_changed")
    return results[0], hashes


def _scene_from_capture(value, *, serial=None, request_id=None):
    if (not isinstance(value, dict)
            or set(value) != {"version", "request_id", "document_serial", "scene", "no_consent", "no_dispatch"}
            or type(value["version"]) is not int or value["version"] != 1
            or type(value["document_serial"]) is not int
            or value["no_consent"] is not True or value["no_dispatch"] is not True
            or (serial is not None and value["document_serial"] != serial)
            or (request_id is not None and value["request_id"] != request_id)):
        raise SessionError("invalid_rhino_capture")
    return GivenScene(value["scene"]).snapshot()


class LiveIdleScene:
    def __init__(self, directory, initial, serial, *, timeout=15):
        self.directory = directory
        self.initial = initial
        self.serial = serial
        self.timeout = timeout

    def snapshot(self) -> SceneState:
        request_id, path = submit(self.directory)
        deadline = time.monotonic() + self.timeout
        while not path.exists():
            if (self.directory / "failure.json").exists():
                raise SessionError("rhino_idle_session_failed")
            if time.monotonic() >= deadline:
                raise SessionError("rhino_idle_snapshot_timeout")
            time.sleep(0.1)
        current = _scene_from_capture(_private_read(path), serial=self.serial, request_id=request_id)
        if current != self.initial:
            raise SessionError("write_grade_scene_changed")
        return current


def _run(args):
    if not _HEX.fullmatch(args.approved_manifest_sha256):
        raise SessionError("invalid_manifest_digest")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.host) or not 1 <= args.port <= 65535:
        raise SessionError("invalid_ssh_endpoint")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", args.user):
        raise SessionError("invalid_ssh_user")
    initial_record = _private_read(args.session_dir / "initial.json")
    initial = _scene_from_capture(initial_record, request_id="initial")
    challenge = os.urandom(32).hex()
    run_dir = args.session_dir / ("run-" + challenge)
    os.mkdir(run_dir, 0o700)
    pinned = _pinned_host_key(args.host, args.port, args.known_hosts,
                              args.expected_host_key_sha256)
    _private_publish_bytes(run_dir, "known_hosts", (pinned + "\n").encode())
    request = json.dumps({
        "task": args.task,
        "scene": {"revision": initial.revision, "scene_sha256": initial.scene_sha256,
                  "summary": initial.summary},
        "challenge": challenge,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    remote = (
        "cd " + shlex.quote(_REMOTE_ROOT) + " && "
        + "sha256sum " + " ".join(shlex.quote(f) for f in _SOURCE_FILES)
        + " && env PYTHONPATH=.r4deps " + shlex.quote(_REMOTE_PYTHON)
        + " tools/r4_v5_one_step_remote_probe.py"
        + " --manifest " + shlex.quote(_REMOTE_MANIFEST)
        + " --operator-approved-sha256 " + shlex.quote(args.approved_manifest_sha256)
        + " --input-json " + shlex.quote(request)
    )
    ssh = subprocess.run(
        ["ssh", "-T", "-o", "StrictHostKeyChecking=yes",
         "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "GlobalKnownHostsFile=/dev/null",
         "-o", "UserKnownHostsFile=" + str(run_dir / "known_hosts"),
         "-o", "NumberOfPasswordPrompts=1", "-o", "ConnectTimeout=10",
         "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2",
         "-p", str(args.port), f"{args.user}@{args.host}", remote],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180,
    )
    if ssh.returncode != 0:
        raise SessionError("ssh_or_model_failed")
    result, hashes = _ssh_output(ssh.stdout)
    _private_publish(run_dir, "remote-result.json", result)
    live = LiveIdleScene(args.session_dir, initial, initial_record["document_serial"])
    live.snapshot()  # Fresh Rhino UI-thread write-grade scene, no Script Editor command.
    tools = load_public_mcp_tools()
    checked = verify_no_dispatch_result(
        result, task=args.task, scene=live, tools=tools,
        challenge=challenge, approved_manifest_sha256=args.approved_manifest_sha256,
    )
    if checked.name not in {"create_box", "move_object"}:
        raise SessionError("write_task_required_for_pending_smoke")
    consent = ConsentStore(run_dir / "review.sqlite3", tools)
    expected_arguments = {
        "create_box": checked.model_arguments,
        "move_object": {"object_id": checked.target_alias, **checked.model_arguments},
    }[checked.name]
    link = consent.prepare(args.task, checked.name, expected_arguments, scene=live)
    try:
        pending, _ = consent.inspect(link)
        if pending["status"] != "pending":
            raise SessionError("pending_not_created")
    finally:
        try:
            consent.abort_without_human(link)
        except Exception:
            # A new process cannot serve a pending record from this session.
            # Restarting the store also durably invalidates lingering rows.
            ConsentStore(run_dir / "review.sqlite3", tools)
    final, _ = consent.inspect(link)
    if final["status"] != "revoked":
        raise SessionError("revocation_not_durable")
    receipt = {
        "status": "pending_observed_then_revoked_no_dispatch",
        "model_contract_verified": True,
        "write_grade_scene_stable": True,
        "tool": checked.name,
        "scene_sha256": initial.scene_sha256,
        "task_sha256": result["task_sha256"],
        "remote_result_sha256": hashlib.sha256(
            (run_dir / "remote-result.json").read_bytes()).hexdigest(),
        "remote_code_sha256": hashes,
        "host_key_sha256": args.expected_host_key_sha256,
        "human_approval": False,
        "consent_consumed": False,
        "rhino_dispatch": False,
    }
    _private_publish(run_dir, "receipt.json", receipt)
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
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    run_dir, receipt = _run(args)
    print(json.dumps({"run_dir": str(run_dir), **receipt}, sort_keys=True))


if __name__ == "__main__":
    main()
