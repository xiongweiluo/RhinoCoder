# A7 覆盖缺口扩展与 500 条边际价值报告

结论：**通过**。当前黄金准入 **500/500**，A7 新增黄金 **200/200**。

## 设计与执行证据

- 继承冻结黄金：300 条；覆盖缺口新增任务：200 条。
- 审核批次：20 批，每批 10 条；异常批次：0。
- 已尝试新增任务：200；AI 初审候选：0。
- 规则路由预演：{'cloud-main': 200}；与预期不符：0。
- 当前黄金集覆盖标签：46 个。
- 新增标签：`clean_trace`, `complex_edit`, `fallback`, `incomplete_scene`, `multi_round`, `route_boundary`。

| 覆盖缺口 | 计划 | 已进入黄金 |
|---|---:|---:|
| boolean_alternative_recovery | 40 | 40 |
| complex_edit_membership | 20 | 20 |
| complex_edit_selection | 20 | 20 |
| incomplete_perception | 20 | 20 |
| multi_round_revision | 40 | 40 |
| route_misclassification | 20 | 20 |
| tool_error_recovery | 20 | 20 |
| undo_recovery_sequence | 20 | 20 |

## 准入与证据审计

- 黄金准入异常：0。
- 截图证据缺失：0。
- 原子批次结构异常：0。

## 500 条后的边际价值决策

决策：`pause_at_500_pending_unified_evaluation`。

A7 达标后在 500 条停止扩张。只有 C3 统一评测证明存在可复现、量化且不能优先通过路由、Prompt 或工具修复的缺口，才重新考虑 1,000–5,000 条；不得因管线已存在而默认扩张。
