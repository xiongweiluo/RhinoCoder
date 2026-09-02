# 第二阶段：100 条黄金轨迹任务设计

## 范围

`phase2-100` 以已冻结并打标的 `golden-set-30` 为前 30 条，新增 70 条任务；新增清单位于 `eval/tasks/phase2_expansion.jsonl`。它不替换第一阶段清单，而通过 `source_campaign_manifests` 只读复用，避免已验证任务发生漂移。

## 七个审核批次

| 批次 | 新任务 | 重点 |
|---|---:|---|
| 04 | p2-001–p2-010 | 多重变换、缩放、分布与坐标基准 |
| 05 | p2-011–p2-020 | 布尔差集、圆曲线拉伸与实体编辑 |
| 06 | p2-021–p2-030 | 感知、修订、删除与空间选择 |
| 07 | p2-031–p2-040 | 群组、图层、对齐与阵列组织 |
| 08 | p2-041–p2-050 | 叠放、相切、距离与装配关系 |
| 09 | p2-051–p2-060 | Undo、错误恢复与最终状态验证 |
| 10 | p2-061–p2-070 | 多工具综合高难场景 |

## 采集规则

- 使用 `--manifest eval/collection/phase2_100.json --batch-size 10`。
- 每条任务必须满足完整断言、至少一次 `get_scene_summary`、脱敏和 AI 视口审核。
- 每 10 条候选生成汇总证据后再进行一次人工 `APPROVE`；Partial 与 Fail 只进入错误分析，不进入黄金集。
- 所有新增任务都使用特征选择器与程序化空间断言，不依赖随机 GUID。

## 校验

```bash
python tools/check_collection_campaign.py --manifest eval/collection/phase2_100.json
python agent/data_collector.py --manifest eval/collection/phase2_100.json --dry-run
```
