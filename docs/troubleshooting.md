# Troubleshooting

## 快速诊断

在项目根目录运行：

```bash
python tools/doctor.py
```

## 无法连接 Rhino Listener

1. 确认 Rhino 8 已启动。
2. 在 Rhino Script Editor 中运行 `plugin/start_rhinocoder_listener.py`。
3. 确认终端可以读取 `http://127.0.0.1:8080/health`。
4. 如果端口被占用，停止旧 Listener 后重新启动。

## reset_environment 被拒绝

该端点只允许评测流程调用。项目根目录 `.env` 中配置 `RHINOCODER_EVAL_TOKEN` 后，需要在 Rhino 中重新启动 Listener；启动过程会只读取该令牌，不会记录令牌值。运行评测器的终端必须读取同一份 `.env`。普通 UI 不应调用该端点。

运行 `python tools/doctor.py` 时应看到 `Rhino eval reset enabled`。如果仍显示 disabled，确认 Rhino 执行的是当前项目中的 `plugin/start_rhinocoder_listener.py`，然后重新启动 Listener。

推荐在 Rhino 命令行运行：

```text
_-ScriptEditor _Run "/absolute/path/to/RhinoCoder/plugin/start_rhinocoder_listener.py"
```

不要使用旧的 `RunPythonScript` 命令；部分 Rhino 安装会让它进入缺少现代标准库的旧 Python 引擎。

## UI 显示尚未构建

```bash
npm ci --prefix agent/ui
npm run build --prefix agent/ui
```

随后重新运行 `./scripts/start.sh`。

## Agent 报模型配置错误

复制 `.env.example` 为 `.env`，填写有效的 `DEEPSEEK_API_KEY`。不要将 `.env` 添加到 Git。

## 任务超时

- 检查 Rhino 是否打开了模态对话框。
- 检查是否有长时间几何操作阻塞主线程。
- 查询操作可安全重试；变更操作应先读取场景，确认没有产生结果后再重试。

## 评测退出码为 3

这表示 Closed-loop Pass@1 低于默认 70% 发布门槛。JSON 与 Markdown 报告仍会生成，可从失败分类和断言明细定位问题。

## 评测退出码为 4

这表示余额耗尽、鉴权失败、配额不足或模型不可用等全局致命基础设施错误触发了熔断。报告会保留已经尝试的任务，并将剩余计划项标记为未运行；此时 Baseline 与 Closed-loop 不可比较。恢复模型服务后应重新运行完整基准。

## 成本显示为区间

DeepSeek 会在响应中提供缓存命中和未命中 token。新运行会保存这两个字段并精确计费；旧报告或不提供缓存拆分的兼容 API 只能根据总输入 token 计算严格上下界。可运行 `python tools/recalculate_benchmark_cost.py <result.json>` 重算历史报告，不会连接 Rhino 或模型。
