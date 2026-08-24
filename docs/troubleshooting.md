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

该端点只允许评测流程调用。在启动 Rhino 前设置 `RHINOCODER_EVAL_TOKEN`，并确保运行评测器的终端使用相同值。普通 UI 不应调用该端点。

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
