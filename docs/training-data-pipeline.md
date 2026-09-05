# A5 训练数据管线验收报告

结论：**通过**。

## 数据规模

- 黄金源任务：300 条。
- 不可拆分模板组：119 组。
- 导出训练样本：995 条。
- 清除运行噪声字段：2324 个。
- 修复历史脱敏占位符造成的参数 JSON：633 处。
- 去重丢弃：0 条；超长丢弃：0 条。
- 最长样本：8527 字符（硬上限 16,384）。

| 分区 | 源任务 | 指令→工具 | 完整轨迹 | 错误→纠正 | 场景→下一步 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 210 | 210 | 210 | 23 | 264 |
| validation | 45 | 45 | 45 | 1 | 52 |
| holdout | 45 | 45 | 45 | 4 | 51 |

## 防泄漏与血缘

- 分区在源任务层完成，某一任务的全部训练视图始终位于同一区域。
- 数值归一化签名与 campaign/标签模板族通过并查集合并后整体分配，不允许跨区。
- 标签、难度和错误恢复视图参与确定性分层打分；模板不可拆分约束优先于逐标签精确比例。
- 既有 `manifest.json` 是 split lock；未来重建或增量加入任务时，holdout 不会迁入 train。
- 每条样本记录源文件、行号、Trace 哈希、run/task/campaign ID 和 Prompt/工具 Schema 版本。
- manifest 固定源数据、campaign、全部导出文件的 SHA-256、字节数和行数。
- 源 Trace SHA-256：`ca90e7f7621a60e1c60c4eaa8a64cfd73fd0d276d76caaf36dbe6bf7bb36a14a`。
- Pipeline / split seed：`a5-training-views-v1` / `rhinocoder-a5-v1`。
- 历史 Trace 中未加引号的脱敏坐标/GUID 占位符仅被规范为合法 JSON 字符串；管线不会猜测或恢复已移除的原值。

## 审计结果

- 模板跨区：0。
- 数值模板跨区：0。
- 重复样本：0。
- 血缘失败：0。
- 敏感发现：0。

## 复现

```bash
python tools/build_training_dataset.py build
python tools/build_training_dataset.py audit
python tools/build_training_dataset.py report --output docs/training-data-pipeline.md
```

训练与验证脚本只能读取 `train/` 和 `validation/`；`holdout/` 标记为锁定保留集，不用于训练或调参。
