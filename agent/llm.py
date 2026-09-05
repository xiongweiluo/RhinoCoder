"""
agent/llm.py  —  Sprint 3: DeepSeek LLM 层

职责:
  - 配置 DeepSeek 客户端（兼容 OpenAI SDK）
  - MCP 工具定义 → OpenAI tools schema 转换
  - Agent 主循环：prompt → MCP 工具发现 → LLM 推理 → 工具执行 → 最终回复
"""

from __future__ import annotations

import asyncio
import ast
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import APITimeoutError, AsyncOpenAI

from agent.model_backends import BackendError, ModelBackend, build_default_backends
from agent.pricing import calculate_cost, resolve_model_pricing
from agent.router import RouteContext, RouterConfig, select_route
from agent.runtime import (
    AgentRunResult,
    CancellationToken,
    EventCallback,
    EventEmitter,
    RunCancelled,
    RunError,
    RunMetrics,
    RunStatus,
    ToolCallRecord,
    monotonic_ms,
    new_run_id,
    utc_now,
)

logger = logging.getLogger("rhinocoder.llm")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent
MCP_SERVER_SCRIPT = Path(
    os.environ.get(
        "RHINOCODER_MCP_SERVER_SCRIPT",
        str(PROJECT_ROOT / "plugin" / "mcp_server" / "main.py"),
    )
).expanduser().resolve()

DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
MAX_TOOL_ROUNDS = 30  # 防止工具调用无限循环
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "90"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "1"))
CREATE_TOOLS = {
    "create_sphere",
    "create_box",
    "create_cylinder",
    "create_line",
    "create_circle",
    "extrude_curve_straight",
    "boolean_difference",
}
GUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
ERROR_CODE_PATTERN = re.compile(
    r"^(?:失败|错误)\s*\[([a-z][a-z0-9_.-]+)\]",
    re.IGNORECASE,
)


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
    return AsyncOpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def _system_prompt(closed_loop: bool) -> str:
    base = (
        "你是 RhinoCoder，一个专业、严谨的 Rhino 3D 建模 AI 助手。"
        "你通过调用工具直接在 Rhino 8 中创建并编辑几何体。\n\n"
        "【坐标系与单位约定】\n"
        "- Rhino 使用右手坐标系，Z 轴朝上（Z-up）。高度和叠放沿 +Z。\n"
        "- 世界原点为 (0,0,0)；未指定位置时新建几何体默认落在原点附近。\n"
        "- 颜色使用 0-255 RGB 三元组。尺寸和间距均为模型单位。\n"
        "- 群组操作使用 group_objects；修改既有要求时以最新要求为准。\n"
        "- get_scene_summary 的 type 是 Rhino 几何类别而不是语义形状名。"
    )
    if not closed_loop:
        return base + "\n请规划并执行用户任务，完成后给出清晰总结。"
    return base + (
        "\n\n【强制闭环：计算 - 执行 - 感知 - 纠错】\n"
        "1. 动手前规划尺寸、位置、颜色和空间关系。\n"
        "2. 调用工具执行。\n"
        "3. 完成后必须调用 get_scene_summary，核对数量、size、color、center、群组和空间关系。\n"
        "4. 发现偏差后使用 move_object、scale_object、set_object_color、delete_objects 或 undo_last_action 修正。\n"
        "5. 修正后再次调用 get_scene_summary；验证通过后才能输出最终总结。"
    )


