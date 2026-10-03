# C5-3：第二轮契约对齐 QLoRA 训练记录

> **2026-10-02后续：**独立最终80家族已单次完成，C5-4/5原门槛通过并完整回收审计，见[最终报告](c5-final-evaluation-report.md)。以下“未消费”与结论边界是2026-10-01训练完成当时的真实状态，不覆盖原记录。整体C5仍等待R研究安全收尾/C5-6/C5-7，不自动接入产品。

日期：2026-10-01。状态：**C5-3 完整交付：唯一正式训练、checkpoint132 登记、73 文件导出及远端/本地逐字节复核全部通过。最终 80 家族 holdout 未消费，C5-4/5 未完成，不能宣告模型 GO 或接入产品。**

## 实验与来源

- 实验：`rhinocoder-qwen25-coder-7b-c5-contract-qlora-v2`；契约：`qwen25-v4-selector-v3-json-invoker-c5-v1`。
- 同一冻结基座 `Qwen/Qwen2.5-Coder-7B-Instruct@c03e6d358207e414f1eca0bb1891e29f1db0e242`，完整 snapshot 14/14 文件哈希验证；没有修改基座或首轮 adapter。
- 真实训练执行源：`160d1c7256bc5bb01a835cef8ea5f4b3f5a02326`；四个执行源文件、v3 条件授权、原 CPU 配置、数据/渲染血缘均锁定；后续文档与最终评测辅助提交不改变这次训练。
- 冻结开发集为 320/60/60 家族、697/126/120 记录。正式训练只用 697 train 记录；选模只用 60 validation 家族；development 与最终 holdout 不用于选模。
- GPU 是既有 RTX 3090 24GB；Python3.11.16、torch2.10.0+cu126、transformers5.2.0、peft0.18.1、accelerate1.12.0、bitsandbytes0.49.2、safetensors0.7.0。未租用新 GPU、重启实例或追加 run。

## 完整执行与选择

通过真实 overfit/system 工程门后重新加载干净基座并初始化新 adapter，不使用诊断权重。固定 NF4/double quant/BF16、rank16/alpha32/dropout0.05、七类 projection、batch1/accumulation16、lr2e-4/cosine/warmup5%、paged AdamW 8-bit、assistant-only labels、2,048-token 无截断；完成 3 epochs / 132 optimizer steps。

validation 真实生成 selector，再向其实际选中的单工具 schema 生成 invocation，不使用黄金选择强制正确工具。family 指标要求该家族的全部步骤通过，而非逐条平均：

| checkpoint | parse | tool name | arguments | sequence | eval loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| 44 | 60/60 | 59/60 | 58/60 | 58/60 | 0.0042089287 |
| 88 | 60/60 | 60/60 | 59/60 | 59/60 | 0.0008649210 |
| 132 | 60/60 | 60/60 | 59/60 | 59/60 | 0.0008472925 |

按预定 `sequence exact → arguments exact → parse exact → 最低 eval loss` 字典序选择 **checkpoint132**。88 与132前三项相同，但132 eval loss更低，故没有触发“全部相同时取更早 checkpoint”。没有按最终 holdout、训练 loss或现场成功择优。

正式 train 初始 eval loss `0.5448526382`，完成后 `0.0004146369`；全程梯度/loss 有限。峰值 allocated `14,864,003,584`、reserved `23,502,782,464` bytes；这些是正式执行进程的峰值，不是产品 standalone 推理显存。checkpoint API 与贪心解码的参数提示完整保留，未改配置消除警告、未发生 OOM/NaN/额外恢复或超预算。

机器结果：[formal result](../eval/c5/gpu-formal-result-20261001.json)、[唯一 registry](../eval/c5/gpu-formal-registry-20261001.json)。adapter 身份是两份文件哈希映射的 canonical SHA-256：`305d72703270d16e93233d1d34ae27cdaddd777e4530afead88c7edb8dc22cae`；不是单一 weights 文件哈希。weights 单文件为 `da8acdcde2671aa397534b35369fe4a84b9d150f80f7b7026a4366a770be2883`。

本地只读取已校验 weights 的 safetensors header，得到 `40,370,176` 个 adapter 参数、392 个 F32 tensor、weights 大小 `161,533,192` bytes；没有加载完整模型或读取最终数据。NF4/BF16 指基座量化与 matmul compute，不把 adapter 的实际 F32 存储误写成全模型 BF16。

## 资源与导出

durable start/finish 账本累计 overfit `0.5529171`、system `0.1206239`、formal `0.8964995` 活跃 GPU-hours，总计 `1.5700404`。诊断低于4、正式低于8、总计低于16；计时口径不冒充整机租期或官方费用，详见 [GPU 执行包](c5-gpu-execution.md)。

[远端导出审计](../eval/c5/gpu-export-audit-remote-20261001.json)与[本地独立复核](../eval/c5/gpu-export-audit-local-20261001.json)逐字节相同，核对 73 个文件、`2,197,879,663` bytes：全部保留 checkpoint 的 adapter/optimizer/scheduler/RNG、environment、连续 steps、validation、context、registry、日志和预算账本；manifest SHA-256 为 `4344f20ad5fe1a5f4cf37a6d84406dd49098f9ddb3bf83218600dbab1309703b`。只复制 overfit/system/formal 三个明确目录与结算事件，没有打包 R、基座、旧 LoRA、holdout 或其他脏文件。

权重/恢复文件保存在本地 Git 忽略、顶层0700的 `data/training/c5/runs/20261001-v3`，远端原件保留；不进入 PR。流式复制未生成重复 tar，完成后本地仍约2GB可用；没有删除任何旧资产或 R 证据。

## 结论边界与下一门

这证明第二轮训练/恢复/validation/登记管线可执行，并给出开发侧严格结构化信号。没有对同一基座在新的最终盲测上进行比较，因此不证明 LoRA 显著优于基座，更不证明真实 Rhino 几何或开放世界质量。

保持 C4 `NO-GO`、A5 两路0/45、P2描述性4/30与5/30、v8 `formal_quality_fail` / 59/60以及默认混合路由。只在完整导出与代码/adapter/阈值冻结、零读取 preflight通过后，由所有者独立保管终端单次运行 [C5-4/5 交接](c5-final-owner-runbook.md)；离线必要门失败就停止下游，不降低门槛或重读 holdout。
