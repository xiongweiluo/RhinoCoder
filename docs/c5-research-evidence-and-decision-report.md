# C5研究证据与C5-7裁决材料

2026-10-09，Europe/Zurich。**当前是证据盘点与裁决材料，不是最终C5-7裁决或总体Goal完成证明。**正式20题已消费且单次失败，不恢复、补题、补槽、换ID复跑或重新解密。保管人已有失败证据的只读摘要尚未收到；源码/冻结/CPU/CI完成不能替代它。

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
| 保管人部分失败核查 | [唯一v3包与操作边界](c5-formal20-incomplete-audit-preparation.md) | 公共部署/69外部文件/实际隔离环境独立核对，源码和完整发布两组双CI成功 | 本人尚未执行；即使七记录绑定核查通过，也不是完整联合/安全/质量审计PASS |
| C5-7和PR/main收口 | [预注册决策规则](c5-contract-aligned-qlora-plan.md#d-最终决策)、[PR交接](c5-pr-stack-review-handoff-20261006.md) | GO门槛不改，默认混合不改，PR可审 | 最终裁决登记/作品集结项、所有者精确merge决定及合并后CI尚缺 |

## 正式迁移门：没有分数，不是零分

冻结要求仍为LoRA≥14/20、配对净胜≥3（≥15pp）、关键安全违规/重复写入/未核实清理均0。正式执行源码`67f131dbcdbc1259c3dfa0d9e575dcfee370a23d`；原spec规范化SHA `1ce7dba2a75a853a6a2b8d81027235c442586f30718f05dc177f64a04b002fa7`，runtime `9f72a0491b49bbb5f21dd83e6c87bb16530218a375593e0308e69caee134f1a3`保持原样。

- 基座成功数、LoRA成功数、净胜、真实差值/置信区间均**不可估计**，不填0/20、0pp或失败分类的几何质量分数。
- 0是原记录的槽计数与已确认阶段计数；`counters_complete=false`阻止把它变成“全部实际生成0”的结论。
- 本人明确未捕获HOST_EXTERNAL_RECEIPT；seal/terminal sidecar存在不补齐外部锚，不从producer文件取SHA自造独立证明。缺锚、未知宿主清理及不完整原始链都保留。
- 原资源monotonic1512.112841秒与wall2505.751636秒差993.638795秒，不改原账本、不猜Mac休眠或服务商为唯一原因；GPU后续驻留及单次停止独立记录，不称完整计费/资源审计通过。

## 裁决边界与不自动继续的路线

现有证据已阻断GO。[原规则](c5-contract-aligned-qlora-plan.md#d-最终决策)把证据不完整列为NO-GO条件；最终C5-7需结合本人已有失败核查、剩余安全缺项和证据登记，不能为得到GO变更完整性要求。工程失败/证据不足与“LoRA无几何能力”是不同命题，不把后者写成已证事实。

MORE-DATA不是重读原80/这20题、补槽、重新解密、调prompt/修解析后换ID重跑的许可。若最终结束当前路线，保留训练adapter、dataset/审核/排除资产、所有失败与工程证据；任何未来新研究要另定目的、数据和事前批准，不由本报告自动启动E或续租。GO即使在另一个可信独立研究成立，也不能自动切换默认混合路线。

R两写B与后续开发安全证据、A/B/C失败、C有限收尾及v8 formal_quality_fail/59/60不改判；R成功不替代LoRA效应验证。R产品UI/用户开放、P2b和精简D不是当前失败审计依赖，仍延期。

## 当前唯一必要的本人操作

[已冻结命令](c5-formal20-incomplete-audit-preparation.md#唯一v3公共冻结与保管人交接)只在本人Mac终端读取**已有**七记录，返回闭合JSON，不提供任务、答案、密钥或私有路径。代理不代为执行，不再要求新承诺或解密。没有本人摘要就保留pending，不把计划或本报告草案当作审计结果。
