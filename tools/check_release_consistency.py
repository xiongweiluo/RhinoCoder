#!/usr/bin/env python3
"""验证正式版本常量、依赖锁、文档链接和发布清单保持一致。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.version import PROMPT_VERSION, TOOL_SCHEMA_VERSION, TRACE_SCHEMA_VERSION, __version__

MANIFEST = ROOT / "docs" / "version-manifest.json"
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_markdown_findings() -> list[str]:
    findings: list[str] = []
    files = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    for source in files:
        text = source.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK_RE.findall(text):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "/")):
                continue
            resolved = (source.parent / target).resolve()
            if not resolved.exists():
                findings.append(f"{source.relative_to(ROOT)}: 链接目标不存在: {target}")
    return findings


def check_release_consistency(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    try:
        manifest = json.loads((root / "docs" / "version-manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"version-manifest 无法读取: {exc}"]

    package = json.loads((root / "agent" / "ui" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "agent" / "ui" / "package-lock.json").read_text(encoding="utf-8"))
    release = manifest.get("release") or {}
    interfaces = manifest.get("interfaces") or {}
    expected = {
        "release.version": (release.get("version"), __version__),
        "release.status": (release.get("status"), "stable_prototype"),
        "interfaces.prompt": (interfaces.get("prompt"), PROMPT_VERSION),
        "interfaces.tool_schema": (interfaces.get("tool_schema"), TOOL_SCHEMA_VERSION),
        "interfaces.trace_schema": (interfaces.get("trace_schema"), TRACE_SCHEMA_VERSION),
        "package.json version": (package.get("version"), __version__),
        "package-lock version": (package_lock.get("version"), __version__),
        "package-lock root version": ((package_lock.get("packages") or {}).get("", {}).get("version"), __version__),
    }
    for label, (actual, wanted) in expected.items():
        if actual != wanted:
            findings.append(f"{label}: {actual!r} != {wanted!r}")

    for label, lock in (manifest.get("dependency_locks") or {}).items():
        path = root / str(lock.get("path", ""))
        if not path.is_file():
            findings.append(f"dependency_locks.{label}: 文件不存在")
        elif _sha256(path) != lock.get("sha256"):
            findings.append(f"dependency_locks.{label}: SHA-256 不一致")

    schema_files = sorted((root / "plugin" / "mcp_server").glob("schemas_*.py"))
    tool_count = sum(path.read_text(encoding="utf-8").count("@mcp.tool()") for path in schema_files)
    if interfaces.get("mcp_tool_count") != tool_count:
        findings.append(f"MCP 工具数: manifest={interfaces.get('mcp_tool_count')} code={tool_count}")

    architecture = (root / "docs" / "architecture.md").read_text(encoding="utf-8")
    for label, value in (
        ("Application", __version__),
        ("Prompt", PROMPT_VERSION),
        ("Tool schema", TOOL_SCHEMA_VERSION),
        ("Trace schema", TRACE_SCHEMA_VERSION),
    ):
        if f"- {label}: `{value}`" not in architecture:
            findings.append(f"architecture.md 缺少版本声明: {label} {value}")

    readme = (root / "README.md").read_text(encoding="utf-8")
    if f"当前稳定原型版本：`{__version__}`" not in readme:
        findings.append("README 未声明当前稳定原型版本")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{__version__}]" not in changelog:
        findings.append("CHANGELOG 缺少当前正式版本条目")
    checklist = (root / "docs" / "release-checklist.md").read_text(encoding="utf-8")
    if "- [ ]" in checklist:
        findings.append("release-checklist 仍有未完成项目")

    if root == ROOT:
        findings.extend(_local_markdown_findings())
    return findings


def main() -> int:
    findings = check_release_consistency()
    if findings:
        print("Release consistency check failed:")
        for finding in findings:
            print(f"  ✗ {finding}")
        return 1
    print(f"Release consistency check passed (version {__version__}, 23 MCP tools).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
