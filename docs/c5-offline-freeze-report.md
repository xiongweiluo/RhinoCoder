# C5-0/C5-1 离线冻结与 500 Trace 审计报告

日期：2026-09-27。状态：**离线冻结包通过；dataset v2 尚未建成，不授权 GPU、训练或最终 holdout 消费。**

> **后续 C5-1b 修正：**本报告的 129 家族/缺 311 是在刻意零读取 A5/P2 时对全部 500 Trace 的来源审计。后续只读取历史 ID/hash 元数据排除 45 个已消费 A5 holdout 来源后，候选池实际保留 103 个来源家族，需新增 337 个；337 个新家族已草拟，440 家族自动门通过但仓库所有者逐家族审核未完成。当前状态见 [dataset v2 候选报告](c5-dataset-v2-draft-report.md)，原始来源审计结论不回写。

> **2026-09-27 治理修订：**仓库所有者是唯一必需的 `reviewer_1`，不再要求 `reviewer_2`；同一人也是最终 holdout 的独立保管人。这里的独立性是相对数据生成、训练和自动化代理的职责隔离。该修订不批准尚未审阅的候选数据，也不改变 `training.authorized=false`、`rows_read=0` 或任何历史实验结论。

本报告落实 [C5 规划](c5-contract-aligned-qlora-plan.md)的第一组可独立交付工作：选择正式候选契约、审计现有 500 条黄金 Trace、形成不泄露正文的分组/split 规划、冻结最终 holdout 保管协议，并提供可重复的 CPU 检查。它没有读取 A5/P2 评测文件或任何 C5 最终 holdout，没有加载模型权重、连接 Rhino 或修改默认产品路线。

## 1. 冻结结果

| 项目 | 冻结值 / 结果 |
| --- | --- |
| 实验 ID | `rhinocoder-qwen25-coder-7b-c5-contract-qlora-v2` |
| 契约 ID | `qwen25-v4-selector-v3-json-invoker-c5-v1` |
| 基座 revision | `c03e6d358207e414f1eca0bb1891e29f1db0e242` |
| selector | v4 required-aware 23 项目录；严格裸 JSON `{"tool":"…"}` 或 `{"tool":null}` |
| invoker | v3 单工具完整 schema；严格裸 JSON，恰含 `name` 与 `arguments` |
| 核心 invocation 工具 | 12 个；见机器清单，不对其余 11 个工具训练调用参数 |
| 总序列预算 | 2,048 tokens；selector 预留 128，invoker 预留 512；超限拒绝，不截断 |
| 解析修复 | 禁止 Markdown 提取、标签补写、参数补全、容错重试 |
| 产品权限 | selector 不是许可；非核心工具返回 `unsupported_for_c5`；默认混合路由不变 |

选择 v4 selector + v3 invoker 是对 R 支线实证的收敛，而不是追认 R 成功。v2 `<tool_call>` 在真实基座探针中稳定输出了不兼容的 Markdown/裸 JSON；v3 invoker 在 selector 已正确时 6/6 严格解析，但整门仍因选择/澄清失败而未通过；v4 selector 自身也只有 10/12。C5 因此冻结 R 中较可行的输入/输出形态，并把“能否经训练显著改善”留给新数据与新实验回答，不能把候选探针写成模型质量结论。

机器可读冻结入口为 [`eval/c5/manifest.json`](../eval/c5/manifest.json)，当前引用：

- `offline-freeze-spec.json`：`4339efb64d34654898930a5800be85d647878af3ea6705b41fb88e8ae79fc545`
- `source-audit.json`：`c75873e4b59320b3b10f945a070b4f10b99d424154534f3dd6c2ccf14160491e`
- 公开 23 工具 schema：`151c5453bf92f83343e93e53013bfc8f3518e5b6a7e9e2fc49e97ba863b0637d`

