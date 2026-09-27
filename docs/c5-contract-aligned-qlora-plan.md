# C5：契约对齐后的第二轮 QLoRA 规划与预注册草案

状态：**C5-0 已通过并建立 PR #2；C5-1b 的 440/440 家族已获仓库所有者批准，审核台账与正式 320/60/60 开发 split 已冻结。C5-1c 的最终 holdout 承诺和一次性门仍未完成；不授权训练、GPU 租赁、holdout 消费或产品切换。**

日期：2026-09-27。实验 ID：`rhinocoder-qwen25-coder-7b-c5-contract-qlora-v2`。本地冻结契约 ID：`qwen25-v4-selector-v3-json-invoker-c5-v1`。机器清单与实际审计见 [C5-0/C5-1 离线冻结报告](c5-offline-freeze-report.md)、[dataset v2 冻结报告](c5-dataset-v2-draft-report.md)和 [`eval/c5/manifest.json`](../eval/c5/manifest.json)。仓库所有者是唯一 `reviewer_1` 和最终 holdout 独立保管人；开发数据审批已通过 exact-set attestation 绑定到公开哈希，训练前预注册仍须补齐 holdout 加密承诺、统计/单次消费门和工程资源决定。任何变更必须升版本，不得覆盖既有哈希。

## 1. 不可改写的历史边界

1. C4 第一轮实验永久保持 `NO-GO`。A5 上基座与 LoRA 的 parse/name/arguments/sequence exact 均为 0/45；P2 描述性配对为基座 4/30、LoRA 5/30，只多成功一题，未达到原 `+10pp / 净胜 3` 门槛。
2. 已消费的 A5 与已分析的 P2 只可作为历史失败诊断和回归来源，不能成为 C5 的训练、validation、development test 或最终未见 holdout。第一轮实验 ID、配置、adapter、原始结果和冻结报告保持只读，不以新配置续跑。
3. v8 正式 60 题仍为 `formal_quality_fail`、实际 59/60，不追认 PASS。R 支线的安全、控制器与真实 Rhino 证据不自动修改 C4/C5 的模型结论。
4. 默认产品继续使用现有混合路由。C5 即使 `GO`，也只授权进入独立产品接入验证，不自动切换默认路线。

## 2. 实验问题与假设

核心问题：**在训练、validation、离线评测和真实推理使用同一工具调用契约后，QLoRA 是否能相对同 revision 的冻结基座模型，在不增加安全回退的前提下，对合法工具调用、工具选择、参数、完整序列和真实 Rhino 任务产生预注册的实际改善？**

- `H1`：双阶段、单工具 schema 的契约对齐能让 LoRA 的合法解析率和完整序列精确率相对冻结基座产生可复核改善。
- `H2`：模型外工具目录选择 + 单一完整 schema 调用可在 2,048-token 上限内覆盖 C5 的冻结工具范围，而不需要把 23 个完整 schema 同时塞入上下文。
- `H3`：若离线结构化改善真实存在，它应在不做解析修复的控制器兼容性测试中保持，并在小规模真实 Rhino 配对中产生同方向信号。
- 零假设：契约和数据修复仍不足以让 LoRA 相对基座产生实际改善，或改善不能传递到安全控制器/真实 Rhino。

[C4 事后诊断](c4-posthoc-failure-diagnosis.md)确认首轮训练/C2 validation 未把运行时工具 schema 传入 Qwen chat template，而真实推理提供约 23 个工具；受控重渲染的 train/validation 中位长度由约 132/99 增至 13,239/13,206 tokens，255/255 超过首轮 2,048 上限。首轮目标只覆盖 6/5 种工具，且 train 155/210、validation 35/45 的 assistant 目标混有自然语言；P2 两路均有 20/30 个有效任务以零工具调用结束。这些是 **C5 的实验假设与设计依据，不是已经证明的唯一因果解释**。下游几何、感知或恢复能力必须在模型能够稳定形成合法调用后再归因。

## 3. 阶段与停止门

