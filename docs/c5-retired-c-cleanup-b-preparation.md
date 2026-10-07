# C最小人工安全收尾B：V2判据准备，待独立精确执行批准

后续状态（2026-10-07）：下文保留事前准备与门禁。本人精确批准后已单次执行并退休，[有限安全关闭与独立原始审计](c5-retired-c-cleanup-b-result.md)完成；原C失败及host blocked/drift不变，不自动D或正式20题。“待批准/未执行”仅描述当时状态。

本人已接受[安全关闭判据V2](../eval/c5/retired-c-manual-safety-closure-admission-proposal-v2.json) canonical SHA `c103d9b9…ae172f`，并明确[仅授权准备收尾B](../eval/c5/retired-c-manual-safety-closure-owner-decision-v2.json)。这不是执行许可。C、收尾A及[只读诊断](c5-retired-c-live-diagnosis-result.md)全部保留、退休，不重跑。

## 唯一变化与不变边界

新ID `C5SAFE-HOSTASSURANCE-C-20261007-B`。只为已核实原隔离空夹具的**人工安全Dispose**，不再要求历史expected0等于当前stored revision1/现场摘要。原atomic drift原样保留，不能snapshot刷新、重置账本、修复结果或将此判据用于模型/产品写入。严格研究/产品CAS门、默认混合、质量阈值和正式20题门禁不变。

[入口](../tools/c5_retired_c_cleanup_b.py)先核对新的B精确grant、accepted V2、源/spec字节，永久admission先于全部现场检查。原C完整runtime、289源码/339可读文件及已消费C/收尾A/诊断的固定证据hash重新核对；纯前置复用旧A验证器的冻结字节，**不调用其main**。唯一owner、pendingNone、精确请求集合、原3槽失败/前2关闭、后5槽无新claim均必须成立。

历史request9仅在内存中校验原HMAC，不调用gate.execute、不重放过期请求，不读取任何key文件正文。只读SQL逻辑行必须等于准备时SHA `2aba3153…cf3420`；当前doc key绑定、一条readonly done/零write、原晚到empty3stable证据均核实。当前safe UI/backend线程、active457/content、fixture475 registry/headless/unsaved/owner与实际空几何再次检查；key仅做regular/owned600元数据检查。

全部前置通过才写第二个effects claim，并单次：

1. block原controller，准确解除child/hub两Idle；不创建或更换delegate。
2. Dispose475一次，读回原生close capture，核实registry缺席及active前后相同。
3. 只删除read-lora key、5个未打开槽key和hub.key，逐个核实实际路径缺席，不删除目录/证据；不承诺内存或外部副本擦除。
4. 只finish既有AssemblyLoad observer，准确解除原delegate并封存原始链与外部回执；允许如实保留drift/blocked，不加白名单，不把C连续性改判PASS。
5. 重新读逻辑账本和原C结果字节保持不变，全部核实后才release原owner。结果是manual safety closed，不是C工程/模型质量PASS。

模型/GPU/工具/holdout/新夹具/新订阅/snapshot/账本更新/key正文读取均0。180秒为逻辑预算、不抢占阻塞CLR；错误或未知保留阶段/partial effects并永久退休，不重试。源/private状态路径固定，不开新的run目录抹去claim。

## 独立审核

[独立B审计器](../training/c5_cleanup_b_audit.py)不导入生产者，分别验证新owner grant、admission/effects、实际UI外部result SHA、raw close capture/empty、七份准确key absence、前后完整逻辑账本、原C失败SHA、历史签名校验及另外实际UI host receipt。之后必须再运行已冻结的独立host原始链审计并检查磁盘key缺席；单一producer result不能替代联合审计。

完整handler absence、opaque宿主零副作用、全部代码字节/因果证明仍不成立。host原始审计可返回failed/incomplete，与手工安全关闭结果分开报告；不追认原C成功，不进入D/正式20题/产品切换。

CPU合成控制40项通过：V2状态漂移仅可用于精确empty Dispose、错误scope/线程/owner/geometry/ledger/request拒绝，prepare接受不能替代execution grant、旧A/整数批准/snapshot/模型扩权拒绝，permanent admission不覆写；独立close/key/active/ledger/host/external/强保证负控。全仓884 passed/8 skipped，尚未真实执行B。

## 当前执行门禁

[spec](../eval/c5/hostassurance-c-cleanup-spec-20261007-b.json)、runtime和独立预执行复核在实际字节及source revision冻结后集中列两个精确哈希。最终发布双CI成功且本人新直接批准之前，不创建B grant/admission/wrapper、不运行入口。只读GPU资源非依赖、本次GPU0，不自动续租或合并；main仍由本人决定，脏主工作区/私有认证材料不打包。

## 唯一有效待批准冻结

源码`2a1f6f2bf71e04511c558c87a5a038017f660305`；B入口字节SHA `05d3fa3ab5813c169b4898001507fc5e6c6d45132a879612f2cf249eb2a492d6`。

- spec规范化SHA-256：`505891816aa4cc471816689c31aa774deadfc30384828c7fe0ac7031bd900100`。
- [runtime](../eval/c5/hostassurance-c-cleanup-runtime-20261007-b.json)规范化SHA-256：`2aab184fd2a54545dc8c3c2b75cc9f55ca02a0dc0b6cd52dea0e03da4d4dae3d`。
- [独立预执行复核](../eval/c5/hostassurance-c-cleanup-preexecution-20261007-b.json)绑定完整旧C runtime canonical/file SHA、289/339重新字节验证、新B/审计/历史纯验证器及raw审计依赖七份代码、八份指定开发证据文件和逻辑账本SHA。所有新代码字节与上述Git revision一致。执行环境只用原Mac/Rhino，不加载GPU/模型或读取训练/holdout语料。

884 passed/8 skipped、40项B专项与Python3.9/secret/release/link/diff通过；现场执行grant/admission/effects/result/failure仍不存在。最新发布双CI成功后才请本人批准上述两个完整哈希，最多一次安全收尾及独立原始审计。没有保证原C整体连续性通过；blocked/drift须保留，不自动D或最终20题。
