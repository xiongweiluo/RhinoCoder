# r3 中断续跑第4次加载：暂停与退出审核

截至2026-10-24，本人已明确批准完整规则、运行包、两个完整哈希，并另行批准原固定顺序剩余33槽的中断续跑。两端登记及本人一次私下入口完成；本次记录11/33槽后因未知原生异常与清理不明暂停。原首轮7/40结果不变，22个续跑槽未尝试，完整原始联合审计尚未收尾，不能宣称完成40槽或恢复安全。

## 精确授权与启动

- spec：`6911d112b1b11bb6bed636eac3f3d456b6400a92ac98dd95dc0105057d46fa22`
- runtime：`ba39557e57027ee4533b4d4d2468540d7af4765d22a5257b123acc8c14fda4ea`
- 原研究 `c5-rhino-paired-20-reuse-v1`、原 `formal-reuse-v1` 账本；r3只选择原索引7–39，原索引0–6不重跑。
- 执行代码对应冻结提交 `2700ce353c0529375edb53122cbca9fdcd1900a4`；执行前Git head `91d128269aed7c4250ae2bb45911fcfa87e0b43f` 的CI `40015389916`全成功：完整启动路径3项，其余2347通过/12跳过。该证据验证启动代码，不能代替本次现场或原始审计。
- 最新Mac/GPU公共闭包、实际权重、Python导入、原GPU boot/UUID及空闲、原Rhino PID44652/空文档均在启动前核对。实际租期仍为2026-10-25 20:00 Europe/Zurich，当日CET；启动所需51000秒完整窗口与剩余驻留额度通过。
- 两端grant独立回读语义一致，指纹 `ea69b4e879339ffccd47fe09917c0e33ad41e2c363a07e0612dbcd2ae793afbf`。Mac结算父目录0755→0700为非递归权限适配；原件字节、源码与完整哈希不变，该次准入拒绝未消费加载。

## 已发生的续跑

原正式加载已用3次，本次持久消费第4次；首次时刻 `1792692329.837715` 保留。r3记录的索引严格为7–17，共11槽，17生成阶段；后续索引18–39共22槽尚未尝试。前10槽已有“继续原定顺序”记录；第11槽为未知异常，关闭/停止不能确认，协调器正确进入 `SLOT_PAUSED_RECONCILIATION`，没有自动重跑该槽或启动第5次加载。

首次7/40与此次11/33分别统计，累计18个不同原索引有尝试记录。当前没有完整phase原始审计，任务成功/失败汇总均为null；进度及生产方布尔值不能代替HMAC、SQLite、生命周期、原模型重解析和清理证明。原C5 NO-GO、原完整40槽门及旧失败均保留。

## 原GPU退出已核实，Rhino清理未核实

原资格父PID1392827/子PID1392873同boot链已核对；自然退出、wait0、reap、原始双流完整、0次停止信号、GPU11MiB/compute为空均通过既有只读审核。后续独立观察也确认同boot父子均缺席；没有向其他进程发送信号。

加载意图 `1792837549.191566`，原资格退出 `1792839912.9373415`，驻留保守上界2363.745775461197秒（约39.40分钟）。这个新增上界已封存，尚未追加到全局结算：原全局已结算67977.15073728561秒保持原值，不把它误写为含本次全部消费的最终值。新增驻留、真实时间线与租期分别保留。

Rhino `hub-stop.json` 与实际宿主终止回执均缺席。phase记录包含原生收尾 `NativeError`；自动联合审核先在缺失终止回执处返回 `FileNotFoundError`。这只说明审核受阻，不能推断夹具已关闭、桥已退订或属于可恢复工程故障。现场应保持原样，未核清前不生成后续槽。

## 已准备的只读诊断与当前门

既有私题隔离职责要求保管人读取正式槽级原始材料。单独只读工具核对原11槽的关闭/停止、受限异常类、与冻结公共源码字面量精确匹配的错误信息，以及原件前后完整清单；完整清单核验会读取原件字节（包括私题文件）计算散列，但不解析或导出私题；不加载模型或Rhino，不联网，不写原证据/账本，不产生恢复授权。未知错误文本不导出。

