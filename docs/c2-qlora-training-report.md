# C2 唯一 QLoRA 配置训练报告

最近更新：2026-09-20

状态：**C2 工程完成；validation 结构化质量为 0；尚无 LoRA 优于基座的结论**

本报告只汇总 MornAI RTX 3090 上已完成的锁定 C2 运行。原始 checkpoint、adapter、日志和注册表保存在私有、Git 忽略的训练目录；本文不包含主机地址、凭据、Token、私有样本或原始生成。

## 冻结血缘

| 项目 | 值 |
|---|---|
| 实验 ID | `rhinocoder-qwen25-coder-7b-itc-lora-v1` |
| 训练 Git revision | `19bf8ca71a65edd88b2b04109c024ca1bdfa54ba` |
| C0 freeze manifest SHA-256 | `40a0771d98f1a110266b8ee6bc1c2194b70f1649650a0b0dfa3363030b1927e5` |
| 配置 canonical SHA-256 | `ae38f0e158dc166940e90e2e335953914e969f841546b3d67e8a1a023ce4bcb1` |
| 基座 | `Qwen/Qwen2.5-Coder-7B-Instruct@c03e6d358207e414f1eca0bb1891e29f1db0e242` |
| 数据 | train 210 / validation 45；`instruction_to_tool_call` |
| Holdout / P2 读取 | `false` / `false` |
| 超参数变体 | 1；未触发 operational fallback，未运行第二配置 |

## C1 门禁

C1 使用与正式运行隔离的 smoke 目录完成两个独立进程：step 1 实际执行 forward、backward、optimizer 并保存 checkpoint；step 2 从同一 checkpoint 恢复到 step 2 并执行 validation。checkpoint、optimizer、数据、配置和 C0 血缘审计通过，正式运行目录与 model registry 均未被 smoke 污染。

C1 最终报告 SHA-256：`5a04dc0716077918d618da26aab8503be67c1494085df053349e8a0387fa709e`。

## C2 训练结果

| 项目 | 结果 |
|---|---:|
| Epoch / optimizer steps | 3 / 42 |
| Train loss | 0.916729979571842 |
| 训练 walltime | 388.2881 秒 |
| 吞吐 | 1.623 samples/s |
| 最佳日志 step | 40 |
| 最后可恢复 checkpoint | 42 |
| 保留 checkpoint | 30 / 40 / 42 |
| Validation loss | 0.7503477931022644 |
| Validation perplexity | 2.1177364226669964 |
| Tool-call parse / name / arguments / sequence exact | 0 / 0 / 0 / 0 |
| Adapter trainable parameters | 40,370,176 |
| Adapter model SHA-256 | `bbd7e4d05447719f243b97250fe0ee8eabae17ca7908dec2c95b52b46572d6ac` |
| Model registry registration ID | `a49a1cbfd9f8031bb6428faf` |

训练与保存过程完成，没有以 validation 结果触发第二配置或改变预注册超参数。随后对 3 条 validation 样本执行的只读诊断探针同样得到 0 个结构化命中：LoRA 更倾向输出自然语言建模步骤，另有输出使用错误标记结构。这一探针只用于解释既有 validation 结果，不用于选择新配置。

## 解释边界

- C2 的工程目标——唯一配置训练、checkpoint、adapter 导出、validation、注册和血缘——已经完成。
- validation loss 下降不能替代工具调用精确率；当前结构化指标全为 0，是明确的负面质量信号。
- 不能据此声称 LoRA 优于基座、能完成 Rhino 建模或应进入部署。
- C2 完成时 A5/P2 均未读取；后续一次性 A5 已按冻结协议完成且未达到 GO 门槛。P2 LoRA 尚未运行，不得因当前结果重训同一实验。

后续 C3 已完成一次性 A5 配对评测：基座与 LoRA 的结构化四指标均为 0/45，A5 GO 门槛未达到。详见 [C3 A5 报告](c3-a5-holdout-report.md)。
