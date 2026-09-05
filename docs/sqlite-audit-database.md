# SQLite 审计数据库与 A2 验收报告

## 结论

A2 已于 2026-09-05 完成并通过验收。300 条黄金 JSONL 记录已完整、幂等地导入本地 SQLite；数据库与源数据均包含 300 个唯一任务和 300 个黄金运行。连续执行两次导入后各表计数不变，SQLite 完整性、外键、敏感字段和全部黄金运行血缘审计均无异常。

数据库是本地审计索引，不替代原始 JSONL。原始 Trace 仍是可恢复的数据源，SQLite 用于跨表查询、血缘追踪、汇总、路由决策和后续训练数据治理。

## Schema 与迁移

当前 Schema 版本为 2。迁移按版本写入 `schema_migrations`，在单一事务中执行；已应用迁移不会重复运行。连接启用外键、WAL、busy timeout，写入使用事务和保存点。

| 表 | 用途 |
| --- | --- |
| `tasks` | campaign、任务 ID、指令、难度、标签和任务元数据 |
| `models` | provider、模型名、版本和本地/云端后端信息 |
| `runs` | 运行状态、版本、消息、事件、错误、黄金标记和内容哈希 |
| `route_decisions` | 后端选择、理由、候选项、预算、延迟和降级结果 |
| `tool_calls` | 工具调用次序、参数、结果、耗时和错误 |
| `scene_checks` | 场景摘要、自检结果和对象计数 |
| `assertions` | 程序化断言、期望值、实际值和通过状态 |
| `feedback` | 人工/AI/程序反馈、决定、理由和内容哈希 |
| `admissions` | 黄金准入结果及各项门禁 |
| `cost_usage` | 输入、缓存和输出 token、费用与币种 |
| `artifacts` | Trace、截图、报告和 manifest 等证据的路径、哈希与元数据 |

辅助表 `schema_migrations` 记录版本，`import_batches` 记录导入源、源文件哈希和导入统计。第二版迁移为常用 run、task、model、tag、失败类型和时间查询增加索引。

## 写入与一致性

- `trace_store` 是 Trace、反馈和黄金批次的统一镜像入口；CLI 与 UI 在运行结束后也会记录实时运行。
- JSONL 保持既有写入语义，SQLite 镜像失败会记录警告，不会破坏用户刚完成的 Rhino 任务或原始 Trace。
- 主实体采用稳定主键和 upsert。工具调用、断言、反馈及证据使用确定性标识，重复导入不会生成副本。
- 每条黄金运行关联任务、模型、工具调用、场景检查、断言、反馈、准入、成本和证据；审计命令会遍历全部黄金运行验证最低血缘要求。
- 运行时数据库可用 `RHINOCODER_AUDIT_DB` 改址，以 `RHINOCODER_AUDIT_ENABLED=0` 明确关闭。

## 命令行操作

```bash
python tools/audit_db.py init
python tools/audit_db.py import-golden
python tools/audit_db.py audit
python tools/audit_db.py summary --output data/audit/summary.json
python tools/audit_db.py lineage <run_id> --output data/audit/lineage.json
```

所有命令都支持全局 `--database` 参数。`import-golden` 默认读取 `data/golden_traces_v2.jsonl`；`summary` 可以按模型、标签与失败类型聚合，`lineage` 返回某一运行的完整关联记录。JSON 输出可以打印到终端或写入指定文件。

## 隐私与文件安全

- 入库前统一调用结构化脱敏器，清理密钥、授权头、敏感字段和用户路径。
- 自动审计扫描所有文本及 JSON 列，同时执行 `PRAGMA integrity_check` 和 `foreign_key_check`。
- 数据库、WAL、SHM 和导出 JSON 默认设置为仅当前用户可读写；新建审计目录默认仅当前用户可访问。
- 证据路径必须位于项目目录内，符号链接会被拒绝；数据库及真实导出继续由 Git 忽略。

## 300 条真实黄金数据验收

源数据：`data/golden_traces_v2.jsonl`。

| 指标 | 结果 |
| --- | ---: |
| 源 JSONL 记录 | 300 |
| 唯一任务 / 黄金运行 | 300 / 300 |
| 模型 | 1 |
| 工具调用 | 2,742 |
| 场景检查 | 367 |
| 断言 | 840 |
| 反馈 | 1,196 |
| 准入记录 | 300 |
| 成本记录 | 300 |
| 证据记录 | 669 |
| 导入批次 | 1 |

两次连续导入得到完全相同的表计数。300 条运行全部为 `deepseek-v4-pro` 完成态黄金运行，覆盖 40 个标签；总 token 为 26,989,864，记录费用为 1.013485。证据包括 300 份 Trace、299 张唯一截图、66 份报告、3 份 manifest 和 1 份黄金 JSONL。`bench-01` 没有独立截图，但其完整 Trace 仍作为可验证证据，因此全部 300 条血缘均满足准入要求。

本地验收输出保存在 Git 忽略目录 `data/audit/`：`audit-report.json`、`summary.json`、两次导入摘要和样例血缘导出。最终审计结果为：完整性 `ok`，外键异常 0，敏感字段发现 0，血缘异常 0。
