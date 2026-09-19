# C0 模型实验预注册：rhinocoder-qwen25-coder-7b-itc-lora-v1

> 状态：`FREEZE READY — EXTERNAL MANIFEST NOT YET CREATED — FORMAL TRAINING LOCKED`
>
> 版本：`c0-v1`。本文件在任何正式 QLoRA optimizer step、A5 holdout 读取或 LoRA P2 运行前完成。合并到一个干净 Git commit 后，必须运行独立的 `tools/freeze_preregistration.py freeze` 生成外部不可覆盖清单；在该清单和完整 C1 GPU smoke/resume 报告同时通过前，正式 `train` 入口会拒绝执行。

## 1. 实验身份与冻结方法

- 实验 ID：`rhinocoder-qwen25-coder-7b-itc-lora-v1`
- 预注册版本：`c0-v1`
- 编写所基于的 Git revision：`561a447b9eb6025517f8d018714bde47584521c7`
- 正式冻结 Git revision：由合并后的干净 checkout 在外部冻结清单中记录；不得使用 dirty worktree 冻结。
- 负责人确认：项目所有者在启动 C2 前通过显式 CLI 确认；该确认不授权读取 holdout。
- 基座与 tokenizer：`Qwen/Qwen2.5-Coder-7B-Instruct@c03e6d358207e414f1eca0bb1891e29f1db0e242`
- 唯一配置：`training/configs/rhinocoder-qwen25-coder-7b-itc-lora-v1.json`
- 配置规范化 SHA-256：`ae38f0e158dc166940e90e2e335953914e969f841546b3d67e8a1a023ce4bcb1`
- A5 train：210 行，`1e533d29f13669b11019e60b76a0e5a77800a7e09df3c6d7750a5d9233d16a99`
- A5 validation：45 行，`2b71d0a8e138c0b188f86086178e06b72ff44421f88d7e615b86cd4a51845d56`
- A5 holdout：45 行；只采用 A5 manifest 中已冻结的哈希 `cdafcaa1a5f19fe748260b1f78ddee38c63e78d3959a326504e60e8fc585390e`，C0/C1/C2 不打开文件。
- P2：30 条；`eval/p2/hard_tasks.jsonl` SHA-256 为 `5fb261c61905e1e29927f1abef3ca5486a008eed63b520eefae236f9c7192772`。
- Prompt / Tool / Trace 版本：`closed-loop-v2` / `1.0` / `1.0`，MCP 工具数 23。

### 外部冻结清单

本文件不记录自身 SHA-256，避免自引用。`python tools/freeze_preregistration.py freeze` 在干净、已提交的 checkout 中创建 Git 忽略的 `data/training/c0/preregistration-freeze.json`。P2 哈希只由这个独立工具采集，不进入训练数据消费模块。清单记录：

- 本文件 SHA-256 和正式 Git revision；
- 唯一配置的文件及规范化 SHA-256；
- A5 manifest、train、validation 哈希，以及只从 manifest 取得的 holdout 哈希；
- P2 freeze/task/fixture/statistics/leakage 文件哈希；
- Prompt、MCP 工具和 Trace 契约组成文件及聚合哈希。

冻结清单自身的 SHA-256 由审计命令输出并写入正式 run manifest，而不写回冻结清单。冻结清单已存在时命令拒绝覆盖；任何实质修改必须使用新实验 ID 并保留旧清单。

## 2. 研究问题与唯一比较

主要问题：唯一 QLoRA 配置是否相对同 revision、未经微调的冻结基座，在相同任务、Prompt、工具契约和确定性推理设置下产生具有实际意义的工具调用与几何成功改进，同时不增加关键隐私、越权、几何破坏或恢复失败？

C3 锁定四路：

1. 未经微调的冻结基座；
2. 唯一预注册 QLoRA；
3. 锁定云端路线；
4. 锁定混合路由。

首轮禁止超参数搜索，禁止新增用于择优的第二个 LoRA 配置。checkpoint 只能按 validation `eval_loss` 选择；A5 holdout 与 P2 结果均不得参与 checkpoint 或配置选择。

## 3. Operational fallback

本实验**没有预授权的第二套超参数配置**。以下恢复动作不改变冻结配置，因此可作为 operational recovery：

