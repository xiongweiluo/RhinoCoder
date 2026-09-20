#!/usr/bin/env python3
"""Build and audit the minimized P2 base/LoRA comparison and C4 decision."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.final_evaluation import paired_binary_statistics
from eval.p2_hard import _is_infrastructure_result
from training.config import ReadinessError
from training.reporting import atomic_json


TASKS = ROOT / "eval" / "p2" / "hard_tasks.jsonl"
PROTOCOL = ROOT / "eval" / "p2" / "model-comparison-protocol.json"
HYBRID = ROOT / "docs" / "p2-hard-set-results.json"
DEFAULT_BASE = ROOT / "data" / "training" / "p2-model-comparison" / "base-results.jsonl"
DEFAULT_LORA = ROOT / "data" / "training" / "p2-model-comparison" / "lora-results.jsonl"
DEFAULT_OUTPUT = ROOT / "docs" / "p2-model-comparison-results.json"
DEFAULT_REPORT = ROOT / "docs" / "c4-model-decision.md"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _filled(rows: list[dict[str, Any]], lane: str, task_ids: set[str]) -> tuple[dict[str, dict[str, Any]], int]:
    by_task: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in task_ids}
    for row in rows:
        if row.get("task_id") not in by_task:
            raise ReadinessError(f"{lane}: unexpected task {row.get('task_id')}")
        if row.get("model_lane") != lane:
            raise ReadinessError(f"{lane}: model_lane mismatch")
        if row.get("holdout_read") != 0:
            raise ReadinessError(f"{lane}: holdout_read must remain zero")
        by_task[row["task_id"]].append(row)
    selected: dict[str, dict[str, Any]] = {}
    interruptions = 0
    for task_id, attempts in by_task.items():
        valid = [row for row in attempts if not _is_infrastructure_result(row)]
        interruptions += len(attempts) - len(valid)
        if len(valid) != 1:
            raise ReadinessError(f"{lane}/{task_id}: expected one filled slot, got {len(valid)}")
        selected[task_id] = valid[0]
    return selected, interruptions


def build(base_path: Path, lora_path: Path) -> dict[str, Any]:
    tasks = _jsonl(TASKS)
    task_ids = {item["id"] for item in tasks}
    if len(task_ids) != 30:
        raise ReadinessError("P2 task set must contain 30 unique tasks")
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["task_set"]["hard_tasks_sha256"] != _sha(TASKS):
        raise ReadinessError("P2 comparison protocol task hash drifted")
    base, base_interruptions = _filled(_jsonl(base_path), "base", task_ids)
    lora, lora_interruptions = _filled(_jsonl(lora_path), "lora", task_ids)
    paired = paired_binary_statistics(
        {task_id: bool(base[task_id]["automated_pass"]) for task_id in task_ids},
        {task_id: bool(lora[task_id]["automated_pass"]) for task_id in task_ids},
    )
    base_failures = Counter(
        row.get("failure_category") for row in base.values() if not row.get("automated_pass")
    )
    lora_failures = Counter(
        row.get("failure_category") for row in lora.values() if not row.get("automated_pass")
    )
    critical_categories = {"privacy_error", "recovery_error", "product_control_error"}
    critical_regressions = sorted(
        task_id
        for task_id in task_ids
        if base[task_id]["automated_pass"]
        and not lora[task_id]["automated_pass"]
        and lora[task_id].get("failure_category") in critical_categories
    )
    hybrid = json.loads(HYBRID.read_text(encoding="utf-8"))["baseline"]
    p2_threshold = (
        paired["difference_percentage_points"] >= 10.0
        and paired["net_wins_right_minus_left"] >= 3
    )
    a5_threshold = False  # immutable published C3 result: 0/45 vs 0/45
    if a5_threshold and p2_threshold and not critical_regressions:
        decision = "GO"
    elif (
        paired["net_wins_right_minus_left"] >= 2
        and paired["difference_percentage_points"] > 0
        and not critical_regressions
    ):
        decision = "MORE-DATA"
    else:
        decision = "NO-GO"
    return {
        "schema_version": "1.0",
        "report_id": "p2-qwen-base-lora-paired-v1",
        "generated_at": date.today().isoformat(),
        "experiment_id": protocol["experiment_id"],
        "scope": "frozen 30-task real-Rhino paired model comparison; P2 remains evaluation-only",
        "freeze": {
            "protocol_sha256": _sha(PROTOCOL),
            "hard_tasks_sha256": _sha(TASKS),
            "task_count": 30,
            "holdout_read": 0,
        },
        "evidence": {
            "base_raw_sha256": _sha(base_path),
            "lora_raw_sha256": _sha(lora_path),
            "base_infrastructure_interruptions": base_interruptions,
            "lora_infrastructure_interruptions": lora_interruptions,
            "raw_committed": False,
            "raw_prompts_or_traces_published": False,
        },
        "base": {
            "passed": sum(bool(row["automated_pass"]) for row in base.values()),
            "total": 30,
            "failure_categories": dict(sorted(base_failures.items())),
        },
        "lora": {
            "passed": sum(bool(row["automated_pass"]) for row in lora.values()),
            "total": 30,
            "failure_categories": dict(sorted(lora_failures.items())),
        },
        "paired_lora_minus_base": paired,
        "safety": {
            "critical_regression_task_count": len(critical_regressions),
            "critical_regression_task_ids": critical_regressions,
        },
        "deployment_context": {
            "published_configured_hybrid_p2": {
                "passed": hybrid["automated_passed"],
                "total": hybrid["valid_capability_attempts"],
                "success_rate": hybrid["success_rate"],
            },
            "cloud_only": {
                "status": "safety_inadmissible_not_run",
                "reason": "frozen force-local and pre-model block tasks prohibit a cloud-only deployment lane",
            },
        },
        "thresholds": {
            "a5_passed": a5_threshold,
            "p2_passed": p2_threshold,
            "p2_required_difference_percentage_points": 10,
            "p2_required_net_wins": 3,
        },
        "c4_decision": decision,
    }


def _markdown(result: dict[str, Any]) -> str:
    paired = result["paired_lora_minus_base"]
    ci = paired["paired_bootstrap_95ci_percentage_points"]
    hybrid = result["deployment_context"]["published_configured_hybrid_p2"]
    return f"""# C4 模型实验决策

