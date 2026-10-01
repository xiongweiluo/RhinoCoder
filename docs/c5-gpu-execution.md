# C5 GPU 执行包（2026-10-01）

状态：专用实现已建立，实际 GPU 工程诊断/正式训练结果尚未产生，不能标记通过。

仓库所有者明确报告续租剩余两天，并授权依次完成诊断包、GPU 工程门、正式训练、最终离线评测与控制器兼容性。实际执行授权记录在 `eval/c5/c5-execution-authorization-v2.json`，绑定原 CPU 配置的 canonical SHA-256 与执行源文件，并验证既有契约/渲染器/schema 血缘。初版 `c5-execution-authorization.json` 未执行，因补齐运行血缘检查而被 v2 取代，原字节保留。它不改写 C0–C4，不批准 PR、不授权自动合并、追加租赁或默认路由切换。

## 执行边界

- RTX 3090 24GB、CUDA/BF16、锁定依赖与冻结基座 14/14 文件哈希已只读核查通过。模型和数据只使用明确离线路径，不允许 Hub 下载、远程代码或 A5/P2/最终 holdout 进入训练加载器。
- 两天为所有者报告的剩余租期，不冒充服务商精确到期时间或账单确认。执行采用授权记录时起 47 小时保守上限，并再保留至少 15 分钟停止/导出余量；不自动续租。
- 工程诊断最多两个 run、累计 4 GPU-hours；正式训练及恢复累计 8；最终必要配对生成累计 4；总上限 16。执行事件先 fsync，进程锁禁止并发，SIGALRM 硬停止；未结算的中断必须人工核实，不能绕过账本恢复。
- 64 条 overfit 索引复核 CPU 冻结哈希。第一独立进程只走到 optimizer step 1并保存模型、优化器、调度器、RNG、进度与逐文件哈希；第二进程验证完整血缘后继续同一个 run 到最多 128 步。仅有限 loss、独立恢复且相同样本 eval loss 相对下降至少 25% 才通过。
- 只有 overfit 通过才运行一次系统诊断：确定性抽取最多 32 个 train 家族，最多 26 optimizer steps；验证有限梯度、validation loss、checkpoint 和资源。它不选正式 adapter。
- 只有两项工程结果及代码/授权血缘匹配才启动唯一正式 run。NF4/double-quant/BF16，rank16/alpha32/dropout0.05，七类 projection，batch1/accumulation16，lr2e-4、cosine、warmup5%、paged AdamW 8-bit，3 epochs，最多 132 步；assistant-only loss，不截断。
- validation 候选为 epoch 末的 44/88/132 三个 checkpoint。同源推理依次生成真实 selector 和其实际选中的单 schema invocation，不用黄金工具名替代错误选择。按 family sequence exact、arguments exact、parse exact、eval loss 的字典序选择；全相同时取更早 checkpoint。validation 不得涉及最终 holdout。
- 每 10 步保存恢复 checkpoint，并保存 step1/epoch末/最终步。最多保留三份，保留已选最佳及 overfit 恢复证据；旋转仅删除该 run 自己生成的 checkpoint 目录，日志保存被旋转 lineage 哈希。正式 adapter、日志、环境和 registry 导出到本地后再逐文件校验。
- OOM、NaN/Inf、依赖故障、超时或账本不明均停止并保留证据；不自动调小上下文、修改 rank/学习率、重新训练或追加 run。模型质量差不是 operational fallback。

## holdout 与下游

本入口没有 holdout 路径/密钥选项，训练 `final_holdout_rows_read=0`。最终评测只在正式 adapter/执行代码/门槛冻结后，由独立保管人运行专用单次消费工具；先 durable claim 再解密，仅回传配对指标和哈希化收据。开发代理不查看任务正文、密钥或原始输出，不用最终结果调参；统计门和严格解析器沿用 PR #4 的冻结实现。

离线最终门失败则停止下游，不通过追加解析修复获取 C5-5 或产品 GO。控制器验证不派发 Rhino，只核验双阶段协议、fail-closed、安全拒绝和资源；真实 Rhino 与产品裁决仍属于之后的条件门。本文件不声称这些阶段已经完成。

相关入口：[GPU 执行器](../tools/run_c5_gpu.py)、[执行实现](../training/c5_execution.py)、[CPU 工程门](c5-engineering-gate.md)、[总体 C5 规划](c5-contract-aligned-qlora-plan.md)。
