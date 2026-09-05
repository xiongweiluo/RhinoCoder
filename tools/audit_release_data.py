#!/usr/bin/env python3
"""验证公开基准报告与 Replay 的脱敏声明、内容锁和基础结构。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.sanitizer import GUID_RE, POSIX_PATH_RE, SECRET_RE, WINDOWS_PATH_RE
from agent.privacy import cloud_sensitive_findings

MANIFEST_PATH = ROOT / "docs" / "release-data-manifest.json"
EXPECTED_ARTIFACTS = {
    "docs/benchmark-report.md",
    "eval/replays/basic_stack.json",
    "eval/replays/self_correction.json",
    "eval/replays/table_group.json",
}
GENERIC_LAYERS = {"Default", "Sample"}
SECRET_KEYS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "access_token",
    "refresh_token",
}


@dataclass(slots=True)
class ReleaseDataAudit:
    checked: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_public_text(relative: str, text: str, audit: ReleaseDataAudit) -> None:
    scrubbed = text.replace("<SECRET_REDACTED>", "").replace("<PATH_REDACTED>", "").replace("<GUID_REDACTED>", "")
    patterns = {
        "API Key": SECRET_RE,
        "本机 POSIX 路径": POSIX_PATH_RE,
        "本机 Windows 路径": WINDOWS_PATH_RE,
        "真实 UUID/GUID": GUID_RE,
    }
    for label, pattern in patterns.items():
        if pattern.search(scrubbed):
            audit.findings.append(f"{relative}: 检测到{label}")
    privacy_findings = [
        finding
        for finding in cloud_sensitive_findings(text)
        if not finding.endswith((":layer", ":group", ":local_path", ":windows_path"))
    ]
    if privacy_findings:
        audit.findings.append(f"{relative}: 检测到隐私内容 {privacy_findings[:5]}")


def _walk_replay(value: Any, relative: str, audit: ReleaseDataAudit, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            child_path = f"{path}.{key}"
            if key_lower in SECRET_KEYS and item not in (None, "", "<SECRET_REDACTED>"):
                audit.findings.append(f"{relative}:{child_path}: 敏感配置字段未脱敏")
            if key_lower in {"layer", "layer_name", "project_layer"}:
                if not isinstance(item, str) or item not in GENERIC_LAYERS:
                    audit.findings.append(f"{relative}:{child_path}: 使用了非通用图层 {item!r}")
            _walk_replay(item, relative, audit, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_replay(item, relative, audit, f"{path}[{index}]")


def _audit_replay(relative: str, payload: dict[str, Any], audit: ReleaseDataAudit) -> None:
    privacy = payload.get("privacy") or {}
    expected_privacy = {
        "reviewed": True,
        "contains_real_trace_data": False,
        "coordinates": "synthetic",
        "object_ids": "synthetic",
        "layers": "generic",
    }
    if payload.get("sample") is not True or payload.get("provenance") != "synthetic":
        audit.findings.append(f"{relative}: Replay 未声明为合成样例")
    if privacy != expected_privacy:
        audit.findings.append(f"{relative}: privacy 声明不完整或已变化")

    events = payload.get("events")
    if not isinstance(events, list) or not events:
        audit.findings.append(f"{relative}: events 为空或格式错误")
        return
    run_ids = {event.get("run_id") for event in events if isinstance(event, dict)}
    if len(run_ids) != 1 or not next(iter(run_ids), "").startswith("replay-"):
        audit.findings.append(f"{relative}: run_id 不是单一的 replay-* 合成标识")
    sequences = [event.get("seq") for event in events if isinstance(event, dict)]
    if sequences != list(range(1, len(events) + 1)):
        audit.findings.append(f"{relative}: 事件序号不是从 1 开始严格递增")
    event_types = {event.get("type") for event in events if isinstance(event, dict)}
    if not {"scene.checked", "run.completed"}.issubset(event_types):
        audit.findings.append(f"{relative}: 缺少 scene.checked 或 run.completed")
    _walk_replay(payload, relative, audit)


def audit_release_data(root: Path = ROOT) -> ReleaseDataAudit:
    audit = ReleaseDataAudit()
    manifest_path = root / "docs" / "release-data-manifest.json"
    if not manifest_path.exists():
        audit.findings.append("docs/release-data-manifest.json: 文件不存在")
        return audit
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        audit.findings.append(f"docs/release-data-manifest.json: 无法读取: {exc}")
        return audit

    artifacts = manifest.get("artifacts") or []
    paths = {item.get("path") for item in artifacts if isinstance(item, dict)}
    if paths != EXPECTED_ARTIFACTS:
        audit.findings.append(
            "docs/release-data-manifest.json: artifact 集合必须精确覆盖正式报告和三份 Replay"
        )
    if manifest.get("review", {}).get("method") != "automated_scan_and_artifact_review":
        audit.findings.append("docs/release-data-manifest.json: 缺少逐文件复核声明")

    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            audit.findings.append("docs/release-data-manifest.json: artifact 条目格式错误")
            continue
        relative = item["path"]
        path = root / relative
        if not path.is_file():
            audit.findings.append(f"{relative}: 文件不存在")
            continue
        audit.checked.append(relative)
        actual_hash = _sha256(path)
        if item.get("sha256") != actual_hash:
            audit.findings.append(f"{relative}: SHA-256 与复核清单不一致，需要重新审计")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            audit.findings.append(f"{relative}: 不是 UTF-8 文本")
            continue
        _scan_public_text(relative, text, audit)
        if relative.startswith("eval/replays/"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                audit.findings.append(f"{relative}: JSON 无效: {exc}")
                continue
            _audit_replay(relative, payload, audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args()
    audit = audit_release_data()
    if args.json:
        print(json.dumps({"passed": audit.passed, "checked": audit.checked, "findings": audit.findings}, ensure_ascii=False, indent=2))
    else:
        for relative in audit.checked:
            print(f"  ✓ {relative}")
        if audit.findings:
            print("Release data audit failed:")
            for finding in audit.findings:
                print(f"  ✗ {finding}")
        else:
            print(f"Release data audit passed ({len(audit.checked)} artifacts).")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
