# R：C5 前的最小研究安全收尾

2026-10-02。**状态：生命周期新版本已在真实 Rhino 验证；完整研究写入/远端交接尚未结项。**此分支不是产品入口，也不是 C5-6 十二工具执行器。所有历史 R 正式结果/失败证据保持原样；v8仍为 `formal_quality_fail`、实际59/60，C4仍NO-GO，默认混合路线不变。

## 本轮实际交付

- 新版[研究生命周期](../plugin/rhino_listener/research_lifecycle.py)、[Rhino入口](../tools/r_research_safety_batch.py)、[客户端](../tools/r_research_lifecycle_smoke.py)与[独立边界核验](../plugin/rhino_listener/research_safety.py)，不修改封存v2源码/清单。仅空的独立未保存headless毫米夹具；未知身份不猜路径，不确定关闭不重试，不把排队close/stop当作清理成功。
- 补入实际必需的两份历史通用依赖 `candidate_atomic_gate.py`、`candidate_live_idle_session.py`，不整包提交未跟踪R代码、题目或私人归档。源码清单保守覆盖已跟踪Python与锁定依赖，运行前后核查实际加载的本地依赖；Rhino侧使用新私有包命名空间，防止缓存旧候选模块冒充当前字节。
- Rhino内嵌Python3.9首次发现训练包初始化使用`dataclass(slots=True)`，脚本在开夹具前中止，控制台失败保留。研究模块已移到Rhino兼容边界，不改正式训练/解析实现；该失败不是任务质量结果。
- 修正新版本密钥删除证明：检查实际`channel/handoff.key`，同时拒绝遗留`channel/secret`；不事后修改历史归档器。

## 真实生命周期证据及其限度

一次新开发case `RSDEV-LIFECYCLE-20261002-A`：open→empty初始读回→同一Rhino UI回调关闭前/后活动内容哈希→close/删密钥→stop。模型调用0、写请求0、SQLite写账本0，关闭/停止均核实。活动内容四次哈希一致：`de8fa7924ad4cf7fbeffdbe982f0b559a77eca7a8cf1f24175df642404ec6cfa`。

[独立公开审计](../eval/r_research/lifecycle-audit-20261002.json)逐项绑定真实三份请求、三份响应、bootstrap、最终capture、原结果和125份源码清单，并只读核查实际handoff key不存在、账本quick_check及零写入。公开文件只含相对源码路径、哈希与状态，不公开会话/用户临时路径。原始私有收据已明确逐文件保留，账本采用SQLite一致backup而非忽略WAL的文件拷贝。

此活动哈希沿用 `_content_digest` 的几何/对象属性、图层、单位和容差序列化范围，不冒称整个3dm文件或摄像机/所有文档表的逐字节哈希。此case证明生命周期和这组内容边界，**不证明写入许可、模型质量、十二工具几何、真实用户产品接入或全部异常现场路径通过**。

## 写入与远端门还缺什么

新核验器独立重算盒体与位移、核对完整对象集合，并交叉绑定任务/签名参数、场景/文档/版本、许可请求及四个事件、执行回执与持久`done`账本。账本key是request ID的一次SHA-256；执行回执保存的是该key再哈希，不能误按原始ID相等处理。该函数不获得批准或派发几何，也不把bbox读回扩展为其他工具验证。

[固定两写无模型烟测](../tools/r_research_two_write_smoke.py)已准备：仅347×353×359盒体和(7,-11,13)平移，最多两次独立许可/签名/保留/执行，逐步精确读回后关闭/删密钥/停机并一致备份账本。spec canonical SHA-256为`c93c7f43eb9527f2fff15c2a28f8bcc3fe8ef6c12221b3fdc276dca3993b861f`。**尚无该两写的所有者批准或现场结果；不得自签批准或自动开始写入。**它是研究安全开发probe，不计C5/R模型质量分，也不声称是全新最终测试家族。

远端模型源码/基座/adapter须独立绑定可信清单；原旧R主机/模型哈希不可静默改成新C5身份。当前C5资产只读复核在[C5 PR #6](https://github.com/xiongweiluo/RhinoCoder/pull/6)，包括原基座14文件、checkpoint132两adapter文件与原最终28源码；它不是新C5-6执行血缘冻结。进入C5-6还须完整12工具适配和几何/属性评分器、独立开发负控、20题所有者排除承诺、执行/预算冻结。

## 当前交接边界

CPU负控覆盖未知/迟到open、关闭超时不重试、错case/序号/fixture、活动哈希篡改、几何/账本/许可/源码篡改及非所有者/错误spec批准拒绝。干净检出测试与CI须按本次提交核对，不拿主脏工作区544项测试替代。

只关闭研究直接阻断；产品loopback UI、逐步预览-发送绑定、真实用户开放、在途停用UX和人类产品评审仍延期。仓库所有者唯一必需reviewer_1；不要求reviewer_2；代理不能替代批准。持续授权推送/创建PR不包含自动merge。

下一门：取得固定两写probe的明确所有者授权并形成/独立审计新几何-许可-账本现场证据，再交接到完整十二工具C5适配。未满足时保留本页的“尚未结项”，不改写成研究安全全通过。
