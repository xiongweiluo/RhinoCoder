# 数据与脱敏验收报告

验收日期：2026-08-27  
范围：黄金 Trace 准入、Partial/Fail 数据分流、正式基准报告与三份 Replay 脱敏

## 验收结论

- 黄金 Trace 只有在运行完成、程序化断言完全通过、非 Partial、至少一次场景检查、成功调用 `get_scene_summary`、人工确认正确、反馈为 `accepted` 且脱敏审计通过时才能写入。
- 黄金写入边界会再次校验上述准入证据；不能通过伪造 `accepted=True` 绕过落盘检查。
- Partial、失败、普通候选分别写入 `partial_traces.jsonl`、`error_traces.jsonl`、`candidates.jsonl`，均不进入黄金 SFT 文件。
- 正式基准报告与三份 Replay 已完成逐文件内容复核；未发现 API Key、本机路径或真实对象 GUID。
- 三份 Replay 均显式声明为合成数据，坐标和对象 ID 为合成值，图层只使用 `Default` / `Sample` 通用名称。
- 四个公开制品已写入 SHA-256 复核清单；文件被修改后 CI 会要求重新审计。

本轮数据与脱敏验收通过。

## 黄金 Trace 准入

### 强制条件

| 条件 | 写入前验证 | 写入边界复核 | 落盘后审计 |
|---|---:|---:|---:|
| `run.status == completed` | 是 | 通过 admission 证明 | 是 |
| 程序化断言完全通过 | 是 | 是 | 是 |
| 非 Partial Pass | 是 | 是 | 是 |
| 至少一次 Scene Check | 是 | 是 | 是 |
| 成功调用 `get_scene_summary` | 是 | 是 | 是 |
| 人工确认正确 | 是 | 是 | 是 |
| 反馈标签为 `accepted` | 是 | 是 | 是 |
| 密钥、路径、对象 GUID、坐标、项目图层和群组已脱敏 | 是 | 是 | 是 |
| 可通过 `run_id` 追溯 | 是 | 是 | 是 |

黄金记录会保存应用/Prompt/工具/Trace 版本、程序化评测、用户反馈和 admission 审计元数据。

### 旧数据处理

本地 `golden_dataset.jsonl` 中有 22 条旧格式记录。其 22 条都包含 `get_scene_summary`，但均缺少 `run_id`、程序化评测、人工反馈和 admission 元数据，因此不能证明满足当前黄金准入规则。

处理方式：

- 不删除、不覆盖旧文件。
- 将其标记为 `legacy_excluded`，禁止进入新 SFT 正样本。
- 新采集只写入被 Git 忽略的 `data/golden_traces_v2.jsonl`。
- `python tools/audit_trace_data.py` 会显示旧数据排除数量，并逐行审计 v2 黄金数据。

验收时本地状态为：v2 黄金 0 条、Partial 0 条、错误分析 0 条、普通候选 0 条、排除旧数据 22 条；审计结果通过。v2 数量为 0 不会降低门槛，后续只有真实完成人工确认的运行才会进入。

## Partial 与失败数据分流

固定分流规则：

| 结果 | disposition | 文件 | 可进入黄金 SFT |
|---|---|---|---:|
| 全部准入条件通过 | `golden` | `golden_traces_v2.jsonl` | 是 |
| Partial Pass | `partial` | `partial_traces.jsonl` | 否 |
| 任务失败、取消或断言完全失败 | `error_analysis` | `error_traces.jsonl` | 否 |
| 运行通过但人工拒绝等其他情况 | `candidate` | `candidates.jsonl` | 否 |

自动测试验证 Partial 与 Fail 物理写入不同文件，并验证已通过黄金准入的记录不能调用拒绝数据写入入口。

## 正式报告与 Replay 脱敏

复核范围由 [release-data-manifest.json](release-data-manifest.json) 精确锁定：

- `docs/benchmark-report.md`：仅保留汇总指标，不包含真实 Trace、完整 Prompt、场景快照或真实 GUID。
- `eval/replays/basic_stack.json`：手工合成 Replay。
- `eval/replays/self_correction.json`：手工合成 Replay。
- `eval/replays/table_group.json`：手工合成 Replay，图层和群组已改为通用样例名称。

Replay 必须同时满足：

- `sample: true`、`provenance: synthetic`。
- `contains_real_trace_data: false`。
- 坐标与对象 ID 声明为 synthetic。
- 图层声明为 generic 且值只能是 `Default` 或 `Sample`。
- `run_id` 使用 `replay-*` 合成标识。
- 事件序号从 1 严格递增，并包含 `scene.checked` 与 `run.completed`。
- 文件 SHA-256 与复核清单一致。

## 自动验证

```bash
python tools/audit_trace_data.py
python tools/audit_release_data.py
./scripts/check.sh
```

前两项已经加入本地检查与 GitHub CI。任何黄金准入回退、数据分流混写、公开制品敏感字段或复核后文件漂移都会使门禁失败。
