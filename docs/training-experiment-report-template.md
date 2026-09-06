# LoRA 实验报告模板

> 正式报告由 `python tools/run_training.py report --run-dir <RUN_DIR> --output <PATH>` 从只读运行证据生成。本文件定义必须保留的人工决策部分。

## 实验血缘

- 实验 ID：
- 配置 SHA-256：
- Git revision：
- 基座模型 ID 与 revision：
- tokenizer ID 与 revision：
- 训练/验证数据路径、行数与 SHA-256：
- Holdout 是否读取（B/C2 必须为 `false`）：

## 环境与资源

- 集群、作业 ID、GPU/显存：
- CUDA、驱动、PyTorch、Transformers、PEFT：
- 实际 walltime、峰值显存与 checkpoint 总大小：

## 训练结果

- loss 曲线及 NaN/Inf 检查：
- 最佳 checkpoint 与选择依据：
- 断点恢复验证：
- 验证集 loss / perplexity：
- 工具调用解析率、工具名精确率、参数精确率、完整序列精确率：

## 与冻结基线比较

- 无微调基座：
- LoRA：
- 云端主模型：
- 规则混合路由：

## 结论

- [ ] 指标提升具有实际意义。
- [ ] 未读取 holdout 调参。
- [ ] 隐私、血缘和模型许可证检查通过。
- [ ] 明确选择：进入最终 holdout / 调整一次配置 / 停止 LoRA 路线。
