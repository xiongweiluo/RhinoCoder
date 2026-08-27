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

# Script Editor 会缓存已导入模块；先关闭旧服务再重载，确保代码和 .env 生效。
listener_main.stop_listener()
for tool_module in (tools_geometry, tools_perception, tools_property, tools_transform):
    importlib.reload(tool_module)
listener_main = importlib.reload(listener_main)
listener_main.start_listener()
