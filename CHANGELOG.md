# Changelog

本项目遵循语义化版本。尚未通过真实 Rhino 基准的内容保留在 Unreleased，不以离线测试代替发布验收。

## [0.2.0-rc.1] - 2026-08-24

### Added

- 结构化 `AgentRunResult`、严格递增的统一事件流和取消令牌。
- 30 题 Baseline / Closed-loop 重复评测、失败分类和 JSON/Markdown 报告。
- React + TypeScript + Vite UI、WebSocket 状态恢复和脱敏 Replay。
- 任务停止、重试、Undo、按任务回滚和三类用户反馈。
- Listener 健康检查、标准错误码、有限重试和变更请求幂等键。
- Trace、脱敏、黄金样本准入和人工反馈关联。
- CI、密钥扫描、一键检查、启动、诊断和基准脚本。

### Changed

- `run_agent()` 以结构化结果为主，同时保留旧式两项解包兼容性。
- `reset_environment` 仅接受本地评测令牌，普通 UI 不暴露清场入口。
- 真实轨迹和生成的评测报告默认不纳入 Git。

### Security

- `.env.example` 只保留占位符。
- 增加仓库密钥扫描与运行数据脱敏。
- 仓库历史中曾出现过疑似有效凭证；发布前必须在提供方控制台完成外部轮换。

### Pending stable-release gates

- 在 Rhino 8 与有效模型环境执行 30 题双模式、各 3 次基准。
- Closed-loop Pass@1 达到 70%，三个核心场景连续 3 次成功。
- 完成凭证外部轮换和新环境安装演练。

## [0.1.0]

- 初始 MCP Server、Rhino HTTP Listener、Agent 和基础几何工具闭环。
