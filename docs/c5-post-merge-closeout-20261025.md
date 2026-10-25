# C5 合并后状态与文档收口

2026-10-25（Europe/Zurich）。已只读复核 GitHub PR 元数据、远端 main、Git 祖先关系及主线 CI：**C5 研究代码和公开材料已合并，主线验证通过；原 C5 NO-GO、默认混合路线及产品接入边界保持。** 本页记录已发生的整合，不新增模型、Rhino、私有审核或训练执行。

## 已合并与已验证

| 范围 | 核实结果 |
| --- | --- |
| 主线 | `258158155d5fa53049ed759d7117a7a053305e2a`，即 [PR #27 合并提交](https://github.com/xiongweiluo/RhinoCoder/commit/258158155d5fa53049ed759d7117a7a053305e2a) |
| PR | #1–#6、#8–#28 均已合并；逐一核实最终 head 与 merge commit 均为上述 main 的祖先。#2–#6 为先前 C5 交付，#8–#27 为追加研究及报告，#28 为历史测试时钟修复 |
| 最后整合顺序 | #24 → #28 → #25 → #26 → #27；#25–#27 最终 head 含主线祖先同步，不能继续把原事前审核表中的 head 当成最终 head |
| 主线 CI | [40196177986](https://github.com/xiongweiluo/RhinoCoder/actions/runs/40196177986)，绑定上述完整 SHA；impact、python、ui、release、validate 五项均 success，2026-10-25 13:21:16 UTC 完成（苏黎世 14:21:16） |
| 独立 R 路线 | [PR #7](https://github.com/xiongweiluo/RhinoCoder/pull/7) 仍为 OPEN / Draft，head `ea85df0918147da13d58d5210269fed54f9876ef`；未纳入此次整合，完整 R 门仍未关闭 |
| 发布与演示 | 正式 Release 仍为 [v0.3.0](https://github.com/xiongweiluo/RhinoCoder/releases/tag/v0.3.0)。研究材料进入 main 不等于新 Release、在线演示重新部署或 LoRA 产品接入 |

完整 PR 最终 head/base、合并时间、merge commit 与 CI job 链接保存在[本次公开快照](c5-analysis/post-merge-snapshot-20261025.json)。它是观测时点记录，不是永久实时状态；原[合并前审核表](c5-pr-8-26-merge-review-20261025.md)及其 JSON 快照保留。

历史 CI 失败不删除：[main #24 后失败](https://github.com/xiongweiluo/RhinoCoder/actions/runs/40185766800)由 [#28](https://github.com/xiongweiluo/RhinoCoder/pull/28)修复 CPU 历史回放测试使用当天墙钟的问题；原生产时钟、租期与门禁未放宽。#28、#25、#26、#27 合并后的 main CI 均已成功；原 #22 等失败记录仍属于历史证据。此处不把 GitHub CI 成功当作现场质量或私有联合审核通过。

## 研究结论与剩余边界

- 第一轮 C4 NO-GO 和原 2026-10-09 C5 NO-GO 均保留。原机器裁决里的 `pr_and_main_closeout_complete=false`、未知质量及其他字段是当时记录，本次不回写；当前 Git 收口由本页和新快照单独证明。
- C5 原 80 家族离线 sequence 为基座 20/80、LoRA 77/80；仅证明冻结契约内结构化改善。
- 后续原 20 题复用分首次 7 槽、r3 的 11 槽、r4 的 22 槽完成尝试。首次不完整、r3 原整阶段审核拒绝与 r4 的 8 成功/14 失败保持，不拼成首次完整通过。
- [追加描述性评分](c5-descriptive-score-analysis-20261025.md)为基座 2/20、LoRA 13/20，工程失败留在分母；已曝光题、跨阶段修复及审核限制保持，不认定新独立盲测或产品 GO。
- 默认产品仍采用混合路线。完整 R 产品 UI、真实用户开放、P2b 与精简 D 继续延期；这些条件项不因 Git 合并自动成为当前执行任务。新研究、重训、现场运行、holdout 消费或路由切换均不由本文授权。
- 最近现场退出与结算使用原报告的时点证据；本次未连接 GPU 或 Rhino，不宣称当前租约、当前机器状态、完整隐藏宿主清理或历史总 GPU 用量已重新核实。

## 文档交付范围

本次统一[项目计划](../PROJECT_OPTIMIZATION_PLAN.md)、[中文 README](../README.md)、[英文 README](../README.en.md)、[作品集](portfolio-evidence.md)、[研究裁决入口](c5-research-evidence-and-decision-report.md)、[分阶段报告](c5-reuse-phased-research-report-20261024.md)、[描述性分析](c5-descriptive-score-analysis-20261025.md)及原合并审核入口。当前入口使用已合并事实；旧的等待、暂停和 Draft 状态明确归入历史，原研究结论、冻结执行文件、JSON 证据、消费及 FIRST 不变。

既有研究栈的 main 收口已完成。本次文档补充在独立分支 `codex/post-merge-docs-closeout` 交付，其自身审核、CI 与是否合并以关联 PR 为准，不能用上述 main CI 冒充本补充的检查。仓库所有者仍是唯一必需 reviewer；本次没有自动合并、发布或执行建议中的后续工作。

本地交付核查已通过：9份变更/新增Markdown中的415处本地链接、折叠区闭合、发布一致性、秘密扫描、原NO-GO一致性与diff检查。逐字核对原分阶段报告/合并前审核正文、裁决历史段落、历史清单与README折叠快照均保留；执行源码、原JSON证据、工作流与产品文件无差异。新增公开Git快照仅记录28个PR元数据及主线CI，不读取私有材料。补充PR沿用既有文档影响选择规则，最终CI以其精确head为准。
