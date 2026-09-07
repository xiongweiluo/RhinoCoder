"""本地轨迹与反馈数据脱敏。"""

from __future__ import annotations

import json
import re
from typing import Any

from agent.privacy import (
    cloud_sensitive_findings,
    extract_local_tool_aliases,
    minimize_text_for_cloud,
)

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
IDENTITY_KEYS = {
    "customer",
    "customer_name",
    "client",
    "client_name",
    "project_name",
    "project_code",
}
LINEAGE_ID_KEYS = {
    "run_id",
    "route_id",
    "decision_id",
    "request_id",
    "feedback_id",
    "call_id",
    "tool_call_id",
    "supersedes_run_id",
}


def _is_secret_key(key: str) -> bool:
    key = key.lower()
    return key in SECRET_KEYS or key.endswith(
        ("_api_key", "_secret", "_password", "_access_token", "_refresh_token")
    )


def sanitize_text(value: str) -> str:
    value = minimize_text_for_cloud(value)
    value = SECRET_RE.sub("<SECRET_REDACTED>", value)
    value = GUID_RE.sub("<GUID_REDACTED>", value)
    value = POSIX_PATH_RE.sub("<PATH_REDACTED>", value)
    value = WINDOWS_PATH_RE.sub("<PATH_REDACTED>", value)
    value = COORD_TUPLE_RE.sub("<COORD_REDACTED>", value)
    value = KEYED_COORD_RE.sub(r"\1<COORD_REDACTED>", value)
    return value