| 阶段 | 内容 | 进入下一阶段的必要条件 |
| --- | --- | --- |
| C5-0 | 契约、数据范围、指标、阈值、预算和泄漏控制冻结 | **已通过：**最小提交 `a87c65d`、PR #2 与仓库所有者非作者签核已形成；未自动合并 |
| C5-1 | dataset v2 构建与仓库所有者质量审查 | **1a/1b 已通过：**来源审计、440 家族 owner 审批与正式 320/60/60 开发 split；**1c 待完成：**最终 holdout 加密承诺、统计脚本与一次性 gate |
| C5-2 | CPU smoke 与最多两次有界 GPU 诊断 | 只验证可训练性、梯度、显存、吞吐、checkpoint/resume；不接触最终 holdout |
| C5-3 | 唯一正式 QLoRA 训练 | 冻结配置完成一个正式 run；adapter、日志、checkpoint 和环境完整导出 |
| C5-4 | 一次性离线最终 holdout 配对 | 基座与 LoRA 同输入、同解码、逐任务配对；先声明消费后读取 |
| C5-5 | 控制器兼容性 | 不做解析修复，输出能通过同一严格解析器、路由和安全门 |
| C5-6 | 小规模真实 Rhino 配对 | 仅 C5-4/5 通过后运行；使用全新预注册任务和隔离执行路径 |
| C5-7 | `GO / MORE-DATA / NO-GO` | 按冻结规则机械裁决，不因结果不佳降低门槛 |

任一阶段失败都保留证据并停止下游消费。C5-0 到 C5-2 不构成正式训练授权；当前完成的 C5-0/C5-1a/C5-1b 只形成可审计的契约、来源和开发 split 冻结。

## 4. 统一训练与推理契约

优先复用已通过 CPU 合成预算门和 R 支线逐步验证的协议，不重新发明与现有控制器不兼容的格式。R 的真实基座探针显示 v2 `<tool_call>` 标签与模型自然输出不匹配；v3 invoker 在 selector 已正确时 6/6 严格解析，v4 selector 仍有 10/12 的失败记录。因此 C5 冻结 **v4 required-aware selector + v3 裸 JSON invoker** 作为待训练契约；这些历史结果只是格式选择依据，不是 C5 模型质量证据。

### 4.1 冻结内容

- 基座与 tokenizer：`Qwen/Qwen2.5-Coder-7B-Instruct@c03e6d358207e414f1eca0bb1891e29f1db0e242`；保持与第一轮同 revision，以隔离契约/数据因素。
- system prompt：selector 和 invocation 各一份规范化 UTF-8 文本及 SHA-256；validation、离线评测和运行时必须调用同一渲染函数。
- chat template：固定 tokenizer revision 的 `apply_chat_template`；记录 transformers/tokenizer 版本及渲染后消息哈希。
- selector：展示按名称排序的 23 项短目录、用途和 required 字段，不展示 23 个完整 schema；严格输出裸 JSON `{"tool":"<name>"}` 或 `{"tool":null}`，禁止附加字段、解释、Markdown、重复键或第二个对象。
- invocation：只展示 selector 选中的一个完整原始 JSON Schema；严格输出一个裸 JSON 对象，恰含 `name` 与 `arguments`，name 必须等于选择结果，arguments 必须通过冻结 schema；不接受 v2 标签、Markdown 或说明文字。
- 澄清、拒绝和无工具：模型统一返回 `{"tool":null}`。冻结的模型外控制器根据缺参、隐私、安全或不支持原因产生结构化 `clarify` / `refused` reason code；不训练自由文本解释，也不把模型选择视为许可。
- 多步：每一步重新读取有界场景状态、重新选择并调用一个工具；不允许模型在一次输出中发多个调用，也不把无限历史拼接进上下文。
- 最大长度：总序列 2,048 tokens；selector 输出预留 128，invocation 输出预留 512。任何 prompt 或 target 超限均拒绝，不截断 schema、任务、场景或标签。
- 解码：最终基座/LoRA 配对使用同一确定性配置；温度、stop tokens、最大新 tokens 和超时在冻结清单中逐项记录。
- 解析：训练 target、validation、development test、最终 holdout、控制器和真实 Rhino 入口共享一个版本化严格解析器；禁止只在评测端添加补丁、正则修复或容错重试。

