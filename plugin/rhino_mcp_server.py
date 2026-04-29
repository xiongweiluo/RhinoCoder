# rhinocoder/plugin/rhino_mcp_server.py
#
# Rhino MCP Server —— 嵌入 Rhino Script Editor 运行的 MCP Server（方案 A）。
# 基于社区项目 rhino-mcp 扩展，Q3 原型期评估稳定性，必要时切换方案 B（自研 .NET Plugin）。
#
# 暴露 MCP 工具集（见 design-document.md §6.2）：
#   get_rhino_context()          — 获取图层列表、选中对象属性、当前坐标系
#   execute_python_script(code)  — 在 Rhino Python 环境执行代码，返回结果或错误
#   get_object_properties(ids)   — 获取几何属性（类型/边界盒/顶点数，不含原始坐标）
#   undo_last_operation()        — 撤销上一次代码执行
#
# 同时在初始化时注册 RhinoCoderPanel（Eto.Forms.WebView），
# 指向 Agent UI 服务地址 http://127.0.0.1:7860/index.html。
#
# 安全约束：MCP Server 仅通过 stdio 与 Agent 通信，不暴露任何网络端口。
