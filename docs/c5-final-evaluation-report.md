# C5-4/5：一次性最终配对评测与公开证据审计

日期：2026-10-02。状态：**C5-4 离线门和 C5-5 严格控制器门通过，原 run 已完整结束并回收核验；整体 C5 裁决仍等待 R 研究安全收尾与 C5-6 真实 Rhino 门。**不重跑、不恢复训练、不重用这 80 家族。

## 原 run、消费和证据血缘

- 唯一 run：`c5-final-3d26f1a4b89eb38766647e93`。
- 所有者权威账本只有一个 run、两项事件：`started` 与 `encrypted_artifact_verified`。消费时间为 `2026-10-02T14:07:44.327037Z`（瑞士时间16:07:44）。远端消费收据与本地账本一致。
- 基座 revision、checkpoint132、NF4/BF16/shared-base adapter disable/enable、同输入/解码/parser 均沿用冻结实现；最终源码 `ced0de9`、28 个实现/依赖文件没有修改。
- adapter canonical SHA-256：`305d72703270d16e93233d1d34ae27cdaddd777e4530afead88c7edb8dc22cae`；最终 freeze：`9a57c1672e5d49d6b1ce8c23ee36c1fa6cf0b4570d08d9030df1c7bd2860a5d8`。
- 独立保管人解密并向原 GPU 作业提供数据；开发代理只回收五份明确的公开文件，未访问正文、密钥或 `owner-private-generations.jsonl`。原 run 目录和 owner 消费账本不覆盖、不重置。
- 远端当前无 Python/GPU 计算进程，公开进度为160个完整路线×家族槽；有资源结算，`failed.json`不存在。连接/客户端未回传报告不等于远端评测失败；本次恢复的是公开证据传输，不是执行。

| 原始公开文件 | SHA-256 |
| --- | --- |
| [progress](../eval/c5/final-progress-20261002.json) | `cf1acdce279fef4b950a6210589a42b2005ec143f9ee261dfb23381ffaa22d89` |
| [report](../eval/c5/final-report-20261002.json) | `b6c46e9ca50a53e4050c453f5071afc9c9e7065a99a67d4b6c5731b83101c855` |
| [hash-only rows](../eval/c5/final-results-20261002.json) | `150b16a6f218f69bfc3024a2f00a502f12b38ea1498626aef08c2f3acc182e1b` |
| [consumption receipt](../eval/c5/final-consumption-receipt-20261002.json) | `61295a117200cb8aa74270515cc7df9681122813729978260f12bfed0428f770` |
| [resource settlement](../eval/c5/final-resource-settlement-20261002.json) | `2546e61c601ef85aeb7b3b1c3e54c12f8dd319f8d1d557322ac6d35c7a5cabbc` |

五份文件回传后的哈希与直接远端 `sha256sum` 逐项一致。独立[公开审计v2](../eval/c5/final-public-audit-20261002-v2.json)核对原 run、唯一消费、artifact 承诺、adapter/context、冻结 parser/schema、两路 selector 输入、160条哈希化家族记录、配对计数、精确 McNemar、10,000次固定seed bootstrap、控制器聚合和预算。最初审计v1保留；v2增加绑定检查，不生成任何新预测。

审计只根据公开布尔评分及哈希收据重算，不冒充重新解析私有原始生成或独立复核不可见任务标签。模型原始生成是否可解析由被冻结运行器按原规则记录；公开审计不增加修复或改变评分器。

## 离线成套必要门

| family-level指标 | 基座 | LoRA | 差值 | 净胜 |
| --- | ---: | ---: | ---: | ---: |
| parse exact | 21/80 | 77/80 | +70.00pp | 56 |
| tool name exact | 21/80 | 77/80 | +70.00pp | 56 |
| arguments exact | 20/80 | 77/80 | +71.25pp | 57 |
| sequence exact | 20/80 | 77/80 | +71.25pp | 57 |

主要指标sequence：LoRA-only57、base-only0，双侧exact McNemar `p=1.3877787807814457e-17`；配对bootstrap95%区间 `[61.25,81.25]pp`。LoRA parse为96.25%，澄清12/12、拒绝/无工具12/12；基座对应11/12、9/12。两路合计关键安全预测错误0。全部原预注册离线门通过，不修改≥90%、+10pp/净胜8/p<.05、name/arguments+5pp和澄清/拒绝≥85%的门槛。

| 分层 | 基座sequence | LoRAsequence |
| --- | ---: | ---: |
| single_step | 0/40 | 37/40 |
| clarification | 11/12 | 12/12 |
| refusal_or_no_tool | 9/12 | 12/12 |
| multistep | 0/8 | 8/8 |
| error_recovery | 0/8 | 8/8 |

基座20个sequence成功全部来自澄清/拒绝分层；这提示改善主要是严格调用契约，不宜解释成基座缺乏一般几何能力。多步/恢复使用事前给定步骤上下文，不是实时执行反馈闭环。LoRA仍有3个single-step失败（哈希见公开逐家族结果），不把77/80包装成全通过，也不读取失败正文来调参重跑本实验。

## 控制器和资源

严格C5 selector/single-schema适配器门通过：LoRA协议完成率96.25%；311个实际生成有完整prompt/output/model/schema/parser哈希；220个被接受输出的schema合法率100%；修复0、派发0、关键安全预测错误0。没有实际Rhino、许可/UI或开放世界产品验证。

LoRA家族模型生成耗时中位3.6185s、p95 11.8941s；基座1.0337s、5.9462s。LoRA成功调用更多，不能把较快失败的基座与LoRA时延简单解释为同等工作量的吞吐比较；报告同时保留生成数、tokens和分阶段速度。该耗时不包含prompt渲染、解析、网络、Rhino。

原run报告569.6368s，结算569.6636s，低于14,400s；峰值allocated8,597,366,272、reserved19,396,558,848 bytes。训练/诊断原1.57004活跃GPU-hours加最终结算约为1.72828，仍低于总16上限；不是整机租期或服务商账单。`new_run_allowed=false`永久保留。

## 下一门与永久结论

C5-4/5只解锁R最小研究收尾与C5-6准备，不单独授权整体GO、真实派发或默认路由切换。进入C5-6前需完整本地/远端血缘、按任务精确核验、最终活动文档原始哈希与不确定清理门，再冻结20条全新题、执行版本与预算。C5-7在真实Rhino证据完成后按原门槛裁决。

同日后续纯只读[资产复核v2](../eval/c5/remote-assets-readonly-v2-20261002.json)确认基座14文件、checkpoint132两adapter和原最终28源码一致，未加载模型或读最终正文。R新的真实无写入生命周期及独立审计进入[草稿PR #7](https://github.com/xiongweiluo/RhinoCoder/pull/7)；不是完整研究安全通过。[C5-6准备稿](c5-rhino-paired-study-preregistration.md)列明12工具适配、独立评分、真正新20题和预算冻结缺口，尚未生成/消费正式题或作C5-7裁决。

C4 `NO-GO`、A5两路0/45、P2描述性4/30对5/30、v8 `formal_quality_fail`/59/60及默认混合路线不改变。代码/证据在独立分支/PR #6，不冒充main已合并。产品UI/用户开放、P2b和精简D仍延期。
