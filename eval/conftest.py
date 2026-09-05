import os

# Unit tests use explicit temporary audit databases and must not write fixtures
# into the developer's default local database.
os.environ.setdefault("RHINOCODER_AUDIT_ENABLED", "0")
os.environ.setdefault("RHINOCODER_ROUTER_ENABLED", "0")
os.environ.setdefault("RHINOCODER_MODEL_REQUEST_AUDIT_ENABLED", "0")

# rhinocoder/eval/conftest.py
#
# pytest 全局配置 —— 在测试收集前注入假 Rhino 命名空间（L1/L2 层）。
# 拦截所有 Rhino import，替换为 MagicMock，使测试可在无 Rhino 授权的 CI 环境运行。
#
# 被 mock 的模块（见 tech-stack.md §6.2）：
#   rhinoscriptsyntax, Rhino, Rhino.Geometry,
#   Rhino.DocObjects, Rhino.Commands, scriptcontext
#
# L3 集成测试（@pytest.mark.integration）不依赖此 mock，需本地 Rhino 8 授权环境。
