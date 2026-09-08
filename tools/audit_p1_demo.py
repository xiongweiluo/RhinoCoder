#!/usr/bin/env python3
"""Audit the three fixed P1 recruiter demos and their read-only browser contract."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "docs" / "demo" / "p1-scenarios.json"
EXPECTED = {
    "normal-loop": {
        "replay": "basic_stack.json",
        "events": {"privacy.assessed", "route.selected", "tool.completed", "scene.checked", "assertion.checked", "run.completed"},
    },
    "self-correction": {
        "replay": "self_correction.json",
        "events": {"tool.completed", "scene.checked", "assertion.checked", "correction.started", "run.completed"},
    },
    "privacy-route": {
        "replay": "table_group.json",
        "events": {"privacy.assessed", "route.selected", "tool.completed", "scene.checked", "assertion.checked", "run.completed"},
    },
}


@dataclass(slots=True)
class P1Audit:
    scenarios: int = 0
    replays: int = 0
    browser_tests: int = 0
    findings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(ROOT)} 顶层必须是对象")
    return payload


def audit_p1(root: Path = ROOT) -> P1Audit:
    audit = P1Audit()
    catalog_path = root / CATALOG.relative_to(ROOT)
    try:
        catalog = _read_json(catalog_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        audit.findings.append(f"P1 场景清单无法读取: {exc}")
        return audit

    privacy = catalog.get("privacy") or {}
    if privacy.get("catalog_contains_real_user_data") is not False:
        audit.findings.append("P1 场景清单未声明不含真实用户数据")
    if privacy.get("replays_are_synthetic") is not True:
        audit.findings.append("P1 场景清单未声明 Replay 为合成数据")
    if privacy.get("browser_payload_policy") != "minimized_and_object_ids_pseudonymized":
        audit.findings.append("P1 浏览器载荷策略缺失或漂移")

    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, list):
        audit.findings.append("P1 场景清单缺少 scenarios")
        return audit
    audit.scenarios = len(scenarios)
    by_id = {str(item.get("id")): item for item in scenarios if isinstance(item, dict)}
    if set(by_id) != set(EXPECTED) or len(scenarios) != 3:
        audit.findings.append(f"P1 必须精确覆盖三个固定场景，实际为 {sorted(by_id)}")

    replay_names: set[str] = set()
    for scenario_id, requirement in EXPECTED.items():
        scenario = by_id.get(scenario_id)
        if scenario is None:
            continue
        for key in ("title", "kicker", "goal", "input"):
            if not isinstance(scenario.get(key), str) or not scenario[key].strip():
                audit.findings.append(f"{scenario_id}: {key} 为空")
        if not isinstance(scenario.get("expected"), list) or not scenario["expected"]:
            audit.findings.append(f"{scenario_id}: expected 为空")
        if not isinstance(scenario.get("asserts"), list) or not scenario["asserts"]:
            audit.findings.append(f"{scenario_id}: asserts 为空")
        replay_name = str(scenario.get("replay", ""))
        replay_names.add(replay_name)
        if replay_name != requirement["replay"]:
            audit.findings.append(f"{scenario_id}: Replay 映射漂移")
        evidence_path = str((scenario.get("evidence") or {}).get("path", ""))
        if Path(evidence_path).name != evidence_path or not (root / "docs" / evidence_path).is_file():
            audit.findings.append(f"{scenario_id}: 证据入口无效")

        replay_path = root / "eval" / "replays" / replay_name
        try:
            replay = _read_json(replay_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            audit.findings.append(f"{scenario_id}: Replay 无法读取: {exc}")
            continue
        audit.replays += 1
        if replay.get("demo_scenario") != scenario_id:
            audit.findings.append(f"{scenario_id}: Replay 反向映射不一致")
        if replay.get("provenance") != "synthetic" or replay.get("privacy", {}).get("reviewed") is not True:
            audit.findings.append(f"{scenario_id}: Replay 缺少合成/隐私复核声明")
        before = replay.get("scene_before") or {}
        if not isinstance(before.get("objects"), list):
            audit.findings.append(f"{scenario_id}: 缺少操作前场景")
        events = replay.get("events")
        if not isinstance(events, list) or not events:
            audit.findings.append(f"{scenario_id}: events 为空")
            continue
        sequences = [event.get("seq") for event in events if isinstance(event, dict)]
        if sequences != list(range(1, len(events) + 1)):
            audit.findings.append(f"{scenario_id}: 事件序号不连续")
        run_ids = {event.get("run_id") for event in events if isinstance(event, dict)}
        if len(run_ids) != 1:
            audit.findings.append(f"{scenario_id}: 事件未共享同一 run_id")
        event_types = {event.get("type") for event in events if isinstance(event, dict)}
        missing = set(requirement["events"]) - event_types
        if missing:
            audit.findings.append(f"{scenario_id}: 缺少事件 {sorted(missing)}")
        if events[-1].get("type") != "run.completed":
            audit.findings.append(f"{scenario_id}: Replay 最终状态不是 completed")
        if not any(
            event.get("type") == "scene.checked"
            and isinstance((event.get("payload") or {}).get("scene_summary", {}).get("objects"), list)
            for event in events
        ):
            audit.findings.append(f"{scenario_id}: 缺少最终 Scene Summary")

        assertions = [event for event in events if event.get("type") == "assertion.checked"]
        if scenario_id == "self-correction":
            outcomes = [(event.get("payload") or {}).get("success") for event in assertions]
            if outcomes != [False, True]:
                audit.findings.append("self-correction: 必须保留首次失败与复检通过证据")
        if scenario_id == "privacy-route":
            privacy_events = [event for event in events if event.get("type") == "privacy.assessed"]
            decision = (privacy_events[0].get("payload") or {}) if privacy_events else {}
            if decision.get("risk") != "medium" or decision.get("action") != "minimize_cloud":
                audit.findings.append("privacy-route: 隐私最小化决策不符合固定口径")
            serialized = json.dumps(replay, ensure_ascii=False)
            if "contact@example.invalid" in serialized or "<EMAIL_REDACTED>" not in serialized:
                audit.findings.append("privacy-route: 合成邮箱未正确最小化")

    if replay_names != {item["replay"] for item in EXPECTED.values()}:
        audit.findings.append("三个固定场景没有一对一映射三份 Replay")

    required_files = [
        root / "agent" / "ui" / "playwright.config.ts",
        root / "agent" / "ui" / "e2e" / "public-demo.spec.ts",
        root / "tools" / "check_ui_performance.py",
    ]
    for path in required_files:
        if not path.is_file():
            audit.findings.append(f"P1 验收文件缺失: {path.relative_to(root)}")
    e2e_path = required_files[1]
    if e2e_path.is_file():
        e2e_text = e2e_path.read_text(encoding="utf-8")
        audit.browser_tests = e2e_text.count("test(")
        for phrase in ("three public Replay scenarios", "privacy route Replay", "390px viewport"):
            if phrase not in e2e_text:
                audit.findings.append(f"浏览器测试缺少覆盖: {phrase}")
    check_text = (root / "scripts" / "check.sh").read_text(encoding="utf-8")
    for command in ("python tools/audit_p1_demo.py", "python tools/check_ui_performance.py", "npm run test:e2e --prefix agent/ui"):
        if command not in check_text:
            audit.findings.append(f"check.sh 缺少 P1 门禁: {command}")
    return audit


def main() -> int:
    audit = audit_p1()
    payload = {
        "passed": audit.passed,
        "scenarios": audit.scenarios,
        "replays": audit.replays,
        "browser_tests": audit.browser_tests,
        "findings": audit.findings,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
