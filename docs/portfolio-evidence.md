# Portfolio evidence index

**2026-10-25合并后状态：** 研究代码及以下公开材料已进入 `main@2581581`，主线五项CI全部通过；原C5 NO-GO、默认混合路线及v0.3.0保持，尚未进入LoRA产品接入。独立R的#7仍为Draft。证据、交付层次与历史边界见[收口记录](c5-post-merge-closeout-20261025.md)。

[在线浏览三套只读 Replay](https://rhinocoder-demo.xiongweiluo1.chatgpt.site) · 无需 Rhino、模型密钥或本地安装

[真实 Rhino 单窗口证据短片](assets/rhinocoder-real-rhino-demo.mov) · [真实结果帧](assets/rhinocoder-real-rhino-result.png)

RhinoCoder 对外只使用能从版本化文件复核的指标。本页是 README、简历表述、演示脚本与面试讲解的统一证据入口；完整真实 Trace、用户身份和项目文件不公开。

## 2026-10-25追加描述性评分

用户提供的已曝光20题、三阶段40槽只读脱敏导出，固定分母为基座 **2/20（10%）**、LoRA **13/20（65%）**，差55个百分点；工程失败2/3槽分别保留在两路分母。11对仅LoRA成功、0对仅基座成功、2对均成功、4对均任务失败、3对受工程失败影响不作模型比较。详见[逐题差异、失败分布和来源限制](c5-descriptive-score-analysis-20261025.md)。

这是追加描述，不是新盲测或正式效果证明。原首次不完整、r3整阶段审核拒绝、全部消费/计时及C5 NO-GO保持；不切换默认路线。下方10月24日分阶段结果保留当时信息范围。

## 2026-10-24研究结果：分阶段呈现

**原C5 NO-GO保持，默认混合路线未切换。** 追加复用研究的原40索引均已尝试；首次不完整、r3审核拒绝和r4任务失败分别保留。以下公开证据已合并至上述main；合并不代表产品接入或新盲测通过。

| 阶段 | 实际结果 | 审核与限制 |
| --- | --- | --- |
| 首次r2，原索引0–6 | 7/40槽；6槽原始链核实，第7槽夹具校验失败、模型调用0次 | 质量成功数未报告，不能写6/7成功；事后部分核验不等于原完整门通过 |
| r3，原索引7–17 | 11槽；已复算前10槽5成功/5失败，末槽原失败保留 | 32/33组件核实，原整阶段 `slot_final_exact_claim_population` 拒绝；不写成整阶段已审核5/11 |
| r4，原索引18–39 | 22槽，8成功/14失败，34生成阶段 | 本阶段原始联合审核核实，GPU退出、Rhino清理与驻留结算完成；不追认首次40/40 |

证据和完整限制见[分阶段研究报告](c5-reuse-phased-research-report-20261024.md)。原离线80家族77/80对20/80仍仅支持离线结构化改善；2026-10-24原摘要不提供新的基座/LoRA配对效应或统计显著性；10月25日追加的固定分母描述见上文。

### 简历与面试可引用表述

> 为Rhino研究执行链实现固定槽序、失败结果保留、有限恢复和原始证据审计。追加研究的后22槽中断续跑取得8成功/14失败，并完成该阶段原始联合审核、退出清理与驻留结算；首次7槽不完整、r3整阶段审核拒绝及原C5 NO-GO均保留。已曝光题结果仅作工程证据，不宣称新的独立盲测或产品质量通过。

面试可先展示无需Rhino的合成Replay，再打开上表及对应原始脱敏摘要，解释“任务失败但证据完整”和“审核拒绝不能追认通过”的区别。既有短片和Replay不是此次研究的连续录像；未重新发布在线站点或Release。

<details>
<summary>2026-10-09历史安全交接与裁决快照（原文保留）</summary>

**最新安全交接：**本人正常退出研究Rhino，独立进程观察确认原PID9831和Rhinoceros缺席，见[单独记录](../eval/c5/formal20-v4-owner-host-exit-observation-20261009.json)。当前会话已结束，不追认历史完整清理/联合审计；当前剩余交付为本人审核后的PR/main收口，以下安全交接未完成/待摘要为退出前历史。

当前最终裁决：[C5-7 NO-GO](c5-research-evidence-and-decision-report.md)，原因是正式现场证据不完整，不是模型质量0/20。本人已有失败核查已完成，消费/案例与计划绑定核实，但完整联合/宿主清理未核实，质量不可估计；原训练、80家族77/80对20/80、D工程和全部失败资产保留。当前LoRa路线不进入产品接入，不追认C4/R成功，不自动新研究；必要安全交接与PR/main仍缺。下方待本人/待最终裁决为原快照。

2026-10-09当前研究状态：[正式20题单次运行已跨消费后在第一槽前因BrokenPipeError/SSH255停止](c5-formal20-v4-incomplete-result.md)，0槽不等于两模型各0/20；计数不完整，质量与完整安全审计未完成，不重跑。下表C收尾/D工程“20题未消费”为各自10月7日的历史时点，不是当前消费状态；原离线80家族结果和D工程证据保留，不自动支持整体GO。

[全链路证据与C5-7材料](c5-research-evidence-and-decision-report.md)将训练/离线/工程/正式质量分开。已另获精确批准单次停止原worker并独立确认GPU释放；本人只读失败审计尚待闭合摘要，缺失外部host锚及完整联合审计不会被部分核查追认PASS。当前报告不是最终C5-7或main已接入证明。

</details>

## 核心指标与来源

下表10月7日C/D开发状态是当时记录，后续正式消费及收尾以本页分阶段表为准。

| 公开表述 | 固定口径 | 证据 |
|---|---|---|
| 黄金数据 500/500、46 个标签 | 四道准入门全部通过；A7 新增 200 条，8 类覆盖缺口达到计划量 | [A7 覆盖与边际价值报告](a7-500-marginal-value.md) |
| 三路固定基线 270/270 通过 | 30 题 × 3 次重复 × 3 种方案；这是饱和固定集，不代表开放世界或困难集效果 | [A6 无微调基线报告](a6-no-finetune-baseline.md) |
| P2a 外部来源困难集 18/30 有效基线通过 | 5 次首轮连接中断以冻结 Prompt 重填同槽并保留；60.0%，Wilson 95% 区间 42.3%–75.4%，不宣称统计显著性 | [P2a 困难集报告](p2-external-hard-set.md)、[机器结果](p2-hard-set-results.json) |
| P2 真实 Rhino 补充拓扑证据完成 | 002/014 均为闭合单实体、包围盒匹配且上下表面内环数符合预期；不改变冻结基线失败或 18/30 分数 | [最小化 JSON](p2-manual-topology-evidence.json)、[002 视口](assets/p2-hard-002-rhino-topology.png)、[014 视口](assets/p2-hard-014-rhino-topology.png) |
| 真实 Rhino 执行证据短片 | 空白临时文档真实执行；单窗口执行前/后帧序列，无音频，读回 2 对象、20×20×2 基座、r=8 红球、5 次工具调用 | [短片](assets/rhinocoder-real-rhino-demo.mov)、[结果帧](assets/rhinocoder-real-rhino-result.png)、[资产清单](demo/demo-assets-manifest.json) |
| 30 题 Baseline/Closed-loop 各 3 次均为 100% Pass@1 | 180 次真实 Rhino 端到端运行；Closed-loop 增加场景检查、延迟与 token 开销 | [30 题基准报告](benchmark-report.md) |
| A7 覆盖缺口 8/8 达标 | 布尔替代恢复与多轮修订各 40；其余 6 类各 20 | [A7 覆盖与边际价值报告](a7-500-marginal-value.md) |
| A4 敏感发现 0 | 12 条隐私红队；1,609 条 Trace、7,016 行 SQLite、3 份 Replay 与模拟日志/请求面 | [A4 隐私红队报告](privacy-red-team-report.md) |
| 23 个 MCP 工具 | 版本清单固定工具数，并由发布一致性检查与源码装饰器计数交叉验证 | [版本清单](version-manifest.json) |
| C3 A5 一次性评测未达到 GO 门槛 | 基座与 LoRA 在 45 条锁定 holdout 上的 parse/name/arguments/sequence exact 均为 0/45；差值 0.0pp、净胜 0，第二 run 已禁止 | [C3 A5 报告](c3-a5-holdout-report.md)、[C2 报告](c2-qlora-training-report.md)、[C3 协议](c3-final-evaluation.md) |
| C4 模型实验裁决为 NO-GO | P2 真实 Rhino 配对描述性结果为基座 4/30、LoRA 5/30；+3.3pp、净胜 1、exact McNemar `p=1.0`、bootstrap 95% CI [0,10]pp，未达到预注册门槛；LoRA 基础设施补位事后发现超出冻结规则 | [C4 原报告](c4-model-decision.md)、[只读诊断与合规性限制](c4-posthoc-failure-diagnosis.md)、[最小化机器结果](p2-model-comparison-results.json) |
| 独立C5离线和严格控制器门通过 | 全新80家族单次配对，sequence基座20/80、LoRA77/80，+71.25pp、净胜57，exact McNemar p≈1.39e-17；原门槛、消费/冻结血缘与公开逐家族统计复算通过，尚非真实Rhino或整体GO | [最终报告](c5-final-evaluation-report.md)、[独立公开审计](../eval/c5/final-public-audit-20261002-v2.json) |
| C5现场开发失败保留，C遗留有限安全收尾完成 | A/B/C工程失败退休；C部分原生写/读不等于完整八槽通过。独立核实精确空夹具关闭、七key删除与委托解除，58记录/39请求绑定封存；host连续性仍blocked，正式20题未消费、C5-7未裁决 | [C失败](c5-hostassurance-development-c-result.md)、[收尾B与独立审计](c5-retired-c-cleanup-b-result.md)、[公开哈希索引](../eval/c5/hostassurance-c-cleanup-result-20261007-b.json) |
| C5独立D现场工程门通过，不是正式质量GO | 新单次8槽/10生成阶段、模型导出写1/读1、97连续记录/67请求锚、指定清理和完整时序独立核实；基座写/读失败保留，已排除train家族不具有盲测代表性。正式20题未读/未消费，当前核查40槽容量与预算 | [D结果与限制](c5-hostassurance-development-d-result.md)、[独立工程审计](../eval/c5/hostassurance-development-independent-audit-20261007-d.json)、[正式容量/资源复核](c5-formal20-capacity-and-resource-review.md) |
| 当前正式版本为 0.3.0 | Tag、GitHub Release 与在线只读演示均有公开入口；当前后续改动属于 Unreleased | [版本清单](version-manifest.json)、[发布清单](release-checklist.md) |

## 代表性可追溯链路

无需 Rhino 的 `self_correction.json` 合成 Replay 展示一条完整失败恢复链：

```text
run.started
  → privacy.assessed (low / allow)
  → route.selected (cloud-main / no fallback)
  → create_sphere
  → scene.checked
  → assertion.checked (mismatch)
  → correction.started
  → scale_object + set_object_color
  → scene.checked
  → assertion.checked (pass)
  → run.completed (metrics)
```

证据入口：[合成 Replay](../eval/replays/self_correction.json) · [自动 GIF](assets/replay-demo.gif) · [演示资产哈希](demo/demo-assets-manifest.json)。Replay 坐标、对象 ID、图层和模型名均为合成值，不是从真实用户项目复制的 Trace。

真实运行使用相同的 `run_id` 关联 `AgentEvent`、隐私与路由决定、工具调用、场景检查、断言、反馈、成本和 SQLite 血缘。完整真实明细默认受 Git 忽略；公开仓库只保留脱敏聚合、合成 Replay 与哈希清单。

## 不应对外声称

- 不把7＋11＋22个曾尝试索引写成首次40/40成功，不把6条原始链写成6次任务成功，也不把r3前缀5/10与r4的8/22拼接为新研究成功率。
- 不把r4本阶段审核核实追认为首次/r3原完整审核通过；不隐去14次任务失败、事后审核修订或已曝光题限制。

- 不声称本地模型已经能完成 Rhino 建模。`local-mock` 只是确定性的接口与安全替身。
- 不把C5冻结契约下80家族离线结构化改善外推为真实Rhino、开放世界或优于云模型。第一轮A5两路0/45、P2描述性4/30对5/30和C4 `NO-GO`保持不变，第二轮结果不追认第一轮成功。
- 不把 P2 包装成完全盲测：它在 LoRA 训练前冻结，但已用于既有系统失败分析；C4 将其作为外部困难回归集与 A5 分层报告。
- 不把本次 LoRA P2 描述性 5/30 说成严格遵守冻结单次基础设施补位规则的 Pass@1；[事后诊断](c4-posthoc-failure-diagnosis.md)披露 15 个任务存在超限中断记录，不事后剔除或重跑。
- 不把 Agent/Rhino 的 Windows/macOS 兼容表述为本地模型跨平台；本地推理只声明实际验证过的平台。
- 不把 30 题 100% 外推为开放世界成功率；该固定集已饱和。P2a 是外部用户出题的自动化困难集，不是真实用户亲自操作 UI；P2b 延期。
- 不把三项代表性失败复测 2/3 外推为全量修复后成功率，也不隐藏 5 次基础设施中断；002/014 补充拓扑证据不用于重写冻结评分。
- 不声称生产级多用户、Windows 或企业部署已经验收。
- 不公开真实用户身份、原始项目文件、完整本地 Trace 或密钥。
