# RhinoCoder Architecture

## Runtime topology

```text
React UI / Replay
      | WebSocket AgentEvent
aiohttp UI Server + RunManager
      | run_agent(prompt)
Local Privacy Gate -> block / force local / minimize
      | allowed request
Rule-first Router -> Main Cloud / Economy Cloud / Local Mock
      | one uniform completion interface
OpenAI-compatible planning <-> MCP ClientSession
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
2. 不可关闭的本地隐私门生成结构化 `PrivacyDecision`；Critical 请求提前阻断，高风险强制本地，中风险标记为出站最小化。
3. 规则路由按隐私、难度、工具复杂度、成本和延迟预算生成结构化 `RouteDecision`。
4. Agent 发现 MCP 工具；云端边界白名单化并最小化消息，二次扫描通过后才发送。
5. 每次隐私判断、路由、规划和工具调用产生单调递增的 `AgentEvent`。
6. 变更操作携带幂等键；Listener 将操作切换到 Rhino 主线程。
7. Closed-loop 模式要求模型读取 `get_scene_summary` 并在需要时纠错。
8. `AgentRunResult` 汇总消息、工具、指标、场景检查、隐私/路由决策、对象 ID 和错误。
9. 运行结束后 Trace 与 `route_decisions` 写入 SQLite；UI 可实时展示或离线 Replay。

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
- 高隐私路由只允许本地后端，候选云后端标记为不可用且没有云端 fallback。
- 凭证、Prompt 注入和数据窃取请求在 MCP/模型启动前阻断；该门禁不受普通路由开关影响。
- 云端请求只保留白名单消息字段，身份、路径、邮箱、图层、群组和密钥在出站前最小化并二次扫描。
- Trace、日志、SQLite、Replay 和实际模型请求台账使用统一可重复审计；几何坐标、尺寸和对象 ID 保留用于闭环验证。
- 完整 Trace 与评测结果默认被 Git 忽略。
- `reset_environment` 要求 Agent 与 Rhino 进程共享本地评测令牌。
- 黄金样本在写入前必须通过断言、自检、人工确认和脱敏。
- 真实数据采集按 campaign/task ID 追踪并防止重复入库；默认拒绝清空非空 Rhino 文档，进度报告只保存在本地忽略目录。
- AI 视口审核结果先进入独立候选层；五条批次只有在汇总证据经人类一次性确认后才原子晋级黄金集，AI 反馈与人类确认均保留在数据血缘中。
- 公开报告和 Replay 通过敏感字段扫描及 SHA-256 复核清单锁定。

## Failure and recovery

- 查询工具遇到瞬时网络错误可重试一次。
- 模型后端只对超时、连接错误、HTTP 429、5xx 和明确的模型不可用错误执行最多一次有限降级；认证和配置错误不降级。
- 后端切换仅发生在规划请求边界，复用完整对话和工具结果，不重放已经执行的 Rhino 工具。
- 变更工具不自动网络重试，并通过幂等键阻止相同请求重复执行。
- Listener 超时会标记队列任务取消，避免 Rhino 恢复后创建幽灵对象。
- Agent 记录任务创建的对象 ID，UI 可执行精准回滚。
- UI 取消会取消当前异步任务；新的工具调用不会继续发出。