def _update_usage(
    metrics: RunMetrics,
    response: Any,
    *,
    model: str = DEEPSEEK_MODEL,
    base_url: str = DEEPSEEK_BASE_URL,
) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    usage_data = usage.model_dump() if hasattr(usage, "model_dump") else {}
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    direct_hit = getattr(
        usage,
        "prompt_cache_hit_tokens",
        usage_data.get("prompt_cache_hit_tokens"),
    )
    direct_miss = getattr(
        usage,
        "prompt_cache_miss_tokens",
        usage_data.get("prompt_cache_miss_tokens"),
    )
    prompt_details = getattr(
        usage,
        "prompt_tokens_details",
        usage_data.get("prompt_tokens_details"),
    )
    if isinstance(prompt_details, dict):
        nested_hit = prompt_details.get("cached_tokens")
    else:
        nested_hit = getattr(prompt_details, "cached_tokens", None) if prompt_details else None
    cache_hit_tokens = int(direct_hit if direct_hit is not None else nested_hit or 0)
    if direct_miss is not None:
        cache_miss_tokens = int(direct_miss or 0)
    elif nested_hit is not None:
        cache_miss_tokens = max(prompt_tokens - cache_hit_tokens, 0)
    else:
        cache_miss_tokens = 0
    metrics.prompt_tokens += prompt_tokens
    metrics.prompt_cache_hit_tokens += cache_hit_tokens
    metrics.prompt_cache_miss_tokens += cache_miss_tokens
    metrics.completion_tokens += completion_tokens
    metrics.total_tokens += int(getattr(usage, "total_tokens", 0) or prompt_tokens + completion_tokens)
    pricing = resolve_model_pricing(model, base_url)
    if pricing is None:
        metrics.prompt_cache_unknown_tokens = max(
            metrics.prompt_tokens
            - metrics.prompt_cache_hit_tokens
            - metrics.prompt_cache_miss_tokens,
            0,
        )
        metrics.cost_estimate_status = "unconfigured"
        return
    cost = calculate_cost(
        prompt_tokens=metrics.prompt_tokens,
        completion_tokens=metrics.completion_tokens,
        cache_hit_tokens=metrics.prompt_cache_hit_tokens,
        cache_miss_tokens=metrics.prompt_cache_miss_tokens,
        pricing=pricing,
    )
    metrics.prompt_cache_unknown_tokens = cost.cache_unknown_tokens
    metrics.input_cost_lower_bound_usd = cost.input_cost_lower_bound_usd
    metrics.input_cost_upper_bound_usd = cost.input_cost_upper_bound_usd
    metrics.output_cost_usd = cost.output_cost_usd
    metrics.estimated_cost_lower_bound_usd = cost.total_cost_lower_bound_usd
    metrics.estimated_cost_upper_bound_usd = cost.total_cost_upper_bound_usd
    metrics.estimated_cost_usd = cost.estimated_cost_usd
    metrics.cost_estimate_status = cost.status


def _parse_scene_output(output: str) -> Optional[dict[str, Any]]:
    marker = "objects = "
    if marker not in output:
        return None
    try:
        objects = ast.literal_eval(output.split(marker, 1)[1].strip())
    except (SyntaxError, ValueError):
        return None
    if not isinstance(objects, list):
        return None
    return {"objects": objects, "total": len(objects), "capped": "已截取前 50 个" in output}


def _tool_output_error_code(output: str) -> Optional[str]:
    """识别 FastMCP 正常文本帧中承载的业务失败。"""
    text = output.strip()
    match = ERROR_CODE_PATTERN.search(text)
    if match:
        return match.group(1).lower()
    if text.startswith(("参数错误", "请求参数错误", "Missing field", "Invalid ")):
        return "tool.invalid_argument"
    if text.startswith(("失败", "错误")):
        return "tool.execution_failed"
    return None


def _flatten_exception_names(exc: BaseException) -> set[str]:
    names = {type(exc).__name__}
    nested = getattr(exc, "exceptions", None)
    if isinstance(nested, tuple):
        for item in nested:
            if isinstance(item, BaseException):
                names.update(_flatten_exception_names(item))
    cause = exc.__cause__ or exc.__context__
    if isinstance(cause, BaseException):
        names.update(_flatten_exception_names(cause))
    return names


def _classify_outer_exception(exc: BaseException) -> RunError:
    """把 stdio/MCP 进程退出从普通未捕获异常中分离出来。"""
    names = _flatten_exception_names(exc)
    mcp_exit_types = {
        "BrokenResourceError",
        "ClosedResourceError",
        "EndOfStream",
        "IncompleteReadError",
        "McpError",
        "ProcessLookupError",
    }
    if names & mcp_exit_types:
        return RunError(
            "mcp.process_exit",
            "MCP Server 连接已中断或子进程提前退出，请重试任务；若持续失败，请检查 MCP Server 日志。",
            recoverable=True,
        )
    return RunError("agent.unexpected", f"{type(exc).__name__}: {exc}", recoverable=False)


