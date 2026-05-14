"""
mcp_server/main.py  —  运行在外部 Python 3.10+ 环境

RhinoCoder MCP Server 主入口。

架构
────────────────────────────────────────────────────────────────────
[Claude Desktop / Agent]
      │  MCP stdio transport
      ▼
[本文件: FastMCP("RhinoCoder")]
      │  动态加载四大家族 schemas_*.register(mcp, call_rhino)
      │  共 22 个 @mcp.tool() 工具挂载完毕
      │  POST http://127.0.0.1:8080/<endpoint>  via call_rhino()
      ▼
[rhino_listener/listener_main.py  —  Rhino 内部 HTTP Listener]
────────────────────────────────────────────────────────────────────

启动方式（Claude Desktop claude_desktop_config.json）:
    {
      "mcpServers": {
        "rhinocoder": {
          "command": "python",
          "args": ["/path/to/RhinoCoder/plugin/mcp_server/main.py"]
        }
      }
    }

前提: Rhino 8 内已执行 listener_main.start_listener()

设计约束：
  - logger 必须输出到 stderr，stdout 专属于 MCP stdio 协议帧。
  - 严禁在此文件顶层 import rhinoscriptsyntax / Rhino / scriptcontext。
"""

from __future__ import annotations

import logging
import sys

# ---------------------------------------------------------------------------
# Logging —— 必须输出到 stderr
# stdio transport 使用 stdout 传输 MCP 协议数据，任何写入 stdout 的日志
# 都会破坏协议帧，导致 Claude Desktop 解析失败。
# ---------------------------------------------------------------------------
logger = logging.getLogger("rhinocoder.mcp_server")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    _log_handler = logging.StreamHandler(sys.stderr)
    _log_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(_log_handler)

# ---------------------------------------------------------------------------
# 依赖检查
# ---------------------------------------------------------------------------
try:
    import httpx  # noqa: F401
except ImportError:
    logger.critical("缺少依赖: pip install httpx")
    sys.exit(1)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    logger.critical("缺少依赖: pip install mcp")
    sys.exit(1)

# ---------------------------------------------------------------------------
# HTTP 客户端（封装所有对 Rhino Listener 的网络通信）
# ---------------------------------------------------------------------------
from _client import call_rhino  # noqa: E402

# ---------------------------------------------------------------------------
# FastMCP 实例
# ---------------------------------------------------------------------------
mcp = FastMCP("RhinoCoder")

# ---------------------------------------------------------------------------
# 动态加载四大家族 Schema 模块，调用各自的 register() 挂载工具
# ---------------------------------------------------------------------------
import schemas_geometry   # noqa: E402
import schemas_transform  # noqa: E402
import schemas_property   # noqa: E402
import schemas_perception # noqa: E402

_SCHEMA_MODULES = [
    schemas_geometry,
    schemas_transform,
    schemas_property,
    schemas_perception,
]

for _mod in _SCHEMA_MODULES:
    _mod.register(mcp, call_rhino)

del _mod  # 清理循环变量


# ---------------------------------------------------------------------------
# 启动横幅（stderr，供调试确认）
# ---------------------------------------------------------------------------
def _log_startup_banner() -> None:
    """打印已注册工具清单。仅在 __main__ 入口调用，避免 import 时产生副作用。"""
    _tools_by_family = {
        "geometry":   [
            "create_sphere", "create_box", "create_cylinder", "create_line",
            "create_circle", "extrude_curve_straight", "boolean_difference",
        ],
        "transform":  [
            "move_object", "rotate_object", "scale_object", "align_objects",
            "distribute_objects", "group_objects", "place_on_at", "undo_last_action",
        ],
        "property":   ["set_object_layer", "set_object_color"],
        "perception": [
            "get_selected_objects", "get_objects_by_name", "get_object_info",
            "get_bounding_box", "get_scene_summary",
        ],
    }
    total = sum(len(v) for v in _tools_by_family.values())
    sep = "=" * 68
    logger.info(sep)
    logger.info("  RhinoCoder MCP Server 启动（stdio transport）")
    logger.info("  已注册工具（共 %d 个）：", total)
    for family, tools in _tools_by_family.items():
        logger.info("    [%s] %s", family, ", ".join(tools))
    logger.info("  等待 MCP 客户端连接…")
    logger.info(sep)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _log_startup_banner()
    mcp.run(transport="stdio")
