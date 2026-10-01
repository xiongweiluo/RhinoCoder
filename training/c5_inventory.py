"""C5-only canonical presentation of the already-frozen public tools.

The Mac/Python 3.13 freeze had cleaned docstrings. Linux/Python 3.11 registry
metadata retains indentation. Normalize descriptions only, then require the
exact original schema digest. Never modify the historical/shared R loader.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json

from training.tool_schema_inventory import load_public_mcp_tools as _public

EXPECTED_SCHEMA_SHA256 = "151c5453bf92f83343e93e53013bfc8f3518e5b6a7e9e2fc49e97ba863b0637d"


def canonical_inventory(tools):
    tools = copy.deepcopy(tools)
    for tool in tools:
        tool["function"]["description"] = inspect.cleandoc(tool["function"]["description"]).strip()
    raw = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SCHEMA_SHA256:
        raise ValueError("C5 canonical inventory differs from original frozen schema")
    return tools


def load_public_mcp_tools():
    return canonical_inventory(_public())
