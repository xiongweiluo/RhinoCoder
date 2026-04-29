# rhinocoder/eval/test_l2_geometry.py
#
# L2 测试层：几何结果正确性验证（每次提交 CI 运行）。
# 运行环境：纯 Python，使用 rhino3dm（Apache 2.0，无需 Rhino 授权）。
#
# 覆盖问题：基础几何操作结果正确性（球体半径、线段端点、曲面参数等）。
# 测试用例格式：(instruction: str, validator: Callable)
#   validator 接受执行结果对象，使用 rhino3dm 几何类型验证预期属性。
#
# 典型测试场景：
#   球体：圆心坐标 + 半径精度（容差 1e-6）
#   线段：起止点 DistanceTo 验证
#   曲面：参数范围 / 法向量方向
