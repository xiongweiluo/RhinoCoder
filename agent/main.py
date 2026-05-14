"""
agent/main.py  —  RhinoCoder Agent 主控入口

Sprint 2 : --test-draw   直连 MCP 物理链路，不经过 LLM
Sprint 3 : --prompt <指令>  DeepSeek LLM + MCP 工具调用完整循环

用法:
    # 链路测试（需先在 Rhino 中执行 start_listener()）
    python agent/main.py --test-draw

    # LLM 完整链路（需设置 DEEPSEEK_API_KEY 并启动 Rhino Listener）
    python agent/main.py --prompt "帮我在原点画一个半径为 50 的球"

    # 查看帮助
    python agent/main.py --help
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# 确保无论从哪里调用，PROJECT_ROOT 都在 sys.path 中（以便 `from agent.llm import ...` 能找到模块）
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import typer
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ---------------------------------------------------------------------------
# 路径 & 环境变量
# ---------------------------------------------------------------------------
# 从项目根目录的 .env 文件加载环境变量（不覆盖已有 shell 变量）
load_dotenv(PROJECT_ROOT / ".env", override=False)
MCP_SERVER_SCRIPT = PROJECT_ROOT / "plugin" / "mcp_server" / "main.py"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    # MCP SDK / httpx / anyio 的内部日志平时只看 WARNING，--verbose 时全开
    sdk_level = logging.DEBUG if verbose else logging.WARNING
    for noisy in ("mcp", "httpx", "httpcore", "anyio"):
        logging.getLogger(noisy).setLevel(sdk_level)


logger = logging.getLogger("rhinocoder.agent")

# ---------------------------------------------------------------------------
# Phase 标记辅助（统一输出格式，便于日志对齐）
# ---------------------------------------------------------------------------
_W = 10  # 标签宽度

def _echo(phase: str, msg: str, err: bool = False) -> None:
    """typer.echo 包装：左对齐 phase 标签，保持视觉一致。"""
    typer.echo(f"[{phase:<{_W}}] {msg}", err=err)


# ---------------------------------------------------------------------------
# MCP 会话核心逻辑
# ---------------------------------------------------------------------------
async def _run_test_draw_session() -> int:
    """
    以 stdio 子进程方式启动外部 MCP Server，执行以下步骤：
      1. 启动子进程 & TCP-like 握手
      2. list_tools() —— 发现可用工具
      3. call_tool("create_sphere", radius=20.0)
      4. 解析并打印结果

    返回 exit code：0 = 成功，非 0 = 失败。
    """
    # ── 前置检查 ─────────────────────────────────────────────────────────
    if not MCP_SERVER_SCRIPT.exists():
        _echo("SETUP", f"MCP Server 脚本不存在: {MCP_SERVER_SCRIPT}", err=True)
        _echo("SETUP", "请确认 plugin/mcp_server/main.py 已创建。", err=True)
        return 1

    server_params = StdioServerParameters(
        command=sys.executable,          # 与主程序共享同一 venv
        args=[str(MCP_SERVER_SCRIPT)],
        # env=None → 继承父进程完整环境变量（包含 VIRTUAL_ENV、PATH 等）
    )

    _echo("SETUP", f"Python      : {sys.executable}")
    _echo("SETUP", f"MCP Server  : plugin/mcp_server/main.py")

    # ── 建立连接 ─────────────────────────────────────────────────────────
    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            _echo("CONNECT", "子进程已启动，正在进行 MCP 握手…")

            async with ClientSession(read_stream, write_stream) as session:

                # 1. initialize —— 交换协议版本与 capabilities
                init_result = await session.initialize()
                server_info = getattr(init_result, "serverInfo", None)
                srv_name    = getattr(server_info, "name",    "unknown")
                srv_version = getattr(server_info, "version", "?")
                _echo("CONNECT", f"握手成功 ✓  server={srv_name}  version={srv_version}")

                # 2. list_tools —— 确认目标工具已注册
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]
                _echo("DISCOVER", f"可用工具: {tool_names}")
                logger.debug("工具详情: %s", tools_result.tools)

                target_tool = "create_sphere"
                if target_tool not in tool_names:
                    _echo(
                        "ERROR",
                        f"{target_tool} 不在工具列表中，"
                        "请检查 rhinocoder_mcp_server.py 是否正确注册了该工具。",
                        err=True,
                    )
                    return 1

                # 3. call_tool —— 硬编码参数，直接发起调用
                arguments = {"radius": 20.0}
                _echo("INVOKE", f"{target_tool}(radius={arguments['radius']})  → 等待 Rhino 主线程…")
                logger.debug("发起 call_tool: name=%s  arguments=%s", target_tool, arguments)

                call_result = await session.call_tool(target_tool, arguments=arguments)

                # 4. 解析结果
                text_lines = [
                    item.text
                    for item in call_result.content
                    if hasattr(item, "text") and item.text
                ]
                full_text = "\n".join(text_lines)

                if call_result.isError:
                    _echo("RESULT", "✗ 工具调用失败", err=True)
                    for line in text_lines:
                        _echo("RESULT", f"  {line}", err=True)
                    logger.error("create_sphere 失败: %s", full_text)
                    return 1

                _echo("RESULT", "✓ 工具调用成功")
                for line in text_lines:
                    _echo("RESULT", f"  {line}")
                logger.info("create_sphere 返回: %s", full_text)
                return 0

    # ── 错误处理 ─────────────────────────────────────────────────────────
    except FileNotFoundError:
        _echo("ERROR", f"找不到 Python 解释器: {sys.executable}", err=True)
        return 1
    except ConnectionError as exc:
        _echo("ERROR", f"MCP 连接异常: {exc}", err=True)
        logger.exception("MCP 连接失败")
        return 1
    except Exception as exc:
        _echo("ERROR", f"{type(exc).__name__}: {exc}", err=True)
        logger.exception("run_test_draw 意外异常")
        return 1


# ---------------------------------------------------------------------------
# RhinoCoderAgent —— 主控逻辑聚合点
#
# Sprint 2 : test_draw()  直连 MCP，不经 LLM
# Sprint 3+: run(prompt)  LLM + Router 完整循环
# ---------------------------------------------------------------------------
class RhinoCoderAgent:

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    # ── Sprint 2 ─────────────────────────────────────────────────────────
    async def test_draw(self) -> int:
        """
        直接调用 MCP 工具，绕过 LLM，用于验证物理链路。
        """
        return await _run_test_draw_session()

    # ── Sprint 3: DeepSeek LLM + MCP 完整循环 ───────────────────────────
    async def run(self, prompt: str) -> int:
        """
        完整 Agent 循环:
          Step 1  MCP 握手 + 工具发现
          Step 2  DeepSeek LLM 推理（含工具调用）
          Step 3  MCP call_tool 执行
          Step 4  将工具结果反馈 LLM，生成最终自然语言回复

        返回 exit code: 0 = 成功, 非 0 = 失败
        """
        from agent.llm import run_agent
        return await run_agent(prompt)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="rhinocoder",
    help="RhinoCoder Agent — Rhino 8 AI 编程助手主控入口",
    add_completion=False,
    pretty_exceptions_show_locals=False,
    rich_markup_mode=None,
)


@app.command()
def main(
    test_draw: bool = typer.Option(
        False,
        "--test-draw",
        help=(
            "[Sprint 2] 直连测试：以子进程启动 MCP Server，"
            "调用 create_sphere(radius=20.0)，不经过任何 LLM。"
            "需先在 Rhino 中执行 rhino_http_listener.start_listener()。"
        ),
    ),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt", "-p",
        help="[Sprint 3+] 向 Agent 发送自然语言指令，触发完整 LLM + Router + MCP 循环。",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="输出 DEBUG 级别日志（包含 MCP SDK 内部日志）。",
    ),
) -> None:
    """RhinoCoder Agent — Rhino 8 AI 编程助手。"""
    _setup_logging(verbose)
    agent = RhinoCoderAgent(verbose=verbose)

    # ── --test-draw ──────────────────────────────────────────────────────
    if test_draw:
        typer.echo("=" * 55)
        typer.echo("  RhinoCoder  Sprint 2  MCP 链路测试")
        typer.echo(f"  目标工具 : create_sphere(radius=20.0)")
        typer.echo(f"  前提     : Rhino 已运行 start_listener()")
        typer.echo("=" * 55)

        exit_code = asyncio.run(agent.test_draw())

        typer.echo("=" * 55)
        status = "✓ 通过" if exit_code == 0 else "✗ 失败"
        typer.echo(f"  测试结果 : {status}")
        typer.echo("=" * 55)
        raise typer.Exit(exit_code)

    # ── --prompt（Sprint 3）──────────────────────────────────────────────
    if prompt is not None:
        typer.echo("=" * 55)
        typer.echo("  RhinoCoder  Sprint 3  LLM + MCP 完整链路")
        typer.echo(f"  Prompt : {prompt}")
        typer.echo(f"  前提   : Rhino 已运行 start_listener()")
        typer.echo(f"           DEEPSEEK_API_KEY 已设置")
        typer.echo("=" * 55)

        exit_code = asyncio.run(agent.run(prompt))

        typer.echo("=" * 55)
        status = "✓ 完成" if exit_code == 0 else "✗ 失败"
        typer.echo(f"  结果   : {status}")
        typer.echo("=" * 55)
        raise typer.Exit(exit_code)

    # ── 无参数：提示用法 ──────────────────────────────────────────────────
    typer.echo("未指定任何命令，请使用 --help 查看选项。")
    raise typer.Exit(0)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app()
