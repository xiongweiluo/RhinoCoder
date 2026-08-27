"""Rhino Listener 路由层共享参数校验。"""

from __future__ import annotations

import uuid


def is_guid(value: object) -> bool:
    """仅接受标准 UUID/GUID 字符串，防止无效 ID 进入 Rhino 主线程。"""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        uuid.UUID(value)
    except (AttributeError, ValueError):
        return False
    return True


def are_guids(values: object) -> bool:
    return isinstance(values, list) and bool(values) and all(is_guid(value) for value in values)
