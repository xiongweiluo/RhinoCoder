# rhinocoder/agent/cli.py
#
# 主 CLI 入口，使用 Typer 声明命令。
# 职责：解析命令行参数，选择平台事件循环（uvloop on macOS/Linux），
#       实例化 RhinoCoderAgent 并启动异步主循环。
#
# 用法：
#   rhinocoder-agent start [--config rhinocoder.yaml]
