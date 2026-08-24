# Benchmark reports

真实报告由以下命令生成：

```bash
./scripts/benchmark.sh
```

默认对30条任务分别运行 Baseline 和 Closed-loop，各重复3次。完整 JSON 写入 `eval/results/`，Markdown 写入 `eval/reports/generated/`；两者默认不提交 Git，因为可能包含运行轨迹或项目数据。

发布报告前应人工确认：

- 使用的模型、Prompt 和工具 Schema 版本固定。
- Rhino 场景在每题前通过受保护端点重置。
- 基础设施错误计入总体失败率，而不是从分母中删除。
- 报告经过脱敏，只保留可公开汇总。

仓库不会提供伪造的基准数字。首次正式报告必须在运行中的 Rhino 8 和有效模型配置下生成。
