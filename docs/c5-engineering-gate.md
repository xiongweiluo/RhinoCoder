# C5-2 工程门：同源数据渲染与有界 GPU 诊断

日期：2026-09-28。状态：**CPU 子门通过；GPU 子门等待主机、预算与显式诊断授权，不得据此启动正式训练。**

本门服务于实验 `rhinocoder-qwen25-coder-7b-c5-contract-qlora-v2`，不修改 C4，不读取最终 holdout，不调用 Rhino，也不改变默认产品路由。冻结配置见 [`eval/c5/c5-engineering-config.json`](../eval/c5/c5-engineering-config.json)，机器可读结果见 [`eval/c5/c5-engineering-readiness.json`](../eval/c5/c5-engineering-readiness.json)。

## 1. 已通过的 CPU 子门

专用入口 [`tools/run_c5_engineering.py`](../tools/run_c5_engineering.py)只接受显式的本地 tokenizer snapshot 和三个冻结开发 split；路径或文件名出现 `holdout`、`final_holdout`、A5、P2 时直接拒绝。它逐字节核对公开冻结哈希后，才使用 `training.c5_contract` 的 v4 selector / v3 invoker 渲染每条记录。

实测结果：

- 320/60/60 个 train/validation/development 家族与 697/126/120 条记录全部匹配公开冻结 manifest；
- 943/943 条记录完成训练/推理同前缀、严格 parser round-trip 和 assistant-only label 核验；
- selector/invocation 为 536/407 条；无无约束自然语言目标、无解析修复、无截断；
- prompt token 为 419–1,272，中位数 755；完整序列为 434–1,296，中位数 764；全部低于冻结的 2,048 上限；
- target 为 7–39 token，中位数 9；`overflow_records=0`；
- 确定性 64 条过拟合 smoke 索引已冻结为 32 selector + 32 invocation，覆盖全部 12 个核心调用工具；只保存 record ID 集合哈希，不公开私有正文；
- `gpu_used=false`、`model_weights_loaded=false`、`final_holdout_rows_read=0`、`single_use_claim_executed=false`。

复核命令（路径由保管开发数据的环境显式提供）：

```bash
python tools/run_c5_engineering.py \
  --dataset-dir /absolute/path/to/c5/v2/accepted \
  --tokenizer-snapshot /absolute/path/to/c03e6d358207e414f1eca0bb1891e29f1db0e242 \
  --output eval/c5/c5-engineering-readiness.json
```

## 2. 冻结的 GPU 诊断边界

GPU 诊断不是超参数搜索，最多两个 development run，总计不超过 4 GPU-hours：

1. **64 条过拟合 smoke：**32 selector + 32 invocation；batch 1；最多 128 optimizer steps；step 1 保存并在独立进程恢复；要求 loss 全程有限、checkpoint/optimizer lineage 不变，最终 loss 相对初始至少下降 25%。结果只判可训练性，不选择正式 checkpoint。
2. **条件式系统诊断：**只有第 1 项通过才允许；最多 32 个 train 家族（正式 train 的 10%）和 26 optimizer steps（预计正式步数的 20%）；验证显存、吞吐、validation 调用、checkpoint/resume 和日志导出。不得改 rank、学习率、模板、schema、阈值或最终 holdout。

固定训练面是 NF4 + double quant + BF16、rank 16、alpha 32、dropout 0.05、Q/K/V/O 与 gate/up/down projection、batch 1 / accumulation 16、2,048 token。诊断失败时按以下方式处理：

- OOM：立即停止并保留失败报告；可验证 checkpoint 清理/恢复，但不得静默缩短序列、减少模块或改量化配置后继续冒充同一冻结诊断；
- NaN/Inf：立即失败，不自动重试；记录首个非有限 step、环境和最后有效 checkpoint；
- 主机/网络/磁盘中断：只从哈希核验通过的本 run checkpoint 恢复；无法证明 lineage 时新建 development run，并计入最多两次限制；
- 超时或预算耗尽：保持 C5-2 未完成，不启动 C5-3；不得用 CPU toy loss 代替 7B QLoRA 证据。

## 3. 尚未满足的输入

进入 GPU 子门前仍须得到并记录：

- 实际 NVIDIA 主机与至少 16 GiB（推荐 24 GiB）显存；
- 基座模型完整 snapshot 的 revision/hash 血缘与严格离线加载路径；
- 最多 4 GPU-hours 诊断预算、停止责任和产物回传目录；
- 将配置中的 `gpu_authorized=false` 通过新的受审提交改为一次性诊断授权；不得覆盖当前 CPU 报告或复用第一轮实验 ID。

这些输入未齐时，C5-2 只标记为 **CPU 子门通过 / GPU 子门待定**。最终 holdout commitment 虽已登记，但 `claim` 仍只属于 C5-4；C5-2/C5-3 均不得执行。
