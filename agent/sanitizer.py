"""本地轨迹与反馈数据脱敏。"""

from __future__ import annotations

import re
from typing import Any

SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
GUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
POSIX_PATH_RE = re.compile(r"(?<![\w.])/(?:Users|home|private|var|tmp)/[^\s\"']+")
WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]+")
COORD_TUPLE_RE = re.compile(
    r"(?<!\w)[\[(]\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*[\])]"
)
KEYED_COORD_RE = re.compile(
    r"(?i)(['\"]?(?:x|y|z|center_[xyz]|origin_[xyz]|start_[xyz]|end_[xyz]|base_[xyz]|point_[xyz])['\"]?\s*[:=]\s*)-?\d+(?:\.\d+)?"
)
LAYER_RE = re.compile(
    r"(?i)(layer|图层)\s*[:=]?\s*['\"]([^'\"]{2,80})['\"]"
)
SECRET_KEYS = {"api_key", "apikey", "token", "secret", "password", "authorization"}
COORD_KEYS = {
    "center",
    "origin",
    "point",
    "start",
    "end",
    "base_point",
    "translation",
    "vector",
    "coordinates",
}
LAYER_KEYS = {"layer", "layer_name", "project_layer"}
GROUP_KEYS = {"group", "groups", "group_name", "group_names"}


def _is_secret_key(key: str) -> bool:
    key = key.lower()
    return key in SECRET_KEYS or key.endswith(
        ("_api_key", "_secret", "_password", "_access_token", "_refresh_token")
    )


def sanitize_text(value: str) -> str:
    value = SECRET_RE.sub("<SECRET_REDACTED>", value)
    value = GUID_RE.sub("<GUID_REDACTED>", value)
    value = POSIX_PATH_RE.sub("<PATH_REDACTED>", value)
    value = WINDOWS_PATH_RE.sub("<PATH_REDACTED>", value)
    value = COORD_TUPLE_RE.sub("<COORD_REDACTED>", value)
    value = KEYED_COORD_RE.sub(r"\1<COORD_REDACTED>", value)
    value = LAYER_RE.sub(lambda match: f"{match.group(1)} '<LAYER_REDACTED>'", value)
    return value


def sanitize_structure(value: Any, *, parent_key: str = "") -> Any:
    key_lc = parent_key.lower()
    # run_id 是数据血缘主键，不是 Rhino 对象 GUID，必须保留以支持追溯。
    if key_lc == "run_id" and isinstance(value, str):
        return value
    if _is_secret_key(key_lc):
        return "<SECRET_REDACTED>"
    if key_lc in LAYER_KEYS and isinstance(value, str):
        return value if value == "Default" else "<LAYER_REDACTED>"
    if key_lc in GROUP_KEYS:
        if isinstance(value, str):
            return "<GROUP_REDACTED>" if value else value
        if isinstance(value, (list, tuple)):
            return ["<GROUP_REDACTED>" for item in value if item]
    if key_lc in COORD_KEYS and isinstance(value, (list, tuple)) and 2 <= len(value) <= 3:
        if all(isinstance(item, (int, float)) for item in value):
            return "<COORD_REDACTED>"
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            key_lower = key_str.lower()
            if (
                key_lower in {"x", "y", "z"}
                or key_lower.endswith(("_x", "_y", "_z"))
            ) and isinstance(item, (int, float)):
                sanitized[key_str] = "<COORD_REDACTED>"
            else:
                sanitized[key_str] = sanitize_structure(item, parent_key=key_str)
        return sanitized
    if isinstance(value, list):
        return [sanitize_structure(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return [sanitize_structure(item, parent_key=parent_key) for item in value]
    return value


def contains_sensitive_data(value: Any, *, parent_key: str = "") -> bool:
    key_lc = parent_key.lower()
    if key_lc == "run_id" and isinstance(value, str):
        return False
    if _is_secret_key(key_lc):
        return value not in (None, "", "<SECRET_REDACTED>")
    if key_lc in LAYER_KEYS and isinstance(value, str):
        return value not in ("", "Default", "<LAYER_REDACTED>")
    if key_lc in GROUP_KEYS:
        if isinstance(value, str):
            return value not in ("", "<GROUP_REDACTED>")
        if isinstance(value, (list, tuple)):
            return any(item not in ("", "<GROUP_REDACTED>") for item in value)
    if key_lc in COORD_KEYS and isinstance(value, (list, tuple)) and 2 <= len(value) <= 3:
        return all(isinstance(item, (int, float)) for item in value)
    if isinstance(value, str):
        value = re.sub(r"<(?:SECRET|PATH|COORD|LAYER|GROUP|GUID)_REDACTED>", "", value)
        return bool(
            SECRET_RE.search(value)
            or GUID_RE.search(value)
            or POSIX_PATH_RE.search(value)
            or WINDOWS_PATH_RE.search(value)
            or COORD_TUPLE_RE.search(value)
            or KEYED_COORD_RE.search(value)
            or LAYER_RE.search(value)
        )
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            if (
                key_lower in {"x", "y", "z"}
                or key_lower.endswith(("_x", "_y", "_z"))
            ) and isinstance(item, (int, float)):
                return True
            if contains_sensitive_data(item, parent_key=str(key)):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_sensitive_data(item, parent_key=parent_key) for item in value)
    return False