### 4.2 工具范围

selector 继续看到 23 项短目录，以测量相近工具区分和安全弃权；C5 adapter 的 invocation 与真实 Rhino 门冻结 **12 个核心工具**：`boolean_difference`、`create_box`、`create_cylinder`、`create_sphere`、`get_bounding_box`、`get_scene_summary`、`group_objects`、`move_object`、`rotate_object`、`scale_object`、`set_object_color`、`set_object_layer`。选择依据是 500 Trace 的实际任务/家族覆盖和当前 Rhino 任务价值；范围在最终 holdout 解锁后不得扩缩。

selector 选中核心范围外工具时，C5 路径必须明确 `unsupported_for_c5` 并回到现有混合路线；不得让缺少 invocation 监督的 LoRA 猜参数。C5 `GO` 仅适用于冻结工具子集，不外推到全部 23 个工具。

### 4.3 同源验证

冻结前生成逐样本 `prompt_sha256`、`target_sha256`、contract/tool-schema hash 和 token 计数；随机抽取的 train/validation/development 样本必须证明训练前缀与推理请求逐字节一致。契约测试必须覆盖未知工具、附加字段、重复键、非有限数、Markdown、多个调用、缺参、超长输入、场景漂移和 parser version 漂移。

## 5. dataset v2

### 5.1 合理规模

不机械扩张到几千条。目标为 **520 个不可拆分任务家族**：train 320、validation 60、development test 60、最终 holdout 80；每个可执行步骤产生 selector 视图，核心工具步骤再产生 invocation 视图，预计形成约 900–1,400 条严格结构化监督记录。500 Trace 审计已经给出实际基线，因此不再用 ±10% 模糊调整掩盖家族不足；若要改变计数，必须在 holdout 不可见时新建 spec 版本并说明统计影响。

- 现有 500 条黄金 Trace 的初始零读取审计得到 129 个家族；C5-1b 通过 ID/hash 排除已消费的 45 个 A5 holdout 来源后，正式候选只剩 103 个来源家族，因此新开发家族缺口修正为 337。337 个新家族与来源合计 440/943 条记录；增强内容 QA 为 0 findings，仓库所有者已批准 exact SHA-256 候选集，构建器已生成 440 行逐家族哈希绑定台账并再次审计通过。
- 最终 80 条 holdout 必须是新写、排重、开发期间不可读的任务家族，不能来自 A5、P2、R v6/v7/v8/v9/受控接入已消费题或其数值/措辞近重复。
- A5/P2 评测文件只提供历史错误类别、排除映射和门槛设计依据，不进入任何 C5 split。当前为坚持零读取，没有用 A5/P2 文件解析 500 Trace 的历史重叠；所以机器分配明确标为 planning-only、`accepted_into_dataset_v2=false`。正式接受数据前必须通过只含 ID/hash 的排除映射移除历史评测重叠，旧 adapter 输出也不能作为 C5 正标签。

新候选池已定向补齐来源缺口：12 个核心 invocation 工具均达到至少 28 个家族，并覆盖 selector 弃权、非核心 fallback、只读/写入、多步和错误恢复。数值模板与 0.92 高相似筛查均无发现；仓库所有者的 exact-set 批准已展开为每家族一行的决定台账，agent 推荐本身不充当签名。

增强审核发现原 24 家族下限无法同时支持 train≥20、validation/development 各≥4，且原多步模板会跨场景对象。现已在总家族数不变的情况下重配模板预算，使每个核心工具达到 28–73 家族并修复多步场景一致性。仓库所有者批准后，同一确定性 assignment 已正式锁定为 320/60/60：train 每工具 20–65，validation/development 每工具恰为 4，11 个非核心 selector 在三个 split 各有 1 家族；内容或 assignment 任一字节变化都会使现有批准失效。

