# rhinocoder/eval/test_l1_api_validity.py
#
# L1 测试层：API 合法性验证（每次提交 CI 运行）。
# 运行环境：纯 Python，无需 Rhino 授权（依赖 conftest.py 注入 mock 命名空间）。
#
# 覆盖问题：幻觉 API 调用、语法错误、危险代码注入（os.system 等）。
# 预期通过率目标：≥ 85%（Pass@1 核心指标）。
#
# 测试用例格式：(instruction: str, should_pass: bool)
# 使用 @pytest.mark.parametrize 参数化，便于批量扩展测试集。