诊断review：`f0fa023a1b45ee969a4c26d4b7c657431f7ae4935bb7530bc2f12620c5051e29`；10项合成CPU检查通过，包括敏感文本脱敏、非有限/重复JSON拒绝、符号链接拒绝、原件不变、仅允许公共错误字面量以及不产生续跑/清理证明。实际本人诊断尚待生成；这些CPU结果不是实际私有证据审核PASS。

当前只等待本人运行已提供的一次只读诊断命令，自动保存脱敏结果，无额外路径、口令、回执或确认词输入。之后才能确定清理/只读审计所缺证据及同包恢复资格；代码若需变更，仍须集中新的精确包批准。没有新的现场代码部署、模型、槽位或工程回归授权。

机器快照见[公开状态与退出证据](../eval/c5/slot-continuation-attempt4-status-20261024.json)。该文档明确为未收尾快照，后续材料只追加，不覆盖原冻结或历史拒绝。


只读诊断完整源码归档：[本人入口](../eval/c5/slot-attempt4-readonly-triage-owner.py.txt)、[诊断与脱敏核心](../eval/c5/slot-attempt4-readonly-triage-core.py.txt)、[合成回归](../eval/c5/slot-attempt4-readonly-triage-tests.py.txt)、[精确指纹与范围](../eval/c5/slot-attempt4-readonly-triage-review-20261024.json)、[10项CPU输出](../eval/c5/slot-attempt4-readonly-triage-tests-20261024.txt)。这些文本是已测试工具的逐字节审核归档；不属于r3现场执行清单，也不修改已批准两哈希。


## 后续追加：V1拒绝复现、V2诊断与独立GPU结算

此前只读诊断V1确实被拒绝，原记录只保存ValueError，不能追认完成。纯目录元数据复现了原 `triage_evidence_cap`：1581份原件共143374572字节，最大单文件560227字节，身份及符号链接检查均通过；累计第1413份到134255367字节时越过128 MiB上限。代理没有读取这些原件字节。原V1源码、完整review及拒绝均保留。

V2只将有限总量容量改为256 MiB，保留32 MiB单文件/20000文件及原件身份检查；增加拒绝的固定阶段、明确错误码和受限数值上下文，并先检查完整元数据再读取字节。25项合成CPU覆盖真实规模旧边界、新边界、原件保护、错误码从核心到入口的持久化和私密文本脱敏。当前目录纯元数据及463份原公共源码/原完整pair预检通过。V2完整review为 `f70be79f3fc4eb4a880b90e7f7377593284842386a723fc2c0df288d8e56ee3e`，不是新的研究执行批准。

本人实际V2诊断已完成，原1581份证据前后不变，清单指纹 `6b3cb059893852dc963284f6deade3577803e9b6cc59c617dea7f763b46889f9`。11份结果均记录closed，10份记录stopped；F04-lora为局部初始夹具回读拒绝，F09-lora为未知原生异常。原失败响应F09-lora/response-0043绑定冻结公共错误 `expired/oversized handoff TTL`：TTL谓词拒绝，实际校验瞬间墙钟未单独记录，不编造精确超时秒数。源码显示原stop适配器把“已停止但had_failure=true”也当作停止失败，可能因此保留current并挡住hub收尾；该原因仍需原尾部回执直接核实，不能只凭生产方结果字段下结论。

GPU驻留已独立追加结算：原资格退出/reap及双流完整证明支持第4次2363.745775461197秒上界，总已结算70340.89651274681秒。原35条账本前缀不变，仅追加gpu_residency_settled到36条；原4次消费、FIRST1792692329.837715、暂停状态不变，没有第5次加载或恢复事件。这不是Rhino清理或联合审核PASS。

## 限原现场收尾与追加审核材料

已准备单独owner收尾包，review `a06cee38902bbb76c6805c148ca3eb5785bdc80de3dd5d74c224d52e4b358cdc`。它在原全局owner互斥锁下，保存全部原件私下副本，严格核对原45条尾部签名/关闭/停止与21条hub请求；条件充分后仅通过原冻结NativeChannelV2发送第22条hub stop，不发送模型、open、execute、child close/stop重放，不部署新Rhino代码。原有unused dispatch keys由原停止逻辑清理，41份审计托管密钥保留；其他原件不得修改。重入仅回读同一个停止请求，不重新发出停止。