### 5.2 覆盖与标签

- 训练集每个核心 invocation 工具至少 20 个独立家族；validation/development 各至少 4 个；最终 holdout 各至少 3 个。达不到时缩小冻结工具范围，不用模板复制凑数。
- selector 覆盖全部 23 个目录项、相近工具对、核心范围外 fallback、缺参澄清、隐私/安全拒绝和明确无工具任务。
- 最终 holdout 的预定结构为：40 条单步合法调用、12 条澄清、12 条拒绝/无工具、8 条多步、8 条错误恢复；多步和恢复按完整序列判分，同时逐步报告。
- 只读、写入、多步、场景变化、目标别名、数值边界、单位、错误回执和不确定结果都必须有显式元数据；模型输出不得混入无约束自然语言。

### 5.3 生成和人工审核

1. 从 500 条黄金 Trace 抽取任务家族、工具、参数、场景前置条件和失败类型；程序先转换为规范化中间表示。
2. 允许规则化数值变体和 AI 草拟缺口样本，但任何候选都必须经过 schema/场景断言、近重复检查、敏感信息扫描和人工逐项批准；AI 草稿不能自动成为黄金标签。
3. 单一所有者审核：仓库所有者以固定身份 `repository_owner` 作为唯一 `reviewer_1`，在同一逐家族台账中核对意图、工具、参数、契约渲染、期望控制结果、场景断言和 split。无需 `reviewer_2`；非所有者、agent 或 Codex 不得代签。任何一项不通过时回退为候选，不进入数据集。
4. campaign、模板族、数值归一化签名、语义近重复簇和来源 Trace 必须整体分区；同一家族的 selector/invocation、多步步骤和错误恢复视图不得跨 split。
5. manifest 保存来源、审阅者角色、生成器版本、contract/schema hash、逐文件 SHA-256、行数、token 分布和拒绝原因。原始客户数据、Rhino GUID、凭据、主机信息和完整私有 Trace 不进入公开仓库。

最终 holdout 由仓库所有者以 `repository_owner` 身份独立生成或封存，并与数据生成、训练和自动化代理保持职责隔离；开发/训练代理只能看到计数、分层和 manifest 摘要。保管协议已在机器清单中冻结为 80 家族、加密 artifact 承诺、排除语料哈希和 append-only 单次消费；本轮 `rows_read=0`，且未创建/记录明文路径。正式入口先 append-only 声明实验/adapter/代码/阈值哈希和消费时间，再解锁基座与 LoRA 的一次配对生成；第二次新 run 永久拒绝。

## 6. 训练策略与资源

### 6.1 暂定正式配置

| 项目 | 暂定值 |
| --- | --- |
| 实验 ID | `rhinocoder-qwen25-coder-7b-c5-contract-qlora-v2` |
| 基座 revision | `c03e6d358207e414f1eca0bb1891e29f1db0e242` |
| 量化 / compute | 4-bit NF4、double quant、BF16 |
| LoRA | rank 16、alpha 32、dropout 0.05；Q/K/V/O + gate/up/down |
| 最大序列 | 2,048；超长拒绝 |
| batch | 每卡 1、梯度累积 16 |
| optimizer / scheduler | 与 v1 同族；学习率暂定 `2e-4`、cosine |
| epoch | 暂定 3 |
| checkpoint | 每 10 optimizer steps；保留最近 3 个与最佳模型 |
| 正式 run | 1 个；不得用最终 holdout 选择配置或 checkpoint |

正式 checkpoint 先按 validation `sequence_exact` 最大选择；并列时依次比较 arguments exact、parse exact、最后才比较 eval loss。该规则及最小改善门必须在正式训练前冻结。

### 6.2 有限开发实验

允许最多两次、明确标记为非正式的诊断运行，且只能访问 train/validation/development：

