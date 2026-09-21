# B1–B4 LoRA 训练就绪与 C0–C2 验收报告

最近更新：2026-09-21

项目状态：**C0–C3 Completed — C4 NO-GO**

MornAI Ubuntu 22.04.4 + RTX 3090 24GB 已完成 C0–C4。C2 共 42 optimizer steps / 3 epochs；validation 结构化四指标均为 0。C3 的 45 条 A5 上，基座与 LoRA 四指标也均为 0/45，差值 0.0pp、净胜 0；独立审计通过且第二 run 已禁止。冻结 P2 真实 Rhino 配对为基座 4/30、LoRA 5/30，差值 +3.3pp、净胜 1、McNemar `p=1.0`，未达到 +10pp / 净胜 3 门槛。C4 最终裁决为 `NO-GO`，部署继续使用已验证的混合路线。

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

模型选择依据：7B 规模能在单卡 24GB QLoRA 上形成现实起点；官方 chat template 原生表达工具调用；首轮 210/45 条“指令→工具调用”数据目标短、边界清晰，可直接用工具名与参数结构精确率判断收益。长轨迹和其他视图不进入首轮实验。

只有预注册且可机械判定的工程故障（OOM、NaN/Inf、硬件或算子不兼容）才允许启用一个预登记的 operational fallback。fallback 只用于恢复可执行性，不与主配置择优；validation 收益低、收敛慢或结果不理想不构成 fallback 条件，而应作为主实验结果进入 C4 判断。

官方证据：

