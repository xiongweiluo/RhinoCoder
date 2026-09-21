# RhinoCoder · 一页简历项目描述

**定位**：AI 全栈 / Agent 工程作品集｜Python、React、TypeScript、MCP、Rhino 8、SQLite｜`v0.3.0` 已发布

## 中文简历版

**RhinoCoder — 可验证、可恢复、隐私感知的 Rhino 空间设计 Agent**

独立设计并实现从自然语言到真实 Rhino 8 几何操作的闭环 Agent：通过 23 个版本化 MCP 工具执行建模，使用 Scene Summary 与程序化断言验证对象数量、属性及空间关系，并以统一事件流、`run_id` 与 SQLite 血缘追踪规划、路由、工具、纠错、成本和反馈。实现不可绕过的本地隐私门、规则优先多后端路由、幂等写入、取消/重试/Undo/精准回滚及无需 Rhino 的脱敏 Replay。

- 建立 500/500 条黄金 Trace 数据闭环，覆盖 46 个标签；A7 新增 200 条任务，8 类覆盖缺口全部达到计划量，准入、证据与敏感审计异常均为 0。
- 在固定 30 题真实 Rhino 基准上完成主模型、低成本模型与规则路由各 3 次重复，共 270/270 次通过；同时明确该基准已饱和，不将 100% 外推为开放世界效果。
- 完成请求前隐私分类、云端最小化与统一存储面审计；12 条红队用例及 1,609 条 Trace、7,016 行 SQLite、3 份 Replay 检查均为 0 敏感发现。
- 构建可复现训练数据和锁定 QLoRA 管线，在 MornAI RTX 3090 上完成 C1–C4；A5 基座/LoRA 均为 0/45，P2 真实 Rhino 为 4/30 对 5/30（+3.3pp、净胜 1），按预注册门槛裁决 `NO-GO`，不把训练完成包装成模型收益。

证据：[A7](a7-500-marginal-value.md) · [A6](a6-no-finetune-baseline.md) · [A4](privacy-red-team-report.md) · [架构](architecture.md) · [公开指标索引](portfolio-evidence.md)

## English résumé version

**RhinoCoder — a verifiable, recoverable, privacy-aware spatial agent for Rhino 8**

Designed and built an end-to-end agent that turns natural-language tasks into real Rhino geometry through 23 versioned MCP tools, reads the resulting scene back, and verifies object counts, properties, and spatial relations with programmatic assertions. Unified planning, routing, tool calls, corrections, cost, and feedback under a monotonic event stream and `run_id`-based SQLite lineage. Added an enforceable local privacy gate, rule-first multi-backend routing, idempotent mutations, cancellation/retry/Undo/precise rollback, and sanitized Replay for reviewers without Rhino.

- Curated 500/500 admitted golden traces across 46 tags; a 200-task A7 expansion filled all eight measured coverage gaps with zero admission, evidence, or privacy findings.
- Ran a locked 30-task real-Rhino benchmark three times across three backends/routes (270/270 passed), while documenting that the saturated set does not establish open-world performance.
- Validated local privacy classification and cloud minimization with 12 red-team cases and scans of 1,609 traces, 7,016 SQLite rows, and three Replays—zero sensitive findings.
- Built reproducible LoRA data/config/checkpoint tooling and completed C1–C4 on a MornAI RTX 3090 without overstating results: A5 scored 0/45 for both lanes and real-Rhino P2 scored 4/30 vs 5/30 (+3.3pp, one net win), producing a preregistered `NO-GO` decision.

## 30 秒面试开场

“RhinoCoder 解决的不是把文本变成一段 Rhino 脚本，而是如何证明一个 Agent 真的在 Rhino 里完成了正确的几何操作。我的核心设计是窄工具边界加闭环验证：隐私门先决定数据能否离开本机，规则路由选择后端，MCP 工具在 Rhino 主线程执行，系统再读取场景并运行断言；整条链通过同一 `run_id` 可追溯，也支持停止、恢复和回滚。模型实验同样接受负面结果：A5 两路都是 0/45，P2 只有 4/30 对 5/30，因此按预注册规则裁决 NO-GO，继续使用已验证的混合路线。”

## 深挖提纲

1. **为什么需要闭环**：LLM 的自然语言“完成”不是几何证据；Scene Summary 与断言把成功定义从话术变成可复算状态。
2. **架构取舍**：FastMCP + localhost Listener 隔离 Agent 与 Rhino 主线程；变更工具不自动网络重试，以幂等键防止重复对象。
3. **隐私与路由**：隐私门先于普通路由和模型初始化；Critical 阻断、High 强制本地、Medium 最小化，关闭路由也不能绕过。
4. **失败案例**：`self_correction` 首次读取发现尺寸/颜色不符，只修改目标对象后复检；A6 余额不足尝试独立留痕，不污染有效矩阵。
5. **指标解读**：270/270 证明固定契约和工程稳定性，不证明开放世界泛化；闭环在旧基准增加 25.2% 延迟和 32.8% token，需要按风险选择。
6. **数据治理**：黄金样本必须通过断言、自检、人工确认和脱敏；模板与数字变体先成组再做 70/15/15 分区，holdout 锁定。
7. **没有做什么**：没有 LoRA 稳定优于基座的证据、没有纯云路线的安全资格、没有 Windows/多用户生产验收；这些限制直接写在 README 和报告里。
8. **下一步**：C4 已裁决 NO-GO；保留训练资产并继续混合路线。只有以新实验 ID、新预注册和新未见保留集启动 dataset v2，才能重新评估本地模型。
