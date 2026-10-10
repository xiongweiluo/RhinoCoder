#!/usr/bin/env python3
"""Fail-closed outbound policy for the isolated v2 remote-GPU R adapter.

This is wired only into the v2 candidate, not the frozen v1 probe or default
product route. Every v2 SSH model call invokes it against the outbound task,
natural-language segment (if any), and current Rhino scene immediately before
transmission. Medium/high data is refused until an independently reviewed
minimization or truly local backend exists.
"""

from __future__ import annotations

import json
from typing import Any

from agent.privacy import PrivacyAction, classify_request
from tools import r4_v6_formal_quality as core
from tools.r4_v5_live_human_write import _remote_result
from training.tool_controller_candidate import SceneState, compose_step_input


class RemoteScopeError(RuntimeError):
    pass


def require_remote_scope(args: Any, *, explicit_task: str,
                         model_task: str | None, scene: SceneState) -> None:
    if (getattr(args, "approved_manifest_sha256", None) != core.MODEL_SHA
            or getattr(args, "expected_host_key_sha256", None) != core.HOST_KEY
            or getattr(args, "host", None) != core.HOST
            or getattr(args, "port", None) != core.PORT
            or getattr(args, "user", None) != core.USER):
        raise RemoteScopeError("approved_remote_identity_required")
    if (getattr(args, "fixture_name", None) != "empty"
            or getattr(args, "delegated_headless_approval", None) is not True):
        raise RemoteScopeError("disposable_headless_scope_required")
    if (not isinstance(explicit_task, str) or not explicit_task.strip()
            or model_task is not None and (not isinstance(model_task, str)
                                           or not model_task.strip())):
        raise RemoteScopeError("invalid_outbound_task")
    try:
        # Validate the alias-only scene contract, then classify the same
        # first-level fields that _remote_result serializes for the SSH call.
        # Nesting an already serialized task would obscure privacy patterns.
        compose_step_input(explicit_task, scene)
        outbound = json.dumps({
            "task": explicit_task,
            "model_task": model_task,
            "scene": {"revision": scene.revision,
                      "scene_sha256": scene.scene_sha256,
                      "summary": scene.summary},
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False)
        decision = classify_request(outbound)
    except Exception as exc:
        raise RemoteScopeError("outbound_privacy_check_failed") from exc
    if decision.action is not PrivacyAction.ALLOW_CLOUD:
        raise RemoteScopeError("remote_gpu_privacy_rejected:" + decision.action.value)


def guarded_remote_result(args: Any, directory, scene: SceneState, run_dir,
                          *, task: str, model_task: str | None = None):
    """Check the exact per-step outbound payload before any SSH/model call."""
    require_remote_scope(args, explicit_task=task, model_task=model_task,
                         scene=scene)
    return _remote_result(args, directory, scene, run_dir,
                          task=task, model_task=model_task)
