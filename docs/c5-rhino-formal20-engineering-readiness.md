# C5-6 正式运行工程准备：核心、评分与冻结缺项

> **2026-10-06最新状态（优先于下方历史准备记录）：**新20题[公开承诺已登记并通过元数据核验](c5-formal20-public-registration-and-field-blockers.md)，所有者私下自动排除/人工审核及age回读声明已收到；代理未读正文、密文或密钥。实际Rhino的CLR/clr未知来源及四个动态非文件程序集阻塞现行字节冻结；新的[宿主溯源方案](c5-host-provenance-design.md)仅获设计/合成验证授权，不放宽现行门禁。正式消费/模型调用0、`execution_ready=false`。新租期为2026-10-07 19:00 Europe/Zurich到期、18:45停止生成、至少900秒导出，见[v5记录](../eval/c5/rhino-resource-boundary-v5-20261006.json)；GPU-hours与精确批准要求不变。

2026-10-05。当前状态：**`FIELD_ADAPTERS_CPU_SYNTHETIC_AUDIT_VERIFIED_NOT_LIVE_FROZEN_OR_AUTHORIZED`**。现场适配器、保管人入口和独立原始证据审计已实现，并仅用 CPU 合成开发题验证；没有新的现场运行、最终 holdout 承诺、真实40槽配对结果、C5-6 PASS 或整体 C5 `GO`。[B 八槽模型桥工程门](c5-modelbridge-development-b-result.md)已独立通过，但其 ID、状态目录、八题、授权和结果均不得转为正式运行。

## 已实现的可复用核心

- [私有题目契约与反平衡顺序](../training/c5_formal20_plan.py)：13字段、20不可拆分家族、12个原核心工具各一题、2/2/2/2补充层；原完整原生参数 schema、最多8播种步骤与3模型步骤、初始/终态实体质量及拓扑断言。固定 seed `20261003`，40槽相邻配对，10题基座先、10题LoRA先；同题两个全新夹具的首轮语义输入逐字节比较。只有原始 `task_text` 可进入模型提示，预期调用/参数/几何不会传给模型适配器。错误恢复目前定义为题面给出**既有事实错误上下文**的纠正，不是一次现场失败后的自动重试；正式冻结前须接受或改设计，不能事后换定义。
- [一次性协调器](../training/c5_formal20_runner.py)：永久 `formal20.started` 在私有 loader 前，逐槽/逐步在动作前写入不可覆盖 claim。最多每步一组双阶段原样生成，无解析修补/重试。合法但错误的参数、未知别名或越权上限在许可前拒绝并记任务失败；严格解析失败/弃权也记失败或零派发结局，清理可核实才继续下一槽。未知回执、运营异常、场景漂移、超预算或未核实清理则停止整个研究。不得把可分类模型错误都当成基础设施中断，也不能以继续下槽为名重复请求本题。
- [现场适配器](../training/c5_formal20_adapters.py)及[40槽 Rhino hub](../plugin/rhino_listener/c5_formal20_hub.py)：新鲜 headless 毫米夹具、最多8播种步骤、每次实际读回、逐步许可先消费/签名/原子账本、关闭删钥与stop。三写链路使用单槽128消息上限；旧B的默认64上限保留。每槽停止后产生一致只读 SQLite backup。超时与迟到ScriptEditor attach竞争同一不可覆盖 admission，避免删除活跃hook的密钥；夹具创建或播种部分失败须人工收尾，不自动再open。
- [冻结双路 GPU worker](../tools/run_c5_formal20_worker.py)、[运行时](../training/c5_formal20_runtime.py)及[保管人入口](../tools/c5_formal20_owner_run.py)：固定新部署/状态目录、hash-only bootstrap、按需接收当前题、基座与checkpoint132同一PEFT基座的disable-adapter对照、逐阶段永久claim、原样私有传输/全部原始记录导出/进程退出/预算结算。构造和import均不加载模型；`run`须先核对完整新冻结与精确授权。`age-x25519`明文只在永久消费登记后于保管人机器解密；密钥不上传GPU。`audit`只读已经消费的状态，不重解密、不重新推理。
- [独立联合审计](../training/c5_formal20_joint_audit.py)：重建40槽顺序、逐步原始模型/许可/派发/几何/清理链、播种、完整远端字节库存、SQLite消费账本、Mac与GPU资源结算，以及私有题→窄计划/任务哈希的绑定；不信runner自报证明标志。删除一次性密钥后不声称重验HMAC，签名验收来源于执行时冻结安全门及原始台账；此局限在报告中明示。
- [独立评分器](../training/c5_formal20_scorer.py)：逐路线把结构化解析、工具名/参数/序列、每次真实只读结果、初始/最终原生实体质量/拓扑/属性、澄清/拒绝零派发与安全清理分别分类。未完成/未审计/未知回执不补题；40槽固定20对，报告配对净胜、exact McNemar 和固定种子10,000次配对 bootstrap。主门固定 LoRA≥14/20、净增≥3题（即≥15pp）、关键安全违规/重复写/未核实清理均0。评分器要求外部**逐原始记录独立联合审计**证明链路，不能靠 runner 或工具自报 `done` 判PASS；它自身不作 C5-7 `GO/MORE-DATA/NO-GO` 产品裁决。
- [保管人侧排除与公开承诺](c5-rhino-formal20-owner-preparation.md)：完整13字段预检、440冻结开发集/历史模板/原80公开Merkle身份/额外R及开发题排除、人工审阅与加密回读声明、不可覆盖且无正文的公开承诺；[开发侧元数据只读校验](../tools/c5_formal20_public_preflight.py)不定位密文或明文，不建立消费 claim。这些工具本轮只在合成题上验证，真实20题/原80正文均未由代理读取。
- [公开冻结准备入口](../tools/c5_formal20_freeze_preflight.py)和 `python tools/c5_formal20_owner_run.py preflight` 只核对源码/公开配置，固定 `execution_ready=false`；不接触私有路径、模型、Rhino、网络或消费状态。[spec草案](../eval/c5/rhino-formal20-spec-draft.json)与[runtime模板](../eval/c5/rhino-formal20-runtime-freeze-draft.json)仍不是可执行冻结。