- [Qwen2.5-Coder-7B-Instruct 模型仓库](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
- [固定 revision](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct/tree/c03e6d358207e414f1eca0bb1891e29f1db0e242)
- [Apache-2.0 许可证](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct/blob/c03e6d358207e414f1eca0bb1891e29f1db0e242/LICENSE)
- [Qwen 官方模型规格与许可说明](https://qwenlm.github.io/blog/qwen2.5-coder-family/)

显存值最初是准入预算；MornAI RTX 3090 的实际模型加载峰值已在下文单独记录。4-bit 权重之外仍需计量化元数据、激活、LoRA/优化器、CUDA 内核和上下文余量，加载通过不能替代 backward 实测。

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
python tools/run_training.py tokenizer-audit --local-files-only
python tools/run_training.py smoke
python tools/run_training.py gpu-smoke --phase initial
# 等 initial 进程退出后，在新的进程中：
python tools/run_training.py gpu-smoke --phase resume
python tools/run_training.py gpu-smoke-audit
```

正式 `train` 现在要求有效的 C0 外部冻结清单、完整 C1 smoke 报告和 `--confirm-formal-training`。在两道门禁通过前不要运行；缺少任一条件时命令会在加载模型前失败。

实现保证：

- 数据加载器只能读取 train/validation，任何路径或 split 指向 holdout 都会失败。
- 使用基座同 revision tokenizer/chat template，并只对 assistant 工具调用目标计算 loss。
- tokenizer 与 base model 加载统一显式尊重 `RHINOCODER_MODEL_CACHE`；`HF_HUB_OFFLINE=1` 或 `TRANSFORMERS_OFFLINE=1` 会强制 `local_files_only`，不再依赖用户额外设置 `HF_HUB_CACHE` 才能找到用同一 cache root 预下载的固定 revision。
- 最大长度超限直接报出 `sample_id`，避免静默截断目标。
- QLoRA 仅训练适配器，启用 gradient checkpointing、NF4 与 BF16。
- checkpoint 自动发现最大 step；恢复前校验配置、基座和数据血缘。
- JSONL 日志记录 step/loss/learning rate/eval 指标；结束后保存最佳 adapter 和环境快照。
- 自动评测只跑 validation，输出 loss、perplexity、工具调用解析率、工具名/参数/完整序列精确率。
- adapter 文件逐项 SHA-256 后才登记到本地 `data/training/model-registry.jsonl`。
- 统一人工结论字段见 [`docs/training-experiment-report-template.md`](training-experiment-report-template.md)。

现有 `evaluate` 命令只允许 validation，这是刻意的训练期保护。C3 使用独立 [`tools/run_final_evaluation.py`](../tools/run_final_evaluation.py)；它不放宽或导入训练加载器，而是先冻结 C2 与评测实现、运行无读取 preflight，再以显式 experiment ID + freeze SHA-256 一次性声明消费。协议见 [`c3-final-evaluation.md`](c3-final-evaluation.md)。

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

### MornAI RTX 3090 实测

| 项目 | 已确认结果 |
| --- | --- |
| OS / GPU | Ubuntu 22.04.4 LTS / NVIDIA GeForce RTX 3090 24,576 MiB |
| 驱动 / CUDA | 550.107.02；`nvidia-smi` CUDA 12.4；PyTorch 2.10.0+cu126 |
| CPU / RAM / Swap | 12 核 / 31 GiB / 2 GiB |
| BF16 | `torch.cuda.is_bf16_supported()` 为真；1024×1024 BF16 CUDA 矩阵运算通过 |
| 数据 | train 210、validation 45；服务器未上传 holdout |
| Tokenizer | 255 条通过，最大 646/572 tokens，overflow 0 |
| 模型缓存 | 固定 revision 完整缓存约 15GB；禁用 Xet 后续传成功 |
| 4-bit / LoRA | bitsandbytes 4-bit 与所有 target modules 挂载通过 |
| 参数 | trainable 40,370,176 / all 7,655,986,688，0.5273% |
| 显存 | peak allocated 13.62 GiB；peak reserved 17.88 GiB |
| C1 GPU smoke | initial 完成 step 1 forward/backward/optimizer/checkpoint；独立进程 resume 到 step 2 并完成 validation；审计通过 |
| C2 正式训练 | 42 steps / 3 epochs；train loss 0.91673；388.29 秒；1.623 samples/s |
| C2 validation | loss 0.75035；perplexity 2.11774；parse/name/arguments/sequence exact 全为 0 |
| C2 导出 | checkpoint 30/40/42；最佳 adapter 已登记；adapter model SHA-256 `bbd7e4d…72d6ac` |

缓存下载曾在 Hugging Face Xet/CAS reconstruction 遇到 401；使用 `HF_HUB_DISABLE_XET=1` 和较长下载 timeout 后断点续传成功。运行时代码现直接把 `RHINOCODER_MODEL_CACHE` 传给 tokenizer/base model 的 `from_pretrained(cache_dir=...)`，严格离线仍保留 model ID + revision 血缘。

模型加载峰值是 C1 初始装载数据；后续 C1 已进一步证明 backward、optimizer、checkpoint 和独立进程恢复。C2 证明唯一配置可完成正式训练与导出，但 **不证明模型质量提升**：validation 结构化指标全为 0。不得因这一结果修改同一实验或启动第二配置；只有 C3 的冻结 base/LoRA 配对和独立 P2 结果才能进入 C4。完整汇总见 [`c2-qlora-training-report.md`](c2-qlora-training-report.md)。

## B4 / C1：GPU 主机接入清单

MornAI 主机参数以上述实测为准；不在公开仓库记录 IP、端口、凭据、Token 或私有绝对路径。历史文件名 `training/school_gpu.example.json` 继续作为通用主机模板，复制为被 Git 忽略的 `training/school_gpu.local.json` 后填写；严格检查仍会拒绝占位项。

| 类别 | 必填记录 | 验证方式 / 通过条件 |
| --- | --- | --- |
| 登录 | host、用户名环境变量、可选跳板、SSH key 规则 | 登录成功；地址和私钥不进入仓库 |
| 调度 | 类型、queue/partition、account、可选 QoS | 支持 Slurm、PBS 或直接节点；相应版本命令与提交模板通过 |
| GPU | 型号、显存 | `nvidia-smi`；单卡至少 16 GiB，推荐 24 GiB |
| CUDA/驱动 | driver、CUDA compiler/runtime | `nvidia-smi`、`nvcc --version` 与 PyTorch CUDA wheel 兼容 |
| 资源限制 | walltime、CPU、RAM | 满足运行预算或按主机上限调整作业参数 |
| 存储 | project/scratch quota、模型 cache | `df -h`、`quota -s`；模型、运行和备份均位于私有获批目录 |
| 下载/网络 | 登录节点与计算节点 Hugging Face 连通性 | 能取固定 revision；否则在允许节点预下载后离线加载 |
| 密钥 | `HF_TOKEN` 注入渠道 | 只经 scheduler secret 或权限 0600 文件，不进参数、日志或 Git |
| 导出 | adapter、manifest、metrics、evaluation | `rsync` 后逐文件 SHA-256 一致 |
| 备份 | 最佳 adapter + 最后可恢复 checkpoint | 获批的加密存储，完成恢复抽查 |

接入顺序：

```bash
# 使用主机支持的 Python 3.11/3.12 创建独立环境，并按 CUDA 版本选择 PyTorch wheel
python3 -m venv <approved-training-venv>
source <approved-training-venv>/bin/activate
python -m pip install -r requirements-training.txt

# 只传输 manifest、train、validation；不要把 holdout 放进 C1/C2 主机
python tools/run_training.py cluster-template-audit
python tools/run_training.py cluster-check --cluster-config training/school_gpu.local.json
python tools/run_training.py audit
# direct / Slurm / PBS 均需先通过 C0 外部冻结与 C1 smoke；正式 train 当前仍被门禁锁定。
```

`cluster-check` 只记录命令输出和环境变量是否存在，不记录 token 或密钥值。正式作业模板要求显式提供训练虚拟环境与私有模型缓存路径。

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
- 通用 GPU 主机模板审计：通过；私有主机配置继续保持 Git 忽略。
- MornAI RTX 3090 的环境、CUDA/BF16、数据、tokenizer、模型缓存、4-bit、LoRA、backward/optimizer/checkpoint/resume 已通过；C1 工程门禁完成。
- C0 已通过外部冻结清单解决自哈希并冻结；C2 唯一配置已训练、validation、保存和登记，没有触发 fallback 或第二配置。
- C2 validation 的结构化工具调用指标全为 0；这必须作为负面结果保留，不能用 loss 或训练完成掩盖，也不能声称本地模型收益。
- C3 一次性入口已实现并与训练入口隔离；正式 A5 运行完成，独立审计覆盖冻结血缘、先声明后读取、第二新 run 拒绝、90 条配对生成、资源事件与统计复算。
- A5 基座/LoRA 结构化四指标均为 0/45；P2 基座/LoRA 为 4/30 与 5/30，+3.3pp、净胜 1、关键安全回退 0。两层均未达到预注册门槛，C4 已裁决 `NO-GO`。

结论：不得重训同一实验或重复读取 A5。保留训练与评测资产，部署继续使用已验证的混合路线；若未来启动 dataset v2，必须创建新实验 ID、新预注册与新的未见保留集。完整结果见 [`c3-a5-holdout-report.md`](c3-a5-holdout-report.md) 与 [`c4-model-decision.md`](c4-model-decision.md)。
