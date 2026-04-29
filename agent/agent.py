# rhinocoder/agent/agent.py
#
# RhinoCoderAgent — 核心异步主控逻辑。
# 职责：
#   - 通过 MCP Python SDK 与 rhino_mcp_server 建立 stdio 连接
#   - 托管路由中枢事件循环（Router.run）
#   - 协调本地推理调用、云端 API 调用与 MCP 工具执行
#   - 管理自愈 Debug 循环（最多重试 2 次）
#
# 进程拓扑角色：rhinocoder-agent（主控进程）
