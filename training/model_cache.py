"""Shared Hugging Face cache and strict-offline loading policy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from training.config import ReadinessError, project_path


MODEL_CACHE_ENV = "RHINOCODER_MODEL_CACHE"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _truthy_environment(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def resolve_model_cache(
    cache_dir: str | Path | None = None,
    *,
    default: str | Path | None = None,
) -> Path | None:
    """Resolve CLI override, RhinoCoder env, then an optional project-local default."""

    value: str | Path | None = cache_dir
    if value is None:
        value = os.getenv(MODEL_CACHE_ENV) or None
    if value is None:
        value = default
    if value is None:
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else project_path(path).resolve()


def strict_offline_requested(explicit: bool | None = None) -> bool:
    """Treat either supported Hugging Face offline switch as authoritative."""

    return bool(explicit) or _truthy_environment("HF_HUB_OFFLINE") or _truthy_environment(
        "TRANSFORMERS_OFFLINE"
    )


def pretrained_load_kwargs(
    *,
    cache_dir: str | Path | None = None,
    default_cache: str | Path | None = None,
    local_files_only: bool | None = None,
) -> dict[str, Any]:
    """Return identical cache/offline/token kwargs for model and tokenizer loaders."""

    offline = strict_offline_requested(local_files_only)
    resolved_cache = resolve_model_cache(cache_dir, default=default_cache)
    kwargs: dict[str, Any] = {
        "local_files_only": offline,
        "token": None if offline else os.getenv("HF_TOKEN") or None,
    }
    if resolved_cache is not None:
        kwargs["cache_dir"] = resolved_cache
    return kwargs


def pinned_pretrained_source(
    model_id: str,
    revision: str,
    load_kwargs: dict[str, Any],
) -> tuple[str, str | None]:
    """Use the exact cached snapshot path offline while callers retain ID/revision lineage."""

    if not load_kwargs.get("local_files_only"):
        return model_id, revision
    cache_dir = load_kwargs.get("cache_dir")
    if cache_dir is None:
        return model_id, revision
    repository_cache = "models--" + model_id.replace("/", "--")
    snapshot = Path(cache_dir) / repository_cache / "snapshots" / revision
    if not snapshot.is_dir():
        raise ReadinessError(
            f"pinned offline snapshot is not cached under {MODEL_CACHE_ENV}: {snapshot}"
        )
    return str(snapshot), None
