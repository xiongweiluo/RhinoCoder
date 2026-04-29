# rhinocoder/data_pipeline/run_pipeline.py
#
# 流水线完整执行入口（按序调用各步骤）。
#
# 执行顺序（见 tech-stack.md §4.4）：
#   ① scrape_all()           采集 McNeel 论坛原始代码块
#   ② filter_rhino_api()     关键词过滤（rhinoscriptsyntax / RhinoCommon）
#   ③ normalize_ast()        AST 解析 + 结构规范化（失败即丢弃）
#   ④ dedup_samples()        结构哈希去重
#   ⑤ validate_in_sandbox()  沙箱 Rhino 环境实际执行验证（Q3 引入）
#   ⑥ format_as_sft()        转换为 SFT 格式
#   ⑦ 写入 ./data/sft_dataset.jsonl
#
# 用法：
#   python -m data_pipeline.run_pipeline [--max-pages 50] [--output ./data/sft_dataset.jsonl]
