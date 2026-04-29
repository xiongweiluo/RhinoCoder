# rhinocoder/data_pipeline/sft_formatter.py
#
# SFT 数据格式化器 —— 流水线最后一步（步骤 ⑥）。
# 将去重后的代码样本转换为标准 SFT 训练格式并写入 ./data/sft_dataset.jsonl。
#
# 输出格式（每行一条 JSON）：
#   {"instruction": "<自然语言指令>", "output": "<对应 Python 代码>"}
#
# 数据构成目标（见 design-document.md §4.4）：
#   Rhino 官方文档示例   ~5,000 条
#   McNeel 论坛代码片段  ~15,000 条
#   内部项目脚本（脱敏）  ~3,000 条
#   GPT-4o 合成增强      ~20,000 条
#   总计                 ~43,000 条
