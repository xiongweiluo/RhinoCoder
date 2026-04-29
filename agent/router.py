# rhinocoder/agent/router.py
#
# 混合路由中枢 —— 两阶段判断架构（规则优先、模型兜底）。
#
# 第一阶段：规则引擎（< 5ms）
#   基于正则关键词与上下文信号快速分类，输出 ROUTE_LOCAL / ROUTE_CLOUD / UNCERTAIN。
#   FORCE_LOCAL_PATTERNS：含坐标值、项目图层名、数值几何微调、增量调整指令。
#   PREFER_CLOUD_PATTERNS：方案规划、how-to 探索、参数化/算法类指令。
#
# 第二阶段：意图分类器（< 80ms，仅 UNCERTAIN 时触发）
#   基于 Qwen2.5-0.5B 蒸馏的 4 分类头（CPU 推理），标签：
#   geo_op | api_call | concept_plan | hybrid
#
# 每条指令均写入路由决策日志（RoutingDB），支持合规审计。
