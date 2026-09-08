# Portfolio evidence index

RhinoCoder 对外只使用能从版本化文件复核的指标。本页是 README、简历表述、演示脚本与面试讲解的统一证据入口；完整真实 Trace、用户身份和项目文件不公开。

## 核心指标与来源

| 公开表述 | 固定口径 | 证据 |
|---|---|---|
| 黄金数据 500/500、46 个标签 | 四道准入门全部通过；A7 新增 200 条，8 类覆盖缺口达到计划量 | [A7 覆盖与边际价值报告](a7-500-marginal-value.md) |
| 三路固定基线 270/270 通过 | 30 题 × 3 次重复 × 3 种方案；这是饱和固定集，不代表开放世界或困难集效果 | [A6 无微调基线报告](a6-no-finetune-baseline.md) |
| 30 题 Baseline/Closed-loop 各 3 次均为 100% Pass@1 | 180 次真实 Rhino 端到端运行；Closed-loop 增加场景检查、延迟与 token 开销 | [30 题基准报告](benchmark-report.md) |
| A7 覆盖缺口 8/8 达标 | 布尔替代恢复与多轮修订各 40；其余 6 类各 20 | [A7 覆盖与边际价值报告](a7-500-marginal-value.md) |
| A4 敏感发现 0 | 12 条隐私红队；1,609 条 Trace、7,016 行 SQLite、3 份 Replay 与模拟日志/请求面 | [A4 隐私红队报告](privacy-red-team-report.md) |
| 23 个 MCP 工具 | 版本清单固定工具数，并由发布一致性检查与源码装饰器计数交叉验证 | [版本清单](version-manifest.json) |
| 训练工程已就绪但没有 GPU 结果 | B1–B4 只完成锁定配置、CPU 冒烟、恢复和集群模板；没有正式训练或 holdout 评测 | [训练就绪报告](training-readiness.md) |
| 当前版本为 0.3.0 release candidate | 本地版本、文档与资产已对齐；Tag 与 GitHub Release 仍需所有者明确授权 | [版本清单](version-manifest.json)、[发布清单](release-checklist.md) |

## 代表性可追溯链路

无需 Rhino 的 `self_correction.json` 合成 Replay 展示一条完整失败恢复链：

```text
run.started
  → privacy.assessed (low / allow)
  → route.selected (cloud-main / no fallback)
  → create_sphere
  → scene.checked
  → assertion.checked (mismatch)
  → correction.started
  → scale_object + set_object_color
  → scene.checked
  → assertion.checked (pass)
  → run.completed (metrics)
```

证据入口：[合成 Replay](../eval/replays/self_correction.json) · [自动 GIF](assets/replay-demo.gif) · [演示资产哈希](demo/demo-assets-manifest.json)。Replay 坐标、对象 ID、图层和模型名均为合成值，不是从真实用户项目复制的 Trace。

真实运行使用相同的 `run_id` 关联 `AgentEvent`、隐私与路由决定、工具调用、场景检查、断言、反馈、成本和 SQLite 血缘。完整真实明细默认受 Git 忽略；公开仓库只保留脱敏聚合、合成 Replay 与哈希清单。

## 不应对外声称

- 不声称本地模型已经能完成 Rhino 建模。`local-mock` 只是确定性的接口与安全替身。
- 不声称 LoRA 已训练或优于云模型。学校 GPU 尚未验收，A5 holdout 未用于训练或调参。
- 不把 30 题 100% 外推为开放世界成功率；该固定集已饱和，P2 困难集和外部用户验证尚未完成。
- 不声称生产级多用户、Windows 或企业部署已经验收。
- 不公开真实用户身份、原始项目文件、完整本地 Trace 或密钥。
