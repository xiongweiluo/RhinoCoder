# P1 招聘者导向产品演示链路

验收日期：2026-09-08

状态：**通过**

公开入口：[https://rhinocoder-demo.xiongweiluo1.chatgpt.site](https://rhinocoder-demo.xiongweiluo1.chatgpt.site)

## 目标与结果

P1 将原有工程型 UI 收敛为招聘者可在数分钟内扫描的证据链：

```text
指令 → 隐私判断 → 路由决策 → Rhino 工具执行
     → 操作前后场景 → 程序断言 → 指标 → Replay
```

三个固定场景由 [`docs/demo/p1-scenarios.json`](demo/p1-scenarios.json) 锁定：

| 场景 | 核心证据 | Replay |
|---|---|---|
| 正常闭环 | 隐私、路由、工具、Scene Summary、通过断言 | `basic_stack.json` |
| 错误恢复 | 首次断言失败、纠错、不重复创建、复检通过 | `self_correction.json` |
| 隐私与路由 | 合成邮箱最小化、规则路由、同 run_id 审计 | `table_group.json` |

## 产品链路

- Tool Trace 已升级为“关键 / 全部 / 决策 / 执行 / 验证 / 恢复”可筛选时间线；Public Replay 默认只投影任务、隐私、路由、几何执行、场景读回、验证和恢复等语义事件，底层工具事件仍完整保留在“全部”。
- 公开托管界面融合精密证据台与 Rhino 空间画布：三场景结果标签、单行任务和六项 Run Summary 位于顶部；左侧 Trace 回答“怎么做”，中间 Scene Summary 投影回答“做出了什么”，右侧 Expected/Actual 程序断言回答“为什么通过”。场景默认 Shaded 并读取 Replay 对象真实 RGB，支持切换 Wireframe；实时输入、恢复操作、路由说明卡和 Recent Runs 只保留在本地实时模式。
- 正常闭环 Replay 的最终 Scene Summary 由既有 verifier 复核，并投影为对象数量、基座尺寸、球体半径/包围盒、球体颜色和球体位置 5 项证据；默认展开前三项，其余折叠。错误恢复场景保留首次 mismatch 和复检通过，不用最终 PASS 覆盖恢复过程。
- 固定真实 Rhino 场景在执行前后只读采集 Scene Summary；最终快照交给既有 `eval.scene_assert.verify`。Agent 自报完成但断言不通过时，演示终态显示失败。
- 仪表盘展示状态、完整 `run_id`、隐私动作、模型后端、端到端延迟、成本、工具错误与恢复次数。
- 恢复区集中提供重试、Undo、精准回滚和反馈，并针对加载、空、离线、运行、完成、失败与取消给出明确状态。
- 本地实时模式的 Recent Runs 支持指令/run_id 搜索和 completed/failed/cancelled/Replay 筛选；按 `/` 可聚焦搜索，`Command/Ctrl + Enter` 执行，`Esc` 停止。
- 桌面保持 Trace → Scene → Verification 三栏；390px 窄屏按 Task → Run Summary → Verification → Scene → Trace → Object Inspector → Data Boundary 排序，并保留键盘焦点与 `prefers-reduced-motion` 策略。

## 公开只读与隐私边界

三个入口使用 `?demo=<scenario>&mode=replay`。公开托管构建将冻结的三份场景与 Replay 编译进静态浏览器资源，不调用 API、不建立 WebSocket，也不依赖模型或 Rhino。本地 UI Server 模式只调用：

```text
GET /api/demo-scenarios
GET /api/replays/{name}
GET /evidence/{name}
```

只读模式不建立 WebSocket，不发送 instruction、retry、Undo、rollback 或 feedback。服务端只接受声明为 `synthetic`、`privacy.reviewed=true` 且不含真实 Trace 的 Replay。

实时 UI 的浏览器出站边界会最小化身份、路径、邮箱、密钥、图层和群组；对象 ID 转为稳定假名。`run_id`、`route_id` 与 `decision_id` 保留用于 Trace/SQLite 血缘。完整模型消息、原始 Trace、SQLite、真实用户身份和真实对象 GUID 不下发到浏览器。

## 自动验收

```bash
python tools/audit_p1_demo.py
npm run build --prefix agent/ui
python tools/check_ui_performance.py
npm run test:e2e --prefix agent/ui
npm run test:e2e:public --prefix agent/ui
python -m pytest -q eval/test_ui_server.py eval/test_p1_demo.py eval/test_ui_performance.py
```

Playwright 使用真实 Chrome，分别覆盖本地 UI Server 与纯静态托管构建：根链接自动播放、三场景完整链路、关键 Trace 默认态、5 项 Expected/Actual、真实 RGB Shaded、Wireframe 切换、零 API 写请求、零 WebSocket、隐私占位符、场景标签键盘焦点、390px 阅读顺序与无横向溢出；实时模式另验收取消终态和运行控制。

当前生产构建为单 JS 与单 CSS；gzip 预算分别为 90 KiB、20 KiB，总预算 120 KiB。

## 验收记录

| 门禁 | 结果 |
|---|---:|
| Python 全量测试 | 193 passed |
| clean-room 公开副本 | 191 passed、2 skipped；3 场景；首个只读 Replay 14 事件 |
| P1 独立场景审计 | 3 场景、3 Replay、4 浏览器测试，0 findings |
| Chrome 端到端 | 本地 UI 5/5；纯静态公开版 5/5 |
| 窄屏 | 390×844，无横向溢出 |
| 公开版 UI gzip | JS 71,002 B；CSS 8,072 B；总计 79,461 B / 122,880 B |
| 密钥扫描 | passed |
| 隐私审计 | 2,821 Trace、18,156 SQLite 行、3 Replay、3,545 模型请求；0 findings |
| 发布数据 / 演示资产 / 版本一致性 | passed / passed / passed（`0.3.0`，23 MCP 工具） |
| 仓库统一检查 | `scripts/check.sh` passed |

取消任务会生成 `run.cancelled` 终态并进入最近运行；固定场景重试会保留原场景 ID、输入和最终断言语义。实时 Rhino 和 Replay 因此使用同一套场景定义、Scene Summary 字段与断言展示口径，但 Replay 仍明确标记为合成证据，不冒充新的真实 Rhino 基准。

本阶段未读取 A5 holdout 或 P2 困难集答案，未执行 C1–C4，也没有新增黄金数据。在线站点只发布既有脱敏合成 Replay，不包含完整本地 Trace、SQLite、真实用户身份、真实项目文件或真实 Rhino 对象 GUID。
