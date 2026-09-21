"""Synthetic-only controller for the future two-stage Qwen contract.

Not imported by the live Agent or frozen C0–C4 paths. The backend and executor
must explicitly identify as synthetic; this module cannot contact Rhino or a
real model. It records only outcome codes, never raw prompts or model text.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from agent.privacy import PrivacyAction, classify_request
from training.tool_contract_candidate import (
    ContractError,
    parse_invocation,
    parse_selection,
    render_invocation,
    render_selection,
    validate_inventory,
)


READ_ONLY_TOOLS = frozenset({
    "get_bounding_box",
    "get_object_info",
    "get_objects_by_name",
    "get_scene_summary",
    "get_selected_objects",
})
MAX_STATE_TEXT_CHARS = 4096
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RHINO_GUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


@dataclass(frozen=True)
class SceneState:
    revision: int
    scene_sha256: str
    summary: Mapping[str, Any]


@dataclass(frozen=True)
class MutationConsent:
    """Externally supplied approval, bound to one task, scene, and tool.

    Constructing this object is not evidence of human approval; a future UI
    must issue it only after explicit confirmation.
    """

    task_sha256: str
    scene_revision: int
    scene_sha256: str
    tool_name: str


@dataclass(frozen=True)
class ExecutionReceipt:
    previous_revision: int
    next_revision: int
    next_scene_sha256: str


@dataclass(frozen=True)
class StepOutcome:
    status: str
    stage: str
    selected_tool: str | None = None
    before_revision: int | None = None
    after_revision: int | None = None


class SceneProvider(Protocol):
    def snapshot(self) -> SceneState: ...


class SyntheticBackend(Protocol):
    kind: str

    def complete(self, stage: str, prompt: str) -> str: ...


class SyntheticExecutor(Protocol):
    synthetic_only: bool

    def simulate_call(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        expected_state: SceneState,
        idempotency_key: str,
    ) -> ExecutionReceipt: ...


def task_sha256(user_request: str) -> str:
    return hashlib.sha256(user_request.encode("utf-8")).hexdigest()


def compose_step_input(user_request: str, state: SceneState) -> str:
    if not isinstance(user_request, str) or not user_request.strip():
        raise ContractError("current task is empty")
    if (
        not isinstance(state, SceneState)
        or isinstance(state.revision, bool)
        or not isinstance(state.revision, int)
        or state.revision < 0
        or not isinstance(state.scene_sha256, str)
        or not _SHA256.fullmatch(state.scene_sha256)
        or not isinstance(state.summary, Mapping)
    ):
        raise ContractError("untrusted scene snapshot")
    try:
        summary = json.dumps(
            state.summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("scene summary is not strict JSON") from exc
    if len(summary) > MAX_STATE_TEXT_CHARS or _RHINO_GUID.search(summary):
        raise ContractError("scene summary exceeds safe alias-only boundary")
    return json.dumps(
        {"task": user_request, "scene_revision": state.revision, "scene_summary": state.summary},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _matches_consent(
    consent: MutationConsent | None, user_request: str, state: SceneState, tool_name: str
) -> bool:
    return bool(
        isinstance(consent, MutationConsent)
        and consent.task_sha256 == task_sha256(user_request)
        and consent.scene_revision == state.revision
        and consent.scene_sha256 == state.scene_sha256
        and consent.tool_name == tool_name
    )


def _idempotency_key(
    user_request: str, state: SceneState, tool_name: str, arguments: Mapping[str, Any]
) -> str:
    canonical = json.dumps(
        {
            "task_sha256": task_sha256(user_request),
            "scene_revision": state.revision,
            "scene_sha256": state.scene_sha256,
            "tool": tool_name,
            "arguments": arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CandidateController:
    """Exactly one selector call, one invocation call, and at most one dispatch."""

    def __init__(self, tokenizer: Any, tools: Sequence[Mapping[str, Any]]) -> None:
        self.tokenizer = tokenizer
        self.tools = list(tools)
        validate_inventory(self.tools)
        self._dispatched_keys: set[str] = set()

    def step(
        self,
        user_request: str,
        *,
        scene: SceneProvider,
        backend: SyntheticBackend,
        executor: SyntheticExecutor,
        consent: MutationConsent | None = None,
    ) -> StepOutcome:
        """Simulate a single action; no fallback, truncation, or automatic retry."""

        if getattr(backend, "kind", None) != "synthetic-local":
            return StepOutcome("route_rejected", "preflight")
        if getattr(executor, "synthetic_only", None) is not True:
            return StepOutcome("executor_rejected", "preflight")
        try:
            before = scene.snapshot()
            current_input = compose_step_input(user_request, before)
        except Exception:
            return StepOutcome("state_rejected", "preflight")
        try:
            privacy_action = classify_request(current_input).action
        except Exception:
            return StepOutcome("privacy_unavailable", "preflight", before_revision=before.revision)
        if privacy_action is PrivacyAction.BLOCK:
            return StepOutcome("privacy_blocked", "preflight", before_revision=before.revision)

        try:
            selection_prompt = render_selection(self.tokenizer, current_input, self.tools)
        except ContractError:
            return StepOutcome("budget_or_contract_rejected", "selector", before_revision=before.revision)
        try:
            selection_text = backend.complete("selector", selection_prompt.prompt)
        except Exception:
            return StepOutcome("model_unavailable", "selector", before_revision=before.revision)
        try:
            selected = parse_selection(selection_text, self.tools)
        except (ContractError, TypeError, AttributeError):
            return StepOutcome("invalid_model_output", "selector", before_revision=before.revision)
        try:
            if scene.snapshot() != before:
                return StepOutcome("state_changed", "selector", before_revision=before.revision)
        except Exception:
            return StepOutcome("state_unavailable", "selector", before_revision=before.revision)
        if selected is None:
            return StepOutcome("needs_clarification", "selector", before_revision=before.revision)
        if selected not in READ_ONLY_TOOLS and not _matches_consent(consent, user_request, before, selected):
            return StepOutcome(
                "needs_confirmation", "selector", selected_tool=selected, before_revision=before.revision
            )

        try:
            invocation_prompt = render_invocation(
                self.tokenizer, current_input, self.tools, selected
            )
        except ContractError:
            return StepOutcome("budget_or_contract_rejected", "invocation", before_revision=before.revision)
        try:
            invocation_text = backend.complete("invocation", invocation_prompt.prompt)
        except Exception:
            return StepOutcome("model_unavailable", "invocation", before_revision=before.revision)
        try:
            call = parse_invocation(invocation_text, selected, self.tools)
        except (ContractError, TypeError, AttributeError):
            return StepOutcome("invalid_model_output", "invocation", before_revision=before.revision)
        try:
            if scene.snapshot() != before:
                return StepOutcome("state_changed", "invocation", before_revision=before.revision)
        except Exception:
            return StepOutcome("state_unavailable", "invocation", before_revision=before.revision)

        key = _idempotency_key(user_request, before, selected, call["arguments"])
        if key in self._dispatched_keys:
            return StepOutcome("duplicate_prevented", "execution", before_revision=before.revision)
        # Mark before dispatch: if a receipt is lost, never guess whether Rhino applied it.
        self._dispatched_keys.add(key)
        try:
            receipt = executor.simulate_call(
                selected, call["arguments"], expected_state=before, idempotency_key=key
            )
            after = scene.snapshot()
        except Exception:
            return StepOutcome("execution_uncertain", "execution", before_revision=before.revision)
        expected_revision = before.revision if selected in READ_ONLY_TOOLS else before.revision + 1
        if (
            not isinstance(receipt, ExecutionReceipt)
            or receipt.previous_revision != before.revision
            or receipt.next_revision != expected_revision
            or after.revision != receipt.next_revision
            or after.scene_sha256 != receipt.next_scene_sha256
            or (selected in READ_ONLY_TOOLS and after != before)
            or (selected not in READ_ONLY_TOOLS and after.scene_sha256 == before.scene_sha256)
        ):
            return StepOutcome("execution_uncertain", "execution", before_revision=before.revision)
        return StepOutcome(
            "read_completed" if selected in READ_ONLY_TOOLS else "mutation_completed",
            "execution",
            selected_tool=selected,
            before_revision=before.revision,
            after_revision=after.revision,
        )
