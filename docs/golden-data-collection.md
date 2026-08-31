# 真实黄金轨迹采集指南

本流程用于在单台 Mac、Rhino 8 和 DeepSeek 兼容 API 环境下逐步积累真实黄金轨迹，不需要 GPU。

## 阶段目标

| 阶段 | 黄金轨迹目标 | 主要目的 |
|---|---:|---|
| 第一阶段 | 30 | 验证采集、人工复核、脱敏和准入流程 |
| 第二阶段 | 100 | 统计失败分布、工具覆盖和任务稳定性 |
| 第三阶段 | 300 | 补齐长尾任务，为后续扩大数据做准备 |
| 后续 | 1,000–5,000 | 数据质量稳定后再考虑 LoRA |

这里的目标是“通过全部黄金准入条件的任务数”，不是模型调用次数。失败、Partial 和未审核轨迹不会冒充黄金数据，但会保留在本地错误分析集中。

## 第一阶段任务设计

第一阶段清单位于 `eval/collection/phase1_30.json`，包含：

- 30 条不重复的自然语言指令。
- 29 个任务标签。
- 难度分布：L1 3 条、L2 6 条、L3 11 条、L4 9 条、L5 1 条。
- 已覆盖单体、组合、阵列、空间关系、感知、自纠错、布尔、拉伸、旋转、移动、分布、对齐、Undo、群组、图层与侧向贴合。
- 最多允许两条指令仅通过替换数字形成相同模板。

清单会在本地检查和 CI 中验证任务数量、ID、指令唯一性、断言结构、难度和必须标签。它不会加入默认 30 题基准，因此不会改变 `0.2.0` 的正式基准口径。

## 安全前置条件

1. 在 Rhino 中新建一个空白、可丢弃的 `.3dm` 文档。
2. 不要在包含项目模型、客户数据或未保存对象的文档中运行采集器。
3. 启动 Rhino Listener，并确认 Agent 与 Rhino 使用相同的 `RHINOCODER_EVAL_TOKEN`。
4. 确认 `.env` 中的模型配置和余额有效。
5. 理解 Closed-loop 会把用户指令和场景摘要发送给所配置的模型 API；不要使用真实客户名称、项目图层或敏感场景。

先运行：

```bash
python tools/doctor.py
python agent/data_collector.py --dry-run
python agent/data_collector.py --status
```

采集器启动时会读取当前场景。如果文档非空，它会拒绝继续，不会默认清场。

## 推荐采集节奏

默认推荐使用 5 条一批的 AI 辅助审核：每条先通过程序断言、Scene Summary、Tool Trace 和 Rhino 视口检查，明确正确的轨迹只进入 `ai_reviewed_candidate`，整批收齐后再由人类一次性确认。AI 审核不能直接写入黄金集。

第一次只跑一条验证链路：

```bash
python agent/data_collector.py --allow-reset --limit 1
```

流程会显示任务，再要求输入 `RUN` 才会清空专用采集文档并执行。运行结束后必须在 Rhino 中人工检查，再输入：

- `y`：完全正确。
- `p`：部分正确。
- `n`：错误。
- `q`：退出，本条只保留脱敏 Trace，不进入训练数据集。

确认流程稳定后，每批建议 3–5 条：

```bash
python agent/data_collector.py --allow-reset --limit 5
```

使用五条批量审核模式：

```bash
python agent/data_collector.py \
  --review-mode batch \
  --batch-size 5 \
  --allow-reset \
  --limit 5
```

AI 审核员会为通过项记录项目内相对截图路径和审核摘要。五条收齐后生成汇总：

```bash
python agent/data_collector.py --batch-status phase1-30-batch-01
python tools/report_collection_campaign.py \
  --batch-id phase1-30-batch-01 \
  --output data/collection_reports/phase1-30-batch-01.md \
  --json-output data/collection_reports/phase1-30-batch-01.json
```

人类检查汇总截图与指标并一次性同意后，运行：

```bash
python agent/data_collector.py --approve-batch phase1-30-batch-01
```

终端仍要求输入精确的 `APPROVE`，避免误触。晋级会先验证整批，再原子写入；任一候选不符合黄金门槛时，整批都不会部分入库。已经逐条确认的任务会显示为 `golden`，不会被重复写入。

同一进程会在下一条任务前清理上一条采集产生的对象。若进程中断且场景仍非空，最安全的做法是新建空白文档后继续。只有确认当前文档完全可丢弃时，才允许显式使用：

```bash
python agent/data_collector.py --allow-reset --allow-nonempty-reset --limit 1
```

## 人工确认标准

只有同时满足以下条件才能输入 `y`：

- 对象数量与任务一致，没有多余对象。
- 几何类型、尺寸、颜色、图层和群组正确。
- 对齐、间距、贴合、上下关系和中心位置正确。
- Tool Trace 没有未恢复错误。
- 至少成功执行一次 `get_scene_summary`。
- 程序化断言显示全部通过。

如果肉眼发现问题，即使程序断言通过也必须选择 `p` 或 `n`。如果程序断言失败，即使模型看起来接近正确，也不能进入黄金集。

## 准入与本地数据边界

黄金轨迹必须同时满足：

- `run.status == completed`。
- 程序化断言全部通过且不是 Partial。
- 至少一次 Scene Check。
- 成功调用 `get_scene_summary`。
- 人工反馈为 `accepted`。
- 脱敏审计通过。
- 同一 campaign 的同一任务尚未进入黄金集。

本地文件均被 Git 忽略：

- `data/golden_traces_v2.jsonl`：黄金轨迹。
- `data/ai_reviewed_candidates.jsonl`：AI 已审核、等待人类批量确认的候选。
- `data/review_batches/`：本地 Rhino 视口截图和批次报告。
- `data/partial_traces.jsonl`：程序或人工 Partial。
- `data/error_traces.jsonl`：失败与断言未通过。
- `data/candidates.jsonl`：其他候选。
- `data/traces/*.json`：每次运行的脱敏完整 Trace。
- `data/feedback.jsonl`：人工反馈。

不要手工复制记录进入黄金文件；写入边界会重新检查准入证据和任务重复。

## 进度与复盘

查看断点续采状态：

```bash
python agent/data_collector.py --status
```

生成本地 Markdown 与 JSON 报告：

```bash
python tools/report_collection_campaign.py \
  --output data/collection_reports/phase1-30.md \
  --json-output data/collection_reports/phase1-30.json
```

报告包含黄金数量、剩余任务、难度与标签覆盖、工具调用、token、成本区间、程序断言失败和黄金准入失败分布。

完成一个 campaign 后，另生成包含首次通过率、重试恢复、纠错事件、失败明细和最终黄金成本的质量报告：

```bash
python tools/report_golden_dataset_quality.py \
  --output data/collection_reports/phase1-30-quality.md \
  --json-output data/collection_reports/phase1-30-quality.json
```

每批结束后运行：

```bash
python tools/audit_trace_data.py
./scripts/check.sh
```

第一阶段完成条件是 `golden=30`、审计通过、30 个任务 ID 无重复，并对所有 Partial/Fail 做过一次失败分布复盘。
