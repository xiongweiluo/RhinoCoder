# rhinocoder/agent/ui_server.py
#
# 轻量 UI 后端 —— aiohttp 静态文件服务 + WebSocket 通道。
#
# Agent 启动时在 127.0.0.1:7860 同步启动：
#   - 静态服务：将 rhinocoder/ui/ 目录暴露为 HTTP，供 Rhino 内嵌 WebView 加载
#   - WebSocket 端点 /ws：Agent ↔ UI 双向通信
#       上行：{"type": "instruction", "content": "..."}
#       下行：{"type": "stream_token"|"route_decision"|"execution_result", ...}
#
# 仅监听 127.0.0.1，拒绝外部网络连接（安全要求）。
