#!/usr/bin/env python3
"""Operator-visible, one-run opt-in for the isolated R candidate CLI.

This is deliberately not a switch in the default product UI. A local caller
cannot confer permission for an active Rhino document through this lease.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from tools import r4_v6_formal_quality as core
from tools.r4_v5_ssh_no_write_session import _private_directory, _private_publish


class OptInError(RuntimeError):
    pass


@dataclass
class OptInLease:
    task_sha256: str
    session_dir: Path
    control_dir: Path
    manifest_sha256: str
    host_key_sha256: str
    expires_at: float
    stopped: bool = False
    claimed: bool = False

    def claim(self, args) -> None:
        if self.claimed:
            raise OptInError("opt_in_lease_already_consumed")
        self.check(args)
        self.claimed = True

    def check(self, args) -> None:
        if (self.stopped or time.monotonic() >= self.expires_at
                or hashlib.sha256(args.task.encode("utf-8")).hexdigest() != self.task_sha256
                or Path(args.session_dir).resolve() != self.session_dir
                or args.approved_manifest_sha256 != self.manifest_sha256
                or args.expected_host_key_sha256 != self.host_key_sha256
                or args.host != core.HOST or args.port != core.PORT or args.user != core.USER
                or getattr(args, "fixture_name", None) != "empty"
                or getattr(args, "delegated_headless_approval", None) is not True):
            raise OptInError("opt_in_scope_inactive_or_changed")
        directory_fd = _private_directory(self.control_dir)
        try:
            try:
                info = os.stat("stop.json", dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise OptInError("unsafe_stop_request")
            self.stopped = True
            raise OptInError("operator_stop_requested")
        finally:
            os.close(directory_fd)

    def stop(self) -> None:
        self.stopped = True
        try:
            _private_publish(self.control_dir, "stop.json", {"status": "requested"})
        except FileExistsError:
            pass


@dataclass
class PendingOptIn:
    """Human approval before fixture creation; no grant until session binding."""

    task_sha256: str
    control_dir: Path
    manifest_sha256: str
    host_key_sha256: str
    expires_at: float
    stopped: bool = False
    bound: bool = False

    def bind(self, args) -> OptInLease:
        if (self.stopped or self.bound or time.monotonic() >= self.expires_at
                or hashlib.sha256(args.task.encode("utf-8")).hexdigest() != self.task_sha256
                or args.approved_manifest_sha256 != self.manifest_sha256
                or args.expected_host_key_sha256 != self.host_key_sha256
                or args.host != core.HOST or args.port != core.PORT or args.user != core.USER
                or getattr(args, "fixture_name", None) != "empty"
                or getattr(args, "delegated_headless_approval", None) is not True):
            raise OptInError("pending_opt_in_scope_inactive_or_changed")
        directory_fd = _private_directory(self.control_dir)
        try:
            if os.path.lexists(self.control_dir / "stop.json"):
                raise OptInError("operator_stop_requested")
        finally:
            os.close(directory_fd)
        session = Path(args.session_dir).resolve(strict=True)
        session_fd = _private_directory(session)
        os.close(session_fd)
        _private_publish(self.control_dir, "grant.json", {
            "scope": "isolated_unsaved_headless_mm", "task_sha256": self.task_sha256,
            "approved_manifest_sha256": core.MODEL_SHA,
            "expected_host_key_sha256": core.HOST_KEY,
            "remote": f"{core.USER}@{core.HOST}:{core.PORT}",
            "session_dir": str(session), "ttl_seconds": 20 * 60,
            "human_interactive_opt_in": True,
        })
        self.bound = True
        return OptInLease(task_sha256=self.task_sha256, session_dir=session,
                          control_dir=self.control_dir, manifest_sha256=self.manifest_sha256,
                          host_key_sha256=self.host_key_sha256, expires_at=self.expires_at)

    def stop(self) -> None:
        self.stopped = True
        try:
            _private_publish(self.control_dir, "stop.json", {"status": "requested"})
        except FileExistsError:
            pass


def _prompt_operator(args) -> None:
    if not sys.stdin.isatty():
        raise OptInError("interactive_terminal_required")
    if (getattr(args, "fixture_name", None) != "empty"
            or getattr(args, "delegated_headless_approval", None) is not True
            or args.approved_manifest_sha256 != core.MODEL_SHA
            or args.expected_host_key_sha256 != core.HOST_KEY
            or args.host != core.HOST or args.port != core.PORT or args.user != core.USER):
        raise OptInError("candidate_scope_not_approved")
    challenge = "APPROVE-R4-" + secrets.token_hex(4).upper()
    print("\n支线 R 一次性受控候选测试（默认产品路线不会切换）")
    print(f"目标：SSH 到 {core.USER}@{core.HOST}:{core.PORT}；批准模型 {core.MODEL_SHA}")
    print("范围：仅独立、空白、未保存的 Rhino headless 文档；每次写入仍需独立许可。")
    print("只允许低风险内容出站；中/高/危风险会在每步 SSH 前拒绝。")
    print("确认后才会开一次性夹具；确认本身不会调用模型或写入 Rhino。")
    print("停用：另一个终端运行 stop 子命令，或在当前终端按 Ctrl+C。停用不撤销已完成写入，")
    print("也无法收回已经发出的远端内容；不确定结果绝不自动重试。")
    print("确认码：" + challenge)
    if input("逐字输入确认码才继续：").strip() != challenge:
        raise OptInError("operator_did_not_opt_in")


def interactive_preflight_opt_in(args) -> PendingOptIn:
    """Ask visibly before creating any headless fixture, then bind once."""
    _prompt_operator(args)
    control_dir = Path(tempfile.mkdtemp(prefix="r4-candidate-optin-", dir="/private/tmp"))
    control_dir.chmod(0o700)
    task_sha256 = hashlib.sha256(args.task.encode("utf-8")).hexdigest()
    print("停用控制目录：" + str(control_dir), flush=True)
    return PendingOptIn(task_sha256=task_sha256, control_dir=control_dir,
                        manifest_sha256=core.MODEL_SHA, host_key_sha256=core.HOST_KEY,
                        expires_at=time.monotonic() + 20 * 60)


def interactive_opt_in(args) -> OptInLease:
    """Legacy immediate binding for isolated callers with an open fixture."""
    _prompt_operator(args)
    control_dir = Path(tempfile.mkdtemp(prefix="r4-candidate-optin-", dir="/private/tmp"))
    control_dir.chmod(0o700)
    task_sha256 = hashlib.sha256(args.task.encode("utf-8")).hexdigest()
    lease = OptInLease(task_sha256=task_sha256,
                       session_dir=Path(args.session_dir).resolve(),
                       control_dir=control_dir,
                       manifest_sha256=core.MODEL_SHA,
                       host_key_sha256=core.HOST_KEY,
                       expires_at=time.monotonic() + 20 * 60)
    _private_publish(control_dir, "grant.json", {
        "scope": "isolated_unsaved_headless_mm", "task_sha256": task_sha256,
        "approved_manifest_sha256": core.MODEL_SHA,
        "expected_host_key_sha256": core.HOST_KEY,
        "remote": f"{core.USER}@{core.HOST}:{core.PORT}",
        "session_dir": str(lease.session_dir), "ttl_seconds": 20 * 60,
        "human_interactive_opt_in": True,
    })
    print("停用控制目录：" + str(control_dir), flush=True)
    return lease


def request_stop(control_dir: Path) -> None:
    directory_fd = _private_directory(control_dir)
    os.close(directory_fd)
    try:
        _private_publish(control_dir, "stop.json", {"status": "requested"})
    except FileExistsError:
        pass
