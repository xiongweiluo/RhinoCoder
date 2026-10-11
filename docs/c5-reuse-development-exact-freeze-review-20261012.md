# 新开发阶段完整冻结与精确批准入口

第1项已完成源码适配、CPU验证和两端实际完整冻结准备。下面只供仓库所有者审核；**尚未取得本冻结的执行批准**，没有创建新state/grant/key/admission，没有运行Rhino脚本、warmup/订阅、模型加载/生成或私题读取。最终发布head双CI以PR实际结果为准，不由本文自证。

| 完整材料 | canonical SHA-256 |
| --- | --- |
| [development spec](../eval/c5/reuse-development-spec-20261011-a.json) | `32f02512402ada907f6ed07381417d7f91c41896acef79ec5fe9b5d037b6d900` |
| [complete runtime freeze](../eval/c5/reuse-development-runtime-freeze-20261011-a.json) | `6c27d31987bed8289b498fd547dd680402b0f526cd773bd58a5c09dfaa9b2ac6` |

哈希使用整个JSON对象按sort_keys、紧凑separators、ensure_ascii、allow_nan=false规范化后的字节，**不是缩写或仅源码哈希**。原始文件SHA及全部逐文件SHA在[runtime](../eval/c5/reuse-development-runtime-freeze-20261011-a.json)和[独立预执行核查记录](../eval/c5/reuse-development-complete-preexecution-validation-20261012.json)中；[完整environment plan](../eval/c5/reuse-field-environment-plan-20261011-a.json)绑定环境、模型、宿主、输送与资源来源。先前runtime `236bc031…`未批准，因审计tokenizer资产闭包补齐已被当前版本取代。

## 冻结范围与当前实际核实

两端同一302个清单文件＋runtime（各303个公共文件，payload 3,286,497字节）已经实际部署。Mac源根`/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261011-a-source`；GPU源根`/data/reuse-dev-20261011-a-source`。独立stdlib检查器不导入目标代码，逐文件重算、核对精确人口和spec/plan/runtime闭包；全部通过。完整可读审阅副本位于`/private/tmp/rhinocoder-c5-reuse-development-freeze-20261012-complete-v2`。

GPU本次原版基座14文件、checkpoint132两adapter、21614个非缓存分发文件、960个stdlib文件、两libpython及解释器/平台/驱动/容量均匹配。实际boot仍`0a861fa3-31c9-4899-a022-c4f9cdb8dbfe`、UUID`GPU-3a14915f-3804-46b7-b98a-aa09f7bbab4f`、UID1000；旧43776缺席、观察时计算进程为空、显存11MiB。额外缓存字节码和原pip缺项保留，不把空闲观察当作历史用量0或完整执行字节因果证明。

Mac339个宿主/3552个controller文件和6个tokenizer文件均逐字节匹配；tokenizer精确人口、固定目录及全部SHA与GPU原版一致，已纳入模型资产闭包和每次Mac guard。缺项、漂移、额外added_tokens、别名及错误目录均拒绝。Rhino仍是本人接受的PID44652/UID501/UTC启动2026-10-11T16:14:32Z、boot-session UUID `F873EC8A-960B-4B86-B35E-65A973D84E99`。以前boottime微秒差异只作历史观察，不用于新身份键；没有猜测原因或改写旧记录。

本人已确认空白、独占及“冻结可读文件＋信任opaque宿主＋有限可见检查点连续性”。活动文档没有被代理独立检查；真正入口在任何warmup/订阅前再次要求主线程与空白。保证不包括全宿主字节闭包、隐藏handler缺席、检查点间无瞬变、密码学人类来源或内存擦除。

## 资源与单次范围

[已接受资源修订](../eval/c5/reuse-resource-owner-acceptance-20261012.json)：新增开发最多5小时、正式最多18小时，总23小时，含加载、idle、停止和保守释放观测；开发余量不转给正式。历史累计仍null，原16小时合规不追认，不要求平台余额、不自动续租/付款。实际到期10月13日20:00 Europe/Zurich（UTC+2），19:45停止生成、900秒导出。开发准入必须有完整5小时，不能截短预约；对应最迟开发准入为10月13日14:45，正式预约及两阶段等待仍要单独满足租期，必要时先更新实际租期与冻结。

本批准只覆盖`C5DEV-REUSE-20261011-A`的固定公开8槽：双模型写、读、澄清和拒绝；原模型/契约/顺序/阈值/无parser repair不变。所有已知派发按原签名许可/SQLite/原生读回/settlement/close/stop走完整链；未知永久退休、不重发、不补槽、不重试。单模型请求180秒、单native ACK120秒、settle60秒、许可TTL120秒不变；多capture handoff及等待受整体预算限制。预算到界只要求按冻结策略停止并如实报告，不保证强抢占、物理释放或成功完成。

开发工程门为全部8槽完整原始联合审计、至少一笔模型导出合法写和一笔读、关键违规/额外重复派发/未核实清理0，并通过有限连续性检查；语义质量单独披露，不强制八槽全对，不降低正式14/20、净胜3、安全0门。原C5 NO-GO与正式失败保留。本冻结**不批准正式20题消费、训练、质量裁决、产品切换或PR合并**。

## 验证及批准后的执行顺序

最终稳定源码本地**1779 passed／11 skipped，319.17秒**；审计资产/入口专项141 passed／2 skipped，Python3.9安全导入、secret scan、发布一致性和diff检查通过。前一源码head4004507双CI已成功（38180452581／38180455510，Linux1768/9），当前资产补齐版本及本完整发布需新的精确head双CI。前面的失败/中断不追认成功。

只有本人直接批准上表**两个完整精确哈希**后，才可：再次复核实际字节/宿主/余量→两端记录本批准→Mac一次prepare→Rhino一次冻结wrapper返回并在首次Idle封基线→controller一次drive→原GPU资格/加载/外部ready→公开8槽→退出/清理/已资格目标释放观察/导出→本人保管锚与独立原始联合审计。prepare/drive固定使用`/opt/anaconda3/bin/python3.13 -I -B`，Rhino包装器使用该新源根的`tools/run_c5_reuse_rhino_wrapper.py`，不使用旧入口或另一次Run。

外部ready/最终host seal、controller/native/export/lifecycle锚必须由本人从实际输出保管，不由producer自造独立来源；相应私有保管文件及实际部署/资产回执供原始审计读取。代理不能代替本人作出保管声明。工程门PASS后才能准备另一份正式40槽完整冻结，并再取另一对精确批准；失败、未知或证据不足都不自动补救重试。
