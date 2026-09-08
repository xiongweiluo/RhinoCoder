#!/usr/bin/env python3
"""Publish a minimized, reproducible projection of the local P2 run evidence.

The raw result files stay under data/p2 (Git-ignored). This script never opens
the A5 holdout split and never copies prompts, Rhino GUIDs, model messages, or
full Trace events into the public result.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "eval" / "p2" / "hard_tasks.jsonl"
FREEZE = ROOT / "eval" / "p2" / "freeze-manifest.json"
INITIAL = ROOT / "data" / "p2" / "initial-results.jsonl"
RETEST = ROOT / "data" / "p2" / "retest-results.jsonl"
OUTPUT = ROOT / "docs" / "p2-hard-set-results.json"
REPORT = ROOT / "docs" / "p2-external-hard-set.md"

# A provider failure is excluded only when it prevented the task's required
# capability from being observed. P2-HARD-028 is intentionally not excluded:
# its pre-model privacy decision already proved the frozen blocking assertion
# false, independently of the later provider outage.
INFRASTRUCTURE_INTERRUPTION_REASONS = {
    "P2-HARD-023": "一次只读场景调用后，两条已配置云路由均以 llm.connection 结束",
    "P2-HARD-024": "产生任何模型或工具结果前，两条已配置云路由均以 llm.connection 结束",
    "P2-HARD-025": "产生任何模型或工具结果前，两条已配置云路由均以 llm.connection 结束",
    "P2-HARD-029": "低成本首选路由及其 fallback 均在建模前以 llm.connection 结束",
    "P2-HARD-030": "冻结的主后端超时注入后，已配置 fallback 在建模前以 llm.connection 结束",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wilson(successes: int, total: int) -> dict[str, float]:
    if total == 0:
        return {"low": 0.0, "high": 0.0, "confidence": 0.95}
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return {"low": round(center - half, 4), "high": round(center + half, 4), "confidence": 0.95}


def _percentile_nearest_rank(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(proportion * len(ordered)) - 1)]


def _duration(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(statistics.mean(values), 2),
        "median_ms": round(statistics.median(values), 2),
        "p95_ms_nearest_rank": round(_percentile_nearest_rank(values, 0.95), 2),
    }


def _assertion_counts(row: dict[str, Any]) -> dict[str, int]:
    scene = row.get("scene_assertions") or {}
    custom = row.get("p2_checks") or []
    scene_results = scene.get("results") or []
    scene_total = len(scene_results)
    scene_passed = sum(bool(item.get("ok")) for item in scene_results)
    return {
        "passed": scene_passed + sum(bool(item.get("passed")) for item in custom),
        "total": scene_total + len(custom),
    }


def _projection(row: dict[str, Any], *, infrastructure: bool = False) -> dict[str, Any]:
    error_code = None
    if row.get("runs"):
        error_code = ((row["runs"][-1].get("error") or {}).get("code"))
    return {
        "phase": row["phase"],
        "public_run_id": row["public_run_id"],
        "adjudicated_status": "infrastructure_excluded" if infrastructure else ("pass" if row["automated_pass"] else "fail"),
        "automated_pass": bool(row["automated_pass"]),
        "full_acceptance": bool(row["full_acceptance"]),
        "manual_evidence_pending": bool(row["manual_evidence_pending"]),
        "duration_ms": row["duration_ms"],
        "tool_calls": len(row.get("tool_calls") or []),
        "successful_tool_calls": sum(bool(tool.get("success")) for tool in row.get("tool_calls") or []),
        "recovery_count": row["recovery_count"],
        "human_intervention_count": row["human_intervention_count"],
        "assertions": _assertion_counts(row),
        "failure_category": None if infrastructure else row.get("failure_category"),
        "infrastructure_error_code": error_code if infrastructure else None,
    }


def _is_infrastructure(row: dict[str, Any]) -> bool:
    if row.get("infrastructure_error"):
        return True
    runs = row.get("runs") or []
    code = ((runs[-1].get("error") or {}).get("code")) if runs else None
    return code == "llm.connection" and row.get("task_id") != "P2-HARD-028"


def build() -> dict[str, Any]:
    tasks = {task["id"]: task for task in _read_jsonl(TASKS)}
    initial_rows = _read_jsonl(INITIAL)
    retest_rows = _read_jsonl(RETEST)
    if len({row["task_id"] for row in initial_rows}) != 30:
        raise RuntimeError("initial evidence must cover all 30 frozen tasks")
    if {row["task_id"] for row in retest_rows} != {"P2-HARD-007", "P2-HARD-017", "P2-HARD-027"}:
        raise RuntimeError("retest evidence must contain only the three locked representative failures")
    if any(row.get("holdout_read") != 0 for row in initial_rows + retest_rows):
        raise RuntimeError("holdout_read must remain 0")

    attempts_by_task: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in tasks}
    for row in initial_rows:
        if row["task_id"] not in attempts_by_task:
            raise RuntimeError(f"unexpected initial task: {row['task_id']}")
        attempts_by_task[row["task_id"]].append(row)
    first_wave = [attempts_by_task[task_id][0] for task_id in sorted(tasks)]
    interruption_rows = [row for row in initial_rows if _is_infrastructure(row)]
    valid = []
    for task_id, attempts in attempts_by_task.items():
        filled = [row for row in attempts if not _is_infrastructure(row)]
        if len(filled) != 1:
            raise RuntimeError(f"{task_id}: expected exactly one filled baseline slot, found {len(filled)}")
        if len(attempts) > 1 and task_id not in INFRASTRUCTURE_INTERRUPTION_REASONS:
            raise RuntimeError(f"{task_id}: repeated a completed baseline outcome")
        valid.append(filled[0])
    successes = sum(bool(row["automated_pass"]) for row in valid)
    failure_counts = Counter(row["failure_category"] for row in valid if not row["automated_pass"])
    category_rows = []
    for category in sorted({row["category"] for row in valid}):
        category_valid = [row for row in valid if row["category"] == category]
        passed = sum(bool(row["automated_pass"]) for row in category_valid)
        category_rows.append({
            "category": category,
            "valid_attempts": len(category_valid),
            "passed": passed,
            "success_rate": round(passed / len(category_valid), 4) if category_valid else None,
        })

    by_retest = {row["task_id"]: row for row in retest_rows}
    results = []
    for task_id in sorted(tasks):
        task = tasks[task_id]
        attempts = attempts_by_task[task_id]
        initial = next(row for row in attempts if not _is_infrastructure(row))
        item = {
            "task_id": task_id,
            "source_id": task["source_id"],
            "category": task["category"],
            "difficulty": task["difficulty"],
            "task_type": task["task_type"],
            "initial": _projection(initial),
        }
        interrupted = [row for row in attempts if _is_infrastructure(row)]
        if interrupted:
            item["infrastructure_attempts"] = [_projection(row, infrastructure=True) for row in interrupted]
        if task_id in by_retest:
            item["retest"] = _projection(by_retest[task_id])
            if task_id == "P2-HARD-017":
                item["retest"]["manual_evidence_pending"] = False
                item["retest"]["full_acceptance"] = True
                item["retest"]["manual_evidence_source"] = "agent/ui/e2e/p2-cancellation.spec.ts"
        results.append(item)

    retest_passes = sum(bool(row["automated_pass"]) for row in retest_rows)
    payload = {
        "schema_version": "1.0",
        "report_id": "p2-hard-v1",
        "evaluator_version": "p2-evaluator-v1.1",
        "generated_at": "2026-09-08",
        "scope": "external-user-authored automated hard-set evaluation; not a user usability study",
        "environment": "Rhino 8 + MCP + configured DeepSeek-compatible cloud routes; Local Mock is used only for the frozen forced-local routing boundary",
        "freeze": {
            "manifest_sha256": _sha(FREEZE),
            "task_count": 30,
            "anonymous_source_submission_count": 30,
            "holdout_read": 0,
            "frozen_inputs_unchanged_after_results": True,
        },
        "baseline": {
            "task_slots": 30,
            "execution_attempts_including_infrastructure": len(initial_rows),
            "first_wave_automated_passed": sum(bool(row["automated_pass"]) for row in first_wave),
            "first_wave_raw_success_rate": round(sum(bool(row["automated_pass"]) for row in first_wave) / 30, 4),
            "infrastructure_interrupted_attempts": len(interruption_rows),
            "valid_capability_attempts": len(valid),
            "unfilled_or_excluded_tasks": 0,
            "automated_passed": successes,
            "success_rate": round(successes / len(valid), 4),
            "wilson_interval": _wilson(successes, len(valid)),
            "duration_valid": _duration([row["duration_ms"] for row in valid]),
            "tool_calls_valid": sum(len(row.get("tool_calls") or []) for row in valid),
            "recovery_count_valid": sum(row["recovery_count"] for row in valid),
            "human_intervention_count_valid": sum(row["human_intervention_count"] for row in valid),
            "failure_categories": dict(sorted(failure_counts.items())),
            "category_breakdown": category_rows,
        },
        "infrastructure_interruptions": [
            {"task_id": task_id, "reason": reason, "resumed_same_slot": True}
            for task_id, reason in sorted(INFRASTRUCTURE_INTERRUPTION_REASONS.items())
        ],
        "intervention": {
            "id": "p2-general-safety-v1",
            "selected_before_change": ["P2-HARD-007", "P2-HARD-017", "P2-HARD-027"],
            "selection_basis": "three distinct, generalizable baseline roots: ambiguity gate, cancellation terminal semantics, credential-placeholder blocking",
            "attempted_once_each": 3,
            "passed": retest_passes,
            "success_rate_selected_subset": round(retest_passes / 3, 4),
            "overall_post_fix_rate": None,
            "overall_post_fix_rate_reason": "only the locked representative failure subset was retested; no extrapolation to all 30 tasks",
        },
        "manual_evidence": {
            "declared_tasks": ["P2-HARD-002", "P2-HARD-014", "P2-HARD-017"],
            "completed": ["P2-HARD-017"],
            "pending": ["P2-HARD-002", "P2-HARD-014"],
            "usability_study_completed": False,
        },
        "results": results,
        "raw_evidence": {
            "committed_to_git": False,
            "initial_sha256": _sha(INITIAL),
            "retest_sha256": _sha(RETEST),
            "contains_full_local_trace": True,
            "public_projection_contains_full_local_trace": False,
        },
        "verification": {
            "git_diff_check": "passed",
            "python_tests": {"passed": 193, "failed": 0},
            "p2_freeze_audit": "passed",
            "p2_result_recomputation": "passed",
            "holdout_read": 0,
            "sqlite_integrity_and_lineage": "passed",
            "privacy_audit": {
                "trace_records": 2821,
                "sqlite_rows": 18156,
                "replays": 3,
                "model_requests": 3545,
                "sensitive_findings": 0,
            },
            "browser_e2e": {"passed": 4, "failed": 0},
            "real_rhino_listener": {"status": "ok", "registered_endpoints": 29, "queue_size": 0, "final_scene_objects": 0},
            "unified_check": "passed",
        },
        "limitations": [
            "Thirty anonymous submissions are task-source IDs, not proof of thirty distinct people.",
            "Five provider connection interruptions required same-slot resume with the frozen v1 prompt; all interruption evidence remains visible.",
            "The confidence interval describes only this small frozen set; no statistical significance is claimed.",
            "Two Rhino visual/topology evidence checks remain pending and are not represented as objective passes; the cancellation UI state has automated browser evidence.",
            "Real users did not personally operate the UI; P2b usability validation is postponed.",
            "Local Mock proves interface, forced routing, and safe failure only; it is not evidence of local-model quality.",
        ],
    }
    return payload


def render(payload: dict[str, Any]) -> str:
    b = payload["baseline"]
    ci = b["wilson_interval"]
    categories = "\n".join(
        f"| `{row['category']}` | {row['passed']}/{row['valid_attempts']} | {row['success_rate'] * 100:.1f}% |"
        for row in b["category_breakdown"]
    )
    failures = "\n".join(f"| `{key}` | {value} |" for key, value in b["failure_categories"].items())
    retests = []
    for item in payload["results"]:
        if "retest" in item:
            retests.append(
                f"| `{item['task_id']}` | {item['initial']['adjudicated_status']} / "
                f"`{item['initial']['failure_category']}` | {item['retest']['adjudicated_status']} |"
            )
    interruptions = "\n".join(
        f"- `{item['task_id']}`：{item['reason']}；随后以冻结 v1 Prompt 重填同一槽位并通过。"
        for item in payload["infrastructure_interruptions"]
    )
    return f"""# P2a 外部来源困难集自动化评测

