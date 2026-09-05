"""Backward-compatible imports for the unified model backend layer.

New code should import from :mod:`agent.model_backends` directly.
"""

from agent.model_backends import (
    BackendError,
    MockLocalBackend,
    ModelBackend,
    OpenAICompatibleBackend,
    build_default_backends,
)

__all__ = [
    "BackendError",
    "MockLocalBackend",
    "ModelBackend",
    "OpenAICompatibleBackend",
    "build_default_backends",
]
