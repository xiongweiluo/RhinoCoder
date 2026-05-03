"""
agent/llm.py  —  Sprint 3: DeepSeek LLM 层

职责:
  - 配置 DeepSeek 客户端（兼容 OpenAI SDK）
  - MCP 工具定义 → OpenAI tools schema 转换
  - Agent 主循环：prompt → MCP 工具发现 → LLM 推理 → 工具执行 → 最终回复
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI, AuthenticationError, APIConnectionError, APIStatusError

logger = logging.getLogger("rhinocoder.llm")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent
MCP_SERVER_SCRIPT = PROJECT_ROOT / "plugin" / "rhinocoder_mcp_server.py"

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_TOOL_ROUNDS = 30  # 防止工具调用无限循环


# ---------------------------------------------------------------------------
# 控制台输出辅助
# ---------------------------------------------------------------------------
_W = 12

def _echo(phase: str, msg: str, err: bool = False) -> None:
    import typer
    typer.echo(f"[{phase:<{_W}}] {msg}", err=err)


# ---------------------------------------------------------------------------
# 工具模式转换：MCP → OpenAI
# ---------------------------------------------------------------------------
def mcp_tools_to_openai(tools: list[Any]) -> list[dict]:
    """
    将 MCP list_tools() 返回的工具列表转换为 OpenAI Chat Completions 的 tools 格式。

    MCP Tool 字段:
        .name         str
        .description  Optional[str]
        .inputSchema  dict  (JSON Schema: type="object", properties, required)

    OpenAI tools 格式:
        [{"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}]
    """
    result = []
    for tool in tools:
        schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
        # 确保 schema 是合法的 JSON Schema object
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


# ---------------------------------------------------------------------------
# DeepSeek 客户端工厂
# ---------------------------------------------------------------------------
def make_deepseek_client() -> AsyncOpenAI:
    """
    从环境变量 DEEPSEEK_API_KEY 读取密钥，返回配置好的 AsyncOpenAI 客户端。
    若密钥缺失则抛出 EnvironmentError（由调用方统一处理）。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "未找到 DEEPSEEK_API_KEY 环境变量。\n"
            "请设置：export DEEPSEEK_API_KEY=your_key\n"
            "或在项目根目录创建 .env 文件并写入 DEEPSEEK_API_KEY=your_key"
        )
    return AsyncOpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


# ---------------------------------------------------------------------------
# 主 Agent 循环
# ---------------------------------------------------------------------------
async def run_agent(prompt: str) -> int:
    """
    完整 Agent 循环:
      1. 启动 MCP 子进程并握手
      2. list_tools() → 转换为 OpenAI schema
      3. 将 prompt + tools 发给 DeepSeek
      4. 若 LLM 决定调用工具 → 执行 → 将结果反馈给 LLM
      5. 输出最终自然语言回复

    返回 exit code: 0 = 成功, 非 0 = 失败
    """
    # ── 前置检查 ─────────────────────────────────────────────────────────
    if not MCP_SERVER_SCRIPT.exists():
        _echo("SETUP", f"MCP Server 脚本不存在: {MCP_SERVER_SCRIPT}", err=True)
        return 1

    try:
        client = make_deepseek_client()
    except EnvironmentError as exc:
        _echo("CONFIG", str(exc), err=True)
        return 1

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_SCRIPT)],
    )

    _echo("SETUP", f"MCP Server  : plugin/rhinocoder_mcp_server.py")
    _echo("SETUP", f"LLM Model   : {DEEPSEEK_MODEL}  @ {DEEPSEEK_BASE_URL}")

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            _echo("CONNECT", "MCP 子进程已启动，正在握手…")

            async with ClientSession(read_stream, write_stream) as session:

                # ── 1. MCP 握手 ────────────────────────────────────────────
                init_result = await session.initialize()
                server_info = getattr(init_result, "serverInfo", None)
                srv_name = getattr(server_info, "name", "unknown")
                _echo("CONNECT", f"MCP 握手成功 ✓  server={srv_name}")

                # ── 2. 工具发现 ────────────────────────────────────────────
                tools_result = await session.list_tools()
                mcp_tools = tools_result.tools
                tool_names = [t.name for t in mcp_tools]
                _echo("DISCOVER", f"可用工具: {tool_names}")

                openai_tools = mcp_tools_to_openai(mcp_tools)
                logger.debug("OpenAI tools schema: %s", json.dumps(openai_tools, ensure_ascii=False, indent=2))

                # ── 3. 构建初始消息 ────────────────────────────────────────
                messages: list[dict] = [
                    {
                        "role": "system",
                        "content": (
                            "你是 RhinoCoder，一个专业的 Rhino 3D 建模 AI 助手。"
                            "你可以通过工具直接在 Rhino 8 中创建几何体。"
                            "请根据用户的指令，决定是否调用工具，并给出清晰的操作结果说明。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]

                _echo("LLM", f"思考中…  prompt={prompt!r}")

                # ── 4. 工具调用循环 ────────────────────────────────────────
                for round_idx in range(1, MAX_TOOL_ROUNDS + 1):
                    logger.debug("LLM round %d, messages=%d", round_idx, len(messages))

                    try:
                        response = await client.chat.completions.create(
                            model=DEEPSEEK_MODEL,
                            messages=messages,
                            tools=openai_tools if openai_tools else None,
                            tool_choice="auto" if openai_tools else None,
                        )
                    except AuthenticationError:
                        _echo("LLM", "API Key 无效，请检查 DEEPSEEK_API_KEY。", err=True)
                        return 1
                    except APIConnectionError as exc:
                        _echo("LLM", f"无法连接到 DeepSeek API: {exc}", err=True)
                        return 1
                    except APIStatusError as exc:
                        _echo("LLM", f"DeepSeek API 错误 {exc.status_code}: {exc.message}", err=True)
                        return 1

                    choice = response.choices[0]
                    finish_reason = choice.finish_reason
                    assistant_msg = choice.message

                    # 将助手消息加入历史（不管有无 tool_calls）
                    messages.append(assistant_msg.model_dump(exclude_unset=True))

                    # ── 4a. 无工具调用 → 输出最终回复 ──────────────────────
                    if finish_reason != "tool_calls" or not assistant_msg.tool_calls:
                        final_text = assistant_msg.content or "(无文字回复)"
                        _echo("RESULT", "✓ LLM 回复:")
                        for line in final_text.splitlines():
                            _echo("RESULT", f"  {line}")
                        return 0

                    # ── 4b. 有工具调用 → 逐一执行 ──────────────────────────
                    _echo("TOOL", f"LLM 决定调用 {len(assistant_msg.tool_calls)} 个工具 (第 {round_idx} 轮)")

                    for tc in assistant_msg.tool_calls:
                        fn_name = tc.function.name
                        try:
                            fn_args = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError:
                            fn_args = {}

                        _echo("INVOKE", f"{fn_name}({fn_args})")
                        logger.debug("call_tool: name=%s  args=%s", fn_name, fn_args)

                        # 执行 MCP 工具
                        call_result = await session.call_tool(fn_name, arguments=fn_args)

                        # 提取文本结果
                        text_lines = [
                            item.text
                            for item in call_result.content
                            if hasattr(item, "text") and item.text
                        ]
                        tool_output = "\n".join(text_lines) if text_lines else "(无返回内容)"

                        if call_result.isError:
                            _echo("INVOKE", f"  ✗ 工具执行失败: {tool_output}", err=True)
                        else:
                            for line in tool_output.splitlines():
                                _echo("INVOKE", f"  → {line}")

                        # 将工具结果反馈给 LLM
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_output,
                        })

                    _echo("LLM", "将工具结果反馈给 LLM，继续生成…")

                # 超过最大轮次
                _echo("RESULT", f"已达最大工具调用轮次 ({MAX_TOOL_ROUNDS})，终止循环。", err=True)
                return 1

    except FileNotFoundError:
        _echo("ERROR", f"找不到 Python 解释器: {sys.executable}", err=True)
        return 1
    except ConnectionError as exc:
        _echo("ERROR", f"MCP 连接异常: {exc}", err=True)
        return 1
    except Exception as exc:
        _echo("ERROR", f"{type(exc).__name__}: {exc}", err=True)
        logger.exception("run_agent 意外异常")
        return 1