- 从最后一个已校验 checkpoint 在干净进程中恢复；
- 对有明确 CUDA allocator 碎片证据的 OOM，重启进程并设置 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`；
- 对固定 revision 缓存损坏或不完整，删除损坏的单个缓存对象并重新取得同 revision，再核对哈希；
- 对瞬时主机/存储中断，恢复同一作业和同一 checkpoint，不改变 seed、数据顺序或训练参数。

只有以下机械故障允许触发上述恢复：

- CUDA OOM，且日志包含失败 allocation、当时 allocated/reserved/total 显存；
- loss 或梯度出现 NaN/Inf，且保存首次异常 step、最近有限 step、输入 sample ID 与环境快照；
- CUDA、bitsandbytes、PyTorch、PEFT 或 Transformers 报出明确的硬件/算子不兼容；
- checkpoint、缓存或存储 I/O 校验失败，并有文件路径、预期/实际哈希或系统错误码。

validation 表现差、收敛慢、收益不明显、成本较高，以及看到 A5/P2 结果后希望重跑，均不得触发 fallback。若上述不改配置的恢复仍不能执行，`v1` 记为工程 `NO-GO/inconclusive`；任何优化器、LoRA rank/alpha、学习率、epoch、序列上限、量化方式或基座变更都必须创建新实验 ID 和新预注册，不与本次结果择优。

## 4. 指标和实际意义门槛

A5 与 P2 始终分层报告。比例门槛同时写成净胜任务数，防止小样本百分比被夸大。

| 层级 | 数据层 | 指标 | `GO` 实际意义门槛 | 关键回退上限 |
|---|---|---|---|---|
| 主要 | A5（45） | 完整工具调用序列精确率，LoRA−基座 | 至少 `+10pp` 且配对净胜至少 5 题 | 不得低于基座 |
| 主要 | P2（30） | 真实 Rhino 几何成功率 / Pass@1，LoRA−基座 | 至少 `+10pp` 且配对净胜至少 3 题 | 不得低于基座 |
| 次要 | A5、P2 | 最终恢复率 | 每层最多比基座少 1 题，且下降必须非关键 | 任何关键恢复破坏为 0 容忍 |
| 次要 | validation | `eval_loss`、解析率、工具名/参数精确率 | 用于 checkpoint 选择和解释，不单独触发 GO | 不得用于选择第二配置 |
| 运行 | 各层 | 延迟、吞吐、峰值显存、成本、云调用比例 | 全量报告；RTX 3090 峰值必须低于物理显存 | OOM 未恢复则不可 GO |
| 安全 | 各层 | 隐私、越权、破坏性工具或数据泄漏 | 0 个新增关键失败 | 0 |

`GO` 要求两个主要门槛均达到、所有安全门槛通过，且没有被平均分隐藏的关键回退。置信区间不要求因小样本而强制排除 0，但必须原样报告；一两题偶然改善不能单独构成 GO。

## 5. 配对统计与失败处理

- A5 与 P2 分层计算，不合并为 75 条样本。
- 二元指标报告四格配对计数：LoRA 赢、基座赢、同成功、同失败；报告双侧 exact McNemar `p` 值作为描述性证据。
- 成功率差、Pass@1 差和恢复率差使用任务为重采样单位的配对 percentile bootstrap，seed `20260917`、10,000 次、95% 区间。
- 连续指标报告中位数、配对中位数差，并以相同 seed/次数给出 95% 配对 bootstrap 区间；同时保留 P50/P95 原始值。
- 不替换任务、不静默删除失败。模型 OOM、无效工具调用、无法完成几何或超出锁定轮数均计该路线失败。
- 仅当失败发生在模型产生首个 token/工具调用之前，且属于主机、网络、存储或 Rhino 连接基础设施错误时，允许对同一冻结槽位恢复一次；原尝试必须保留。第二次仍失败则记 missing，并同时报告 complete-case 与保守边界。
- 若任一层 missing 超过 5%，或 missing 的最有利/最不利处理可以改变 C4 结论，则不得给出 `GO`。
- 人工取消按失败计，除非在运行前已经记录为操作员安全中止；安全中止不替换任务，并进入 missing 敏感性分析。
- 多指标裁决优先级：安全/越权 → 几何成功 → 完整工具序列 → 最终恢复 → 资源、延迟和成本。

P2 已用于既有系统失败分析，因此只称外部困难回归集，不称完全盲测。A5 是一次性未见保留集。

## 6. GPU 环境、时间窗与退出条件

已确认环境：MornAI Ubuntu 22.04.4 LTS 云主机、RTX 3090 24,576 MiB、驱动 550.107.02、`nvidia-smi` CUDA 12.4、PyTorch 2.10.0+cu126、12 CPU 核、31 GiB RAM。BF16 CUDA 矩阵运算通过；固定模型的 4-bit 加载与 LoRA 挂载通过，峰值 allocated/reserved 为 13.62/17.88 GiB。上述结果尚不等于 backward、optimizer、checkpoint 或恢复通过。

租赁准确结束时间：**未提供，不伪造**。当前计划采用操作员控制的云实例，不假定固定的提供方截止时间。正式启动 C2 前必须在私有运行记录中填写当时可用预算；若存在硬截止，则按下列缓冲规则计算最迟停止时间。

- C1：两个独立进程，step 1 保存后退出，step 2 从 checkpoint 恢复并做一次 validation loss；最多 2 个 optimizer steps。
- C2：唯一锁定配置，3 epochs；以 C1 实测 step walltime 估算完整训练、validation 和 checkpoint 时间。
- 必要生成：在租期内优先完成基座与 LoRA 的 A5/P2 冻结输入原始生成；Rhino 执行与无需 GPU 的统计可在导出后完成。
- 缓冲：停止新训练的时间不得晚于“剩余可用时间小于预计未完成 GPU 工作 + 6 小时导出/哈希/恢复抽查缓冲”的时点。
- 立即退出条件：持续 OOM/NaN/算子不兼容；磁盘剩余低于 20 GiB；无法保留最佳 adapter 与最后 checkpoint；环境或数据哈希漂移；C0/C1 门禁失败；发现 holdout/P2 被非授权代码读取。

退出前必须导出并逐文件 SHA-256：外部 C0 冻结清单、C1 报告、最佳 adapter、最后可恢复 checkpoint、训练/validation 日志、环境快照、模型与 tokenizer revision、配置、run manifest、基座/LoRA 必要生成、任务/运行 ID、失败记录和 model registry。原始输出只保存在获批的私有或 Git 忽略存储；不得包含 Token、服务器凭据或连接信息。若使用临时推理端点，还要导出请求审计并记录关闭时间。

## 7. C1、checkpoint 与一次性 holdout 门禁

C1 必须使用独立 `data/training/gpu-smoke/` 输出，最多两个 optimizer steps，不写正式 `data/training/runs/`、model registry 或正式实验结果。完成条件：真实 forward/backward/optimizer、step-1 checkpoint、独立进程 step-2 resume、optimizer state 恢复、有限 loss、validation loss、峰值显存、walltime、环境快照及配置/数据/checkpoint 血缘全部通过；最后由 `python tools/run_training.py gpu-smoke-audit` 独立核验，不借用正式 `train` 命令做验收。

C3 holdout 前必须再次冻结：

- adapter/checkpoint 文件 SHA-256；
- 配置、Git revision、推理参数；
- Prompt/工具/Trace 契约版本及聚合哈希；
- A5/P2 任务哈希；
- 一次性评测冻结清单 SHA-256。

独立 holdout 入口必须与 `training.data.load_samples` 隔离，要求显式实验 ID 与冻结清单确认，append-only 写入 `holdout_consumed_at`、运行 ID、原始输出哈希，并拒绝重复消费。该入口尚未实现，因此即使 C2 完成也不得开始 C3 holdout。训练/validation 加载器永久拒绝 holdout。

## 8. C4 决策

- `GO`：两个主要实际意义门槛和所有安全门槛均通过，没有关键几何/工具/恢复回退，且资源可在实际验证平台运行。
- `MORE-DATA`：未达到 GO，但存在跨预注册指标稳定、可解释的局部正向信号；只针对失败簇建立 dataset v2，以新实验 ID 重新冻结，不重复声称旧 holdout 未见。
- `NO-GO`：主要门槛未达到、出现关键回退、工程不可执行，或 missing/血缘问题使结论不可信；保留数据与训练管线，继续云端或混合路由。

任何安全或破坏性回退优先于质量提升并否决 GO。A5 与 P2 方向冲突时不取加权平均：A5 工具序列提高但 P2 几何未达到门槛，最多为 MORE-DATA；P2 提高但 A5 工具序列或安全回退，同样不得 GO。

## 9. 平台声明

- 本次训练与 C1/C2 待验证平台：Ubuntu 22.04.4 + NVIDIA RTX 3090/CUDA。
- Rhino Agent 桌面层既有主要验证平台：macOS + Rhino 8；Windows 尚未完成发布验收。
- Windows 本地推理：not evaluated。
- macOS MLX / Metal / llama.cpp：not evaluated。
- Ubuntu 训练环境通过不等于 Rhino 桌面或跨平台本地推理通过。
- C4 之前产品继续使用已验证的云端/混合路线；`local-mock` 仍只承担接口与隐私安全替身，不冒充真实本地模型。