## 合成验证覆盖与新隐私边界

[合成现场测试](../eval/test_c5_formal20_field_adapters.py)使用真实研究签名/许可/SQLite/私有文件协议/评分审计，但 Rhino几何与模型/SSH管道是模拟对象。覆盖40槽、盒体/播种/只读、二写和三写、错误别名零许可拒绝、前置收尾/迟到attach竞争、资源停止，以及模型输出、额外派发、密钥重现、远端库存、额外许可、计划、消费claim和结算篡改负控。这不是十二工具全现场覆盖或真实模型质量证据；既有native12实际证据只属于它自己的冻结。

本轮[CPU验证记录](../eval/c5/formal20-cpu-engineering-validation-20261005.json)记录18项现场合成测试及238份源码（含eval）身份，明确列出模拟组件/负控和零真实调用。现场环境守卫另核对所有已加载项目文件（含`__main__`与私有别名），不能仅凭模块命名前缀把未冻结源码放过。

合成测试发现默认隐私分类器会把场景JSON的`layer`结构键视为项目标签，阻断第二步。新的[formal20隔离检查](../training/c5_formal20_privacy.py)保留提示字节与原schema：题面及字符串值仍经原分类器检查，场景图层/组名仅准 `Default` 或 `C5-` 加1–64位ASCII字母/数字/下划线/短横线。非公开标签在签名前拒绝，绝不脱敏后发送。仅新正式ID使用此策略；旧开发协议和产品默认隐私规则未放宽。新策略须进入完整源码冻结、所有者批准与开发验证，不能事后改变正式题。

## 冻结前仍须完成，且不可借用 B 授权

2026-10-06晚间后续：保管人预检、人工审阅与加密回读声明已交回，[公开承诺](../eval/c5/rhino-formal20-public-commitment-v1.json)已登记/校验，代理未读取私有正文。以下第1项已完成保管交接而非执行冻结；第2项实际发现CLR/clr与四个动态程序集阻塞，339文件仅部分库存；第3项完整新冻结/双CI/精确批准仍缺。顶部状态及[只读审计](../eval/c5/formal20-field-readonly-audit-20261006.json)优先于下方历史措辞。

1. 仓库所有者在独立环境备好真正未见的20题、完整R/开发排除清单、人工语义与几何审阅、加密回读，并只交无正文公开承诺。当前正式题、密文身份和承诺均不存在；原80只由保管人私下比对，原离线run不得重读。
2. 新源码下的**实际环境/import闭包复核**与另行冻结、精确批准的合成现场开发探针：嵌入式Python/CLR及Mac tokenizer依赖、GPU资产与已加载依赖、现场播种/多步/清理/输出导出须实际核实。代码已实现但本轮没有调用Rhino或GPU；未知/动态CLR代码、外来import或漂移资产均fail closed。不能用CPU mock证明实际闭包，也不能借B授权执行新探针。
3. 在与正式题不重合的合成资料上完成 CPU 全链路与必要的受控真实 Rhino/模型开发门，再冻结**完整**源码/import闭包、Mac/Rhino/GPU环境、基座与 checkpoint132、公开承诺、40槽顺序、评分器、资源及停止条件；两项CI和仓库所有者对新正式 spec/runtime 两个**精确**哈希的直接批准须先于任何正式 claim。此批准不由本页、B授权或推送PR推定。

所有者最新精确回复为 **2026-10-06 22:00 Europe/Zurich到期（20:00 UTC），21:45停止生成（19:45 UTC）**；[v4资源记录](../eval/c5/rhino-resource-boundary-v4-20261005.json)仅替代旧截止，不改旧证据/批准。至少900秒导出，开发≤1/正式≤3/研究合计≤4、原累计≤16 GPU-hours不因续租扩大；A+B已有340.027秒，用量与服务商状态仍需执行前只读复核。当前不启动GPU、不读20题正文或原80、不建新正式run、不切默认混合路由、不合并PR。C4 NO-GO、v8 `formal_quality_fail`/59/60及原80永久消费保持不变。
