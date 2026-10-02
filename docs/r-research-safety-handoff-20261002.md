# R：C5 前的最小研究安全收尾

2026-10-02。**最新状态：授权两写尝试A在第一写后核验失败并封存；精确首写读回及清理经事后独立核实，第二写未执行，完整研究写入/远端交接尚未结项。**此前无写入生命周期通过仍有效；本页不把失败A追认为PASS。此分支不是产品入口，也不是C5-6十二工具执行器。所有历史R正式结果/失败证据保持原样；v8仍为`formal_quality_fail`、实际59/60，C4仍NO-GO，默认混合路线不变。

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

[固定两写无模型烟测](../tools/r_research_two_write_smoke.py)的原spec为347×353×359盒体和(7,-11,13)平移，最多两次独立许可/签名/保留/执行；canonical SHA-256为`c93c7f43eb9527f2fff15c2a28f8bcc3fe8ef6c12221b3fdc276dca3993b861f`。仓库所有者明确回复“授权该两写研究安全烟测”后，A仅执行一次，结果见下节。它是研究安全开发probe，不计C5/R模型质量分，也不声称是全新最终测试家族。**A的批准不得用于修复后的重跑或其他ID；运行入口现已明确拒绝A，即使另选fresh output也不可重用。**

[两写独立只读审计入口](../tools/audit_r_research_two_write.py)已实现，[合成负控](../eval/test_research_two_write_audit.py)核对并篡改真实形状的SQLite表/请求/回执：必须仅有两份唯一execute、两份签名载荷，实际几何capture绑定精确尺寸/位移，现场与一致backup账本逐行相等，两份consumed许可/八个事件与任务-参数-场景链一致；同一回调最终活动哈希、实际删密钥及停止均要通过。源码清单须与完整当前跟踪运行源码一致。审计不恢复已删除的HMAC密钥，不能声称重新验证签名；外部人类授权记录也不能自行生成授权。该入口与14项合成测试通过**不是现场两写通过或完整R门通过**。

远端模型源码/基座/adapter须独立绑定可信清单；原旧R主机/模型哈希不可静默改成新C5身份。当前C5资产只读复核在[C5 PR #6](https://github.com/xiongweiluo/RhinoCoder/pull/6)，包括原基座14文件、checkpoint132两adapter文件与原最终28源码；它不是新C5-6执行血缘冻结。进入C5-6还须完整12工具适配和几何/属性评分器、独立开发负控、20题所有者排除承诺、执行/预算冻结。

## 当前交接边界

CPU负控覆盖未知/迟到open、关闭超时不重试、错case/序号/fixture、活动哈希篡改、几何/账本/许可/源码篡改及非所有者/错误spec批准拒绝。干净检出测试与CI须按本次提交核对，不拿主脏工作区544项测试替代。

授权前的`ae74b0e`干净快照为312 passed、5 skipped，40项研究测试通过，双CI通过；它是本次A真实运行的完整128源码血缘，不以修复后的源码追认。skip不作现场成功证明。PR #7保留draft，CI只证明该分支代码检查，不自动授权merge或C5-6。

## 本次授权A：失败保留、诊断与清理核验

`RSDEV-TWO-WRITE-20261002-A`在2026-10-02的Zurich约20:32执行，仅创建了盒体；第一次绑定核验抛出`ResearchSafetyError:pre-scene chain differs`后停止，平移未尝试，模型调用0、holdout访问/消费0。原运行结果保持`two_write_research_safety_fail`、records空数组、cleanup_verified=false，不修改、不删除、不将A追认为两写成功。

实际原始输入场景revision为0，签名载荷、持久账本expected_revision和consent.scene_revision也均为0，scene/document/task/args身份一致。原新核验器误写`before_revision >= 1`，与既有Rhino空夹具、GivenScene及签名契约的合法零版本冲突。盒体读回bbox为min(0,0,0)、max(347,353,359)，after revision=1；只有一份execute及签名handoff、一个done账本、一次consumed许可和四个许可事件。此诊断是研究核验器错误，不是模型/Rhino两写质量通过。

[独立事后审计](../eval/r_research/two-write-A-incident-audit-20261002.json)与[审计入口](../tools/audit_r_research_two_write_incident.py)从实际执行文件、几何capture、SQLite行和最终UI回执重建第一写；完整原128源码清单按冻结Git `ae74b0e`字节复核。明确只证明首写边界和清理：fixture关闭、实际handoff.key及secret不存在、控制器停止、初始/关闭前/关闭后/stop的活动内容哈希均为`de8fa7924ad4cf7fbeffdbe982f0b559a77eca7a8cf1f24175df642404ec6cfa`。原cleanup_verified=false把任务错误与清理错误合并了；独立审计另记清理已核实，而原标记保持原样。HMAC密钥不恢复，签名只由冻结运行路径当时验证。

原始batch九份JSON、client原结果/授权及一致consent backup、fixture原始27份JSON/一份handoff和一致账本backup已逐文件保留在忽略的700私有归档，不打包旧R文件、密钥或holdout。活动文档仍为未保存Untitled，未作为几何写入目标。

修复仅用于未来独立版本：接受非负整数revision（仍拒绝负数/bool/float并保持身份等式）；绑定核验前保存raw step；任务错误与已严格核实清理分开；A被明确退休。合成负控补齐revision0/非法版本、失败任务与成功清理分离、不确定清理不通过、已尝试A拒绝重放，以及原始回放/几何/许可/清理/追认篡改。相关73项测试通过，不是新的现场结果。

本次修复的干净跟踪快照为345 passed、5 skipped，secret scan与发布一致性检查通过。历史125/128运行源码证据只能按各自冻结清单核验，不拿当前修复后源码冒充当时执行字节；A的事后入口明确读取冻结`ae74b0e`Git对象。

只关闭研究直接阻断；产品loopback UI、逐步预览-发送绑定、真实用户开放、在途停用UX和人类产品评审仍延期。仓库所有者唯一必需reviewer_1；不要求reviewer_2；代理不能替代批准。持续授权推送/创建PR不包含自动merge。

下一门：以新的研究版本/实验ID/spec批准执行修复后的两写烟测，再独立审计几何-许可-账本-清理闭环；不得恢复或重跑A。闭环未完成前，不交接为完整研究安全通过，不启动C5-6正式20题。
