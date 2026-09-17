# B1–B4 LoRA 训练就绪验收报告

验收日期：2026-09-06

项目状态：**GPU Access Available — C0 Preregistration Pending**

本阶段没有执行正式训练、没有下载 7B 权重，也没有读取 A5 holdout。项目所有者于 2026-09-17 确认已获得 GPU 访问；集群参数、CUDA/驱动、配额和调度器仍需在 C1 现场验收后才能启动训练。

## B1：首个实验范围

首轮只保留一个基座、一个训练视图和一组超参数。正式比较对象是未经微调的冻结基座与这一唯一 QLoRA 配置，不额外训练“保守版”参与择优：

| 项目 | 锁定值 |
| --- | --- |
| 基座 | `Qwen/Qwen2.5-Coder-7B-Instruct` |
| Revision | `c03e6d358207e414f1eca0bb1891e29f1db0e242` |
| 参数量 | 7,615,616,512 |
| 权重 | 官方 Hugging Face SafeTensors，BF16 |
| Tokenizer | 同一仓库、同一 revision 的 `AutoTokenizer` 与上游工具调用 chat template |
| 许可证 | Apache-2.0 |
| 主要训练视图 | `instruction_to_tool_call` |
| 配置数量 | 1；首轮禁止超参搜索 |
| 显存预期 | 16 GiB 最低、24 GiB 推荐 |

模型选择依据：7B 规模能在单卡 QLoRA 上形成现实的学校 GPU 起点；官方 chat template 原生表达工具调用；首轮 210/45 条“指令→工具调用”数据目标短、边界清晰，可直接用工具名与参数结构精确率判断收益。长轨迹和其他视图不进入首轮实验。

只有预注册且可机械判定的工程故障（OOM、NaN/Inf、硬件或算子不兼容）才允许启用一个预登记的 operational fallback。fallback 只用于恢复可执行性，不与主配置择优；validation 收益低、收敛慢或结果不理想不构成 fallback 条件，而应作为主实验结果进入 C4 判断。

官方证据：

