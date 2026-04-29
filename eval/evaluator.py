# rhinocoder/eval/evaluator.py
#
# RhinoCoderEvaluator —— Pass@1 批量评估核心类。
#
# 方法：
#   generate(instruction)              — 调用本地模型生成代码
#   check_syntax_and_imports(code)     — L1：语法检查 + API 合法性验证（mock 环境）
#   execute_with_rhino3dm(code)        — L2：在 rhino3dm 几何计算环境中执行并返回结果
#
# run_pass_at_1_benchmark(test_cases, evaluator) — 批量评估，统计 L1/L2 通过率。
#
# 目标：
#   L1 Pass@1（语法+API 合法性）≥ 85%（见 design-document.md §1.3）
#   L2 Pass@1（几何正确性）     作为 L1 的子集持续追踪
