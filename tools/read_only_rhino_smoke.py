#!/usr/bin/env python3
"""通过 MCP 只读调用 Rhino Scene Summary，不输出或保存场景内容。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER = ROOT / "plugin" / "mcp_server" / "main.py"


async def _smoke() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)])
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            if len(names) != 23 or "get_scene_summary" not in names:
                raise RuntimeError(f"MCP 工具发现异常: count={len(names)}")
            result = await session.call_tool("get_scene_summary", arguments={})
            text = "\n".join(
                item.text for item in result.content if hasattr(item, "text") and item.text
            )
            if result.isError or not text.startswith("场景中共有"):
                raise RuntimeError("get_scene_summary 只读调用失败")
    print("Read-only Rhino smoke passed (23 tools, scene content not printed).")


def main() -> int:
    try:
        asyncio.run(_smoke())
    except Exception as exc:
        print(f"Read-only Rhino smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
