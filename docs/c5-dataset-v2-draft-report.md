# C5-1b dataset v2 候选开发集报告

日期：2026-09-27。状态：**增强后的全量内容质量门通过；仓库所有者已批准当前 SHA-256 绑定的 440/440 家族，逐家族审核台账已生成，320/60/60 开发 split 已正式冻结。仍不授权训练、GPU 或最终 holdout 消费。**

## 结果

在不读取 C5 最终 holdout 的前提下，构建器生成了 440 个候选开发家族、943 条严格结构化记录：

| 类别 | 家族数 |
| --- | ---: |
| 排除历史评测后的黄金 Trace 来源 | 103 |
| 核心工具调用 | 240 |
| 非核心工具 selector/fallback | 33 |
| 澄清 | 20 |
| 拒绝/无工具 | 20 |
| 多步与恢复 | 24 |
| **合计** | **440** |

记录包括 536 条 selector 和 407 条 invocation；12 个核心 invocation 工具各有至少 28 个家族，实际范围为 28–73。固定 tokenizer 的 prompt 最大 1,272 tokens、完整序列最大 1,296 tokens，低于 2,048 上限；严格 parser/schema/round-trip、敏感信息、数值模板重复和 0.92 高相似度筛查均为 0 项发现。

本轮逐家族审计发现并修复了两个不能直接放行的问题：24 个多步家族原先会在后续步骤切换到不同场景对象；原 split 算法虽满足 320/60/60 总数，却无法保证每个核心工具达到 train≥20、validation/development 各≥4。修复后，多步家族始终绑定同一上下文；在总家族数不变的情况下，将来源覆盖充足的 box/cylinder/sphere 模板预算转移到六个稀缺工具，并用带 train 保留量的确定性约束分配替代无约束均衡。

## 历史排除修正

最初的 500 Trace 来源审计刻意不读取 A5/P2，因此得到 129 个保守家族并估算还需 311 个新家族。C5-1b 现在只读取历史评测的 ID/hash 元数据建立排除映射：

- A5：排除已消费 holdout 的 45 个来源 task ID；不读取 holdout JSONL 正文。
- P2：30 个已分析任务的 ID、数值归一化文本签名与冻结文件哈希进入排除表，不运行任务。
- R：7 个已消费任务源形成 289 个 ID hash 与 145 个数值文本签名，不运行 Rhino 或模型。

应用 A5 排除后，来源池为 455 个任务、103 个不可拆分家族，因此正式缺口修正为 **337 个新家族**。这取代“311”作为当前 dataset v2 规划值，但不回写或覆盖原始离线冻结 manifest；新排除清单单独版本化。

公开文件：

- [`eval/c5/historical-exclusions.json`](../eval/c5/historical-exclusions.json)：仅保存哈希、计数和来源文件哈希，不输出历史题目正文。
- [`eval/c5/dataset-v2-draft-manifest.json`](../eval/c5/dataset-v2-draft-manifest.json)：候选数据哈希、聚合审计和零 holdout 读取声明。
- [`eval/c5/dataset-v2-review-audit.json`](../eval/c5/dataset-v2-review-audit.json)：440 家族的 agent 内容质量建议、增强检查项与所有者批准仍为 0 的边界。
- [`eval/c5/dataset-v2-split-plan.json`](../eval/c5/dataset-v2-split-plan.json)：未签字前的确定性 split 计划；320/60/60 精确，12 个核心工具为 train 20–65、validation/development 各 4，11 个非核心 selector 每个 split 各 1。
- [`eval/c5/dataset-v2-owner-approval.json`](../eval/c5/dataset-v2-owner-approval.json)：所有者批准、候选/推荐/分配/台账哈希和 owner-only 审核边界。
- [`eval/c5/dataset-v2-freeze-manifest.json`](../eval/c5/dataset-v2-freeze-manifest.json)：正式 320/60/60 开发 split 的文件哈希、行数、审计结果与未授权训练声明。
- 构建器与质量门：[`training/c5_dataset.py`](../training/c5_dataset.py)、[`tools/build_c5_dataset_v2.py`](../tools/build_c5_dataset_v2.py)。

私有候选正文、所有者审核模板、agent 推荐台账和 provisional assignment 位于 Git 忽略目录 `data/training/c5/v2/`，不会随公共 manifest 上传。当前 draft SHA-256 为 `468d32aaac63e3c1ce0d91e032dd618115cb50bf97c9c9a997e43bec75271ced`，agent 推荐台账 SHA-256 为 `d4fc5e1d879795748e0e696191ecaa66869285ac1e0ddbdd1a0d635252113fd9`，provisional assignment SHA-256 为 `39b49d733e2f2ea7735728877dfc1b66c00dbaa42f8bb352e86c41ee306e0ee4`。

## 正式接受与冻结结果

自动审计本身不等于黄金数据获批。仓库所有者随后明确批准 draft SHA-256 `468d32aaac63e3c1ce0d91e032dd618115cb50bf97c9c9a997e43bec75271ced` 对应的全部 440 个家族，并授权正式 320/60/60 split。构建器先验证当前候选、agent 推荐与 provisional assignment 的字节级哈希，再把这份 exact-set attestation 展开为 440 行、每家族内容哈希绑定的 owner review ledger；任何内容变动、缺行、拒绝、非所有者身份或 `reviewer_2` 字段都会阻止冻结。

正式冻结结果为 train 320 家族/697 记录、validation 60/126、development 60/120；split 文件 SHA-256 分别为 `69cdcfbf…b192a`、`839b5fad…b370`、`1e7ad89d…786e`。当前 `accepted_family_count=440`、`owner_approved_family_count=440`、`formal_split_locked=true`、`training_authorized=false`、`final_holdout_rows_read=0`。私有候选、attestation、审核台账和 split 正文位于 Git 忽略目录；公开仓库只保存不可逆哈希、聚合统计和状态清单。

C5-1b 的开发数据接受与正式 split lock 已完成。[C5-1c 独立保管交接](c5-final-holdout-custody.md)也已完成：最终 80 家族的公开 commitment 已校验并不可覆盖登记，统计脚本与 append-only 单次 gate 通过测试，正文/路径/密钥未进入开发代理上下文，`final_holdout_rows_read=0`。[C5-2 CPU 工程子门](c5-engineering-gate.md)现已对冻结开发集的 943/943 条记录完成同源渲染、严格 round-trip、assistant-only label 与 token 审计；GPU 子门仍待主机和授权，本阶段不自动授权正式训练或 holdout 读取。

复核命令：

```bash
python -m pytest -q eval/test_c5_dataset.py
python tools/build_c5_dataset_v2.py draft
python tools/build_c5_dataset_v2.py audit
python tools/build_c5_dataset_v2.py review-packet
python tools/build_c5_dataset_v2.py plan-split
python tools/build_c5_dataset_v2.py owner-approve
python tools/build_c5_dataset_v2.py freeze
python tools/build_c5_dataset_v2.py audit --require-reviews
```
