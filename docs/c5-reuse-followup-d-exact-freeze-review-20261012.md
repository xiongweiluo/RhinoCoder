# D 披露式后续开发：完整冻结与执行审议

**最新实际状态：**本人随后明确批准以下两完整哈希，唯一 D 开发已启动并在本人 ready 门失败，现已两端永久退休；见[原始失败与收尾记录](c5-reuse-followup-d-readiness-failure-20261012.md)。下文保留完整准备时点，不能再据此启动或复用批准。

2026-10-12。本人与代理的当前授权是后续准备；本人已接受禁用草案和本次独立资源预约，见[准备接受记录](../eval/c5/reuse-followup-owner-preparation-acceptance-20261012-d.json)、[资源接受记录](../eval/c5/reuse-followup-resource-acceptance-20261012-d.json)。没有生成两端 owner grant、研究 state、key、本人保管目录或 v2 准入 manifest。此次完整公共源码已两端部署和无 grant 预检；这不等于已执行、8槽工程 PASS、正式授权或 PR 合并。

## 两个可审议的完整哈希

| 材料 | 规范化 SHA-256 |
|---|---|
| [完整开发 spec](../eval/c5/reuse-followup-development-spec-20261012-d.json) | `62e6a66c77604858a0b0109003af1cff74f3ffbdb2ae33b8756c76951746e1d6` |
| [完整 runtime](../eval/c5/reuse-followup-development-runtime-freeze-20261012-d.json) | `af589bebd37a6786a01843275ec3add7b868edcc9e6a495fa989d67b93842f67` |

只绑定 `C5DEV-REUSE-20261012-D` / `reuse-dev-20261012-d` 的一次固定公开8槽。不是 C 的重放或原批准的转移；A/B/C 原入口永久退休。批准对象是完整 spec/runtime 字节、环境/资产清单及本文件说明的范围，不能只凭简写 hash、上次批准或 CPU PASS 启动。本人明确完整两哈希后仍需其私下 ready/final 保管，代理不代签。当前仅准备批准，未登记执行批准。

## 实际验证

[完整独立预执行记录](../eval/c5/reuse-followup-preexecution-validation-20261012-d.json)保留真实两端输出及原始回执 SHA。每端337项source清单＋runtime，共338份公共文件，合计3,839,999字节。真实固定解释器、权限、主机/boot/UID、完整资产字节、完整5小时窗口的 CLI 均退出0、stderr空；没有真实或合成 owner grant。外部 stdlib 实现另逐文件核对人口/字节，原 Mac 四文件/两条C消费行前后不变，GPU 原全局根仍缺席。两端 A/B/C 三组退休与封存批准的完整哈希重核，旧活动批准缺席。

