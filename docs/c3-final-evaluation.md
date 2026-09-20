# C3 一次性最终评测协议

最近更新：2026-09-20

状态：**入口已实现并完成一次性 A5 评测；第二新 run 已永久禁止**

## 设计边界

`tools/run_final_evaluation.py` 是与 `tools/run_training.py` 分离的入口。训练与 validation 加载器继续永久拒绝 holdout；C3 不通过开关放宽该保护，也不导入训练数据加载模块。

评测分为四个不可混淆的动作：

1. `freeze`：在干净 checkout 中锁定 C0/C1/C2、adapter、最后 checkpoint、配置、模型、Prompt/工具/Trace/P2 契约、确定性推理参数和评测实现哈希。它只读取 A5 manifest 中的 holdout 行数与 SHA-256，不打开 holdout 文件。
2. `freeze-audit`：重新计算全部非 holdout 输入并拒绝漂移。
3. `preflight`：只检查 holdout 路径是否存在以及消费台账状态，明确返回 `holdout_file_opened=false`。
4. `holdout-run`：只有显式传入完全匹配的 experiment ID 与 freeze SHA-256 后，才先原子声明一次性消费，再打开并校验 holdout。

## 一次性与恢复语义

- append-only 台账使用 POSIX advisory lock，避免两个进程同时声明首次运行。
- 第一个 `started` 事件必须先于 holdout 文件打开并 `fsync`。
- 新 run 只允许一个；已有任何消费事件后，第二个新 run 在重新打开 holdout 前失败。
- 只有已记录 `dataset_verified` 的同一 run 可恢复一次；冻结哈希必须相同。完成、验证前失败或第二次恢复都会失败关闭。
- base 与 LoRA 原始生成逐条追加；每个推理段的 walltime、峰值 allocated/reserved 显存和样本 ID 写入独立资源事件流。恢复只补缺失的 route/sample 对。
- 完成事件锁定 raw generations、resource events 与 summary 的 SHA-256；`run-audit` 从这些不可变证据重算指标，不重新打开 holdout。

## 固定推理与统计

- 路线：冻结基座与 C2 已登记 LoRA；顺序为 base 后 LoRA，每次只驻留一个模型。
- 推理：固定 tokenizer/chat template、greedy decoding、batch 1、锁定 seed 与 `max_new_tokens=512`。
- A5 主指标：完整工具调用序列精确率，LoRA 减基座。
- 所有二元结构化指标都报告配对四格计数、双侧 exact McNemar `p` 值，以及 seed `20260917`、10,000 次任务级 paired percentile bootstrap 95% 区间。
- A5 与 P2 始终分层；此入口不把 P2 包装为盲测，也不会把它合并进 A5 统计。

## 命令

以下前三条不会读取 holdout：

```bash
python tools/run_final_evaluation.py freeze
python tools/run_final_evaluation.py freeze-audit
python tools/run_final_evaluation.py preflight
```

只有审阅 freeze 与 preflight 后，才可由操作者单独授权一次性命令：

```bash
python tools/run_final_evaluation.py holdout-run \
  --experiment-id rhinocoder-qwen25-coder-7b-itc-lora-v1 \
  --confirm-freeze-sha256 <EXACT_C3_FREEZE_SHA256>
```

中断后的唯一允许恢复形式：

```bash
python tools/run_final_evaluation.py holdout-run \
  --experiment-id rhinocoder-qwen25-coder-7b-itc-lora-v1 \
  --confirm-freeze-sha256 <EXACT_C3_FREEZE_SHA256> \
  --resume-run-id <EXACT_INCOMPLETE_RUN_ID>
```

本实验已于评测 commit `32bc6f4` 按上述流程完成一次消费，`run-audit` 通过；不得再次执行新 run。A5 原始样本、生成和消费台账都在 Git 忽略的私有目录中；公开仓库只记录协议与[聚合结果](c3-a5-holdout-report.md)。