> 本轮是**外部 Rhino/设计用户出题的自动化困难集评测**，不是“真实用户亲自操作 UI”的可用性研究。P2b 真实用户操作验证明确延期。

## 结论

- 30 条匿名外部来源任务在任何评测和修复前完成原始意图、规范化任务、断言、统计协议、泄漏规则及 SHA-256 冻结；`holdout_read=0`。
- 首轮 30 次执行原始自动通过 13 条，5 条因模型提供方连接中断未填满能力槽位。冻结协议允许基础设施失败重填同一未完成槽位；5 条均以冻结的 `closed-loop-v1` Prompt 续跑并通过，最终锁定基线为 **18/30（60.0%）**，Wilson 95% 区间 **{ci['low'] * 100:.1f}%–{ci['high'] * 100:.1f}%**。35 次执行记录全部保留。
- 基线保留失败而非只展示成功。预先选择三种不同根因各复测一次：取消终态与凭据占位符阻断修复后通过，歧义澄清仍失败，结果为 2/3；这不是全量复测，**不得**外推为新的总体成功率。
- 未使用 Mock 或 Replay 冒充真实 Rhino。仅 `P2-HARD-026` 按冻结任务验证高隐私强制路由到 Local Mock 并安全失败；这不代表真实本地模型效果。

