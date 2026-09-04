# 黄金数据冻结与恢复报告

## 结论

A1“冻结与备份 300 条黄金数据”于 2026-09-04 验收通过。

- 黄金记录：300 条。
- 唯一 `run_id`：300 个，无重复。
- 唯一 campaign/task ID：300 个，无重复。
- 完整 Trace：300 份。
- 截图引用：300 次，对应 299 个唯一文件；`p2-011` 的两次审核复用同一证据文件。
- 已接受反馈覆盖：300/300 个黄金 `run_id`。
- 采集及质量报告：66 份。
- Campaign manifest：3 份。
- SHA-256 清单：671 个源文件，共 55,722,516 字节。
- API 密钥与私钥扫描：通过。
- 隔离恢复演练：通过，671 个恢复文件与源文件逐一哈希一致。
- 本地权限：备份目录 `0700`，所有备份文件 `0600`。

## 冻结范围

备份包含以下本地证据，且保持原项目相对路径：

- `data/golden_traces_v2.jsonl`
- 与黄金 `run_id` 对应的 `data/traces/*.json`
- AI 审核记录引用的 `data/review_batches/` 截图
- `data/feedback.jsonl` 和 `data/ai_reviewed_candidates.jsonl`
- `data/collection_reports/` 下的采集、批次和质量报告
- `eval/collection/` 下三个 campaign manifest

备份不包含 `.env`、`.env.*`、模型密钥、项目外文件、符号链接、Partial/Fail 数据或训练产物。

## 本地备份产物

下列产物位于 Git 忽略目录 `data/backups/golden-set-300/`：

- `SHA256SUMS`：所有源文件的 SHA-256 清单。
- `MANIFEST.json`：冻结版本、Git 源版本和数据统计。
- `golden-set-300.tar.gz`：本地压缩备份。
- `ARCHIVE.sha256`：备份归档自身的 SHA-256。
- `RESTORE_VERIFICATION.json`：隔离恢复验证结果。
- `FREEZE_SUMMARY.json`：机器可读验收摘要。

本次归档 SHA-256：

```text
2572d67e5b4b57234c6a49f72157185bcde25fb570ee9d5019b21c94c541357e
```

冻结时的源版本为 `d65135138bdbb550e436c9faab7da1792c2d66a1`。`golden-set-300` 注释标签标记 A1 完成版本。

## 恢复演练

冻结工具将归档解压到独立临时目录，拒绝绝对路径、`..` 路径以及非普通文件，然后对 `SHA256SUMS` 中的 671 个文件重新计算哈希。结果如下：

- 清单文件与归档内清单一致。
- 恢复文件数量完整。
- 源文件与恢复文件 SHA-256 全部一致。
- 临时恢复目录在验证完成后自动清理，原始数据未被修改。

复现命令：

```bash
python tools/freeze_golden_set.py --overwrite
```

该命令会覆盖旧的本地备份，因此日常验证应优先读取现有的 `RESTORE_VERIFICATION.json`；只有明确需要重新冻结当前数据时才使用 `--overwrite`。
