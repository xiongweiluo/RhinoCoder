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
from tools.check_demo_assets import check_demo_assets

MANIFEST = ROOT / "docs" / "version-manifest.json"
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_markdown_findings() -> list[str]:
    findings: list[str] = []
    files = [
        ROOT / "README.md",
        ROOT / "README.en.md",
        ROOT / "PROJECT_OPTIMIZATION_PLAN.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
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

    status = release.get("status")
    if status not in {"stable_prototype", "release_candidate", "released"}:
        findings.append(f"release.status: unsupported value {status!r}")
    external = release.get("external_release") or {}
    if status == "release_candidate" and (
        external.get("git_tag") is not False or external.get("github_release") is not False
    ):
        findings.append("release_candidate must record git_tag=false and github_release=false")
    if status == "released" and (
        external.get("git_tag") is not True or external.get("github_release") is not True
    ):
        findings.append("released status requires git_tag=true and github_release=true")

    for label, lock in (manifest.get("dependency_locks") or {}).items():
        path = root / str(lock.get("path", ""))
        if not path.is_file():
            findings.append(f"dependency_locks.{label}: 文件不存在")
        elif _sha256(path) != lock.get("sha256"):
            findings.append(f"dependency_locks.{label}: SHA-256 不一致")

    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for action, pin in (manifest.get("ci_actions") or {}).items():
        expected_use = f"uses: {action}@{pin.get('sha')} # {pin.get('version')}"
        if expected_use not in workflow:
            findings.append(f"ci_actions.{action}: CI 未使用清单中的精确 SHA 与版本")

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
    readme_en = (root / "README.en.md").read_text(encoding="utf-8")
    if status == "released":
        if f"当前正式版本：[`v{__version__}`]" not in readme:
            findings.append("README 未声明当前正式版本")
        if f"Current release: [`v{__version__}`]" not in readme_en:
            findings.append("README.en 未声明当前正式版本")
    else:
        if f"当前候选版本：`{__version__}`" not in readme:
            findings.append("README 未声明当前候选版本")
        if f"Current candidate version: `{__version__}`" not in readme_en:
            findings.append("README.en 未声明当前候选版本")
    for phrase in ("500/500", "46 个标签", "270/270", "local-mock"):
        if phrase not in readme:
            findings.append(f"README 缺少公开口径: {phrase}")
    for phrase in ("500/500", "46 tags", "270/270", "local-mock"):
        if phrase not in readme_en:
            findings.append(f"README.en 缺少公开口径: {phrase}")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{__version__}]" not in changelog:
        findings.append("CHANGELOG 缺少当前正式版本条目")
    checklist = (root / "docs" / "release-checklist.md").read_text(encoding="utf-8")
    incomplete_local = [
        line for line in checklist.splitlines()
        if line.startswith("- [ ]") and "[外部门禁]" not in line
    ]
    if incomplete_local:
        findings.append(f"release-checklist 仍有 {len(incomplete_local)} 个本地未完成项目")
    if status == "release_candidate" and "- [ ] [外部门禁]" not in checklist:
        findings.append("release-checklist 未显式记录外部发布门禁")
    if status == "released" and "当前状态：**Released**" not in checklist:
        findings.append("release-checklist 未记录正式发布状态")

    check_script = (root / "scripts" / "check.sh").read_text(encoding="utf-8")
    if "build_training_dataset.py build" in check_script:
        findings.append("check.sh 不得在常规发布检查中重建冻结的 A5 数据")
    if "run_training.py audit" not in check_script:
        findings.append("check.sh 缺少冻结训练产物审计")

    evidence = manifest.get("portfolio_evidence") or {}
    expected_evidence = {
        "golden_traces": 500,
        "golden_tags": 46,
        "a7_new_tasks": 200,
        "a7_coverage_gaps_met": 8,
        "a6_real_rhino_runs_passed": 270,
        "a6_real_rhino_runs_total": 270,
        "privacy_sensitive_findings": 0,
        "p2_valid_attempts": 30,
        "p2_automated_passed": 18,
        "p2_infrastructure_excluded": 0,
        "p2_infrastructure_interrupted_attempts": 5,
        "p2_holdout_read": 0,
    }
    for label, wanted in expected_evidence.items():
        if evidence.get(label) != wanted:
            findings.append(f"portfolio_evidence.{label}: {evidence.get(label)!r} != {wanted!r}")
    for source in (evidence.get("sources") or {}).values():
        if not (root / str(source)).is_file():
            findings.append(f"portfolio evidence source missing: {source}")

    findings.extend(check_demo_assets(root))

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