GPU 新解释器位于 `/data/c5-reuse-compatible-python-20261012-d/runtime/bin/python3.11`。以[官方 CPython 3.11.17](https://www.python.org/downloads/release/python-31117/)源码及页面公布 SHA `bfb74ad39efae27cda510f134ab408e00f9992c56851cfc0b1cdb5646da11599` 独立构建；原 conda 未替换或修改。三原语实际存在，当前第一门禁通过。固定 `.pth` 只引入原模型包根，21614原包文件、960原标准库文件及2份原libpython字节与C冻结一致；新安装2684份文件、1899份stdlib Python/native文件、实际原生链接库和符号链接另完整冻结。真实CPU-only包导入和张量运算通过，`CUDA_VISIBLE_DEVICES`为空、Torch CUDA未初始化，未加载模型；不能由此推认实际GPU推理或完整现场工程PASS。

使用固定 `-I -B -X pycache_prefix=...bytecode-cache-must-remain-absent`，防止使用未冻结的旧字节码；两个缓存前缀必须缺席，不能在现场改解释器/参数或回落到系统Python/整数PID/name kill。详细字节、参数和限制见[兼容环境记录](../eval/c5/reuse-followup-compatible-runtime-20261012-d.json)及environment plan。GPU编译版本里的本地日期是服务器编译时区，计时/截止使用UTC epoch，不据显示日期改租期。

Mac仍为 `/opt/anaconda3/bin/python3.13`，3552 controller文件、339可读host文件、6原tokenizer全部实际重哈希；原Rhino PID44652 / UID501 / boot session / start identity只读匹配。沿用本人同一真实进程的三项保证及本次接受后续方案，未伪造新的本人确认或当前空白现场观察。实际批准后的入口会在任何warmup/订阅前再次要求空白活动文档及main thread；完整opaque host/内核字节、隐藏handler缺席及内存擦除仍不声称。

## 保留消费历史的准入修订

D不重开v1 SQLite、不清表、不覆盖C行或角色文件，也不新建另一全局根。[非空历史 genesis](../eval/c5/reuse-followup-admission-genesis-20261012-d.json)绑定原两行/四文件、GPU原缺席、三次退休及原C失败摘要，连同新唯一身份和本人准备接受SHA钉入spec/runtime。

只有未来完整两哈希批准后的Mac prepare / GPU serve可在**原同一根**创建一次 `followup-v2-genesis.json`。GPU首次根虽原本缺席，manifest导入的历史仍包含Mac已消费C两行，不能空表绕过。原v1四文件全程按byte SHA/SQLite schema/行/tombstone只读检查。新角色以 `followup-d-<role>.consumed.json` O_EXCL、文件及目录fsync永久消费；MAC仅controller/host，GPU仅worker/stop。额外文件、角色错误、根/manifest替换、旧字节漂移及半写文件都禁止新作用，不修复/刷新/清理后重试。不是跨机器分布式事务或任意命名空间发现保证，完整原始审计必须核对两端。

[源码](../plugin/rhino_listener/c5_followup_admission.py)的constructor不会初始化；初次初始化在批准入口中显式执行，先于第一worker claim/模型加载。原C/A/B全部源/状态/失败不变。新D若失败同样永久退休，没有第二D、新E、补槽或旧角色重用。

## 启动与失败留存

GPU保持原生pidfd所有子进程资格屏障和一次SIGTERM规则，未改模型、adapter132、two-stage契约、seed、解码、许可TTL或阈值。真实无grant预检覆盖新的首原语、单线程/无torch前段与实际计划cwd；它的argv是预检argv，不能冒充未来serve实际资格记录。未来serve仍核验真实完整argv/boot/UID/owned child identity。

Mac在唯一远端launch前创建两份原始流文件。stdout最多64MiB，stderr最多262144字节，独立读取线程持续排空、记录完整已观察流SHA和保留前缀SHA；有限协议队列溢出、截断、缺EOF/退出码或持久字节漂移都如实判不完整并永久退休。stop/export也独立有界留存。不会用stderr摘要替代原始数据，也不重建C丢失的旧stderr。

原始启动错误保持主错误，停止异常、日志异常和已知原生收尾异常分别记录；GPU停止失败不能跳过首次已知hub/child收尾。每个已知动作至多一次，不推测身份、重复stop、回连或名称kill；诊断不完整也不阻挡这次已知收尾。捕获完整不等于执行成功、资格释放证明或联合审计PASS，未知退出/清理保持未知。

## 时间、资源和下一门

本人已接受本次**开发5小时＋条件正式18小时，总23小时**有限预约，含加载、idle、停止与保守释放观察，不返还C旧预算、开发余量不自动转正式。历史累计仍未知，原16小时合规不追认；不是平台余额。原完整链路依据见[时间估算](c5-reuse-chain-time-and-resource-proposal-20261011.md)：开发窗口账本4.54小时、正式压力代理6.07小时，主动链路示意4.5–14.5小时，人工/CI等待及故障不是有限日历保证。

当前实际租期只记录本人最后报告的 **2026-10-13 20:00 Europe/Zurich**；19:45停止生成，保留900秒导出，每阶段另留60秒停止窗口，开发必须有完整18000秒，最迟10月13日14:45准入。本人已说将提前续租，但没有编造一个新到期时刻，也不自动付款。正式仍需开发完整原始联合审计PASS后的独立40槽冻结、实际租期/完整18小时窗口及另一精确批准；不足时在加载前拒绝，按实际续租事实更新该阶段，不再次索取已接受的同一预算决定。

42项新增D故障/命名空间/真实Python3.9 CPU控制通过。全仓CPU与精确发布head的push/PR双CI实际结果见此准备PR；不能继承PR16旧CI。仓库所有者仍为唯一必需reviewer和独立私有保管人；main、原九份WIP与原NO-GO不自动改变。同一公开8槽、同一密封20题复用和全部原失败须披露，不声称新的盲holdout，不读取私题。
