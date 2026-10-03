# C5-6 十二工具研究运行边界：CPU 基础交付

2026-10-03后续状态为 `CPU_FOUNDATION_AND_NATIVE12_CONTROL_VERIFIED_NOT_COMPLETE_MODEL_GATE`。原2026-10-02交付仅为CPU基础；随后新的原生单次控制通过，不追认CPU测试为现场成功。这仍不是完整模型工程门、正式20题或 C5 GO。

> 后续模型桥状态（优先于下方历史段落）：[A 事前预注册](c5-modelbridge-development-preregistration.md)获精确批准后单次启动，但首个 Rhino hub open 即[失败退休](c5-modelbridge-development-failure.md)，生成/夹具/派发/holdout均为0；另获批准的人工安全收尾已删除九份临时密钥并解绑 hook，不追认为冻结 clean stop。[新 B 预注册与完整冻结](c5-modelbridge-development-b-preregistration.md)已建立，待新双 CI 和新精确所有者批准，尚未执行。[v3资源用量边界](../eval/c5/rhino-resource-boundary-v3-20261003.json)计入 A 的17.614秒并把B开发上限设为3500秒。下方“尚未冻结/旧截止”是本CPU基础交付时的历史文字；完整模型工程门依旧未关闭。

## 已落实的边界

| 模块 | 实现及验证范围 | 不能据此声称 |
| --- | --- | --- |
| [原 schema 导出](../eval/c5/rhino-runtime-schema-v1.json) | 原23项目录与12个完整参数 schema；core 参数 SHA-256 `4b5710c2b7f13513fd3355654d22bff6b5631be53ba3bbd20472c09063f40bf6` | 已换成旧 R 去目标协议 |
| [模型步适配](../training/c5_rhino_adapter.py) | 原 C5 selector/invoker/render/parser；一次选择、合法时一次调用，无修复/重试；真实别名场景规范化；物理身份不入提示 | 真实模型或端到端质量已通过 |
| [原生后端](../plugin/rhino_listener/c5_research_native.py) | 全12工具仅面向独立未保存 headless 毫米文档；主线程/活动身份/内容保护；实体质量、属性与拓扑读回 | 实际 Rhino API 已全部跑通 |
| [签名原子门](../plugin/rhino_listener/c5_research_gate.py) | 单任务/所有者冻结/场景/短 TTL 绑定；写前持久预留；零写只读台账；不确定会话与重放拒绝 | 签名或构造对象就是人类批准 |
| [许可签名器](../training/c5_research_permission.py) | 原始输出再解析且参数不改；生成时场景与当前场景交叉绑定；先消费许可后签名；持久 observation 预留阻止重签 | caller 自签所有者许可，或可以跳过运行审批 |
| [只读交叉审计](../training/c5_research_audit.py) | 两份 SQLite、许可四事件、模型交接、实际执行回执/场景/账本完整对应，遗漏/篡改/额外记录拒绝 | 生命周期、源码、签名密钥删除后重验或完整任务 PASS 已证明 |
| [独立几何评分](../training/c5_rhino_scorer.py) | 体积/实体/拓扑/顶点、尺寸、变换、组/层/RGB、只读结果与非目标不变；拒绝仅 bbox 的实体断言 | 几何通过可替代安全/许可/清理门 |
| [私有一次性 I/O](../plugin/rhino_listener/c5_research_channel.py) | 700目录/600文件、无符号链接、严格有限 JSON、原子不覆盖发布、固定状态根永久 slot claim、精确密钥删除 | 新输出目录可恢复消费槽，或已接入现场控制器 |
| [UI Idle 桥](../plugin/rhino_listener/c5_research_session.py) | 已批准夹具上的签名控制/执行、至少三个稳定样本、保留立即回执、失败不重放、关闭/实际删密钥/停hook；假UI+真文件/SQLite测试 | 已有实际打开入口、loaded import冻结、现场生命周期审计 |
| [源码/import 守卫](../plugin/rhino_listener/c5_research_provenance.py) | 冻结清单字节、外来/未冻 module origin、私有 namespace、符号链接/正文与权重路径拒绝 | 已完成实际运行 manifest 或独立第三方依赖/模型审计 |

Rhino 内模块仅依赖 Python3.9 标准库和 RhinoCommon，不导入训练包；Mac 许可/模型适配模块不由 Rhino 内嵌解释器导入。以上模块均无独立执行入口、无默认 Listener 注册、无自动批准/模型加载。

## 复用来源与版本边界

从 R 事前冻结 `b77e71e` 逐字节复用三份已验证基础源码，而非批量迁入 R 脏工作区：

