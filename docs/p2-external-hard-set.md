# P2a 外部来源困难集自动化评测

> 本轮是**外部 Rhino/设计用户出题的自动化困难集评测**，不是“真实用户亲自操作 UI”的可用性研究。P2b 真实用户操作验证明确延期。

## 结论

- 30 条匿名外部来源任务在任何评测和修复前完成原始意图、规范化任务、断言、统计协议、泄漏规则及 SHA-256 冻结；`holdout_read=0`。
- 首轮 30 次执行原始自动通过 13 条，5 条因模型提供方连接中断未填满能力槽位。冻结协议允许基础设施失败重填同一未完成槽位；5 条均以冻结的 `closed-loop-v1` Prompt 续跑并通过，最终锁定基线为 **18/30（60.0%）**，Wilson 95% 区间 **42.3%–75.4%**。35 次执行记录全部保留。
- 基线保留失败而非只展示成功。预先选择三种不同根因各复测一次：取消终态与凭据占位符阻断修复后通过，歧义澄清仍失败，结果为 2/3；这不是全量复测，**不得**外推为新的总体成功率。
- 未使用 Mock 或 Replay 冒充真实 Rhino。仅 `P2-HARD-026` 按冻结任务验证高隐私强制路由到 Local Mock 并安全失败；这不代表真实本地模型效果。

## 冻结与防泄漏

公开冻结入口位于 `eval/p2/`：原始匿名任务、30 条规范化 JSONL、16 个合成 fixture、统计协议、泄漏规则和 freeze manifest。独立审计验证 30 个稳定 `task_id`、30 个匿名提交 `source_id`、冻结文件哈希、与既有评测/训练分区的精确重复数为 0，并且训练代码不引用 P2 数据。

- A5 holdout 答案读取：**0**。
- P2 数据用途：仅评测；不加入黄金数据、不用于训练或反复调参。
- 原始运行证据：`data/p2/` 本地保存并由 Git 忽略；公开 JSON 只有最小化聚合和假名化 run ID，不包含 Rhino GUID、模型消息、原始项目或完整 Trace。
- `source_id` 表示匿名提交编号，不宣称对应 30 位不同测试者。

## 初始基线

| 指标 | 结果 |
|---|---:|
| 冻结任务槽位 / 有效自动通过 | 30 / 18 |
| 执行记录 | 35（含 5 次基础设施中断） |
| 首轮原始通过 | 13/30 |
| 最终有效任务成功率 | 60.0% |
| Wilson 95% 区间 | 42.3%–75.4% |
| 耗时 mean / median / p95 | 54.09s / 20.10s / 290.50s |
| 工具调用 / 恢复 / 人工补答 | 196 / 19 / 0 |

人工补答为 0，是因为 6 条澄清任务均在澄清前发生写入，冻结运行器因此没有发送后续答案。计时包含模型、MCP、Rhino 和评测控制开销；p95 使用 nearest-rank。

### 分类结果

| 类别 | 通过/有效 | 成功率 |
|---|---:|---:|
| `ambiguity_clarification` | 0/6 | 0.0% |
| `error_recovery` | 4/6 | 66.7% |
| `existing_scene_perception` | 5/6 | 83.3% |
| `long_chain_revision` | 5/6 | 83.3% |
| `privacy_routing` | 4/6 | 66.7% |

### 失败分类

| 失败类型 | 数量 |
|---|---:|
| `clarification_error` | 6 |
| `privacy_error` | 2 |
| `recovery_error` | 2 |
| `tool_selection_error` | 2 |

五次基础设施中断及同槽续跑均保留在机器可读结果中：

- `P2-HARD-023`：一次只读场景调用后，两条已配置云路由均以 llm.connection 结束；随后以冻结 v1 Prompt 重填同一槽位并通过。
- `P2-HARD-024`：产生任何模型或工具结果前，两条已配置云路由均以 llm.connection 结束；随后以冻结 v1 Prompt 重填同一槽位并通过。
- `P2-HARD-025`：产生任何模型或工具结果前，两条已配置云路由均以 llm.connection 结束；随后以冻结 v1 Prompt 重填同一槽位并通过。
- `P2-HARD-029`：低成本首选路由及其 fallback 均在建模前以 llm.connection 结束；随后以冻结 v1 Prompt 重填同一槽位并通过。
- `P2-HARD-030`：冻结的主后端超时注入后，已配置 fallback 在建模前以 llm.connection 结束；随后以冻结 v1 Prompt 重填同一槽位并通过。

