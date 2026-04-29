# rhinocoder/agent/sanitizer.py
#
# 数据脱敏管道 —— 云端请求发送前的最后一道安全屏障。
#
# 处理规则（见 design-document.md §5.4）：
#   - 具体坐标值 (x, y, z)          → <COORD_REDACTED>
#   - 项目专有图层名                  → layer_A, layer_B, ...
#   - 文件路径                        → <PATH_REDACTED>
#   - 企业自定义函数名                → custom_func_N
#
# 注意：凡触发脱敏规则的指令，规则引擎应已标记为 FORCE_LOCAL；
#       本模块是双重保险，不应成为常规执行路径。
# 注意：超长上下文（> 500K tokens）场景下脱敏性能开销需纳入端到端延迟预算。