def _collect_sensitive_aliases(value: Any) -> dict[str, str]:
    """Find trusted labels, then redact their later unlabelled repetitions."""
    aliases: dict[str, str] = {}

    def collect_text(text: str) -> None:
        detected = extract_local_tool_aliases(text)
        aliases.update({item: "<LAYER_REDACTED>" for item in detected["layer_name"]})
        aliases.update({item: "<GROUP_REDACTED>" for item in detected["group_name"]})

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            role = str(item.get("role") or "").lower()
            if role == "user" and isinstance(item.get("content"), str):
                collect_text(item["content"])
            for key, child in item.items():
                key_lc = str(key).lower()
                if key_lc in LAYER_KEYS and isinstance(child, str) and child != "Default":
                    aliases[child] = "<LAYER_REDACTED>"
                elif key_lc in GROUP_KEYS:
                    children = child if isinstance(child, (list, tuple)) else [child]
                    for candidate in children:
                        if isinstance(candidate, str) and candidate:
                            aliases[candidate] = "<GROUP_REDACTED>"
                elif key_lc in {"instruction", "prompt"} and isinstance(child, str):
                    collect_text(child)
                walk(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                walk(child)

    walk(value)
    return {
        key: marker
        for key, marker in aliases.items()
        if key and not key.startswith("<") and any(char.isalnum() for char in key)
    }


def sanitize_structure(
    value: Any,
    *,
    parent_key: str = "",
    _aliases: dict[str, str] | None = None,
) -> Any:
    if _aliases is None:
        _aliases = _collect_sensitive_aliases(value)
    key_lc = parent_key.lower()
    # 系统血缘 ID 不是 Rhino 对象 GUID，必须保留以支持跨表追溯。
    if key_lc in LINEAGE_ID_KEYS and isinstance(value, str):
        return value
    if key_lc == "arguments" and isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            pass
        else:
            return json.dumps(
                sanitize_structure(decoded, _aliases=_aliases),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
    if _is_secret_key(key_lc):
        return "<SECRET_REDACTED>"
    if key_lc in LAYER_KEYS and isinstance(value, str):
        return value if value == "Default" else "<LAYER_REDACTED>"
    if key_lc in GROUP_KEYS:
        if isinstance(value, str):
            return "<GROUP_REDACTED>" if value else value
        if isinstance(value, (list, tuple)):
            return ["<GROUP_REDACTED>" for item in value if item]
    if key_lc in IDENTITY_KEYS:
        return "<IDENTITY_REDACTED>" if value else value
    if key_lc in COORD_KEYS and isinstance(value, (list, tuple)) and 2 <= len(value) <= 3:
        if all(isinstance(item, (int, float)) for item in value):
            return "<COORD_REDACTED>"
    if isinstance(value, str):
        sanitized = sanitize_text(value)
        for alias in sorted(_aliases, key=len, reverse=True):
            sanitized = sanitized.replace(alias, _aliases[alias])
        return sanitized
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
                sanitized[key_str] = sanitize_structure(
                    item,
                    parent_key=key_str,
                    _aliases=_aliases,
                )
        return sanitized
    if isinstance(value, list):
        return [
            sanitize_structure(item, parent_key=parent_key, _aliases=_aliases)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            sanitize_structure(item, parent_key=parent_key, _aliases=_aliases)
            for item in value
        ]
    return value


def contains_sensitive_data(
    value: Any,
    *,
    parent_key: str = "",
    inspect_embedded_json: bool = False,
) -> bool:
    """Return whether ``value`` still contains protected content.

    ``inspect_embedded_json`` enables the stricter SQLite/storage boundary: it
    decodes serialized tool arguments so coordinate arrays are interpreted by
    their semantic key instead of by the broad free-text tuple detector.  It is
    opt-in because frozen trace corpora were admitted under the original
    byte-level contract and must not be retroactively reclassified.
    """

    key_lc = parent_key.lower()
    if key_lc in LINEAGE_ID_KEYS and isinstance(value, str):
        return False
    if inspect_embedded_json and key_lc == "arguments" and isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            pass
        else:
            return contains_sensitive_data(decoded, inspect_embedded_json=True)
    if _is_secret_key(key_lc):
        return value not in (None, "", "<SECRET_REDACTED>")
    if key_lc in LAYER_KEYS and isinstance(value, str):
        return value not in ("", "Default", "<LAYER_REDACTED>")
    if key_lc in GROUP_KEYS:
        if isinstance(value, str):
            return value not in ("", "<GROUP_REDACTED>")
        if isinstance(value, (list, tuple)):
            return any(item not in ("", "<GROUP_REDACTED>") for item in value)
    if key_lc in IDENTITY_KEYS:
        return value not in (None, "", "<IDENTITY_REDACTED>")
    if key_lc in COORD_KEYS and isinstance(value, (list, tuple)) and 2 <= len(value) <= 3:
        return all(isinstance(item, (int, float)) for item in value)
    if isinstance(value, str):
        # Preserve a separator where an earlier sanitization pass inserted a
        # marker. Removing markers entirely can join adjacent lines (for
        # example ``z=<COORD_REDACTED>\n4.`` becomes ``z=\n4``) and create a
        # false positive for sensitive data that is no longer present.
        # An empty layer value must stay empty; a placeholder inside quotes
        # would itself look like a real project layer to ``LAYER_RE``.
        value = value.replace("<LAYER_REDACTED>", "")
        value = re.sub(
            r"<(?:SECRET|PATH|COORD|GROUP|GUID)_REDACTED>",
            " REDACTED ",
            value,
        )
        cloud_findings = [
            finding
            for finding in cloud_sensitive_findings(value)
            if not finding.endswith((":layer", ":group"))
        ]
        return bool(
            cloud_findings
            or
            SECRET_RE.search(value)
            or GUID_RE.search(value)
            or POSIX_PATH_RE.search(value)
            or WINDOWS_PATH_RE.search(value)
            or COORD_TUPLE_RE.search(value)
            or KEYED_COORD_RE.search(value)
        )
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            if (
                key_lower in {"x", "y", "z"}
                or key_lower.endswith(("_x", "_y", "_z"))
            ) and isinstance(item, (int, float)):
                return True
            if contains_sensitive_data(
                item,
                parent_key=str(key),
                inspect_embedded_json=inspect_embedded_json,
            ):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(
            contains_sensitive_data(
                item,
                parent_key=parent_key,
                inspect_embedded_json=inspect_embedded_json,
            )
            for item in value
        )
    return False
