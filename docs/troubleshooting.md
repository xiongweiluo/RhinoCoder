# Troubleshooting

## 快速诊断

在项目根目录运行：

```bash
python tools/doctor.py
```

## bootstrap 提示 Python 版本过低

RhinoCoder 0.2.0 支持 Python 3.11–3.13。macOS 上的 `python3` 可能仍指向旧系统解释器，先运行 `python3 --version`，然后显式指定新解释器：

```bash
RHINOCODER_PYTHON=/absolute/path/to/python3.13 ./scripts/bootstrap.sh
```

不要删除或覆盖系统 Python。安装脚本只会在项目目录创建 `.venv`。

## npm ci 提示 Node.js 版本不支持

前端构建需要 Node.js `^20.19.0` 或 `>=22.12.0`。升级 Node.js 后重新运行 `./scripts/bootstrap.sh`；发布依赖版本由 `agent/ui/package-lock.json` 固定。

## 锁定依赖安装失败

确认网络可访问 Python 与 npm 包源，并确认平台为 macOS、Python 为 3.11–3.13。不要直接修改锁文件绕过冲突；依赖升级需要同步更新 `requirements-lock.txt`、`package-lock.json` 和 `docs/version-manifest.json`，再运行 `./scripts/check.sh` 与 clean-room 验收。

若 MCP Server 报告 SDK 缺失或版本不兼容，运行 `python -m pip show mcp`。RhinoCoder `0.2.0` 固定使用官方 `mcp 1.29.1`，支持范围为 `>=1.0,<2.0`；同名 2.x 包不提供 `mcp.server.fastmcp`，不能用于本项目。

## 无法连接 Rhino Listener

1. 确认 Rhino 8 已启动。
2. 在 Rhino Script Editor 中运行 `plugin/start_rhinocoder_listener.py`。
3. 确认终端可以读取 `http://127.0.0.1:8080/health`。
4. 如果端口被占用，停止旧 Listener 后重新启动。

## reset_environment 被拒绝

该端点只允许评测流程调用。项目根目录 `.env` 中配置 `RHINOCODER_EVAL_TOKEN` 后，需要在 Rhino 中重新启动 Listener；启动过程会只读取该令牌，不会记录令牌值。运行评测器的终端必须读取同一份 `.env`。普通 UI 不应调用该端点。

运行 `python tools/doctor.py` 时应看到 `Rhino eval reset enabled`。如果仍显示 disabled，确认 Rhino 执行的是当前项目中的 `plugin/start_rhinocoder_listener.py`，然后重新启动 Listener。

推荐在 Rhino 命令行运行：

```text
_-ScriptEditor _Run "/absolute/path/to/RhinoCoder/plugin/start_rhinocoder_listener.py"
```

不要使用旧的 `RunPythonScript` 命令；部分 Rhino 安装会让它进入缺少现代标准库的旧 Python 引擎。

## UI 显示尚未构建

```bash
npm ci --prefix agent/ui
npm run build --prefix agent/ui
```

随后重新运行 `./scripts/start.sh`。

## Agent 报模型配置错误

复制 `.env.example` 为 `.env`，填写有效的 `DEEPSEEK_API_KEY`。不要将 `.env` 添加到 Git。

## 任务超时

- 检查 Rhino 是否打开了模态对话框。
- 检查是否有长时间几何操作阻塞主线程。
- LLM 超时会显示 `llm.timeout`；该轮没有产生新工具调用，可直接从 UI 重试。
- Rhino 主线程超时会显示 `rhino.main_thread_timeout`。查询和变更操作均只做有限网络重试；变更操作的全部尝试复用同一幂等键，Listener 会跳过已超时任务并重放超时结果，不会重复创建对象。

## MCP 子进程退出

UI 显示 `mcp.process_exit` 时，先点击“重试任务”。每次任务都会启动新的 MCP 子进程，瞬时退出通常无需重启 UI。若持续失败，运行 `python tools/doctor.py`，并检查 `plugin/mcp_server/main.py` 是否存在、Python 依赖是否完整。

## 参数或 GUID 无效

- `http.invalid_argument` 表示 GUID 格式或 Listener 请求参数不合法。
- `tool.invalid_argument` / `tool.execution_failed` 表示 MCP Schema 已拒绝缺失字段或错误类型。
- 修正 UI 指令中的对象来源和必填参数后重试；无效 GUID 与空参数会在进入 Rhino 主线程前被拒绝。

## Undo 提示成功但场景未变化

确认 Rhino 运行的是当前仓库中的 Listener，并在 Rhino 命令行重新执行启动脚本完成热重载。当前 Listener 会为创建、变换、属性修改和精准删除建立 Rhino Undo 事务；旧进程仍可能运行未包含该修复的代码。Undo 完成后 UI 会自动刷新 Scene Summary，可用对象数量和目标对象是否消失判断是否真正生效。

## 评测退出码为 3

这表示 Closed-loop Pass@1 低于默认 70% 发布门槛。JSON 与 Markdown 报告仍会生成，可从失败分类和断言明细定位问题。

## 评测退出码为 4

这表示余额耗尽、鉴权失败、配额不足或模型不可用等全局致命基础设施错误触发了熔断。报告会保留已经尝试的任务，并将剩余计划项标记为未运行；此时 Baseline 与 Closed-loop 不可比较。恢复模型服务后应重新运行完整基准。

## 成本显示为区间

DeepSeek 会在响应中提供缓存命中和未命中 token。新运行会保存这两个字段并精确计费；旧报告或不提供缓存拆分的兼容 API 只能根据总输入 token 计算严格上下界。可运行 `python tools/recalculate_benchmark_cost.py <result.json>` 重算历史报告，不会连接 Rhino 或模型。

## 文档或版本一致性检查失败

运行 `python tools/check_release_consistency.py` 查看具体漂移。常见原因是只修改了 `agent/version.py`、前端版本、依赖锁或某份文档中的一处。修复所有对应声明后再更新正式版本；不要关闭该 CI 门禁。
