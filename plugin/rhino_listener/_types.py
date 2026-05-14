"""
rhino_listener/_types.py  —  运行在 Rhino 8 内部（Python 3.9，纯标准库）

Rhino 侧共享数据结构，被 listener_main.py 和所有 tools_*.py 共同依赖。

包含：
  _OBJECT_TYPE_MAP  — rs.ObjectType() 整数返回值 → 人类可读字符串映射
  _PendingWork      — 跨线程工作单元（HTTP 请求线程 ↔ Rhino 主线程）
  _work_queue       — 全局工作队列（请求线程 put，Idle 回调 get）

设计约束：
  - 此文件只能使用 Python 3.9 标准库，严禁导入 rhinoscriptsyntax / Rhino / mcp / httpx。
  - 此文件不含任何业务逻辑，只定义数据结构和共享状态。
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Rhino 对象类型语义化映射（rs.ObjectType() 返回值 → 人类可读字符串）
# 来源：RhinoCommon ObjectType 枚举，保持与原 rhino_http_listener.py 完全一致。
# ---------------------------------------------------------------------------
_OBJECT_TYPE_MAP: Dict[int, str] = {
    1:          "Point",
    2:          "PointCloud",
    4:          "Curve",
    8:          "Surface",
    16:         "Polysurface",
    32:         "Mesh",
    256:        "Light",
    512:        "Annotation",
    4096:       "InstanceReference",
    8192:       "TextDot",
    32768:      "Grip",
    65536:      "Detail",
    131072:     "Hatch",
    262144:     "MorphControl",
    1073741824: "Extrusion",
}


# ---------------------------------------------------------------------------
# 跨线程工作单元
# ---------------------------------------------------------------------------
@dataclass
class _PendingWork:
    """
    一次几何体操作请求在主线程和请求处理线程之间共享的状态。

    生命周期：
      1. HTTP 请求线程创建，填入 operation 和 params，put 到 _work_queue。
      2. Rhino 主线程（Idle 回调）get 出来，执行后填入 result_*/error，调用 done.set()。
      3. HTTP 请求线程在 done.wait(timeout) 解除阻塞后读取结果，生成 HTTP 响应。

    字段说明：
      result_guid   — 单体操作成功时的 GUID 字符串（如 create_sphere）
      result_guids  — 多体操作成功时的 GUID 列表（如 boolean_difference）
      result_data   — 数据型操作成功时的完整字典（如 get_bounding_box）
      error         — 执行失败时的错误描述字符串
      done          — 主线程完成后 set()，请求线程在此 wait()
      cancelled     — 请求线程超时后置 True，主线程据此跳过已超时任务
    """
    operation:    str
    params:       dict
    result_guid:  Optional[str]  = None
    result_guids: Optional[List] = None
    result_data:  Optional[dict] = None
    error:        Optional[str]  = None
    done:         threading.Event = field(default_factory=threading.Event)
    cancelled:    bool = False


# ---------------------------------------------------------------------------
# 全局工作队列
# ---------------------------------------------------------------------------
_work_queue: queue.Queue = queue.Queue()
