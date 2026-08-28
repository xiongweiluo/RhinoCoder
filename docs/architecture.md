# RhinoCoder Architecture

## Runtime topology

```text
React UI / Replay
      | WebSocket AgentEvent
aiohttp UI Server + RunManager
      | run_agent(prompt)
OpenAI-compatible LLM <-> MCP ClientSession
                              | stdio
                         FastMCP Server
                              | localhost HTTP + Idempotency-Key
                         Rhino Listener
                              | queued work
                         Rhino main thread
                              | scene state
                    get_scene_summary / assertions
```

## Run data flow

1. UI 或 CLI 创建 `run_id` 并调用 `run_agent`。
2. Agent 发现 MCP 工具，向模型发送统一系统 Prompt。
3. 每次规划和工具调用产生单调递增的 `AgentEvent`。
4. 变更操作携带幂等键；Listener 将操作切换到 Rhino 主线程。
5. Closed-loop 模式要求模型读取 `get_scene_summary` 并在需要时纠错。
6. `AgentRunResult` 汇总消息、工具、指标、场景检查、对象 ID 和错误。
7. 评测器读取最终场景并运行声明式断言；UI 可实时展示或离线 Replay。

## Interface versions

- Application: `0.2.0`
- Prompt: `closed-loop-v1`
- Tool schema: `1.0`
- Trace schema: `1.0`

版本常量位于 `agent/version.py`。修改 Prompt、工具字段或 Trace 结构时必须提升对应版本。

正式版本还由 `docs/version-manifest.json` 锁定以下边界：

- Python `requirements-lock.txt` 与前端 `package-lock.json` 的 SHA-256。
- macOS、Rhino、Python 和 Node.js 支持范围及真实验收环境。
- MCP 工具数量和应用、Prompt、工具 Schema、Trace Schema 的一致性。

`python tools/check_release_consistency.py` 会验证代码、两份依赖锁、版本清单、README、CHANGELOG、架构文档、发布清单和 Markdown 本地链接。版本或文档漂移会使本地检查与 CI 失败。

## Security boundaries

- UI 与 Listener 只绑定本机回环地址。
- 模型密钥仅从环境变量读取，不进入事件和报告。
- 完整 Trace 与评测结果默认被 Git 忽略。
- `reset_environment` 要求 Agent 与 Rhino 进程共享本地评测令牌。
- 黄金样本在写入前必须通过断言、自检、人工确认和脱敏。
- 真实数据采集按 campaign/task ID 追踪并防止重复入库；默认拒绝清空非空 Rhino 文档，进度报告只保存在本地忽略目录。
- 公开报告和 Replay 通过敏感字段扫描及 SHA-256 复核清单锁定。

## Failure and recovery

- 查询工具遇到瞬时网络错误可重试一次。
- 变更工具不自动网络重试，并通过幂等键阻止相同请求重复执行。
- Listener 超时会标记队列任务取消，避免 Rhino 恢复后创建幽灵对象。
- Agent 记录任务创建的对象 ID，UI 可执行精准回滚。
- UI 取消会取消当前异步任务；新的工具调用不会继续发出。