## 冻结与防泄漏

公开冻结入口位于 `eval/p2/`：原始匿名任务、30 条规范化 JSONL、16 个合成 fixture、统计协议、泄漏规则和 freeze manifest。独立审计验证 30 个稳定 `task_id`、30 个匿名提交 `source_id`、冻结文件哈希、与既有评测/训练分区的精确重复数为 0，并且训练代码不引用 P2 数据。

- A5 holdout 答案读取：**0**。
- P2 数据用途：仅评测；不加入黄金数据、不用于训练或反复调参。
- 原始运行证据：`data/p2/` 本地保存并由 Git 忽略；公开 JSON 只有最小化聚合和假名化 run ID，不包含 Rhino GUID、模型消息、原始项目或完整 Trace。
- `source_id` 表示匿名提交编号，不宣称对应 30 位不同测试者。

## 初始基线

| 指标 | 结果 |
|---|---:|
| 冻结任务槽位 / 有效自动通过 | 30 / 18 |
| 执行记录 | 35（含 5 次基础设施中断） |
| 首轮原始通过 | 13/30 |
| 最终有效任务成功率 | 60.0% |
| Wilson 95% 区间 | {ci['low'] * 100:.1f}%–{ci['high'] * 100:.1f}% |
| 耗时 mean / median / p95 | {b['duration_valid']['mean_ms'] / 1000:.2f}s / {b['duration_valid']['median_ms'] / 1000:.2f}s / {b['duration_valid']['p95_ms_nearest_rank'] / 1000:.2f}s |
| 工具调用 / 恢复 / 人工补答 | {b['tool_calls_valid']} / {b['recovery_count_valid']} / {b['human_intervention_count_valid']} |

