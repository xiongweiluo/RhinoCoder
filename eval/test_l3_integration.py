# rhinocoder/eval/test_l3_integration.py
#
# L3 测试层：全量集成测试（每周回归，需本地 Rhino 8 授权）。
# 运行环境：本地 Rhino.Compute 无头服务（localhost:6500）。
#
# 启动 Rhino.Compute：
#   ./compute.geometry.exe --port 6500 --childcount 2
#
# 覆盖问题：Grasshopper 组件执行、显示管线、Rhino 事件钩子。
#
# 所有测试用 @pytest.mark.integration 标记，日常 CI 通过 -m "not integration" 跳过。
# 每周回归：pytest eval/ --tb=long -v（完整三层）
