"""Isolated signed-consent handoff to the Rhino main-thread atomic gate.

No Listener route, socket, or model parser is exposed here. A trusted caller
must supply a secret provisioned outside the repository and a Rhino-main-thread
dispatcher. The model cannot sign an envelope or choose an object GUID.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re

from .candidate_alias_scene import AliasGateError, candidate_scene_snapshot, resolve_unique_writable_alias


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_PAYLOAD_KEYS = frozenset({
    "version", "request_id", "task_sha256", "document_key", "scene_revision",
    "scene_sha256", "operation", "arguments",
})


class EnvelopeGateError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _signature(secret, payload):
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise EnvelopeGateError("invalid_handoff_secret")
    return hmac.new(secret, _canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def _finite_number(value, positive=False):
    return (
        not isinstance(value, bool) and isinstance(value, (int, float))
        and math.isfinite(value) and abs(value) <= 100_000
        and (not positive or value > 0)
    )


def _validate_payload(payload):
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise EnvelopeGateError("invalid_payload")
    if payload["version"] != 1 or isinstance(payload["version"], bool):
        raise EnvelopeGateError("unsupported_version")
    request_id = payload["request_id"]
    if not isinstance(request_id, str) or not 24 <= len(request_id) <= 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", request_id):
        raise EnvelopeGateError("invalid_request_id")
    if not isinstance(payload["task_sha256"], str) or not _SHA256.fullmatch(payload["task_sha256"]):
        raise EnvelopeGateError("invalid_task_digest")
    if not isinstance(payload["document_key"], str) or not _SHA256.fullmatch(payload["document_key"]):
        raise EnvelopeGateError("invalid_document_key")
    if (isinstance(payload["scene_revision"], bool) or not isinstance(payload["scene_revision"], int)
            or payload["scene_revision"] < 0):
        raise EnvelopeGateError("invalid_scene_revision")
    if not isinstance(payload["scene_sha256"], str) or not _SHA256.fullmatch(payload["scene_sha256"]):
        raise EnvelopeGateError("invalid_scene_digest")
    operation, arguments = payload["operation"], payload["arguments"]
    if not isinstance(arguments, dict):
        raise EnvelopeGateError("invalid_arguments")
    if operation == "create_box":
        if set(arguments) != {"width", "depth", "height"} or not all(
            _finite_number(arguments[field], positive=True) for field in ("width", "depth", "height")
        ):
            raise EnvelopeGateError("invalid_box_arguments")
    elif operation == "move_object":
        if set(arguments) != {"alias", "translate_x", "translate_y", "translate_z"}:
            raise EnvelopeGateError("invalid_move_arguments")
        if not isinstance(arguments["alias"], str) or not _ALIAS.fullmatch(arguments["alias"]):
            raise EnvelopeGateError("invalid_target_alias")
        if not all(_finite_number(arguments[field]) for field in ("translate_x", "translate_y", "translate_z")):
            raise EnvelopeGateError("invalid_move_arguments")
    else:
        raise EnvelopeGateError("unsupported_operation")


def _verified_payload(envelope, secret):
    """Detach and authenticate one envelope without granting execution authority."""

    if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
        raise EnvelopeGateError("invalid_envelope")
    signature = envelope["signature"]
    try:
        # Detach from a mutable transport object before checking the HMAC.
        payload = json.loads(_canonical(envelope["payload"]))
        _validate_payload(payload)
        correct = _signature(secret, payload)
    except EnvelopeGateError:
        raise
    except Exception as exc:
        raise EnvelopeGateError("invalid_envelope") from exc
    if not isinstance(signature, str) or not _SHA256.fullmatch(signature) or not hmac.compare_digest(signature, correct):
        raise EnvelopeGateError("invalid_signature")
    return payload


def verify_and_execute(envelope, *, secret, doc, gate, dispatch):
    """Verify consent binding and reserve durably before one trusted dispatch.

    Must be called on Rhino's UI thread. `dispatch` is trusted local code, not
    derived from the envelope. The response has no raw object ID or geometry.
    """

    if not callable(dispatch):
        raise EnvelopeGateError("invalid_envelope")
    payload = _verified_payload(envelope, secret)
    try:
        scene = candidate_scene_snapshot(doc, gate)
    except AliasGateError as exc:
        raise EnvelopeGateError(exc.code) from exc
    expected = {"document_key": payload["document_key"],
                "revision": payload["scene_revision"], "scene_sha256": payload["scene_sha256"]}
    if {key: scene[key] for key in expected} != expected:
        raise EnvelopeGateError("scene_changed")
    key = hashlib.sha256(payload["request_id"].encode("utf-8")).hexdigest()
    operation = payload["operation"]
    arguments = payload["arguments"]

    def trusted_dispatch(_operation, _arguments):
        if operation == "move_object":
            target_id = resolve_unique_writable_alias(doc, gate, scene, arguments["alias"])
            actual = {
                "object_id": target_id,
                "translation": [arguments["translate_x"], arguments["translate_y"], arguments["translate_z"]],
            }
        else:
            actual = dict(arguments)
        return dispatch(operation, actual)

    try:
        gate.execute(key, expected, operation, arguments, trusted_dispatch)
    except AliasGateError as exc:
        raise EnvelopeGateError(exc.code) from exc
    # The caller must not expose the Rhino dispatcher result or raw IDs to the model.
    return {"status": "done", "idempotency_key_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest()}
