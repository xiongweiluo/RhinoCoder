#!/usr/bin/env python3
"""Run the reproducible A4 privacy red-team and storage/request audits."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.db import AuditDatabase, DEFAULT_AUDIT_DB  # noqa: E402
from agent.privacy import (  # noqa: E402
    classify_request,
    cloud_sensitive_findings,
    configured_request_audit_path,
    minimize_text_for_cloud,
    prepare_cloud_messages,
    sanitize_for_log,
)
from agent.sanitizer import contains_sensitive_data, sanitize_structure  # noqa: E402
from tools.audit_release_data import audit_release_data  # noqa: E402


RED_TEAM_PATH = ROOT / "eval" / "privacy" / "red_team.json"
ACTIVE_TRACE_PATHS = (
    ROOT / "data" / "golden_traces_v2.jsonl",
    ROOT / "data" / "feedback.jsonl",
    ROOT / "data" / "candidates.jsonl",
    ROOT / "data" / "ai_reviewed_candidates.jsonl",
    ROOT / "data" / "partial_traces.jsonl",
    ROOT / "data" / "error_traces.jsonl",
)


@dataclass(slots=True)
class PrivacyAuditResult:
    passed: bool = True
    red_team_cases: int = 0
    blocked_cases: int = 0
    forced_local_cases: int = 0
    minimized_cloud_cases: int = 0
    allowed_cloud_cases: int = 0
    trace_records_scanned: int = 0
    log_files_scanned: int = 0
    sqlite_rows_scanned: int = 0
    replay_files_scanned: int = 0
    recorded_model_requests_scanned: int = 0
    simulated_model_requests_scanned: int = 0
    simulated_log_records_scanned: int = 0
    findings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def finalize(self) -> "PrivacyAuditResult":
        self.passed = not self.findings
        return self


def _load_json_records(path: Path, result: PrivacyAuditResult) -> list[Any]:
    if not path.is_file():
        return []
    try:
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else [payload]
    except (OSError, json.JSONDecodeError) as exc:
        result.findings.append(f"{path.relative_to(ROOT)}: 无法解析: {exc}")
        return []


def _audit_red_team(result: PrivacyAuditResult) -> None:
    cases = _load_json_records(RED_TEAM_PATH, result)
    result.red_team_cases = len(cases)
    seen_ids: set[str] = set()
    seen_categories: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            result.findings.append("red_team.json: case 必须是 object")
            continue
        case_id = str(case.get("id") or "")
        category = str(case.get("category") or "")
        prompt = str(case.get("prompt") or "")
        if not case_id or case_id in seen_ids:
            result.findings.append(f"red_team.json: ID 缺失或重复: {case_id!r}")
        seen_ids.add(case_id)
        seen_categories.add(category)
        decision = classify_request(prompt)
        if decision.risk.value != case.get("expected_risk"):
            result.findings.append(
                f"{case_id}: risk={decision.risk.value}, expected={case.get('expected_risk')}"
            )
        if decision.action.value != case.get("expected_action"):
            result.findings.append(
                f"{case_id}: action={decision.action.value}, expected={case.get('expected_action')}"
            )
        counts = {
            "block": "blocked_cases",
            "force_local": "forced_local_cases",
            "minimize_cloud": "minimized_cloud_cases",
            "allow_cloud": "allowed_cloud_cases",
        }
        attribute = counts.get(decision.action.value)
        if attribute:
            setattr(result, attribute, getattr(result, attribute) + 1)

        minimized = minimize_text_for_cloud(prompt)
        for token in case.get("must_redact") or []:
            if str(token) in minimized:
                result.findings.append(f"{case_id}: 最小化后仍包含 {token!r}")
        for token in case.get("must_keep") or []:
            if str(token) not in minimized:
                result.findings.append(f"{case_id}: 几何必要信息丢失 {token!r}")
        findings = cloud_sensitive_findings(minimized)
        if findings:
            result.findings.append(f"{case_id}: 云端最小化仍有敏感项 {findings}")
        result.simulated_log_records_scanned += 1
        if cloud_sensitive_findings(sanitize_for_log(prompt)):
            result.findings.append(f"{case_id}: 日志脱敏仍有敏感项")
        if decision.cloud_allowed:
            try:
                prepare_cloud_messages([{"role": "user", "content": prompt}])
                result.simulated_model_requests_scanned += 1
            except Exception as exc:
                result.findings.append(f"{case_id}: 合法最小化请求被拒绝: {exc}")

    required_categories = {
        "credential",
        "prompt_injection",
        "credential_exfiltration",
        "customer_name",
        "project_name",
        "file_path",
        "layer_name",
        "group_name",
        "personal_identifier",
        "necessary_geometry",
        "benign",
    }
    missing = required_categories.difference(seen_categories)
    if missing:
        result.findings.append(f"red_team.json: 缺少类别 {sorted(missing)}")


def _audit_traces(result: PrivacyAuditResult) -> None:
    paths = [*ACTIVE_TRACE_PATHS, *sorted((ROOT / "data" / "traces").glob("*.json"))]
    for path in paths:
        for index, record in enumerate(_load_json_records(path, result), 1):
            result.trace_records_scanned += 1
            raw_findings = [
                finding
                for finding in cloud_sensitive_findings(record)
                if not finding.endswith((":layer", ":group", ":layer_field", ":group_field"))
            ]
            if raw_findings:
                result.findings.append(
                    f"{path.relative_to(ROOT)}:{index}: Trace 敏感项 {raw_findings[:5]}"
                )
            if contains_sensitive_data(sanitize_structure(record)):
                result.findings.append(
                    f"{path.relative_to(ROOT)}:{index}: Trace 写入脱敏后仍有敏感数据"
                )


def _audit_logs(result: PrivacyAuditResult) -> None:
    paths = {
        *sorted((ROOT / "logs").glob("**/*.log")),
        *sorted((ROOT / "data" / "logs").glob("**/*.log")),
    }
    for path in paths:
        result.log_files_scanned += 1
        try:
            findings = cloud_sensitive_findings(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            result.findings.append(f"{path.relative_to(ROOT)}: 日志无法读取: {exc}")
            continue
        if findings:
            result.findings.append(f"{path.relative_to(ROOT)}: 日志敏感项 {findings[:5]}")


def _audit_sqlite(result: PrivacyAuditResult) -> None:
    if not DEFAULT_AUDIT_DB.is_file():
        result.notices.append("SQLite 审计库不存在；已由临时数据库自动测试覆盖")
        return
    with AuditDatabase(DEFAULT_AUDIT_DB) as database:
        audit = database.audit()
    result.sqlite_rows_scanned = sum(audit.counts.values())
    if not audit.passed:
        result.findings.extend(
            [f"SQLite sensitive: {item}" for item in audit.sensitive_field_findings]
            + [f"SQLite foreign key: {item}" for item in audit.foreign_key_findings]
            + [f"SQLite lineage: {item}" for item in audit.lineage_findings]
        )


def _audit_replays(result: PrivacyAuditResult) -> None:
    audit = audit_release_data(ROOT)
    result.replay_files_scanned = sum(
        1 for item in audit.checked if item.startswith("eval/replays/")
    )
    result.findings.extend(f"Replay: {finding}" for finding in audit.findings)


def _audit_model_requests(result: PrivacyAuditResult) -> None:
    for index, row in enumerate(_load_json_records(configured_request_audit_path(), result), 1):
        result.recorded_model_requests_scanned += 1
        request = (
            {"messages": row.get("messages"), "tools": row.get("tools")}
            if isinstance(row, dict)
            else row
        )
        findings = cloud_sensitive_findings(request)
        if findings:
            result.findings.append(f"model_requests.jsonl:{index}: {findings[:5]}")


def run_privacy_audit() -> PrivacyAuditResult:
    result = PrivacyAuditResult()
    _audit_red_team(result)
    _audit_traces(result)
    _audit_logs(result)
    _audit_sqlite(result)
    _audit_replays(result)
    _audit_model_requests(result)
    return result.finalize()


def render_markdown(result: PrivacyAuditResult) -> str:
    status = "通过" if result.passed else "失败"
    lines = [
        "# A4 隐私红队与零泄漏验收报告",
        "",
        f"验收日期：{date.today().isoformat()}",
        "",
        f"结论：**{status}**。",
        "",
        "## 覆盖与结果",
        "",
        "| 检查项 | 数量 |",
        "| --- | ---: |",
        f"| 红队用例 | {result.red_team_cases} |",
        f"| 请求前阻断 | {result.blocked_cases} |",
        f"| 强制本地 | {result.forced_local_cases} |",
        f"| 最小化后允许云端 | {result.minimized_cloud_cases} |",
        f"| 低风险允许云端 | {result.allowed_cloud_cases} |",
        f"| 活跃 Trace 记录扫描 | {result.trace_records_scanned} |",
        f"| 日志文件扫描 | {result.log_files_scanned} |",
        f"| 红队日志记录模拟 | {result.simulated_log_records_scanned} |",
        f"| SQLite 行扫描 | {result.sqlite_rows_scanned} |",
        f"| Replay 文件扫描 | {result.replay_files_scanned} |",
        f"| 已记录模型请求扫描 | {result.recorded_model_requests_scanned} |",
        f"| 红队模型请求模拟 | {result.simulated_model_requests_scanned} |",
        f"| 敏感数据发现 | {len(result.findings)} |",
        "",
        "## 验收断言",
        "",
        "- 凭证、Prompt 注入和数据窃取请求在模型及 MCP 启动前阻断。",
        "- 客户、项目、路径、图层和群组信号强制本地，不允许静默发送云端。",
        "- 邮箱等中风险标识先最小化，再由云端边界执行第二次扫描。",
        "- 云端最小化保留坐标、尺寸和对象 ID，使必要的几何闭环验证仍可执行。",
        "- 控制台日志不输出原始 prompt，并统一清理凭证、路径、身份、图层和群组。",
        "- Trace、SQLite、Replay 与模型请求均由同一命令重复扫描。",
        "",
        "## 请求决策矩阵",
        "",
        "| 风险 | 典型信号 | 动作 |",
        "| --- | --- | --- |",
        "| Critical | 凭证、Prompt 注入、密钥/环境窃取 | 在 MCP 和模型启动前阻断 |",
        "| High | 客户/项目身份、本机路径、图层/群组、明确仅本地 | 强制本地，禁止云 fallback |",
        "| Medium | 邮箱等可移除个人标识 | 最小化后经第二道扫描才允许云端 |",
        "| Low | 纯几何意图与必要参数 | 允许按正常路由选择云端 |",
        "",
        "## 实现边界",
        "",
        "- 请求入口生成唯一 `decision_id`、风险、动作、原因码和可读原因；阻断事件可在 UI 与 Trace 中复核。",
        "- 云模型边界只接受白名单消息字段，并记录实际尝试发送的最小化消息、工具定义、内容哈希和后端信息。",
        "- Agent 日志在格式化后统一清洗；MCP 与 Rhino Listener 只记录键、数量、类型和状态，不记录对象名、图层、群组或路径值。",
        "- 审计命令检查现有文件；当前没有日志文件或模型请求台账时，数量可为零，但红队模拟和自动测试仍覆盖相应写入边界。",
        "",
        "## 复现",
        "",
        "```bash",
        "python tools/privacy_audit.py",
        "python tools/privacy_audit.py --json",
        "python tools/privacy_audit.py --write-report docs/privacy-red-team-report.md",
        "```",
    ]
    if result.notices:
        lines.extend(["", "## 说明", "", *[f"- {notice}" for notice in result.notices]])
    if result.findings:
        lines.extend(["", "## 发现", "", *[f"- {finding}" for finding in result.findings]])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args()
    result = run_privacy_audit()
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(render_markdown(result), encoding="utf-8")
        print(args.write_report)
    elif args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print(
            f"Privacy audit {'passed' if result.passed else 'failed'}: "
            f"red_team={result.red_team_cases}, traces={result.trace_records_scanned}, "
            f"sqlite_rows={result.sqlite_rows_scanned}, replays={result.replay_files_scanned}, "
            f"model_requests={result.recorded_model_requests_scanned}, findings={len(result.findings)}"
        )
        for notice in result.notices:
            print(f"  ! {notice}")
        for finding in result.findings:
            print(f"  ✗ {finding}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
