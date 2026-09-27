# C5-1b dataset v2 候选开发集报告

日期：2026-09-27。状态：**自动质量门通过；仓库所有者逐家族审核未完成，正式 split 未冻结，不授权训练。**

## 结果

在不读取 C5 最终 holdout 的前提下，构建器生成了 440 个候选开发家族、955 条严格结构化记录：

| 类别 | 家族数 |
| --- | ---: |
| 排除历史评测后的黄金 Trace 来源 | 103 |
| 核心工具调用 | 240 |
| 非核心工具 selector/fallback | 33 |
| 澄清 | 20 |
| 拒绝/无工具 | 20 |
| 多步与恢复 | 24 |
| **合计** | **440** |

记录包括 548 条 selector 和 407 条 invocation；12 个核心 invocation 工具各有至少 24 个家族，实际范围为 24–89。固定 tokenizer 的完整序列最大 1,300 tokens，低于 2,048 上限；严格 parser/schema/round-trip、敏感信息、数值模板重复和 0.92 高相似度筛查均为 0 项发现。

## 历史排除修正

最初的 500 Trace 来源审计刻意不读取 A5/P2，因此得到 129 个保守家族并估算还需 311 个新家族。C5-1b 现在只读取历史评测的 ID/hash 元数据建立排除映射：

- A5：排除已消费 holdout 的 45 个来源 task ID；不读取 holdout JSONL 正文。
- P2：30 个已分析任务的 ID、数值归一化文本签名与冻结文件哈希进入排除表，不运行任务。
- R：7 个已消费任务源形成 289 个 ID hash 与 145 个数值文本签名，不运行 Rhino 或模型。

应用 A5 排除后，来源池为 455 个任务、103 个不可拆分家族，因此正式缺口修正为 **337 个新家族**。这取代“311”作为当前 dataset v2 规划值，但不回写或覆盖原始离线冻结 manifest；新排除清单单独版本化。

公开文件：

- [`eval/c5/historical-exclusions.json`](../eval/c5/historical-exclusions.json)：仅保存哈希、计数和来源文件哈希，不输出历史题目正文。
- [`eval/c5/dataset-v2-draft-manifest.json`](../eval/c5/dataset-v2-draft-manifest.json)：候选数据哈希、聚合审计和零 holdout 读取声明。
- 构建器与质量门：[`training/c5_dataset.py`](../training/c5_dataset.py)、[`tools/build_c5_dataset_v2.py`](../tools/build_c5_dataset_v2.py)。

私有候选正文和审核模板位于 Git 忽略目录 `data/training/c5/v2/`，不会随公共 manifest 上传。治理 schema 更新后当前 draft SHA-256 为 `955ee758efc0ce8f1469b221fabef09d277b0b319cfc43b031b7ec084ee79436`。

## 接受门

自动审计通过不等于黄金数据获批。构建器要求 440 个家族逐一由仓库所有者以固定身份 `repository_owner` 作为唯一 `reviewer_1` 批准；不再设置或要求 `reviewer_2`。任何拒绝、缺审、内容哈希不匹配、非所有者签名或 agent/Codex 自签都会阻止 `freeze`。只有所有者审核后再次通过全部审计，才写出精确 320/60/60 家族 split 和正式 manifest。

构建器、公开哈希清单和测试已在分支 `codex/c5-dataset-v2` 形成基础提交 `9dc1660`；私有候选正文未入 Git。当前 `accepted_family_count=0`、`training_authorized=false`、`final_holdout_rows_read=0`。仓库所有者身份已经冻结，但 440 家族的逐项决定台账尚未完成，因此 C5-1b 尚未完成，不能进入 C5-2。

复核命令：

```bash
python -m pytest -q eval/test_c5_dataset.py
python tools/build_c5_dataset_v2.py draft
python tools/build_c5_dataset_v2.py audit
```
