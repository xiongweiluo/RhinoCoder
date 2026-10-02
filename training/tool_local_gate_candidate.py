"""Isolated, offline-only model gate for the candidate tool selector.

This module is not imported by the live Agent, frozen C0-C4 evaluation, or
Rhino executor. It can observe a model's selection but has no tool-dispatch
API. A loopback URL, model response, or ``kind`` string is never evidence of
locality: only this adapter's verified, offline in-process load is accepted.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from agent.privacy import PrivacyAction, classify_request
from training.tool_contract_candidate import ContractError, parse_selection, render_selection, validate_inventory
from training.tool_controller_candidate import SceneState, StepOutcome, compose_step_input, task_sha256


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RHINO_GUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_LOAD_PERMIT = object()


class LocalGateError(ValueError):
    """The offline snapshot or its declared identity is not trustworthy."""


@dataclass(frozen=True)
class VerifiedSnapshot:
    """Operator-approved file hashes for one local model snapshot.

    The hash list must be frozen independently of the files being loaded. A
    manifest generated from untrusted files at load time proves nothing.
    """

    approved_root: Path
    snapshot_dir: Path
    file_sha256: Mapping[str, str]

    def approval_sha256(self) -> str:
        """Digest to freeze out of band, never derive from files during approval."""

        payload = json.dumps(
            {
                "approved_root": str(self.approved_root),
                "snapshot_dir": str(self.snapshot_dir),
                "file_sha256": dict(self.file_sha256),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify(self) -> Path:
        if not self.approved_root.is_absolute() or not self.snapshot_dir.is_absolute():
            raise LocalGateError("approved model paths must be absolute")
        try:
            root = self.approved_root.resolve(strict=True)
            snapshot = self.snapshot_dir.resolve(strict=True)
            if not root.is_dir() or not snapshot.is_dir():
                raise LocalGateError("local model root and snapshot must be directories")
            snapshot.relative_to(root)
        except (OSError, ValueError, RuntimeError) as exc:
            raise LocalGateError("model snapshot is not inside the approved local root") from exc

        expected = dict(self.file_sha256)
        if not expected or any(
            not isinstance(name, str)
            or not name
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            for name, digest in expected.items()
        ):
            raise LocalGateError("invalid or empty approved model manifest")
        if "config.json" not in expected or not any(
            name.endswith(".safetensors") for name in expected
        ) or not any(name in expected for name in ("tokenizer.json", "tokenizer.model")):
            raise LocalGateError("manifest lacks model weights or tokenizer files")

        observed: set[str] = set()
        try:
            for entry in snapshot.rglob("*"):
                if entry.is_dir():
                    if entry.is_symlink():
                        raise LocalGateError("symlinked model directory is forbidden")
                    continue
                if not entry.is_file():
                    raise LocalGateError("non-file model snapshot entry")
                resolved = entry.resolve(strict=True)
                resolved.relative_to(root)
                name = entry.relative_to(snapshot).as_posix()
                if name not in expected:
                    raise LocalGateError("unlisted model snapshot file")
                digest = hashlib.sha256()
                with entry.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected[name]:
                    raise LocalGateError("model snapshot hash mismatch")
                observed.add(name)
        except (OSError, ValueError, RuntimeError) as exc:
            if isinstance(exc, LocalGateError):
                raise
            raise LocalGateError("model snapshot cannot be verified locally") from exc
        if observed != set(expected):
            raise LocalGateError("approved model manifest does not match snapshot files")
        return snapshot


def _transformers_loaders() -> tuple[Any, Any]:
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise LocalGateError("offline Transformers runtime is unavailable") from exc
    return AutoTokenizer, AutoModelForCausalLM


class OfflineTransformersBackend:
    """In-process model loaded from an independently hashed local snapshot."""

    __slots__ = ("_permit", "tokenizer", "model")

    def __init__(self, permit: object, tokenizer: Any, model: Any) -> None:
        if permit is not _LOAD_PERMIT:
            raise LocalGateError("backend must be constructed by the offline loader")
        self._permit = permit
        self.tokenizer = tokenizer
        self.model = model

    @classmethod
    def load(
        cls, manifest: VerifiedSnapshot, *, operator_approved_sha256: str
    ) -> OfflineTransformersBackend:
        if cls is not OfflineTransformersBackend or not isinstance(manifest, VerifiedSnapshot):
            raise LocalGateError("unsupported offline backend configuration")
        if (
            not isinstance(operator_approved_sha256, str)
            or not _SHA256.fullmatch(operator_approved_sha256)
            or not secrets.compare_digest(manifest.approval_sha256(), operator_approved_sha256)
        ):
            raise LocalGateError("operator approval does not match model manifest")
        snapshot = manifest.verify()  # No model loader is called before identity verification.
        tokenizer_loader, model_loader = _transformers_loaders()
        source = str(snapshot)
        common = {"local_files_only": True, "trust_remote_code": False, "token": None}
        tokenizer = tokenizer_loader.from_pretrained(source, **common)
        model = model_loader.from_pretrained(
            source, **common, use_safetensors=True, device_map="auto", dtype="auto"
        )
        model.eval()
        return cls(_LOAD_PERMIT, tokenizer, model)

    def _generate(self, prompt: str, *, max_new_tokens: int) -> str:
        encoded = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        inputs = {name: value.to(self.model.device) for name, value in encoded.items()}
        prompt_length = int(inputs["input_ids"].shape[-1])
        output = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )
        return self.tokenizer.decode(output[0][prompt_length:], skip_special_tokens=False)

    def complete(self, stage: str, prompt: str) -> str:
        if stage != "selector" or not isinstance(prompt, str) or not prompt:
            raise LocalGateError("only a nonempty selector prompt is permitted")
        return self._generate(prompt, max_new_tokens=128)

    def invoke(self, prompt: str) -> str:
        """Generate one strict invocation only in the separate controlled path."""

        if not isinstance(prompt, str) or not prompt:
            raise LocalGateError("nonempty invocation prompt required")
        return self._generate(prompt, max_new_tokens=512)


class SceneProvider(Protocol):
    def snapshot(self) -> SceneState: ...


class LocalSelectionGate:
    """Fail-closed preflight and selector probe; never executes a Rhino tool."""

    def __init__(self, tools: Sequence[Mapping[str, Any]]) -> None:
        self.tools = list(tools)
        validate_inventory(self.tools)

    def probe(self, user_request: str, *, scene: SceneProvider, backend: object) -> StepOutcome:
        if type(backend) is not OfflineTransformersBackend or backend._permit is not _LOAD_PERMIT:
            return StepOutcome("route_rejected", "preflight")
        try:
            if isinstance(user_request, str) and _RHINO_GUID.search(user_request):
                raise ContractError("raw Rhino GUID in task")
            before = scene.snapshot()
            current_input = compose_step_input(user_request, before)
        except Exception:
            return StepOutcome("state_rejected", "preflight")
        try:
            action = classify_request(current_input).action
        except Exception:
            return StepOutcome("privacy_unavailable", "preflight", before_revision=before.revision)
        if action is PrivacyAction.BLOCK:
            return StepOutcome("privacy_blocked", "preflight", before_revision=before.revision)
        if action not in {PrivacyAction.ALLOW_CLOUD, PrivacyAction.MINIMIZE_CLOUD, PrivacyAction.FORCE_LOCAL}:
            return StepOutcome("privacy_unavailable", "preflight", before_revision=before.revision)

        try:
            prompt = render_selection(backend.tokenizer, current_input, self.tools).prompt
        except Exception:
            return StepOutcome("budget_or_contract_rejected", "selector", before_revision=before.revision)
        try:
            response = backend.complete("selector", prompt)
        except Exception:
            return StepOutcome("model_unavailable", "selector", before_revision=before.revision)
        try:
            selected = parse_selection(response, self.tools)
        except (ContractError, TypeError, AttributeError):
            return StepOutcome("invalid_model_output", "selector", before_revision=before.revision)
        try:
            if scene.snapshot() != before:
                return StepOutcome("state_changed", "selector", before_revision=before.revision)
        except Exception:
            return StepOutcome("state_unavailable", "selector", before_revision=before.revision)
        if selected is None:
            return StepOutcome("needs_clarification", "selector", before_revision=before.revision)
        # This is an observation, never a write permission or dispatch decision.
        return StepOutcome(
            "selection_observed", "selector", selected_tool=selected,
            before_revision=before.revision, task_sha256=task_sha256(user_request),
            before_scene_sha256=before.scene_sha256,
        )