# ---------------------------------------------------------------------------
# 主 Agent 循环
# ---------------------------------------------------------------------------
async def run_agent(
    prompt: str,
    *,
    closed_loop: bool = True,
    event_callback: Optional[EventCallback] = None,
    cancellation_token: Optional[CancellationToken] = None,
    run_id: Optional[str] = None,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
    route_context: RouteContext | None = None,
    router_config: RouterConfig | None = None,
    backend_registry: Mapping[str, ModelBackend] | None = None,
) -> AgentRunResult:
    """
    完整 Agent 循环:
      1. 启动 MCP 子进程并握手
      2. list_tools() → 转换为 OpenAI schema
      3. 将 prompt + tools 发给 DeepSeek
      4. 若 LLM 决定调用工具 → 执行 → 将结果反馈给 LLM
      5. 输出最终自然语言回复

    返回结构化 AgentRunResult。结果对象仍支持旧式二元解包以兼容现有调用方。
    """
    actual_run_id = run_id or new_run_id()
    token = cancellation_token or CancellationToken()
    metrics = RunMetrics(started_at=utc_now())
    result = AgentRunResult(
        run_id=actual_run_id,
        status=RunStatus.RUNNING,
        metrics=metrics,
    )
    emitter = EventEmitter(actual_run_id, event_callback)
    started_ms = monotonic_ms()

    async def finish(
        status: RunStatus,
        *,
        error: Optional[RunError] = None,
        final_text: str = "",
    ) -> AgentRunResult:
        metrics.completed_at = utc_now()
        metrics.duration_ms = round(monotonic_ms() - started_ms, 2)
        result.status = status
        result.error = error
        result.final_text = final_text
        terminal_type = {
            RunStatus.COMPLETED: "run.completed",
            RunStatus.CANCELLED: "run.cancelled",
        }.get(status, "run.failed")
        payload: dict[str, Any] = {"status": status.value, "metrics": metrics.to_dict()}
        if error:
            payload["error"] = {
                "code": error.code,
                "message": error.message,
                "recoverable": error.recoverable,
            }
        await emitter.emit(terminal_type, payload)
        result.events = list(emitter.events)
        try:
            from agent.db import record_live_trace
            from agent.trace_store import build_trace_record

            record_live_trace(build_trace_record(prompt, result))
        except Exception as exc:
            logger.warning("运行结束后的 SQLite 审计镜像失败: %s", exc)
        return result

    try:
        backends = dict(
            backend_registry
            or build_default_backends(
                main_model=DEEPSEEK_MODEL,
                main_base_url=DEEPSEEK_BASE_URL,
                main_client_factory=make_deepseek_client,
                timeout_seconds=LLM_TIMEOUT_SECONDS,
                max_retries=LLM_MAX_RETRIES,
            )
        )
        routing = router_config or RouterConfig.from_env()
        decision = select_route(
            prompt,
            {name: backend.profile for name, backend in backends.items()},
            context=route_context,
            config=routing,
        )
        active_backend = backends[decision.selected_backend]
        remaining_fallbacks = routing.max_fallbacks if routing.fallback_enabled else 0
        result.route_decision = decision.to_dict()
    except (KeyError, ValueError) as exc:
        await emitter.emit(
            "run.started",
            {"prompt": prompt, "model": DEEPSEEK_MODEL, "closed_loop": closed_loop},
        )
        return await finish(
            RunStatus.FAILED,
            error=RunError("config.routing_invalid", str(exc), recoverable=True),
        )

    await emitter.emit(
        "run.started",
        {
            "prompt": prompt,
            "model": active_backend.profile.model,
            "backend": active_backend.profile.backend_id,
            "closed_loop": closed_loop,
        },
    )
    await emitter.emit("route.selected", decision.to_dict())

    async def complete_with_fallback(
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        nonlocal active_backend, remaining_fallbacks
        try:
            return await active_backend.complete(messages=messages, tools=tools)
        except BackendError as exc:
            fallback_name = decision.fallback_backend
            if not (
                exc.fallback_eligible
                and remaining_fallbacks > 0
                and fallback_name
                and fallback_name in backends
            ):
                raise
            previous = active_backend.profile.backend_id
            active_backend = backends[fallback_name]
            remaining_fallbacks -= 1
            decision.apply_fallback(active_backend.profile, exc.code)
            result.route_decision = decision.to_dict()
            await emitter.emit(
                "route.fallback",
                {
                    **decision.to_dict(),
                    "previous_backend": previous,
                    "safe_boundary": "planning_request",
                    "replayed_tool_calls": 0,
                },
            )
            return await active_backend.complete(messages=messages, tools=tools)

    # ── 前置检查 ─────────────────────────────────────────────────────────
    if not MCP_SERVER_SCRIPT.exists():
        message = f"MCP Server 脚本不存在: {MCP_SERVER_SCRIPT}"
        _echo("SETUP", message, err=True)
        return await finish(RunStatus.FAILED, error=RunError("setup.mcp_missing", message))

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_SCRIPT)],
    )

    _echo("SETUP", "MCP Server  : plugin/mcp_server/main.py")
    _echo(
        "SETUP",
        f"LLM Route   : {active_backend.profile.backend_id} / {active_backend.profile.model}",
    )

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
                        "content": _system_prompt(closed_loop),
                    },
                    {"role": "user", "content": prompt},
                ]
                result.messages = messages

                _echo("LLM", f"思考中…  prompt={prompt!r}")

                # ── 4. 工具调用循环 ────────────────────────────────────────
                scene_is_current = False
                awaiting_recheck = False
                unresolved_tool_error: Optional[RunError] = None
                for round_idx in range(1, max_tool_rounds + 1):
                    token.raise_if_cancelled()
                    metrics.tool_rounds = round_idx
                    logger.debug("LLM round %d, messages=%d", round_idx, len(messages))
                    await emitter.emit("planning.started", {"round": round_idx})

                    planning_started_ms = monotonic_ms()
                    try:
                        response = await complete_with_fallback(messages, openai_tools)
                    except BackendError as exc:
                        _echo("LLM", exc.message, err=True)
                        return await finish(
                            RunStatus.FAILED,
                            error=RunError(exc.code, exc.message, recoverable=exc.recoverable),
                        )

                    metrics.planning_ms = round(
                        metrics.planning_ms + monotonic_ms() - planning_started_ms,
                        2,
                    )
                    _update_usage(
                        metrics,
                        response,
                        model=active_backend.profile.model,
                        base_url=active_backend.base_url,
                    )

                    choice = response.choices[0]
                    finish_reason = choice.finish_reason
                    assistant_msg = choice.message

                    # 将助手消息加入历史（不管有无 tool_calls）
                    messages.append(assistant_msg.model_dump(exclude_unset=True))

                    # ── 4a. 无工具调用 → 输出最终回复 ──────────────────────
                    if finish_reason != "tool_calls" or not assistant_msg.tool_calls:
                        final_text = assistant_msg.content or "(无文字回复)"
                        if closed_loop and not scene_is_current:
                            if not awaiting_recheck:
                                metrics.corrections += 1
                                await emitter.emit(
                                    "correction.started",
                                    {
                                        "round": round_idx,
                                        "reason": "scene_check_required",
                                    },
                                )
                                awaiting_recheck = True
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "闭环尚未完成：请调用 get_scene_summary 验证当前最终场景；"
                                        "如果发现偏差先纠正并再次验证，然后再给出最终答复。"
                                    ),
                                }
                            )
                            _echo("VERIFY", "尚无有效的最终场景自检，继续执行闭环…")
                            continue
                        if unresolved_tool_error is not None and not scene_is_current:
                            _echo("RESULT", "工具错误尚未恢复，任务标记为失败。", err=True)
                            return await finish(
                                RunStatus.FAILED,
                                error=unresolved_tool_error,
                                final_text=final_text,
                            )
                        _echo("RESULT", "✓ LLM 回复:")
                        for line in final_text.splitlines():
                            _echo("RESULT", f"  {line}")
                        if active_backend.profile.backend_id == "local-mock":
                            return await finish(
                                RunStatus.FAILED,
                                error=RunError(
                                    "local.mock_only",
                                    "本地 Mock 后端只验证安全路由和接口，不执行建模任务。",
                                    recoverable=True,
                                ),
                                final_text=final_text,
                            )
                        return await finish(RunStatus.COMPLETED, final_text=final_text)

                    # ── 4b. 有工具调用 → 逐一执行 ──────────────────────────
                    _echo("TOOL", f"LLM 决定调用 {len(assistant_msg.tool_calls)} 个工具 (第 {round_idx} 轮)")

                    for tc in assistant_msg.tool_calls:
                        token.raise_if_cancelled()
                        fn_name = tc.function.name
                        try:
                            fn_args = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError:
                            fn_args = {}

                        if scene_is_current and fn_name != "get_scene_summary":
                            metrics.corrections += 1
                            await emitter.emit(
                                "correction.started",
                                {"round": round_idx, "tool": fn_name},
                            )
                            scene_is_current = False
                            awaiting_recheck = True

                        _echo("INVOKE", f"{fn_name}({fn_args})")
                        logger.debug("call_tool: name=%s  args=%s", fn_name, fn_args)

                        tool_started_ms = monotonic_ms()
                        tool_record = ToolCallRecord(
                            call_id=tc.id,
                            name=fn_name,
                            arguments=fn_args,
                            round_index=round_idx,
                            started_at=utc_now(),
                        )
                        result.tool_calls.append(tool_record)
                        metrics.tool_calls += 1
                        await emitter.emit(
                            "tool.started",
                            {"call_id": tc.id, "name": fn_name, "arguments": fn_args, "round": round_idx},
                        )

                        # 执行 MCP 工具
                        try:
                            call_result = await session.call_tool(fn_name, arguments=fn_args)
                        except Exception as exc:
                            tool_record.completed_at = utc_now()
                            tool_record.duration_ms = round(monotonic_ms() - tool_started_ms, 2)
                            metrics.tool_execution_ms = round(
                                metrics.tool_execution_ms + tool_record.duration_ms,
                                2,
                            )
                            tool_record.error_code = "mcp.call_failed"
                            tool_record.output = str(exc)
                            await emitter.emit(
                                "tool.completed",
                                {
                                    "call_id": tc.id,
                                    "name": fn_name,
                                    "success": False,
                                    "duration_ms": tool_record.duration_ms,
                                    "error": str(exc),
                                },
                            )
                            raise

                        # 提取文本结果
                        text_lines = [
                            item.text
                            for item in call_result.content
                            if hasattr(item, "text") and item.text
                        ]
                        tool_output = "\n".join(text_lines) if text_lines else "(无返回内容)"
                        tool_record.completed_at = utc_now()
                        tool_record.duration_ms = round(monotonic_ms() - tool_started_ms, 2)
                        metrics.tool_execution_ms = round(
                            metrics.tool_execution_ms + tool_record.duration_ms,
                            2,
                        )
                        semantic_error_code = _tool_output_error_code(tool_output)
                        tool_record.success = not bool(call_result.isError) and semantic_error_code is None
                        tool_record.output = tool_output
                        if not tool_record.success:
                            tool_record.error_code = semantic_error_code or "tool.execution_failed"
                            unresolved_tool_error = RunError(
                                tool_record.error_code,
                                tool_output,
                                recoverable=True,
                            )

                        if call_result.isError:
                            _echo("INVOKE", f"  ✗ 工具执行失败: {tool_output}", err=True)
                        else:
                            for line in tool_output.splitlines():
                                _echo("INVOKE", f"  → {line}")

                        await emitter.emit(
                            "tool.completed",
                            {
                                "call_id": tc.id,
                                "name": fn_name,
                                "success": tool_record.success,
                                "duration_ms": tool_record.duration_ms,
                                "output": tool_output,
                                "error_code": tool_record.error_code,
                                "error": tool_output if not tool_record.success else None,
                            },
                        )

                        if fn_name == "get_scene_summary":
                            parsed_scene = _parse_scene_output(tool_output)
                            check = {
                                "round": round_idx,
                                "call_id": tc.id,
                                "output": tool_output,
                                "scene_summary": parsed_scene,
                                "timestamp": utc_now(),
                                "success": tool_record.success and parsed_scene is not None,
                            }
                            result.scene_checks.append(check)
                            metrics.scene_checks += 1
                            metrics.scene_check_ms = round(
                                metrics.scene_check_ms + tool_record.duration_ms,
                                2,
                            )
                            scene_is_current = bool(tool_record.success and parsed_scene is not None)
                            awaiting_recheck = not scene_is_current
                            if scene_is_current:
                                unresolved_tool_error = None
                            await emitter.emit("scene.checked", check)

                        if fn_name in CREATE_TOOLS and tool_record.success:
                            for object_id in GUID_PATTERN.findall(tool_output):
                                if object_id not in result.created_object_ids:
                                    result.created_object_ids.append(object_id)

                        # 将工具结果反馈给 LLM
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_output,
                        })

                    _echo("LLM", "将工具结果反馈给 LLM，继续生成…")

                # 超过最大轮次
                message = f"已达最大工具调用轮次 ({max_tool_rounds})，终止循环。"
                _echo("RESULT", message, err=True)
                return await finish(
                    RunStatus.FAILED,
                    error=RunError("agent.max_rounds", message, recoverable=True),
                )

    except asyncio.CancelledError:
        token.cancel()
        message = "任务已由用户取消"
        _echo("CANCEL", message, err=True)
        return await finish(
            RunStatus.CANCELLED,
            error=RunError("run.cancelled", message, recoverable=True),
        )
    except RunCancelled as exc:
        _echo("CANCEL", str(exc), err=True)
        return await finish(
            RunStatus.CANCELLED,
            error=RunError("run.cancelled", str(exc), recoverable=True),
        )
    except FileNotFoundError:
        message = f"找不到 Python 解释器: {sys.executable}"
        _echo("ERROR", message, err=True)
        return await finish(RunStatus.FAILED, error=RunError("setup.python_missing", message))
    except ConnectionError as exc:
        message = f"MCP 连接异常: {exc}"
        _echo("ERROR", message, err=True)
        return await finish(
            RunStatus.FAILED,
            error=RunError("mcp.connection", message, recoverable=True),
        )
    except Exception as exc:
        run_error = _classify_outer_exception(exc)
        _echo("ERROR", run_error.message, err=True)
        logger.exception("run_agent 意外异常")
        return await finish(
            RunStatus.FAILED,
            error=run_error,
        )