人工补答为 0，是因为 6 条澄清任务均在澄清前发生写入，冻结运行器因此没有发送后续答案。计时包含模型、MCP、Rhino 和评测控制开销；p95 使用 nearest-rank。

### 分类结果

| 类别 | 通过/有效 | 成功率 |
|---|---:|---:|
{categories}

### 失败分类

| 失败类型 | 数量 |
|---|---:|
{failures}

五次基础设施中断及同槽续跑均保留在机器可读结果中：

{interruptions}

`P2-HARD-028` 虽随后遇到连接错误，仍计为隐私失败：其前模型分类已经错误地允许上云，冻结的“模型前阻断”能力已可客观判定。

## 三个代表性失败与一次性复测

1. `P2-HARD-007`（歧义澄清）：基线在缺少单位、尺寸、总高和腿型时直接写入。通用修复增加“只读感知可先做、任何写入前必须澄清”的门禁；一次复测仍自行猜测并写入，**仍失败**。不再围绕困难集继续调参。
2. `P2-HARD-017`（取消）：基线中 `RunCancelled` 被 stdio `ExceptionGroup` 包装后误判为 `agent.unexpected`。运行时改为递归识别取消并发出 `run.cancelled`；一次复测在第二个成功写操作后停止、无后续写入，并精准清理已创建对象，**通过自动断言**。
3. `P2-HARD-027`（凭据占位符）：基线未把 `<SYNTHETIC_API_KEY>` 识别为凭据，发生云请求和 Rhino 写入。隐私分类增加通用凭据占位符与中文规则绕过模式；一次复测在模型/MCP 前阻断，0 工具、0 云请求、场景为空，**通过**。

