# C5研究证据与C5-7最终裁决

2026-10-09，Europe/Zurich。**C5-7最终裁决：NO-GO（正式现场证据不完整，当前LoRA路线不进入产品接入）。**[机器裁决](../eval/c5/c5-final-decision-20261009.json)与[本人部分失败核查摘要](../eval/c5/formal20-v4-owner-incomplete-audit-summary-20261009.json)分开登记；不改原摘要的`not_decided_here`。正式20题已消费且单次失败，不恢复、补题、补槽、换ID复跑或重新解密。此裁决不是完成40槽、完整联合审计或总体Goal完成证明；研究宿主清理仍未核实、PR/main尚未收口。

## 裁决与本人证据登记

本人终端已单次执行冻结v3只读入口并回传闭合JSON。代理仅核对这份公开摘要：与本地固定公开输出逐字段一致，review-runtime及部署源码字节匹配，**没有读取案例/答案/密钥/模型原始帧或再次执行审计**。摘要规范化SHA `0c3fc7fd0564167397b505dcc24c86da4c1595f677ba097aaca7a420a4875716`；原保管人公开文件字节SHA `8e58a1eef2ddae7eecb508850e282bd93cd6075a47ea7d3240fbad3484012e4c`。仓库排版副本保持同一规范化值，原字节SHA不是仓库排版副本的文件SHA。

已核实消费/既有案例承诺与40槽计划绑定；**没有**重做案例语义/参数schema、完整联合审计、宿主连续性或清理验证。摘要的`remote_gpu_absence_verified=false`表示该入口没有验证GPU，不否定[另获批准的独立worker停止观察](../eval/c5/formal20-v4-worker-stop-result-20261009-a.json)；二者不互相追写。停止观察仅是当时PID/GPU释放证据，不宣称当前整机状态、Rhino清理或内存擦除。

[只读裁决一致性检查](../tools/audit_c5_final_decision.py)绑定上述公开摘要及原停止/独立资源证据、核对未变的预注册阈值和NO-GO规则。其CPU负控拒绝伪造GO/MORE-DATA、把未知填0、修改阈值/原摘要或宣告总体完成；这只是文档/公开证据一致性检查，不替代缺失的完整私有原始审计。

## 实验问题与可支持的结论

第二轮问题是：训练与推理使用同一冻结双阶段工具调用契约后，QLoRA相对同一冻结基座能否改善结构化调用，并把改善传递到安全控制器和真实Rhino任务？第一轮schema缺失、长上下文与自然语言目标混合是设计假设，不是已证明的唯一原因；[C4诊断](c4-posthoc-failure-diagnosis.md)和C4 NO-GO不改。

第二轮已证明的是在本实验契约/离线80家族上的结构化改善，以及一个受控开发范围的实际模型—许可—Rhino—账本链路可运行。**未证明未见20题的真实配对改善、完整现场安全审计或产品接入可行性。**首次正式现场迁移停止属于已观察的基础设施/传输错误；不能由此断言LoRA几何能力失败，也不能由离线77/80追认整体GO。

## 全链路证据盘点

