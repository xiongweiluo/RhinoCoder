# LoRA 实验报告模板

> 正式报告由 `python tools/run_training.py report --run-dir <RUN_DIR> --output <PATH>` 从只读运行证据生成。本文件定义必须保留的人工决策部分。

## 预注册

- 预注册 ID、冻结时间与文件 SHA-256：
- 唯一主配置 ID：
- 主要/次要指标与实际意义门槛：
- A5 / P2 分层的同任务配对统计方法：
- `GO / MORE-DATA / NO-GO` 判定规则：
- Operational fallback 配置与允许触发条件（仅 OOM、NaN/Inf、硬件或算子不兼容）：
- 是否触发 fallback、客观证据与触发时间：

> validation 表现不佳、收敛慢或收益不明显不得触发 fallback；正常完成但效果差属于实验结果。

## 实验血缘

- 实验 ID：
- 配置 SHA-256：
- Git revision：
- 基座模型 ID 与 revision：
- tokenizer ID 与 revision：
- 训练/验证数据路径、行数与 SHA-256：
- Prompt 与工具契约版本：
- 推理参数与评测任务哈希：
- Holdout 是否读取（C0–C2 必须为 `false`）：

## 环境与资源

- 集群、作业 ID、GPU/显存：
- CUDA、驱动、PyTorch、Transformers、PEFT：
- 实际 walltime、峰值显存与 checkpoint 总大小：
- 基座 / LoRA 推理吞吐与单任务峰值显存：
- GPU 使用窗口起止时间：
- 临时受控推理端点（如使用）的创建、请求审计和关闭时间：
- 导出文件清单与逐文件 SHA-256 校验：

## 训练结果

- loss 曲线及 NaN/Inf 检查：
- 最佳 checkpoint 与选择依据：
- 断点恢复验证：
- 验证集 loss / perplexity：
- 工具调用解析率、工具名精确率、参数精确率、完整序列精确率：
- 最终 adapter、最后可恢复 checkpoint 与 model registry 哈希：

## 最终冻结与一次性评测

- 最终 checkpoint / adapter SHA-256：
- 冻结配置与 Git revision：
- 冻结推理参数、Prompt/工具契约与任务清单哈希：
- Holdout 审计入口版本：
- `holdout_consumed_at`：
- Holdout 实验 ID / 运行 ID / 冻结清单哈希：
- 完整原始输出保存位置与 SHA-256：
- 分段资源事件保存位置与 SHA-256（base/LoRA walltime、峰值 allocated/reserved 显存）：
- append-only 消费台账完成事件与独立 `run-audit` 结果：
- 确认训练加载器的 holdout 保护未解除：

> A5 是一次性未见保留集；P2 是训练前冻结、但已用于既有系统失败分析的外部困难回归集。两者必须分层报告，不得合并包装成一个完全盲测集合。

## 与冻结基线比较

- 无微调基座：
- LoRA：
- 云端主模型：
- 规则混合路由：

每一路都应记录逐任务结果、几何成功率、Pass@1、最终恢复率、延迟、成本、GPU 资源、云端比例、隐私风险和工具错误率。A5 与 P2 分别提供同任务配对差值及置信区间；独立成功率区间不能替代配对分析。

## 失败与适用边界

- 共同失败任务：
- 仅基座成功 / 仅 LoRA 成功任务：
- 相对云端或混合路线的关键回退：
- 能通过路由、Prompt 或工具修复而不应扩数据的问题：
- 只能由失败簇定向数据补强的问题：
- 已验证的 Agent/Rhino 桌面平台：
- 已验证的本地模型推理平台：
- 未验证平台及其云端/混合回退：

## 结论

- [ ] 指标提升具有实际意义。
- [ ] 未读取 holdout 调参。
- [ ] 隐私、血缘和模型许可证检查通过。
- [ ] 未因 validation 结果启用第二套配置或 operational fallback。
- [ ] A5 holdout 只消费一次，且消费后未修改同一实验。
- [ ] 明确选择：`GO / MORE-DATA / NO-GO`。
- 决策依据与预注册阈值对照：
- 若 `MORE-DATA`：失败簇、dataset v2 范围、新实验 ID 与重新冻结要求：
- 若 `NO-GO`：保留资产、云端/混合路线和复评条件：
- 若 `GO`：仅限实际验证平台的部署范围、监控与安全回退：