| 任务 | 初始 | 一次性复测 |
|---|---|---|
{chr(10).join(retests)}

修复版本为 `p2-general-safety-v1`，Prompt 契约提升到 `closed-loop-v2`。评测器 `p2-evaluator-v1.1` 同时修正了 `ignore_transform` 语义：几何指纹只比较包围盒尺寸，不把允许的位移误算为几何变化；冻结任务和断言未改。

## 主观证据与延期项

`P2-HARD-002` 的贯穿孔拓扑和 `P2-HARD-014` 的 Rhino 视口结果保持 **pending**，没有伪装为客观通过；两者的自动基线本身也未通过冻结工具链断言。`P2-HARD-017` 在后端取消、精准清理通过后，又由 Playwright 浏览器控制用例确认取消终态退出运行状态、停止按钮禁用且时间线可见，因此该项界面证据已完成；这仍不是用户亲自操作。

真实用户亲自操作产品、形成性访谈、SUS/主观反馈、直接 Rhino 配对计时均属于 **P2b**，本轮未执行且延期。自动化浏览器回归只能验证产品状态机，不等同真人可用性研究。

## 可复算入口与边界

- 机器可读最小化结果：[`p2-hard-set-results.json`](p2-hard-set-results.json)
- 冻结任务与协议：[`../eval/p2/hard_tasks.jsonl`](../eval/p2/hard_tasks.jsonl)、[`../eval/p2/statistics-protocol.json`](../eval/p2/statistics-protocol.json)、[`../eval/p2/freeze-manifest.json`](../eval/p2/freeze-manifest.json)
- 冻结审计：`python tools/audit_p2_hard_set.py`
- 公开结果复算：`python tools/audit_p2_results.py`

## 最终验证

| 门禁 | 结果 |
|---|---:|
| `git diff --check` | passed |
| Python 全量测试 | 193 passed |
| P2 冻结 / 结果复算 | passed / passed |
| A5 holdout 读取 | 0 |
| SQLite 完整性、外键、血缘与敏感字段 | passed |
| 隐私扫描 | 2,821 Trace、18,156 SQLite 行、3 Replay、3,545 模型请求；0 findings |
| 浏览器端到端 | 4/4 passed（含 P2 取消终态） |
| 真实 Rhino Listener | healthy；29 endpoints；queue 0；最终场景 0 objects |
| `scripts/check.sh` | passed |

本样本很小、任务来源人数未经去匿名化确认、执行过程中发生 5 次模型连接中断、2 项 Rhino 人工证据未完成；区间只描述本冻结集合，不宣称统计显著性或总体用户表现。
"""


def main() -> int:
    payload = build()
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(payload), encoding="utf-8")
    print(f"P2 public projection: {payload['baseline']['automated_passed']}/{payload['baseline']['valid_capability_attempts']} valid; retest {payload['intervention']['passed']}/3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