1. 32–64 条样本的过拟合/格式 smoke，验证 loss mask、严格输出和 checkpoint/resume。
2. 不超过训练集 10%、正式步数 20% 的吞吐/显存/梯度稳定性 run；只允许按预登记规则确认可执行性或触发 operational fallback。

诊断 run 不进入最终比较，不注册为候选产品模型，不因指标高低增加第三个配置。若要改变基座、LoRA rank/alpha、学习率、epoch、序列上限或契约，必须在最终 holdout 消费前创建新的实验 ID/预注册；不能与 C5 正式结果择优。

### 6.3 预算、恢复和 fallback

- C5 初始预算上限暂定 16 GPU-hours：诊断/工程 smoke ≤4、唯一正式训练及恢复 ≤8、基座/LoRA 必要最终生成 ≤4。C5-0 必须用实测吞吐重算；超预算时先缩小数据或工具范围并重新冻结，不静默追加租期。
- checkpoint、optimizer、adapter、日志、环境、CUDA/驱动、Git、数据/契约哈希和 model registry 全部导出并逐文件校验。恢复只能从同实验同配置的最近完整 checkpoint 继续。
- 只有 OOM、NaN/Inf、硬件/算子不兼容、checkpoint 损坏或外部基础设施中断等机械故障可触发预登记 fallback。低准确率、收敛慢、没有胜过基座或结果难看都不是 fallback。
- 当前文档不授权租用、重启或连接 GPU；实际主机、预算支付和数据传输需另行确认。

## 7. 分阶段评测与冻结门槛

### A. 离线结构化最终 holdout

在 80 条全新任务上对冻结基座与唯一 LoRA 使用同一 prompt、schema、解码和 parser。逐任务报告 parse exact、tool name exact、arguments exact、sequence exact、clarify/refuse、LoRA 赢/基座赢/同成/同败、exact McNemar 和 paired bootstrap 95% CI。

C5 `GO` 的离线必要门：

- LoRA parse exact ≥90%；任何被控制器接受的输出必须 100% 通过 schema，不得靠评测后修复。
- 主要指标 sequence exact：LoRA−base ≥10pp、配对净胜 ≥8/80，且双侧 exact McNemar `p < 0.05`。
- tool name exact 与 arguments exact 各自 LoRA−base ≥5pp，且均不得低于基座。
- 澄清和拒绝正确率各 ≥85%，且不得低于基座；关键隐私/越权错误为 0。
- 不把 loss、平均分或某个饱和子集替代上述成套门槛。

这些阈值是当前草案，必须在最终 holdout 内容解锁前由预注册冻结；只能因样本规模或分层在**看不到结果**时调整并留下版本理由。

### B. 控制器兼容性

将 A 的原始输出原封不动送入冻结双阶段控制器，不新增 prompt、解析修复或重试：

- 100% 生成带 contract/model/task/schema/parser hash 的收据；有效调用的 schema 校验率 100%。
- LoRA 的两阶段协议完成率 ≥90%，未知工具、额外字段、重复键、多个调用和超长输出全部 fail closed。
- 记录 selector/invocation 输出 token、端到端延迟、吞吐、峰值 allocated/reserved 显存和失败分类。
- 任何未授权写入、许可/场景/账本绕过或不确定结果自动重试均直接阻断 C5 `GO`。

### C. 真实 Rhino 小规模门

仅 A/B 全部通过后运行。另行预注册 20 条全新、非 A5/P2/R 已消费题的配对任务，冻结任务、顺序随机化、代码、模型、Rhino 版本、控制器、安全门、评分器和哈希；基座与 LoRA 各一次，不补跑模型/工具结果。

- 覆盖核心范围内的只读、写入、多步、澄清、拒绝和错误恢复；每题记录几何读回、活动文档边界、许可、签名、持久账本、关闭/删密钥、延迟、显存和失败类别。
- LoRA 必须 ≥14/20，且相对基座至少 +15pp / 配对净胜 ≥3；关键安全违规、重复写入和未核实清理均为 0。
- 基础设施中断只按事前固定的一次补位规则处理并原样保留；不得重演 C4 P2 的补位偏差。
- 20 题只是迁移门，不外推一般产品成功率；单题成功不能替代配对统计。

