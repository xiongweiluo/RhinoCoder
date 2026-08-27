# 原型发布检查清单

当前代码已具备稳定原型所需的离线基础能力，但只有以下项目全部通过后才能标记正式版本。

## 1. 安全与版本

- [x] 在 API 提供方控制台轮换仓库历史中出现过的凭证。
- [x] `python tools/check_secrets.py` 通过。
- [x] `.env`、真实 Trace、评测明细和项目数据均未进入提交。
- [ ] 应用、Prompt、工具 Schema 与 Trace 版本固定。

## 2. 自动检查

- [x] `./scripts/check.sh` 全部通过。
- [x] CI 的编译、单元测试、任务格式、前端构建和密钥扫描通过。
- [x] 工作区不存在与发布无关的未提交改动。

## 3. 真实环境验收

- [x] Rhino 8 已打开，Listener 健康检查通过。
- [x] Agent、MCP Server 与 UI 可由 `./scripts/start.sh` 启动。
- [x] `./scripts/benchmark.sh` 完成 30 题 Baseline / Closed-loop，各重复 3 次。
- [x] 30 题全部进入报告，基础设施错误保留在失败分母。
- [x] Closed-loop Pass@1 不低于 70%。
- [x] 报告包含任务级结果、均值、标准差、稳定性、延迟、token、成本和失败分类。

## 4. 交互与恢复

- [x] 三个核心任务在真实 Rhino 环境连续运行 3 次成功，详见 [UI 真实环境验收报告](ui-acceptance-report.md)。
- [x] WebSocket 断线重连后可恢复当前任务快照，详见 [断线与故障恢复验收报告](recovery-acceptance-report.md)。
- [ ] 停止后不再产生新工具调用。
- [ ] 重试、Undo、任务级精准回滚和反馈均已人工演练。
- [x] Rhino Listener 重启或重连后无需重启 Agent/UI 即可开始新任务。
- [x] 无效 GUID、空参数、LLM 超时和 MCP 退出均展示可理解的恢复入口。
- [x] 网络层重试复用幂等键，Listener 超时不会重复入队或产生重复对象。

## 5. 数据与交付

- [ ] 黄金 Trace 同时满足断言通过、至少一次场景自检、人工确认与脱敏审计。
- [ ] Partial Pass 和失败 Trace 只进入候选/错误分析集。
- [ ] 正式报告与三份 Replay 已人工复核脱敏。
- [ ] 新 macOS 环境可按 README 完成安装和首次任务。
- [ ] 已知限制与故障排查内容和当前版本一致。

完成后将 `agent/version.py` 中的应用版本升级为发布版本，并把 `CHANGELOG.md` 的 Unreleased 内容移动到对应版本条目。