这些冻结值最初随 12 个严格限定的契约/审计/测试文件写入分支 `codex/c5-contract-freeze` 的提交 `a87c65d`，随后已推送并建立 [PR #2](https://github.com/xiongweiluo/RhinoCoder/pull/2)，没有夹带 R 现场证据或其他脏文件。仓库所有者已确认 reviewer 角色；后续分支推送及 PR 创建/更新已持续授权，但不包含自动合并。只有完成所有者数据审核和 holdout 加密承诺后，才能形成可执行的训练前预注册。任何契约、工具范围或门槛变更都必须生成新 contract/spec 版本，不能覆盖历史证据。

## 2. CPU 契约审计

固定 tokenizer 从本地 cache 加载，未下载或加载权重。相同函数生成训练标签前缀和推理前缀，逐字节一致；selector 选择、selector 弃权和 invoker 调用共 3 个严格 round-trip 通过。

| 检查 | 结果 |
| --- | ---: |
| v4 selector 合成提示 | 743 tokens |
| 12 个核心工具的单 schema invoker 提示 | 429–1,213 tokens |
| `create_box` 合成 invoker 完整标签 | 662 tokens |
| 12/12 保留 512 输出 token 后是否在 2,048 内 | 是 |
| 训练/推理前缀 | exact |
| 非核心工具 selector 结果 | fail-closed 至 `unsupported_for_c5` |
| GPU / 模型权重 / Rhino / holdout | 均未触达 |

正式封装在 [`training/c5_contract.py`](../training/c5_contract.py)。它组合既有 v4 selector 与 v3 invoker，不复制另一套 prompt/parser；训练、validation、评测和未来运行适配器都必须导入这一入口。源文件、system prompt、渲染前缀、tokenizer 与 schema 哈希均记录在 `offline-freeze-spec.json`。

## 3. 500 Trace 实际审计

只读取 `data/golden_traces_v2.jsonl`，SHA-256 为 `0b69147c58a19e95fa0d46d5281fbff1657245e7e8af30e6dfdada71965a28ea`。文件有 500 行、500 个唯一 task ID、500 个唯一 run ID；来源为 phase1 30、phase2 70、phase3 200、A7 200。公开审计只保存聚合值与加盐 task hash，不输出 instruction、arguments、工具结果或 reasoning。

沿用 A5 的保守规则，将相同 `campaign + exact tag set` 或数值归一化 instruction 连接成同一不可拆分组。结果不是 500 个独立家族，而是 **129 个家族**：98 个单题、1 个两题、20 个十题、10 个二十题。因此现有来源不能单独支持 320/60/60 共 440 个开发家族，至少还需 **311 个真正新增且排重后的家族**。这不是要求机械扩成数千条：新增家族应围绕契约负例、工具缺口和多步/恢复边界定向建设，每个家族只生成必要的 selector/invocation 视图。

12 个核心工具在 500 Trace 中都有调用，但按独立家族计算，训练最低 20 家族的直接缺口为：

| 工具 | 现有家族 | 达到 20 至少新增 |
| --- | ---: | ---: |
| `get_bounding_box` | 8 | 12 |
| `set_object_layer` | 9 | 11 |
| `scale_object` | 13 | 7 |
| `boolean_difference` | 16 | 4 |
| `rotate_object` | 17 | 3 |

其余核心工具已有至少 20 个来源家族，但仍需按最终 train/validation/development 分配及标签质量重新验收；“旧 Trace 中出现过”不等于已形成契约对齐的合格监督样本。

审计器给 500 个来源任务生成了保持家族完整的规划性分配：320/60/60/60 个任务落入 candidate train/validation/development/source reserve，对应 42/32/23/32 个家族。它只用来测量覆盖和缺口，**不是 dataset v2 接受清单**，也不能把任务数冒充家族数。新家族加入并完成语义近重复聚类后，必须从头生成正式的 320/60/60 家族 split lock。

## 4. 最终 holdout 零读取与保管协议

本轮没有创建、定位或读取最终 holdout；机器清单固定 `rows_read=0`、`content_created_by_this_command=false`、`content_path_recorded_in_repository=false`。冻结协议要求：

1. 80 个最终家族由仓库所有者以 `repository_owner` 身份独立保管；其不得把正文提供给生成/训练代理，也不得在正式一次性消费前用于 prompt、数据、阈值或 checkpoint 调整。
2. 仓库只接收加密 artifact SHA-256、80 家族计数与分层、排除语料哈希集合、作者/审核角色证明，不保存明文路径或正文。
3. 开发者在一次性正式评测前不可读；入口必须先写 append-only 消费收据，绑定 experiment、base、adapter、代码、契约、schema、阈值与解码哈希，再解密并同时生成 base/LoRA 配对结果。
4. A5、P2、R 已消费题及其数值/措辞近重复只进入排除语料或历史诊断，不得进入最终 holdout；不得因 C5 结果不好而二次消费或降低门槛。

保管协议和保管人身份已经冻结；**加密 artifact 承诺尚未产生**。这会阻止 C5 正式训练和最终评测，但不阻止在不可见 holdout 之外建设 dataset v2。

## 5. 可重复检查与边界

执行命令：

```bash
python -m pytest -q eval/test_c5_contract.py eval/test_c5_freeze.py
python tools/freeze_c5_offline.py build
python tools/freeze_c5_offline.py verify
```

结果：7 项新测试通过；build/verify 均通过。测试覆盖正式工具范围、非核心 fail-closed、严格格式、训练/推理同前缀、数值/语义家族不跨组、唯一允许的数据源、原文最小化、holdout 隔离声明与篡改检测。

本阶段完成的是 **C5-0a 契约/门槛的本地机器冻结**和 **C5-1a 来源审计/保管协议**。后续已完成 337 个新增开发家族及契约对齐视图草拟，但以下仍未完成，因此 `training.authorized=false`：仓库所有者对 440 个候选家族的逐项审核、正式语义排重和 split lock、holdout 加密承诺、统计脚本与一次性消费 gate 的端到端测试、GPU 主机/预算确认，以及进入真实 Rhino 小门前的 R 最小研究收尾。