实际终止回执、原observer精确Remove调用和等待dispatcher退订分别核对；完整handler缺席/物理来源不作密码学保证。严格宿主审核若拒绝，将单独保留拒绝，不阻止已被证明的有限退出清理，也不授予恢复。所有新字段须明确是晚到的收尾，不把它伪装为原运行中未中断完成。

随后在验证后的私下副本上分别复算原前10槽、全部模型prompt/raw返回、HMAC、SQLite、原生/worker时序、宿主、资格GPU退出、资源与原账本消费。原冻结phase审核器和权限审核器照原规则运行、拒绝保留；对TTL已签发但未执行的许可单独核对，不删除数据库行让原审核器通过。原第11槽不完整记录与缺失step/backup如实报告，完整原门始终不追认PASS，首次40槽质量仍null，NO-GO不变。该包不写全局账本，也不产生恢复授权。

24项合成CPU（含原冻结HMAC/权限审核器的纯CPU路径、SQLite、重复收尾不重发、原件保护、原host审核失败与清理分开）通过，ResourceWarning按错误处理；原Mac可读环境和公开tokenizer契约、原Rhino PID44652已复核。当前等待本人私下执行这个只限退出与审核的入口；实际清理与联合审核尚未完成，不启动模型或剩余22槽。

来源与证据：
- [V1原拒绝](../eval/c5/slot-attempt4-triage-v1-refusal-20261024.json)、[纯元数据复现](../eval/c5/slot-attempt4-triage-v1-cap-reproduction-20261024.json)。
- [V2本人脱敏诊断](../eval/c5/slot-attempt4-triage-v2-result-20261024.json)、[V2精确review](../eval/c5/slot-attempt4-readonly-triage-v2-review-20261024.json)、[V2 CPU](../eval/c5/slot-attempt4-readonly-triage-v2-tests-20261024.txt)。
- [GPU原始驻留追加结算](../eval/c5/slot-attempt4-original-gpu-settlement-20261024.json)。
- [收尾与审核精确review](../eval/c5/slot-attempt4-close-audit-review-20261024.json)、[本人入口源码](../eval/c5/slot-attempt4-close-audit-owner.py.txt)、[核心源码](../eval/c5/slot-attempt4-close-audit-core.py.txt)、[合成测试源码](../eval/c5/slot-attempt4-close-audit-tests.py.txt)、[24项CPU输出](../eval/c5/slot-attempt4-close-audit-cpu-20261024.txt)。

原报告提交11e4156的CI40089503851已全部成功。以上后续材料作为同一批公开审核归档提交；新增head的适用CI由PR实际结果单独记录，不借旧head成功声称新head通过。现场批准的spec/runtime及执行源码不变。

追加机器快照：[V2诊断、已结算驻留与待核实收尾](../eval/c5/slot-attempt4-diagnosis-settlement-checkpoint-20261024.json)。此前暂停快照保留当时状态；该新快照明确区分已完成GPU结算与尚未完成的Rhino/原始联合审计。


## 最后追加：本人实际晚到收尾及原始审核程序完成（保留拒绝）

本人原退出/审核入口现已完成，实际清理verified，33项组件32项核实；原冻结phase审核以 `slot_final_exact_claim_population` 拒绝。原11份step claim与10份record不匹配，最后claim存在但record/原DB备份缺席，不补造或删除。前10槽独立复算5成功/5失败，第11槽保留失败。254条实际终止回执、原observer Remove及dispatcher退订核实，原非密钥证据不变；全局36条/已用4次/原FIRST/70340.89651274681秒均未改，未新增GPU消费。

完整结论见[最终收尾与拒绝说明](c5-slot-continuation-attempt4-final-review-20261024.md)和[实际本人脱敏摘要](../eval/c5/slot-attempt4-owner-raw-review-result-20261024.json)。前文“待诊断/待收尾/尚未结算”均为当时快照，保留历史；当前程序结束不等于原完整门PASS，不产生恢复授权，仍不加载模型、续跑或重跑。