- `training/consent_candidate.py`：`b65576b2dd947a5f53768df844be2714651471ff78fa91116266174fb6d30f12`。
- `plugin/rhino_listener/candidate_atomic_gate.py`：`e751305e7b78900ca09f929a4755e41acb1f51e1ffd9585fb32af35f271febf1`。
- `plugin/rhino_listener/candidate_alias_scene.py`：`dae8033935cb56b3ef1b4c2cac1d5e411e767cb4b4c3068a1451952608a185e8`。

许可 approval 事件明确是 `codex_delegated_headless`，不伪装真人点击。只有可信运行器先核实人类所有者对新 spec/源码冻结的直接批准，才可构造 signer；构造参数本身不是批准证据。R B 的批准只适用于 B 已消费的两写，不可借给新十二工具研究。R B 原源码、两个永久 claim 与私有证据不修改。

模型步骤须先在已核实当前夹具读回上构造 `step_input`，把当前物理状态作为**不发给模型的** `scene_binding` 交给 `invoke_step`。签名器同时核对这份状态及实际语义提示哈希；模型生成期间的漂移或旧结果不能重新签名。期望工具、参数及评分断言不进入生成接口。最终运行器还必须在生成/打开夹具之前，在固定所有者状态根登记永久 slot claim；只用内存列表不够。

## 本次验收与尚缺工作

新增 CPU 测试覆盖严格双阶段、全部12参数边界、只读/零写/TTL/错误作用域、真实 SQLite 预留/消费/跨实例重签拒绝、源场景漂移、几何假阳性、私有 I/O、source/import与假UI稳定/超时/关闭/stop。另有完整十二步 native-control 假UI/文件/SQLite wire 与每步独立评分/负控；这不是模型输出，不借用模型交接表伪造模型调用。全仓回归与 secret/release/diff 检查记录在本次分支交付及 CI；测试全部合成，不运行模型、Rhino 或正式题。

2026-10-03形成[固定 native12 开发预注册](c5-native12-development-preregistration.md)与独立新 ScriptEditor/Mac 驱动/审计入口。源码3106ea4/203文件、预执行e5524f4双CI和两个精确哈希批准后，`C5DEV-NATIVE12-20261003-A`单次现场执行并[独立审计通过](../eval/c5/native12-development-audit-20261003.json)：全12工具、10签名变更请求/2只读、终端无效HMAC零派发、每步几何/许可/账本/稳定读回、关闭/删钥/stop/活动文档保护均核实。74原JSON和两份一致DB backup私有封存，不归档密钥。该probe已消费、禁止重放，R B不重跑；模型/GPU/holdout0，不关闭完整模型/真实任务工程门。上表“不能据此声称”是原CPU基础自身的边界，现场子门只由这份独立实际报告支持，不由合成测试追认。

完整工程门尚未关闭。以下1/2是已完成的原生子门边界，3/4仍需有新 ID/spec/源码冻结和人类批准的独立开发验证：

1. 已闭合此次原生控制的 Rhino 官方 ScriptEditor/UI Idle 生命周期桥：实际源码/import守卫、私有通道、各步稳定读回、关闭回调/registry消失、实际密钥删除和stop原始证据。后续模型运行仍须独立绑定新冻结，不能沿用此已消费probe。
2. 已闭合固定全12原生 API/独立评分正控及终端无效HMAC现场负控；超时/漂移/重放/不确定状态的其它故障路径只有CPU测试证据，不宣称均已现场验证。后续工程验证仍禁止失败自动重试或使用正式题。
3. 新 C5 专用远端模型调用入口及实际闭包/环境冻结，复用已核实的原基座和 checkpoint132；落实[新资源边界](../eval/c5/rhino-resource-boundary-20261002.json)的开发≤1、正式≤3、合计≤4且原累计≤16 GPU-hours，沿用更早原停止截止及900秒导出预留。所有者已直接确认还有两天并同意配额，不将近似租期冒充服务商精确到期；该批准不是新烟测或正式运行批准。原最终 run/80 家族永久不重跑、不读取。
4. 模型原始回执→许可→签名→原生台账→稳定几何→生命周期的完整独立联合审计。两个局部审计器均故意返回 `formal_task_passed=false`，尚不能组装成完整任务判定。

只有这些工程门通过，才生成/冻结新20题并由所有者私下排除原80；随后按[执行准备稿](c5-rhino-paired-study-preregistration.md)审批并单次配对。LoRA至少14/20、净胜至少3/+15pp、关键安全/重复写/未核实清理0及默认混合路线均不变。没有正式题补位或门槛追认。
