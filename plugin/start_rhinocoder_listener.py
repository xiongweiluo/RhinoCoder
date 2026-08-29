# -*- coding: utf-8 -*-
"""在 Rhino 8 Script Editor 中运行此文件以启动或热重载 Listener。"""

import importlib
import os
import sys

plugin_path = os.path.dirname(os.path.abspath(__file__))
if plugin_path not in sys.path:
    sys.path.insert(0, plugin_path)

from rhino_listener import listener_main
from rhino_listener import tools_geometry, tools_perception, tools_property, tools_transform

# Script Editor 会缓存已导入模块。正常运行的 Listener 先走优雅关闭；如果
# serve_forever 线程已经异常退出，则不要调用 HTTPServer.shutdown()（它要求
# 服务循环仍在另一个线程中，否则会永久阻塞 Rhino 主线程），直接释放残留
# socket 与 Idle 回调后再重载。
server_thread = getattr(listener_main, "_server_thread", None)
if server_thread is not None and server_thread.is_alive():
    listener_main.stop_listener()
else:
    stale_server = getattr(listener_main, "_server_instance", None)
    if stale_server is not None:
        stale_server.server_close()
    if getattr(listener_main, "_idle_registered", False):
        import Rhino

        Rhino.RhinoApp.Idle -= listener_main._idle_handler
    listener_main._server_instance = None
    listener_main._server_thread = None
    listener_main._idle_registered = False

for tool_module in (tools_geometry, tools_perception, tools_property, tools_transform):
    importlib.reload(tool_module)
listener_main = importlib.reload(listener_main)
listener_main.start_listener()
