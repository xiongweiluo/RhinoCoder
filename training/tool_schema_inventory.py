"""Read public MCP tool definitions without starting Rhino or the MCP server."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def load_public_mcp_tools() -> list[dict[str, Any]]:
    """Mirror the Agent's MCP-to-OpenAI schema conversion for offline audits."""

    plugin_path = str(ROOT / "plugin/mcp_server")
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)
    import main  # type: ignore[import-not-found]  # noqa: PLC0415
    if Path(main.__file__).resolve() != ROOT / "plugin/mcp_server/main.py":
        raise RuntimeError("main module does not resolve to the public MCP server")

    result = []
    for tool in main.mcp._tool_manager.list_tools():
        schema = tool.parameters
        if not isinstance(schema, dict):
            schema = {}
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": schema, "required": []}
        result.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": (tool.description or "").strip(),
                "parameters": schema,
            },
        })
    return result