C5 真实 Rhino 门可复用 R 已验证的隔离 headless、签名、场景、许可、账本和证据格式，但必须冻结 C5 自己的代码血缘。进入该门前至少关闭与研究证据直接相关的 R 阻断：完整源码/远端血缘、按任务重算的精确几何与场景链、最终活动文档哈希、迟到回执/关闭超时的不确定清理。产品级 loopback UI、真实用户开放和人类 PR 批准不是 dataset v2、离线训练或这组操作者受控研究夹具的前置条件；它们只在 C5 `GO` 后进入产品接入路线。

### D. 最终决策

- `GO`：A/B/C 全部达到冻结门槛且无关键安全回退。只授权准备受限产品接入验证和独立产品决策；默认混合路线不自动变化。
- `MORE-DATA`：离线存在预注册的稳定正向信号且安全无回退，但失败集中在一个有界、可解释的覆盖缺口或真实 Rhino 迁移证据不足。必须另建新实验 ID、数据增量和未见 holdout，不能改 C5 后重读原 holdout。
- `NO-GO`：主要离线门未达到、需要解析修复、真实 Rhino 无实际改善、出现关键安全回退或证据不完整。保留训练/数据/评测资产，如实结束当前 LoRA 路线，不再以产品化为由追加实验。

## 8. R 支线、产品与延期工作的依赖

- R 的 v8 `FAIL`/59/60、第五题真实烟测和所有失败收据永久保留；它们证明控制器/安全执行层的部分能力，不是 LoRA 效果证据。
- `codex/r-controlled-access-review@979bee4` 是已推送的脱敏评审代码快照，当前没有 GitHub PR；它可作为 C5 安全执行适配器的起点，但不能冒充现场源码或人类批准。
- C5 当前主线只需要 R 的最小研究交接：默认路线隔离、版本化代码/契约、fail-closed、持久账本、证据可复核和已知阻断清单。完整产品 opt-in UI、预览/发送绑定、真实用户开放和人类 PR 评审降为 C5 `GO` 后的次优先工作。
- P2b 真人可用性与精简 D 继续按需延期；它们不阻塞 C5。C5 也不以作品集需要为理由牺牲 holdout 隔离或安全门。

## 9. C5 启动前仍缺少的输入与决定

1. **已完成本地冻结：**experiment/contract ID、12 个核心 invocation 工具、23 项 selector 目录、严格 parser、同源渲染、解码、2,048-token 预算与门槛机器清单；仍须受控提交和独立签核。
2. **已完成 dataset v2 开发集冻结：**A5/P2/R 历史排除后为 103 个来源家族，337 个新家族已生成；440 家族/943 记录通过全量审计。仓库所有者作为唯一 `reviewer_1` 批准当前候选 SHA-256，440 行审核台账与正式 320/60/60 split 已锁定；不要求 `reviewer_2`。
3. **仍缺 C5-1c：**仓库所有者作为最终 80 条 holdout 的独立保管人提交不可读加密承诺，并完成统计脚本和一次性 holdout gate 的端到端审计；不得创建或读取明文 holdout 来完成此门。
4. 冻结正式配置、checkpoint 选择规则、解码参数、统计脚本、20 条真实 Rhino 任务生成/保管协议和 `GO / MORE-DATA / NO-GO` 门槛。
5. 明确 GPU 主机、最多 16 GPU-hours 预算、私有数据传输/导出路径和停止责任；在此之前不租赁或启动 GPU。
6. 在 C5-C 前选定 R 研究执行版本并关闭血缘、精确核验、最终哈希和不确定清理四类直接阻断；产品 UI/人类产品评审另行排期。

任何输入未冻结时，下一步只能继续离线设计、数据审计和测试，不得创建正式 adapter 或消费最终 holdout。
