"""Strict, no-consent import of one v5 model result received over trusted SSH.

SSH authenticates the remote host; this module independently verifies the
task/scene/challenge binding and untrusted model text. It cannot create a
consent record, sign a Rhino envelope, or dispatch anything.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from training.explicit_step_gate_candidate import before_invoker, preflight
from training.tool_invocation_v5_candidate import CheckedInvocation, check_invocation


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RESULT_KEYS = frozenset({
    "version", "challenge", "task_sha256", "scene_revision", "scene_sha256",
    "summary_sha256", "approved_manifest_sha256", "selection_text",
    "invocation_text", "status", "no_consent", "no_dispatch",
})


class RemoteResultError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def build_no_dispatch_result(*, task, scene, tools: Sequence[Mapping], challenge,
                             approved_manifest_sha256, selection_text, invocation_text):
    """Remote-side strict result; never carries a consent token or Rhino GUID."""
    if not isinstance(challenge, str) or not _HEX.fullmatch(challenge):
        raise RemoteResultError("invalid_challenge")
    if (not isinstance(approved_manifest_sha256, str)
            or not _HEX.fullmatch(approved_manifest_sha256)):
        raise RemoteResultError("invalid_manifest_digest")
    if not all(isinstance(text, str) and len(text) <= 8192
               for text in (selection_text, invocation_text)):
        raise RemoteResultError("invalid_model_text")
    expected = preflight(task, scene=scene, tools=tools)
    before_invoker(expected, selection_text, scene=scene, tools=tools)
    check_invocation(expected, invocation_text, scene=scene, tools=tools)
    return {
        "version": 1,
        "challenge": challenge,
        "task_sha256": expected.task_sha256,
        "scene_revision": expected.scene_revision,
        "scene_sha256": expected.scene_sha256,
        "summary_sha256": expected.summary_sha256,
        "approved_manifest_sha256": approved_manifest_sha256,
        "selection_text": selection_text,
        "invocation_text": invocation_text,
        "status": "contract_passed_no_execution",
        "no_consent": True,
        "no_dispatch": True,
    }


def verify_no_dispatch_result(result, *, task, scene, tools: Sequence[Mapping],
                              challenge, approved_manifest_sha256) -> CheckedInvocation:
    """Mac-side recheck; caller must separately authenticate SSH and live scene."""
    if not isinstance(result, dict) or set(result) != _RESULT_KEYS:
        raise RemoteResultError("invalid_result_shape")
    if (type(result["version"]) is not int or result["version"] != 1
            or result["status"] != "contract_passed_no_execution"
            or result["no_consent"] is not True or result["no_dispatch"] is not True):
        raise RemoteResultError("invalid_result_status")
    if not isinstance(challenge, str) or not _HEX.fullmatch(challenge) or result["challenge"] != challenge:
        raise RemoteResultError("challenge_mismatch")
    if (not isinstance(approved_manifest_sha256, str)
            or not _HEX.fullmatch(approved_manifest_sha256)
            or result["approved_manifest_sha256"] != approved_manifest_sha256):
        raise RemoteResultError("manifest_mismatch")
    if not all(isinstance(result[name], str) and len(result[name]) <= 8192
               for name in ("selection_text", "invocation_text")):
        raise RemoteResultError("invalid_model_text")
    expected = preflight(task, scene=scene, tools=tools)
    if (result["task_sha256"] != expected.task_sha256
            or type(result["scene_revision"]) is not int
            or result["scene_revision"] != expected.scene_revision
            or result["scene_sha256"] != expected.scene_sha256
            or result["summary_sha256"] != expected.summary_sha256):
        raise RemoteResultError("binding_mismatch")
    before_invoker(expected, result["selection_text"], scene=scene, tools=tools)
    return check_invocation(expected, result["invocation_text"], scene=scene, tools=tools)