- [Qwen2.5-Coder-7B-Instruct 模型仓库](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
- [固定 revision](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct/tree/c03e6d358207e414f1eca0bb1891e29f1db0e242)
- [Apache-2.0 许可证](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct/blob/c03e6d358207e414f1eca0bb1891e29f1db0e242/LICENSE)
- [Qwen 官方模型规格与许可说明](https://qwenlm.github.io/blog/qwen2.5-coder-family/)

显存值是准入预算，不冒充学校硬件实测：4-bit 权重约 3.8 GB，另计量化元数据、激活、LoRA/优化器、CUDA 内核和 2,048 token 上下文余量；正式接入时必须由 `nvidia-smi` 实测验证。

## B2：冻结配置

唯一机器可读配置为 [`training/configs/rhinocoder-qwen25-coder-7b-itc-lora-v1.json`](../training/configs/rhinocoder-qwen25-coder-7b-itc-lora-v1.json)，当前规范化 SHA-256：`ae38f0e158dc166940e90e2e335953914e969f841546b3d67e8a1a023ce4bcb1`。

| 参数 | 值 |
| --- | ---: |
| 最大序列长度 | 2,048；超长拒绝，不静默截断 |
| LoRA rank / alpha / dropout | 16 / 32 / 0.05 |
| Target modules | Q/K/V/O + gate/up/down projections |
| 量化 | 4-bit NF4、double quant、BF16 compute |
| 每卡 train/eval batch | 1 / 1 |
| 梯度累积 | 16（有效 batch 16） |
| 学习率 / scheduler | `2e-4` / cosine |
| Epoch | 3 |
| Seed / data seed | 20260906 / 20260906 |
| 验证与保存频率 | 每 10 optimizer steps |
| 最佳模型 | validation `eval_loss` 最小 |
| checkpoint 保留 | 最近 3 个；默认 `resume=auto` |

配置同时锁定 A5 pipeline 版本、训练/验证行数和文件哈希。运行目录已有 manifest 时，配置、基座或数据发生漂移会拒绝断点恢复。训练依赖固定在 `requirements-training.txt`，运行时额外记录 Python、依赖、Git、CUDA、驱动和 GPU 信息。

干净克隆不包含本地黄金数据。上集群时只传输 A5 `manifest.json`、train 与 validation 的 `instruction_to_tool_call.jsonl`；holdout 不传入训练作业。`audit` 会用冻结哈希验证这三个文件，CI 则用 `audit --no-data` 验证静态契约。

## B3：训练、恢复与评测

统一入口：

```bash
python tools/run_training.py audit
python tools/run_training.py tokenizer-audit
python tools/run_training.py smoke
accelerate launch --num_processes 1 tools/run_training.py train --resume auto
python tools/run_training.py evaluate --adapter data/training/runs/rhinocoder-qwen25-coder-7b-itc-lora-v1/best-adapter
python tools/run_training.py report --run-dir data/training/runs/rhinocoder-qwen25-coder-7b-itc-lora-v1 --output data/training/runs/rhinocoder-qwen25-coder-7b-itc-lora-v1/report.md
```

实现保证：

- 数据加载器只能读取 train/validation，任何路径或 split 指向 holdout 都会失败。
- 使用基座同 revision tokenizer/chat template，并只对 assistant 工具调用目标计算 loss。
- 最大长度超限直接报出 `sample_id`，避免静默截断目标。
- QLoRA 仅训练适配器，启用 gradient checkpointing、NF4 与 BF16。
- checkpoint 自动发现最大 step；恢复前校验配置、基座和数据血缘。
- JSONL 日志记录 step/loss/learning rate/eval 指标；结束后保存最佳 adapter 和环境快照。
- 自动评测只跑 validation，输出 loss、perplexity、工具调用解析率、工具名/参数/完整序列精确率。
- adapter 文件逐项 SHA-256 后才登记到本地 `data/training/model-registry.jsonl`。
- 统一人工结论字段见 [`docs/training-experiment-report-template.md`](training-experiment-report-template.md)。

现有 `evaluate` 命令只允许 validation，这是刻意的训练期保护。C3 前需要新增一个与训练加载器隔离的一次性 holdout 评测入口；不得把现有加载器的 `holdout` 拒绝逻辑改为普通开关。

固定官方 tokenizer 已对全部非 holdout 样本实测：train 210 条为 68–646 tokens（P95 484），validation 45 条为 113–572 tokens（P95 404），0 条超过 2,048。审计只下载 tokenizer/config，不下载 7B 权重；结果保存在 `data/training/tokenizer-audit.json`。

### CPU 冒烟实测

网络隔离的微型适配器完成 2 个训练 step，并在保存第 1 步后以新模型/新优化器恢复：

| 项目 | 结果 |
| --- | ---: |
| Train / validation / holdout 样本 | 2 / 1 / 0 |
| Step 1 loss | 5.642378 |
| 恢复后 Step 2 loss | 5.640349 |
| Validation loss | 5.691484 |
| Adapter-only 参数检查 | 通过 |
| Checkpoint 保存 / 恢复 | 通过 / 通过 |
| 网络 / 基座下载 | 未使用 / 未下载 |

机器报告位于 Git 忽略目录 `data/training/smoke/smoke-report.json`。

## B4：学校 GPU 接入清单

GPU 访问已获得，但实际学校参数尚未在本仓库执行 C1 验收，因此不伪造主机名、GPU、CUDA 或配额。已提供完整模板 `training/school_gpu.example.json`；C1 开始时复制为被 Git 忽略的 `training/school_gpu.local.json` 并填写。严格检查会拒绝任何 `REQUIRED/RECORD/VERIFY_AT_ACCESS` 占位项。

| 类别 | 必填记录 | 验证方式 / 通过条件 |
| --- | --- | --- |
| 登录 | host、用户名环境变量、可选跳板、学校 SSH key 规则 | 登录成功；私钥不进入仓库 |
| 调度 | 类型、queue/partition、account、可选 QoS | 支持 Slurm、PBS 或直接节点；相应版本命令与提交模板通过 |
| GPU | 型号、显存 | `nvidia-smi`；单卡至少 16 GiB，推荐 24 GiB |
| CUDA/驱动 | driver、CUDA compiler/runtime | `nvidia-smi`、`nvcc --version` 与 PyTorch CUDA wheel 兼容 |
| 资源限制 | walltime、CPU、RAM | 满足 8 小时模板或按学校上限调整作业参数 |
| 存储 | project/scratch quota、模型 cache | `df -h`、`quota -s`；模型、运行和备份均位于获批目录 |
| 下载/网络 | 登录节点与计算节点 Hugging Face 连通性 | 能取固定 revision；否则在允许节点预下载后离线加载 |
| 密钥 | `HF_TOKEN` 注入渠道 | 只经 scheduler secret 或权限 0600 文件，不进参数、日志或 Git |
| 导出 | adapter、manifest、metrics、evaluation | `rsync` 后逐文件 SHA-256 一致 |
| 备份 | 最佳 adapter + 最后可恢复 checkpoint | 学校批准的加密存储，完成恢复抽查 |

接入顺序：

```bash
# 使用学校支持的 Python 3.11/3.12 创建独立环境，并按学校 CUDA 版本选择 PyTorch wheel
python3 -m venv <approved-training-venv>
source <approved-training-venv>/bin/activate
python -m pip install -r requirements-training.txt

# 从本机安全传输且只传输 manifest、train、validation；不要把 holdout 放进训练作业
python tools/run_training.py cluster-template-audit
python tools/run_training.py cluster-check --cluster-config training/school_gpu.local.json
python tools/run_training.py audit
# Slurm:
sbatch --partition=<school-partition> --account=<school-account> scripts/train_school_gpu.slurm
# PBS:
qsub -q <school-queue> scripts/train_school_gpu.pbs
```

`cluster-check` 只记录命令输出和环境变量是否存在，不记录 token 或密钥值。正式作业模板要求显式提供训练虚拟环境与学校批准的模型缓存路径。

## C0–C4 执行边界

GPU 使用窗口不假定足够完成全部统计与报告。租期内优先完成 C1、正式 QLoRA、validation checkpoint 选择，以及原始基座/LoRA 后续比较所需的全部生成；租期结束后再做无需 GPU 的 Rhino 复核、云端/混合路线运行、配对统计、失败分类和 C4 决策。若无法在租期内完成生成，只能使用预注册、受控且可审计的临时推理端点，并在导出完整结果后记录关闭时间。

租期结束前必须导出并逐文件校验：

- 最佳 adapter 与最后可恢复 checkpoint；
- 配置、Git revision、基座 revision、tokenizer 与推理参数；
- 训练/validation 日志、环境快照、峰值显存和 walltime；
- 基座与 LoRA 的必要原始生成、运行 ID 和任务哈希；原始输出只进入获批的私有/Git 忽略存储，不进入公开仓库；
- model registry、逐文件 SHA-256 和备份恢复抽查结果。

正式 A5 holdout 运行前必须冻结 adapter/checkpoint 哈希、配置与 Git revision、推理参数、Prompt/工具契约版本和评测任务哈希。独立入口应要求显式确认，写入 append-only 的实验/运行 ID、`holdout_consumed_at`、冻结清单哈希与完整原始输出。holdout 只用于最终锁定方案的一次正式评测；消费后不得修改同一实验再重新声称未见。

A5 与 P2 不合并为一个样本池。A5 是 45 条未见保留集；P2 是 30 条训练前冻结、但已用于既有系统失败分析的外部困难回归集。四路比较应保留逐任务配对结果并分别报告差值置信区间；单独的成功率或 Wilson 区间不能替代配对差异分析。

C4 只允许三种结论：

- `GO`：达到预注册的实际意义门槛且无关键回退，在实际验证的平台进入本地或混合部署。
- `MORE-DATA`：存在稳定、可解释的局部正向信号；只针对失败簇建立 dataset v2，以新实验 ID 重新冻结。
- `NO-GO`：没有实际收益或出现明显回退；保留训练管线，继续使用云端或混合路由。

Agent/Rhino 桌面兼容与本地模型兼容分别验收。Windows + NVIDIA/CUDA 可以验证当前 QLoRA 推理路线；macOS 若采用 MLX、Metal 或 llama.cpp，必须作为独立推理路线验收。未验证平台不声明本地 LoRA 支持，只使用云端或混合路由。

## 验收结论

- B1–B4 共 12 项工程准备均完成。
- 配置审计：通过；train 210、validation 45，哈希与 A5 manifest 一致。
- CPU 保存/恢复/评测冒烟：通过。
- 学校接入模板审计：通过；13 个现场值等待 C1 填写，支持 Slurm/PBS/直接节点，严格检查不会把未知值当成通过。
- GPU 访问已由项目所有者确认，但当前不满足也不声称完成 C1：尚无现场 GPU 实测、正式训练或 holdout 评测。
- 唯一 QLoRA 配置、租期导出边界、一次性 holdout、配对统计与 `GO / MORE-DATA / NO-GO` 决策规则已写入计划；预注册文件和独立 holdout 入口仍须在相应门禁前完成。

结论：数据、唯一训练配置、恢复、validation 评测、登记、报告和学校接入门禁均已就绪；下一步先填写并冻结 [`training-preregistration-template.md`](training-preregistration-template.md)，再执行 C1 现场验收和站点配置。现有代码足以启动最小训练；C3 前仍需实现隔离的一次性 holdout 入口，不能解除训练期保护。