| 要求/阶段 | 权威证据 | 已证明 | 未证明或未完成 |
| --- | --- | --- | --- |
| dataset v2与唯一训练 | [数据报告](c5-dataset-v2-draft-report.md)、[正式训练](c5-formal-training-report.md) | 440家族/943记录、320/60/60开发split、唯一132-step训练和checkpoint132资产 | 不把开发集当最终未见集，不重训 |
| C5-4/5离线与控制器 | [原80家族报告](c5-final-evaluation-report.md)、[公开复算](../eval/c5/final-public-audit-20261002-v2.json) | sequence基座20/80、LoRA77/80，净胜57；严格控制器门通过 | 不外推实时多步、真实Rhino或产品质量；80已消费 |
| 实际来源观察器 | [17记录实际结果](../eval/c5/host-observer-result-20261006-a.json) | 单次事件/同实例表面变化/detach静默、外部seal与独立原始审计 | CLR/clr仍无文件来源，隐藏发射字节/因果来源/无瞬变未证明 |
| 研究保证与宿主准备 | [本人直接接受记录](../eval/c5/host-assurance-transition-owner-approval-v2-20261006.json)、[明确边界](c5-host-assurance-transition-v2.md) | 本人选择冻结可读字节＋明确信任整个opaque宿主＋可见checkpoint连续性 | 非clean新进程、非完整字节闭包，不按名称或结构指纹证明代码安全 |
| 独立D现场工程门 | [D结果](c5-hostassurance-development-d-result.md)、[完整独立工程审计](../eval/c5/hostassurance-development-independent-audit-20261007-d.json) | 单次8槽/10生成阶段、实际写1读1、97连续记录及67请求锚、指定清理核实 | 开发四任务不代表未见20题质量，基座写/读失败保留，不能复用批准 |
| 正式20题冻结/批准 | [v4独立冻结复核](../eval/c5/formal20-v4-preexecution-validation-20261008.json)、[精确批准](../eval/c5/formal20-owner-approval-v4-20261008.json) | 原公开承诺、模型/源码/环境/40槽顺序/评分/预算绑定与独立批准 | 冻结/批准不证明成功执行 |
| 正式40槽与完整私有审计 | [单次公开停止记录](../eval/c5/formal20-v4-public-stop-observation-20261009.json)、[失败报告](c5-formal20-v4-incomplete-result.md) | 已消费、formal_incomplete_no_replay、BrokenPipeError、SSH255，槽尝试/完成0 | 40槽未完成；counters_complete=false，实际生成总量未知；没有完整独立联合审计或配对质量估计 |
| 失败后的资源安全收尾 | [新精确批准单次停止与独立GPU观察](../eval/c5/formal20-v4-worker-stop-result-20261009-a.json) | 一次pidfd SIGTERM后PID43776缺席、计算进程为空、显存11MiB | 不证明Rhino全部委托缺席、内存擦除或历史连续性 |
| 保管人部分失败核查 | [本人闭合摘要](../eval/c5/formal20-v4-owner-incomplete-audit-summary-20261009.json)、[冻结入口](c5-formal20-incomplete-audit-preparation.md) | 本人单次核查七份已有记录，消费/案例承诺与计划绑定核实，公开摘要独立比对通过 | 不是完整联合/安全/质量审计PASS；未重解密或重跑 |
| C5-7和PR/main收口 | [机器裁决](../eval/c5/c5-final-decision-20261009.json)、[PR交接](c5-pr-stack-review-handoff-20261006.md) | NO-GO按原证据完整性规则登记；报告/公开状态同步，默认混合不改 | 40槽与完整审计未完成；研究宿主清理仍未核实，所有者精确merge决定及合并后CI尚缺 |

## 正式迁移门：没有分数，不是零分

冻结要求仍为LoRA≥14/20、配对净胜≥3（≥15pp）、关键安全违规/重复写入/未核实清理均0。正式执行源码`67f131dbcdbc1259c3dfa0d9e575dcfee370a23d`；原spec规范化SHA `1ce7dba2a75a853a6a2b8d81027235c442586f30718f05dc177f64a04b002fa7`，runtime `9f72a0491b49bbb5f21dd83e6c87bb16530218a375593e0308e69caee134f1a3`保持原样。

- 基座成功数、LoRA成功数、净胜、真实差值/置信区间均**不可估计**，不填0/20、0pp或失败分类的几何质量分数。
- 0是原记录的槽计数与已确认阶段计数；`counters_complete=false`阻止把它变成“全部实际生成0”的结论。
- 本人明确未捕获HOST_EXTERNAL_RECEIPT；seal/terminal sidecar存在不补齐外部锚，不从producer文件取SHA自造独立证明。缺锚、未知宿主清理及不完整原始链都保留。
- 原资源monotonic1512.112841秒与wall2505.751636秒差993.638795秒，不改原账本、不猜Mac休眠或服务商为唯一原因；GPU后续驻留及单次停止独立记录，不称完整计费/资源审计通过。

## 裁决边界与不自动继续的路线

现有证据阻断GO。[原规则](c5-contract-aligned-qlora-plan.md#d-最终决策)把证据不完整列为NO-GO条件；本人失败核查进一步保留完整联合/连续性/清理false、配对估计null，故登记**NO-GO**，不修改14/20、净胜3、安全0或完整性要求。MORE-DATA要求安全无回退及有界可解释缺口，本次没有足够证据证明这些条件，不能把基础设施中断包装成这种分支。工程失败/证据不足与“LoRA无几何能力”是不同命题，不把后者写成已证事实。

MORE-DATA不是重读原80/这20题、补槽、重新解密、调prompt/修解析后换ID重跑的许可。若最终结束当前路线，保留训练adapter、dataset/审核/排除资产、所有失败与工程证据；任何未来新研究要另定目的、数据和事前批准，不由本报告自动启动E或续租。GO即使在另一个可信独立研究成立，也不能自动切换默认混合路线。

R两写B与后续开发安全证据、A/B/C失败、C有限收尾及v8 formal_quality_fail/59/60不改判；R成功不替代LoRA效应验证。R产品UI/用户开放、P2b和精简D不是当前失败审计依赖，仍延期。

## 剩余收口，不恢复评测

本人操作已完成，**不要再次运行审计命令或旧owner/正式入口**，不再要求新承诺/私有文件。当前LoRa研究路线按NO-GO结束，训练/数据/adapter/所有失败证据保留；后续只做必要研究宿主安全交接及所有者审核后的PR/main收口。宿主清理未核实，保持研究独占，不默认回到普通建模/其他客户端；需要本人安全处置或新的精确批准方案，不能以本裁决追认历史清理成功。最终合并不解除任何现场或holdout门禁。
