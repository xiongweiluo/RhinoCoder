# C3 A5 一次性 holdout 配对评测报告

评测日期：2026-09-20

状态：**一次性 A5 评测完成并通过证据审计；A5 GO 门槛未达到**

## 冻结与消费血缘

| 项目 | 值 |
|---|---|
| 实验 ID | `rhinocoder-qwen25-coder-7b-itc-lora-v1` |
| 评测 Git revision | `32bc6f4192f42816678f3e84ee648e959cc35f04` |
| 训练 Git revision | `19bf8ca71a65edd88b2b04109c024ca1bdfa54ba` |
| C3 freeze SHA-256 | `af7d247c9eaa8d65d4f6eebce1ed19ef9090f3f71375e0c2ef9d8dab54eac478` |
| Run ID | `c3-4ad4d98c19374d229b30f0646db796a8` |
| Holdout | A5 `instruction_to_tool_call`，45 条；一次性消费 |
| 路线 | 冻结基座 / C2 已登记 LoRA；greedy、batch 1、最多 512 新 tokens |
| 恢复 / 第二 run | 0 / 禁止 |
| 独立 `run-audit` | `passed=true`；完成后未重新打开 holdout |

原始 holdout、逐题期望、模型生成和消费台账均保存在私有、Git 忽略目录，不进入公开仓库。本报告只发布聚合结果和不可逆哈希。

## 配对结果

| 指标 | 基座 | LoRA | LoRA−基座 | 配对净胜 | Exact McNemar p | Paired bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| Parse success | 0/45 | 0/45 | 0.0pp | 0 | 1.0 | [0.0, 0.0]pp |
| Tool name exact | 0/45 | 0/45 | 0.0pp | 0 | 1.0 | [0.0, 0.0]pp |
| Arguments exact | 0/45 | 0/45 | 0.0pp | 0 | 1.0 | [0.0, 0.0]pp |
| Full sequence exact（主指标） | 0/45 | 0/45 | 0.0pp | 0 | 1.0 | [0.0, 0.0]pp |

四项指标的配对四格均为：共同成功 0、仅基座成功 0、仅 LoRA 成功 0、共同失败 45。预注册 A5 `GO` 门槛要求至少 `+10pp` 且净胜至少 5 题；本次为 0.0pp / 0 题，明确未达到。

## 资源

| 路线 | Walltime | Median / P95 latency | Peak allocated / reserved VRAM |
|---|---:|---:|---:|
| 基座 | 1,064.13 s | 24.99 / 26.44 s | 5.35 / 13.97 GiB |
| LoRA | 769.79 s | 14.63 / 48.80 s | 5.51 / 14.01 GiB |

资源结果只描述本次服务器、量化栈和冻结推理设置，不外推到其他平台。

## 证据哈希

| 私有证据 | SHA-256 |
|---|---|
| Raw paired generations | `bb9e9cd2b0122580ea4d2adac54212883184d0bebd0fb8687f260a386b937568` |
| Resource events | `75a627142ba2f7cfbc3b4b662ce4ec5a0f1ea215e91ca36f6b772866f2c2159e` |
| Summary | `48aa3e8f1bfc56fb860a64705ad3fb13809fe72a4fc06956fed307b254628971` |
| Append-only consumption ledger | `78f99c03b602e62683c65ba72ee514e5f18b6119b6ec34ca04d126171812d836` |

全部证据已从租赁主机复制到本地 Git 忽略目录，哈希一致。完成后的 preflight 显示 `consumption_events=5`、`new_run_allowed=false`、`resume_run_ids=[]`。

## 结论边界

- A5 主门槛失败，因此本实验不可能得到预注册的 `GO`。
- 这不是“LoRA 与基座等价”的开放世界结论；它只说明在冻结 A5 工具调用序列口径下，两者均未产生可解析的目标格式。
- 不允许重训同一实验后再次使用 A5，也不允许为改善结果启动第二超参数配置。
- P2、云端和混合路线尚未完成同层比较。最终 `MORE-DATA / NO-GO` 仍需结合 P2 失败类型、安全/几何回退与替代路线成本；无论后续结果如何，本实验都不能判为 `GO`。