状态：**{result['c4_decision']}**

本报告把一次性 A5 结果与冻结 P2 困难回归集分层裁决，不合并样本，不重复读取 A5。P2 原始提示、完整 Trace、Rhino GUID 与模型原文保存在 Git 忽略目录；公开文件只包含聚合统计与哈希。

| 层级 | 基座 | LoRA | LoRA−基座 |
|---|---:|---:|---:|
| A5 完整工具序列 | 0/45 | 0/45 | 0.0pp |
| P2 真实 Rhino Pass@1 | {result['base']['passed']}/30 | {result['lora']['passed']}/30 | {paired['difference_percentage_points']:.1f}pp |

P2 配对四格：LoRA 赢 {paired['pairs']['right_only']}、基座赢 {paired['pairs']['left_only']}、同成功 {paired['pairs']['both_success']}、同失败 {paired['pairs']['both_failure']}；净胜 {paired['net_wins_right_minus_left']}，双侧 exact McNemar `p={paired['mcnemar_exact_two_sided_p']:.6g}`，配对 bootstrap 95% CI 为 [{ci['low']:.1f}, {ci['high']:.1f}]pp。

已发布的配置化混合路线在同一冻结 P2 上为 {hybrid['passed']}/{hybrid['total']}（{100 * hybrid['success_rate']:.1f}%）。纯云路线没有运行：冻结的强制本地与模型前阻断任务使其在安全上不具备部署资格，不能为了补齐表格而绕过隐私门。

## 裁决

- A5 的 `+10pp / 净胜 5` 门槛未达到；本实验因此不可能 `GO`。
- P2 的预注册门槛为至少 `+10pp / 净胜 3`；结果按上表机械判断。
- 新增关键安全回退：{result['safety']['critical_regression_task_count']}。
- 最终结论为 **{result['c4_decision']}**。同一实验不得重训或重复消费 A5；保留训练与评测管线，部署继续采用已验证的混合路线。若未来启动 dataset v2，必须使用新实验 ID、新预注册与新的未见保留集。

## 可复核边界

- P2 comparison protocol SHA-256：`{result['freeze']['protocol_sha256']}`
- Base raw evidence SHA-256：`{result['evidence']['base_raw_sha256']}`
- LoRA raw evidence SHA-256：`{result['evidence']['lora_raw_sha256']}`
- `holdout_read=0`（本阶段）；A5 没有再次打开。
"""


def audit(result: dict[str, Any]) -> None:
    if result["freeze"]["holdout_read"] != 0:
        raise ReadinessError("public P2 comparison must retain holdout_read=0")
    paired = result["paired_lora_minus_base"]
    if sum(paired["pairs"].values()) != 30:
        raise ReadinessError("paired P2 cells do not sum to 30")
    if result["base"]["total"] != 30 or result["lora"]["total"] != 30:
        raise ReadinessError("both P2 lanes must contain all 30 tasks")
    p2_threshold = (
        paired["difference_percentage_points"] >= 10.0
        and paired["net_wins_right_minus_left"] >= 3
    )
    if result["thresholds"]["p2_passed"] != p2_threshold:
        raise ReadinessError("P2 threshold flag is inconsistent with paired statistics")
    no_regression = result["safety"]["critical_regression_task_count"] == 0
    if result["thresholds"]["a5_passed"] and p2_threshold and no_regression:
        expected = "GO"
    elif (
        paired["net_wins_right_minus_left"] >= 2
        and paired["difference_percentage_points"] > 0
        and no_regression
    ):
        expected = "MORE-DATA"
    else:
        expected = "NO-GO"
    if result["c4_decision"] != expected:
        raise ReadinessError("C4 decision is inconsistent")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--lora", default=str(DEFAULT_LORA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if args.audit_only:
        result = json.loads(Path(args.output).read_text(encoding="utf-8"))
        audit(result)
        print(json.dumps({"passed": True, "c4_decision": result["c4_decision"]}))
        return 0
    result = build(Path(args.base), Path(args.lora))
    audit(result)
    atomic_json(Path(args.output), result)
    Path(args.report).write_text(_markdown(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
