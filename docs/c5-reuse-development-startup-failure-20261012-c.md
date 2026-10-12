# C单次worker-ready启动失败、首次宿主收尾与两端退休

本人直接批准修订C spec `10f821cacb0e5681c3b2f8286230eab7dfdd69102ed7ca3adf540f6cd2148446` / runtime `160e74bb15497960d51d499f51bac6a8be67b38c0124af385296c1119ecedc24` 后，按发布head `5815a043908a3510fdf5cf41bd531100ab00c54a` 双CI成功（push1853/10、614.10秒；PR1853/10、964.23秒）单次推进。详见[精确批准与准备](../eval/c5/reuse-development-owner-exact-approval-and-preparation-20261012-c.json)、[原完整冻结](c5-reuse-development-c-boot-revision-review-20261012.md)及[完整追加失败记录](../eval/c5/reuse-development-startup-failure-20261012-c.json)。原C boot漂移在grant前的停止与此次真实失败是两个时点，前者未消耗入口，后者已消费C单次机会。

## 实际结果

两端批准各一次登记/回读，raw SHA `359892d9adc45bc33a966bc013b5bc4f2a04b979100e760ee506f2edf2304225`。Mac使用主机权限一次prepare成功，密钥和目录人口/权限复核通过；首次只读检查器错误把regular-file nlink==1条件用于目录，纠正后复核通过，prepare未重跑。本人私下TTY ready工具就绪后，代理一次Run C wrapper；CUA观察调用返回timeoutReached，但持久entry release、host ready及实际Rhino UI确认包装器返回，未重跑。warmup空headless文档已关闭，原活动文档为空；基线在模型加载前封存。

随后唯一controller（本地PID11179）在2026-10-12 **17:37:55—17:38:01 Europe/Zurich** 之间启动/退出1；这两端时刻来自实际launcher的观测epoch，不替代每个远端事件精确时间。等待worker ready时收到EOF，原错误 `reuse_worker_eof_or_chunk`；冻结独立stop命令也退出1，产生 `reuse_ssh_independent_stop_unknown_no_retry`。不再serve、stop、export、补槽或重跑，也未猜测PID/按名称kill/重连或升级信号。

没有worker-ready/external-begin帧、模型请求或槽启动/完成记录。语义质量不可估计，不能称0/4或能力失败；完整独立物理生成总量仍null。GPU实际state只有原grant、无supervisor/worker/资格/全局GPU准入；当前GPU compute为空、11MiB，boot与原UUID匹配。但这些只证明当前观察，不能认证冻结要求的durably qualified child释放或完整物理零调用。stderr按原transport策略DEVNULL，没有原始远端异常可供归因；后续纯scope/cold依赖/plan只读诊断通过，明确没有检查原serve argv/调用者origin，也没有运行supervise或信号，不能补成真实预检成功或唯一根因。

## 首次既有空hub收尾

controller在independent_stop抛错后跳过原 `_known_native_cleanup`，既有hub仍在。代理先核实从未发任何hub请求、8槽未open/无夹具，随后以原冻结NativeChannel、cleanup guard、已有确切hub和第一次seq1发送**stop**，不重新Run包装器/订阅/打开夹具。实际收尾 `hub_stopped`：opened_slots为空，8未用handoff key与hub key实际缺席，Idle hook同一callback精确remove，active serial268435458/content摘要保持，有限观察器记录detach完成。原始失败未被修改，收尾不改判工程结果。

Rhino实际外部终止回执：seal `96c5680d69d1d6b613db68e7af16406a00c1953a87eb3d2ef0f1b68e4cf61805`，head `c55bdf0dc0dfb3e9e54184befa1b618e08a54d9e249a297538d3cdb519cbcc8c`，9条，blocked=false、execution_authority=false。代理通过CUA实际UI读取这条回执；本人报告已Ctrl+C结束无ready等待并私下保存实际完整回执和失败观察，未索取其私下文件或冒充密码学人类来源。正常ready/final工具因无完整worker/final/export不运行，不伪造owner-final。

独立失败审计核对40可用原文件：controller1、native-controller3、lifecycle4完整人口/绑定/哈希链；唯一首次hub-stop HMAC及service/client两份120秒时序回执；9条host原快照/事件/单次detach的有限连续性复算。审计密钥仅私下保留用于复算，未公开；不能据此证明隐藏handler全部缺席、历史全部清理、内存擦除或完整8槽联合PASS。缺worker、原stderr、资格/退出/正常导出与正常本人最终保管，完整工程门未通过。

## 两端永久退休与当前门

两端C grant均可恢复改名为 `owner-approval.retired-no-retry.json`，原 `owner-approval.json` 缺席，源根/原始记录/审计钥保留。两端退休记录raw SHA `310797d0dfbe9e787424f62140f8dae460fcd443b7b23043ca5e6dc1e8befb80` 一致。Mac已消费host/controller两条全局准入原样保留，GPU准入仍缺席；不清空/改名/换全局命名空间。A/B既有失败及退休字节不变。C不得恢复、重试或补槽。

本次失败证据与追加报告在准备分支/PR #15，main未自动包含或merge；源代码、完整批准spec/runtime与两端308公共源文件不变。原C5 NO-GO、原正式失败、同题复用披露、模型/契约/阈值、默认混合与23小时有限修订保持。没有正式40槽冻结、私有消费或新候选。

当前需要本人审阅失败并决定是否另行授权下一候选的完整准备；若授权，应先做真实固定argv/冷入口/首次GPU准入及stderr持久化的无研究作用诊断与CPU控制，再形成独立完整冻结、双CI和另一份精确批准。此处只是下一步门，不自动执行新候选，也不把同一C修后重跑。

现有共享准入已经消费host/controller，当前仅允许空表的准备规则不能直接用于另一候选。任何后续方案须本人审议单次研究/准入政策，并保留这两行与原tombstone；不能清空表、复用C角色或换命名空间绕过准入。上面的下一候选准备是需审议的条件项，不是已有可执行路线。
