"""Issue one signed candidate envelope only after a consumed scoped approval.

The signer is trusted local code. It never talks to Rhino or grants approval;
the human UI or an explicitly delegated headless-only policy must have put
the matching request into `approved` first. A missing or uncertain handoff is
not retried automatically after consent consumption.
"""

from __future__ import annotations

import json
import hashlib
import re
from typing import Mapping, Sequence

from plugin.rhino_listener.candidate_envelope_gate import _signature, _validate_payload
from training.consent_candidate import ConsentError, ConsentLink, ConsentStore
from training.explicit_step_gate_candidate import ExplicitStepError, SceneProvider, _same_scene, preflight
from training.tool_controller_candidate import READ_ONLY_TOOLS
from training.tool_invocation_v5_candidate import CheckedInvocation


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class HandoffError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def issue_signed_handoff(
    *, task: str, checked: CheckedInvocation, link: ConsentLink,
    scene: SceneProvider, consent: ConsentStore, tools: Sequence[Mapping], secret: bytes,
) -> dict:
    """Consume exactly one approved record before returning a signed envelope."""

    if type(consent) is not ConsentStore or not isinstance(link, ConsentLink):
        raise HandoffError("untrusted_consent_store")
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise HandoffError("invalid_handoff_secret")
    try:
        expected = preflight(task, scene=scene, tools=tools)
        _same_scene(expected, scene)
        state = scene.snapshot()
        if expected.tool_name in READ_ONLY_TOOLS or not isinstance(checked, CheckedInvocation):
            raise HandoffError("not_an_approved_write")
        model_arguments = expected.arguments
        target_alias = None
        if expected.tool_name == "move_object":
            target_alias = model_arguments.pop("object_id")
        if (checked.name != expected.tool_name or checked.target_alias != target_alias
                or checked.model_arguments != model_arguments):
            raise HandoffError("model_binding_mismatch")
        document_key = state.summary.get("document_key")
        if not isinstance(document_key, str) or not _SHA256.fullmatch(document_key):
            raise HandoffError("unbound_document")
        row, display = consent.inspect(link)
        if row["status"] != "approved" or display.task != task:
            raise HandoffError("not_approved")
        current_summary = json.dumps(state.summary, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False)
        if display.scene_summary_json != current_summary:
            raise HandoffError("scene_changed")
        consumed = consent._consume(
            link, task=task, tool_name=expected.tool_name,
            arguments=expected.arguments, scene=scene,
        )
        after = scene.snapshot()
        if after != state or consumed != state:
            # Consent is now consumed; do not retry or reissue automatically.
            raise HandoffError("scene_changed_after_consumption")
        try:
            _same_scene(expected, scene)
        except ExplicitStepError as exc:
            raise HandoffError("scene_changed_after_consumption") from exc
        arguments = expected.arguments
        if expected.tool_name == "move_object":
            arguments = {"alias": arguments.pop("object_id"), **arguments}
        payload = {
            "version": 1,
            "request_id": link.request_id,
            "task_sha256": hashlib.sha256(task.encode("utf-8")).hexdigest(),
            "document_key": document_key,
            "scene_revision": state.revision,
            "scene_sha256": state.scene_sha256,
            "operation": expected.tool_name,
            "arguments": arguments,
        }
        _validate_payload(payload)
        envelope = {"payload": payload, "signature": _signature(secret, payload)}
        with consent._tx() as db:
            consent._event(db, link.request_id, "signed_handoff_issued")
        return envelope
    except HandoffError:
        raise
    except (ConsentError, ExplicitStepError) as exc:
        raise HandoffError(getattr(exc, "code", "handoff_rejected")) from exc
    except Exception as exc:
        raise HandoffError("handoff_unavailable_manual_review") from exc
