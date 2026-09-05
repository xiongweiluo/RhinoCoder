# 规则优先混合路由与 A3 验收报告

## 结论

A3 已于 2026-09-05 完成并通过离线自动验收。RhinoCoder 现在使用统一的模型后端接口，在可靠主云模型、低成本云模型和本地 Mock 后端之间进行确定性决策。路由不调用额外模型，决策结果会同步进入运行事件、`AgentRunResult`、UI、Trace 和 SQLite。

本阶段的本地后端是明确标记的安全 Mock，用于接口验证、高隐私阻断和离线测试，不冒充具备复杂建模能力的本地 LLM。它可以按统一协议请求只读场景摘要，但最终运行会以可恢复的 `local.mock_only` 明确结束，而不会谎报建模成功。真实本地推理模型属于后续工作。

## 后端

| 后端 | 默认模型 | 定位 | 云端 |
| --- | --- | --- | --- |
| `cloud-main` | `deepseek-v4-pro` | 复杂任务、可靠性优先 | 是 |
| `cloud-economy` | `deepseek-v4-flash` | 简单任务、成本或延迟优先 | 是 |
| `local-mock` | `mock-local-v1` | 高隐私安全演练和确定性测试 | 否 |

三者实现同一 `ModelBackend.complete(messages, tools)` 接口。OpenAI-compatible 后端统一把认证、超时、连接和 HTTP 状态错误转换为 `BackendError`；本地 Mock 使用相同响应契约，不需要 API 密钥。

## 决策规则

规则按以下优先级执行：

1. 路由关闭时固定使用 `cloud-main`，用于兼容原有单模型行为。
2. `main`、`economy`、`local` 手动模式固定选择对应后端；高隐私信号仍会覆盖手动云端模式。
3. 密钥、密码、机密、禁止上云、仅本地及用户绝对路径等高隐私信号强制进入 `local-mock`，云端候选标记为不可用且无 fallback。
4. 难度或工具复杂度达到 L4/L5 时选择 `cloud-main`。
5. 非复杂任务在成本预算不高于 0.01 USD 或延迟预算不高于 30 秒时选择 `cloud-economy`。
6. 其余简单任务选择 `cloud-economy`，多步任务选择 `cloud-main`。

`RouteContext` 允许调用方显式传入隐私级别、L1–L5 难度、L1–L5 工具复杂度、成本预算和延迟预算；未传入的信号由本地规则推断。结构化 `RouteDecision` 包含唯一 `route_id`、时间、候选后端、最终后端/模型、全部输入信号、机器原因码、人类可读理由和降级结果。

## 有限安全降级

只有超时、连接错误、HTTP 429、5xx 和明确的模型不可用错误可触发降级，默认最多一次。认证失败、缺少密钥、其他无效请求和高隐私本地路由不会降级。

降级发生在模型规划请求边界。模型调用本身不能直接修改 Rhino；Agent 仅在收到完整工具调用后才执行 MCP 工具。切换后沿用完整消息、已有 tool call 与 tool result，不重新运行 Agent，也不重放任何工具。集成测试覆盖“主模型已创建一个对象，下一轮超时并切换低成本模型”的路径，最终 Rhino `create_box` 调用次数严格为 1，`route.fallback` 同时记录 `replayed_tool_calls=0`。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RHINOCODER_ROUTER_ENABLED` | `1` | `0` 恢复固定主模型行为 |
| `RHINOCODER_ROUTE_MODE` | `auto` | `auto/main/economy/local` |
| `RHINOCODER_ROUTER_FALLBACK` | `1` | 是否允许瞬时故障降级 |
| `RHINOCODER_ROUTER_MAX_FALLBACKS` | `1` | 最大降级次数；实现硬限制为 0 或 1 |
| `RHINOCODER_ECONOMY_MODEL` | `deepseek-v4-flash` | 低成本模型名 |
| `RHINOCODER_ECONOMY_BASE_URL` | 主模型 URL | 可选独立兼容 API 地址 |
| `RHINOCODER_ECONOMY_API_KEY` | `DEEPSEEK_API_KEY` | 可选独立密钥 |
| `RHINOCODER_LOCAL_MODEL` | `mock-local-v1` | 本地接口显示名 |

可以在不调用 Rhino 或模型的情况下检查决策：

```bash
python tools/route_preview.py "创建一个方块"
python tools/route_preview.py "创建参数化立面，然后阵列并执行布尔差集"
python tools/route_preview.py "仅本地处理这个机密项目，不要上传"
```

## 追溯与 UI

- `run.started` 记录初选模型和后端，随后发出 `route.selected`。
- 发生降级时发出 `route.fallback`，包含原后端、错误码、安全边界和工具重放数。
- `AgentRunResult.route_decision` 保存最终决策；Trace 构建无需额外映射。
- SQLite 根据最终后端更新 `models`，并自动 upsert 到 `route_decisions`；单次运行 lineage 可同时查询任务、模型、路由、工具和证据。
- UI 的 Model Route 卡片显示当前后端、模型、理由、隐私/难度/复杂度信号和降级结果，历史运行恢复后仍可查看。

现有 300 条黄金运行产生于 A3 之前，原始 Trace 没有路由决策，因此不会伪造或回填 `route_decisions`；A3 上线后的每个新运行会在结束时自动写入。临时 SQLite 集成测试验证了模型外键、最终后端和 `route_id` 的完整落库。

## 自动验收覆盖

- 高隐私强制本地且云端候选不可用。
- 复杂任务选择可靠主后端。
- 简单、成本受限和延迟受限任务选择低成本后端。
- 自动/手动/关闭模式及 fallback 上限。
- OpenAI-compatible 错误标准化和原有单模型兼容性。
- 降级复用上下文且不重复 Rhino 工具调用。
- Trace 自动写入结构化路由决策、模型和 SQLite 外键。
- UI 历史快照保留路由决策，TypeScript 生产构建通过。