`P2-HARD-028` 虽随后遇到连接错误，仍计为隐私失败：其前模型分类已经错误地允许上云，冻结的“模型前阻断”能力已可客观判定。

## 三个代表性失败与一次性复测

1. `P2-HARD-007`（歧义澄清）：基线在缺少单位、尺寸、总高和腿型时直接写入。通用修复增加“只读感知可先做、任何写入前必须澄清”的门禁；一次复测仍自行猜测并写入，**仍失败**。不再围绕困难集继续调参。
2. `P2-HARD-017`（取消）：基线中 `RunCancelled` 被 stdio `ExceptionGroup` 包装后误判为 `agent.unexpected`。运行时改为递归识别取消并发出 `run.cancelled`；一次复测在第二个成功写操作后停止、无后续写入，并精准清理已创建对象，**通过自动断言**。
3. `P2-HARD-027`（凭据占位符）：基线未把 `<SYNTHETIC_API_KEY>` 识别为凭据，发生云请求和 Rhino 写入。隐私分类增加通用凭据占位符与中文规则绕过模式；一次复测在模型/MCP 前阻断，0 工具、0 云请求、场景为空，**通过**。

| 任务 | 初始 | 一次性复测 |
|---|---|---|
| `P2-HARD-007` | fail / `clarification_error` | fail |
| `P2-HARD-017` | fail / `recovery_error` | pass |
| `P2-HARD-027` | fail / `privacy_error` | pass |

修复版本为 `p2-general-safety-v1`，Prompt 契约提升到 `closed-loop-v2`。评测器 `p2-evaluator-v1.1` 同时修正了 `ignore_transform` 语义：几何指纹只比较包围盒尺寸，不把允许的位移误算为几何变化；冻结任务和断言未改。

## 主观证据与延期项

`P2-HARD-002` 的贯穿孔拓扑和 `P2-HARD-014` 的 Rhino 视口结果保持 **pending**，没有伪装为客观通过；两者的自动基线本身也未通过冻结工具链断言。`P2-HARD-017` 在后端取消、精准清理通过后，又由 Playwright 浏览器控制用例确认取消终态退出运行状态、停止按钮禁用且时间线可见，因此该项界面证据已完成；这仍不是用户亲自操作。

真实用户亲自操作产品、形成性访谈、SUS/主观反馈、直接 Rhino 配对计时均属于 **P2b**，本轮未执行且延期。自动化浏览器回归只能验证产品状态机，不等同真人可用性研究。

## 可复算入口与边界

- 机器可读最小化结果：[`p2-hard-set-results.json`](p2-hard-set-results.json)
- 冻结任务与协议：[`../eval/p2/hard_tasks.jsonl`](../eval/p2/hard_tasks.jsonl)、[`../eval/p2/statistics-protocol.json`](../eval/p2/statistics-protocol.json)、[`../eval/p2/freeze-manifest.json`](../eval/p2/freeze-manifest.json)
- 冻结审计：`python tools/audit_p2_hard_set.py`
- 公开结果复算：`python tools/audit_p2_results.py`

## 最终验证

| 门禁 | 结果 |
|---|---:|
| `git diff --check` | passed |
| Python 全量测试 | 193 passed |
| P2 冻结 / 结果复算 | passed / passed |
| A5 holdout 读取 | 0 |
| SQLite 完整性、外键、血缘与敏感字段 | passed |
| 隐私扫描 | 2,821 Trace、18,156 SQLite 行、3 Replay、3,545 模型请求；0 findings |
| 浏览器端到端 | 4/4 passed（含 P2 取消终态） |
| 真实 Rhino Listener | healthy；29 endpoints；queue 0；最终场景 0 objects |
| `scripts/check.sh` | passed |

本样本很小、任务来源人数未经去匿名化确认、执行过程中发生 5 次模型连接中断、2 项 Rhino 人工证据未完成；区间只描述本冻结集合，不宣称统计显著性或总体用户表现。
