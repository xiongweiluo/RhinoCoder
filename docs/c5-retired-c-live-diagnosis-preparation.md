# C遗留状态逐项只读诊断：准备与独立审核，不是收尾或D

本人已选择仅准备冻结材料。新ID `C5DIAG-HOSTASSURANCE-C-20261007-A` 与退休的收尾A/C实验不同；没有创建现场admission/运行授权或wrapper，没有运行诊断。正式20题、原80、密钥内容均不读取。

## 实际线索与保证范围

[收尾A失败审计](c5-hostassurance-c-cleanup-attempt-a-result.md)保留单次真实traceback和原C FAIL。随后CPU只读SQLite确认candidate_scene存储revision1、历史expected0，摘要也不同。旧`RhinoAtomicGate.snapshot()`会通过写事务刷新candidate_scene；这一实现事实不证明更新时刻、是否唯一失败原因或Rhino几何发生了变化。冻结的scene_digest还包含全局object serial及文档undo watermark，不能将摘要差异直接解释成几何错误。

本次沿用已接受的整个opaque宿主信任，不提出新保证、不加白名单。不证明隐藏代码字节、因果来源、快照间无瞬变、clean进程或整个宿主零副作用。Script Editor/JSON序列化/宿主插件也可能有未覆盖作用，必须保留不确定性。

## 唯一允许的现场读取

[入口源码](../tools/c5_retired_c_live_diagnosis.py)没有导入即执行效果。新的直接owner spec/runtime批准与自哈希核对之后，先写永久O_EXCL admission，才导入Rhino/检查原289源码和339可读文件、读取已有C历史证据。

1. 固定读取历史C request9的expected，不打开任何任务语料；定位唯一原C owner及cached flags，不修改对象状态。
2. 只读SQLite的scene/read/write逻辑行，`mode=ro`/query_only/SELECT；禁止snapshot、_read_scene、重置revision或创建账本。
3. 单次检查UI flag与原backend线程；false/unknown时不读取Rhino文档，不invoke到其他线程、不注册Idle或AssemblyLoad。
4. 活动文档必须serial457；不同文档不序列化。活动content必须原SHA。随后仅查原fixture475的registry、headless/unsaved、owner及实际serial。
5. 安全条件成立才单次调用冻结backend.readback和纯读取rhino_scene_digest，只输出空/计数/摘要，不存几何正文。最多两次**显式**active digest，backend内置守卫仍有额外只读active检查，不冒称全部调用只有两次。
6. 第二次只读SQL与原C结果SHA核对；只发布诊断admission及result或failure，completed fields/unknown/阶段在异常时保留。读取差异不会变成修复许可。

模型/GPU/holdout/工具派发/新夹具/关闭/读删key/新订阅/解除委托/snapshot/逻辑账本更新均0。180秒为逻辑预算，不抢占阻塞CLR。CPU正控用合成对象与临时SQLite，不操作真实C状态。缺少或错误授权在任何现场作用前拒绝；admission后错误永久退休，不可重试。

## 独立审核与执行后验收

[独立审计](../training/c5_cleanup_diagnosis_audit.py)不导入诊断生产者，分别重建精确grant/claim、验证实际UI外部packet hash、零操作边界、原C结果/历史binding及安全读取图。拒绝非UI线程上的文档/几何读取、错误grant/claim/外部回执、cleanup/snapshot扩权、逻辑行变化和虚假的整宿主零作用证明。

独立审核仅能验证冻结记录契约，不证明opaque宿主没有其他代码或瞬变。返回`limited_readonly_diagnosis_packet_verified_not_cleanup`不授权关闭、删钥、D或正式20题；false/unknown是真实诊断结果，不是为了通过而改检查。实际回执未知同样不重跑。

## 冻结与当前门禁

[spec](../eval/c5/hostassurance-c-live-diagnosis-spec-20261007-a.json)和新runtime冻结待源码提交、实际字节复核及发布双CI完成后集中给出两个规范化SHA。runtime完整引用原C canonical/file SHA、289/339库存与新增入口/独立审计两份源码字节，源自已批准限定宿主，不依赖GPU/SSH可用性。

准备与测试不是现场运行许可；正式执行授权仍false。本地未创建新owner grant/admission/结果，也没有部署或运行wrapper。只允许CPU、文档与PR更新，不自动运行；诊断完成后先提交审计和下一安全收尾方案，由本人另行决定/批准。C失败、默认混合、C4 NO-GO、v8 formal_quality_fail59/60不变。

## 最终准备冻结（尚未现场批准/执行）

最终源码`8fc2c2bef91356c755f107c921f7e231bc579fca`，新入口字节SHA `c69ab1e2a5c0608d50df788ed89696a37c09d305c6c96ac48ed9a3c65e4b41de`。

- spec规范化SHA-256：`8a2e0218d956cae322a0b5c44a11fde5731fc1140417750eb19d4c8d383c9e01`。
- [runtime冻结](../eval/c5/hostassurance-c-live-diagnosis-runtime-20261007-a.json)规范化SHA-256：`e7a7728342fc0e6e4579312510113d9a9d1d38ef1a72aab1fd526be22a9b56db`。
- [独立预执行复核](../eval/c5/hostassurance-c-live-diagnosis-preexecution-20261007-a.json)：原289源码/339可读host重新核对，新入口与独立审计两份字节绑定；全仓844 passed/8 skipped，新诊断/独立审计42项、加原收尾专项共75项；Python3.9、secret/release/link/diff通过。

先前未批准、未运行的runtime `e9ef34ee…192247e` 已[原字节封存](../eval/c5/hostassurance-c-live-diagnosis-runtime-unapproved-e9ef34ee.json)，不再有效。修正仅为独立审计严格区分整数1/0与布尔true/false，并增加两项负控；未扩大操作/保证范围、未执行或重试。唯一有效待批准runtime为上述`e7a77283…a9b56db`，spec未变。

完整旧C runtime canonical/file SHA均引用，原C结果与真实收尾A观察SHA绑定；不是把整个脏工作区打包或声称完整动态代码闭包。现场保证仅沿用已接受的opaque宿主选择，诊断不依赖GPU/SSH、不增加GPU预算。当前new owner grant/admission/result/failure均不存在，调用0。最终发布head双CI成功后才集中请求新的两个精确哈希批准，准备路线选择或旧收尾A批准均不能替代。
