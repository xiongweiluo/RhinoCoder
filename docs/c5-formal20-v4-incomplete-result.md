# C5 formal20 v4：单次基础设施停止，质量结果不可用

2026-10-09（Europe/Zurich）。[公开停止观察](../eval/c5/formal20-v4-public-stop-observation-20261009.json)优先于[此前零题准备](../eval/c5/formal20-v4-public-zero-stage-observation-20261008.json)。原唯一spec/runtime、批准、源码与所有历史结论不改。本文不是完整独立私有审计或C5-7最终裁决。

### 后续安全观察（优先）

本人明确确认未捕获HOST_EXTERNAL_RECEIPT，只可见ARM_WAIT和HOST_READY。已按新的两精确哈希批准单次停止孤立worker；[独立观察](../eval/c5/formal20-v4-worker-stop-result-20261009-a.json)核实PID43776缺席、GPU计算进程为空、显存11 MiB，仅一次SIGTERM，无模型/Rhino/私有读取。此前“远端未核实/认证缺席”为原观察时点；GPU释放不补齐外部锚或宿主清理。已补[失败审计CPU核心与边界](c5-formal20-incomplete-audit-preparation.md)，实际保管人审计入口尚未冻结或执行，仍无质量分数/整体GO。

## 已证实与尚未证实

- 本人完成私有路径输入后，永久`formal20.started`已写入；公开状态为`stopped_incomplete_no_replay`，结果错误类`BrokenPipeError`，SSH子进程退出255，原本人入口PID61346已不存在。固定20题已跨过一次性消费屏障，不允许重新解密、换ID、补题或重跑。
- 40槽中尝试/完成均0，确认生成阶段0，但`counters_complete=false`。不能把它报告为基座0/20、LoRA0/20、全部生成0或真实几何质量失败。没有配对质量估计、净胜、置信区间或整体GO。
- 只核对固定文件存在性：私有案例、两类计划、hub bootstrap/初始化claim均已形成。结合协调器源码，这次停止发生在第一槽前的适配器启动区间；没有读取案例正文、模型帧、stderr、答案、密钥或私有账本。更具体的管道断开原因尚未独立证明，不能断言模型、GPU、服务商或Mac休眠为唯一原因。
- 41个已知临时key文件均缺席（未读内容/哈希），宿主seal/terminal sidecar存在。不过观察到的Rhino界面只有ARM_WAIT/HOST_READY，没有捕获独立外部终端回执；不能从producer文件取SHA冒充外部锚。完整委托解除、连续性与清理须保管人侧审计，不据文件存在追认安全PASS。
- 固定SSH认证socket已缺席，远端GPU/模型进程是否仍驻留未核实。已请求本人仅恢复诊断认证；不恢复原worker、重新bootstrap、派发模型或再次Run。

## 资源记录保持原样

公开progress的12.747386秒从formal协调器开始计时，不含此前加载与本人等待，不是总GPU使用时长。原`resource-settlement.json`报告monotonic 1512.112841秒，而其墙钟stop-start为2505.751636秒，差993.638795秒。原账本和冻结不重写；休眠、时钟调整或其他原因均未证明。资源审计暂不能宣称完整，较大墙钟区间只能作为保守占用参考，不是独立GPU计费或实际时长证明；远端驻留若存在另须核实。

## 审计与裁决边界

现有[完整私有审计入口](../tools/c5_formal20_owner_run_v2.py)要求完整host外部锚、40槽原始链和完整worker协议；本次不完整，不能为了得到PASS省略这些要求，也不应让本人反复运行完整审计。需要准备只读的**失败/不完整证据审计**：本人读取已有私有状态（不重读密文/identity、不调用模型/Rhino），仅导出闭合脱敏摘要；独立区分已证实、缺失和不可证实，不赋予补槽、恢复或强保证。实施/冻结材料可继续准备，保管人实际入口应在审核后使用，不把新诊断混成新评测。

按[既定C5规则](c5-contract-aligned-qlora-plan.md#d-最终决策)，证据不完整阻断GO。当前C5-6不合格，C5-7最终裁决及安全收口仍待失败审计与路线决定；不事后降低14/20、净胜3或安全/重复写/未核实清理0，不将MORE-DATA作为复用这20题的理由。原80家族77/80对20/80、训练资产、D工程PASS保留，但不能替代本次真实迁移结果。

C4 NO-GO、A5两路0/45、P2基座4/30对LoRA5/30、v8 formal_quality_fail/59/60、R独立路线及默认混合永久保持。没有新训练/E/holdout/续租/默认接入或PR合并授权。本次只准备已有失败的审计与如实报告。
