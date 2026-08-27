"""RhinoCoder 可重复端到端评测器。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=False)

import httpx

from agent.runtime import AgentRunResult, RunStatus
from eval.scene_assert import verify

RHINO_BASE_URL = os.environ.get("RHINOCODER_RHINO_URL", "http://127.0.0.1:8080")
TASKS_DIR = _HERE.parent / "tasks"
DEFAULT_RESULTS_DIR = _HERE.parent / "results"
DEFAULT_REPORT_DIR = _HERE.parent / "reports" / "generated"
FAILURE_CATEGORIES = {
    "planning_error",
    "tool_selection_error",
    "argument_error",
    "spatial_error",
    "perception_error",
    "recovery_error",
    "infra_error",
}


def load_tasks(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_no} JSON 解析失败: {exc}") from exc
        if "instruction" not in task or "asserts" not in task:
            raise ValueError(f"{path.name}:{line_no} 缺少 instruction 或 asserts 字段")
        task.setdefault("id", f"{path.stem}-{line_no}")
        task.setdefault("tags", [])
        task.setdefault("difficulty", 0)
        if not isinstance(task["asserts"], list) or not task["asserts"]:
            raise ValueError(f"{path.name}:{line_no} asserts 必须是非空列表")
        tasks.append(task)
    return tasks


def collect_task_files(path_arg: str | None) -> list[Path]:
    if path_arg:
        path = Path(path_arg)
        return [path] if path.is_file() else sorted(path.glob("*.jsonl"))
    return sorted(TASKS_DIR.glob("*.jsonl"))


def load_all_tasks(task_files: list[Path]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in task_files:
        for task in load_tasks(path):
            if task["id"] in seen:
                raise ValueError(f"重复任务 ID: {task['id']}")
            seen.add(task["id"])
            tasks.append(task)
    return tasks


def _eval_headers() -> dict[str, str]:
    token = os.environ.get("RHINOCODER_EVAL_TOKEN", "").strip()
    if not token or token.startswith("<"):
        raise RuntimeError("reset_environment 需要配置 RHINOCODER_EVAL_TOKEN")
    return {"X-RhinoCoder-Eval-Token": token}


async def _post(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, Any],
    *,
    evaluation_only: bool = False,
) -> dict[str, Any]:
    response = await client.post(
        f"{RHINO_BASE_URL}{endpoint}",
        json=payload,
        headers=_eval_headers() if evaluation_only else None,
        timeout=httpx.Timeout(connect=3.0, read=30.0, write=5.0, pool=5.0),
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") == "error":
        code = (data.get("error") or {}).get("code", "rhino.application_error")
        raise RuntimeError(f"{code}: {data.get('message', 'Rhino 执行失败')}")
    return data


async def reset_environment(client: httpx.AsyncClient) -> None:
    await _post(client, "/reset_environment", {}, evaluation_only=True)


async def get_scene_summary(client: httpx.AsyncClient) -> dict[str, Any]:
    return await _post(client, "/get_scene_summary", {})


def classify_failure(
    run_result: AgentRunResult | None,
    verification: dict[str, Any] | None,
    exception: BaseException | None = None,
) -> str | None:
    if exception is not None:
        return "infra_error"
    if run_result is not None and run_result.status is not RunStatus.COMPLETED:
        code = run_result.error.code if run_result.error else ""
        if code.startswith(("llm.", "mcp.", "setup.", "config.")):
            return "infra_error"
        if code == "agent.max_rounds":
            return "recovery_error"
        return "planning_error"
    failed_tools = [tool for tool in (run_result.tool_calls if run_result else []) if not tool.success]
    if failed_tools:
        text = " ".join(tool.output.lower() for tool in failed_tools)
        if any(word in text for word in ("参数", "invalid", "missing", "guid")):
            return "argument_error"
        return "tool_selection_error"
    if verification and not verification.get("passed"):
        reasons = " ".join(verification.get("failed_reasons", [])).lower()
        if run_result and run_result.scene_checks:
            if any(word in reasons for word in ("中心", "距离", "对齐", "紧贴", "尺寸", "size")):
                return "spatial_error"
            return "recovery_error"
        return "perception_error"
    return None


async def eval_one(
    task: dict[str, Any],
    *,
    closed_loop: bool,
    repeat_index: int,
) -> dict[str, Any]:
    from agent.llm import run_agent

    started = time.monotonic()
    timings: dict[str, float] = {}
    run_result: AgentRunResult | None = None
    summary: dict[str, Any] = {"objects": [], "total": 0, "capped": False}
    verification: dict[str, Any] = {
        "score": 0.0,
        "passed": False,
        "partial": False,
        "results": [],
        "failed_reasons": [],
    }
    caught: BaseException | None = None

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            phase = time.monotonic()
            await reset_environment(client)
            timings["reset_ms"] = round((time.monotonic() - phase) * 1000, 2)

            phase = time.monotonic()
            run_result = await run_agent(task["instruction"], closed_loop=closed_loop)
            timings["agent_ms"] = round((time.monotonic() - phase) * 1000, 2)

            phase = time.monotonic()
            summary = await get_scene_summary(client)
            timings["scene_read_ms"] = round((time.monotonic() - phase) * 1000, 2)
            verification = verify(summary, task["asserts"])
    except BaseException as exc:  # 每题都必须进入报告，包含基础设施失败
        caught = exc
        verification["failed_reasons"] = [f"{type(exc).__name__}: {exc}"]

    passed = bool(
        caught is None
        and run_result is not None
        and run_result.status is RunStatus.COMPLETED
        and verification.get("passed")
    )
    partial = bool(not passed and verification.get("score", 0) > 0)
    failure_category = classify_failure(run_result, verification, caught)

    correction_count = 0
    if run_result is not None:
        correction_count = sum(1 for event in run_result.events if event.type == "correction.started")

    return {
        "id": task["id"],
        "instruction": task["instruction"],
        "tags": task["tags"],
        "difficulty": task["difficulty"],
        "mode": "closed_loop" if closed_loop else "baseline",
        "repeat": repeat_index,
        "passed": passed,
        "partial": partial,
        "score": verification.get("score", 0.0),
        "assertions": verification.get("results", []),
        "failed_reasons": verification.get("failed_reasons", []),
        "failure_category": failure_category,
        "scene_summary": summary,
        "scene_check_count": len(run_result.scene_checks) if run_result else 0,
        "correction_count": correction_count,
        "timings": {
            **timings,
            "total_ms": round((time.monotonic() - started) * 1000, 2),
        },
        "run": run_result.to_dict() if run_result else None,
    }


def _mode_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = len(results)
    passed = sum(1 for result in results if result["passed"])
    partial = sum(1 for result in results if result["partial"])
    task_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        task_runs[result["id"]].append(result)
    stable = sum(1 for runs in task_runs.values() if runs and all(item["passed"] for item in runs))
    durations = [float(result["timings"]["total_ms"]) for result in results]
    costs = [float(((result.get("run") or {}).get("metrics") or {}).get("estimated_cost_usd", 0)) for result in results]
    scores = [float(result["score"]) for result in results]
    return {
        "attempts": attempts,
        "passed": passed,
        "partial": partial,
        "pass_rate": round(passed / attempts, 4) if attempts else 0.0,
        "partial_rate": round(partial / attempts, 4) if attempts else 0.0,
        "average_score": round(statistics.mean(scores), 4) if scores else 0.0,
        "score_stddev": round(statistics.pstdev(scores), 4) if len(scores) > 1 else 0.0,
        "average_duration_ms": round(statistics.mean(durations), 2) if durations else 0.0,
        "average_cost_usd": round(statistics.mean(costs), 8) if costs else 0.0,
        "stable_tasks": stable,
        "unique_tasks": len(task_runs),
        "failure_categories": dict(Counter(r["failure_category"] for r in results if r["failure_category"])),
    }


def _tool_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for result in results:
        seen_in_attempt: set[str] = set()
        tool_calls = ((result.get("run") or {}).get("tool_calls") or [])
        for call in tool_calls:
            name = str(call.get("name", "unknown"))
            row = grouped.setdefault(
                name,
                {"calls": 0, "successful_calls": 0, "failed_calls": 0, "durations": [], "attempts": 0},
            )
            row["calls"] += 1
            if call.get("success"):
                row["successful_calls"] += 1
            else:
                row["failed_calls"] += 1
            row["durations"].append(float(call.get("duration_ms", 0) or 0))
            if name not in seen_in_attempt:
                row["attempts"] += 1
                seen_in_attempt.add(name)

    summary: dict[str, dict[str, Any]] = {}
    for name, row in sorted(grouped.items()):
        calls = row["calls"]
        summary[name] = {
            "calls": calls,
            "successful_calls": row["successful_calls"],
            "failed_calls": row["failed_calls"],
            "success_rate": round(row["successful_calls"] / calls, 4) if calls else 0.0,
            "average_duration_ms": round(statistics.mean(row["durations"]), 2) if calls else 0.0,
            "attempts": row["attempts"],
        }
    return summary


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    modes = sorted({result["mode"] for result in results})
    by_mode = {
        mode: _mode_summary([result for result in results if result["mode"] == mode])
        for mode in modes
    }
    by_tag: dict[str, dict[str, Any]] = {}
    tags = sorted({tag for result in results for tag in result["tags"]})
    for tag in tags:
        by_tag[tag] = {
            mode: _mode_summary(
                [result for result in results if tag in result["tags"] and result["mode"] == mode]
            )
            for mode in modes
        }
    by_difficulty = {
        str(difficulty): {
            mode: _mode_summary(
                [
                    result
                    for result in results
                    if result["difficulty"] == difficulty and result["mode"] == mode
                ]
            )
            for mode in modes
        }
        for difficulty in sorted({result["difficulty"] for result in results})
    }
    comparison = None
    if "baseline" in by_mode and "closed_loop" in by_mode:
        baseline = by_mode["baseline"]
        closed = by_mode["closed_loop"]
        comparison = {
            "pass_rate_delta": round(closed["pass_rate"] - baseline["pass_rate"], 4),
            "duration_ms_delta": round(closed["average_duration_ms"] - baseline["average_duration_ms"], 2),
            "cost_usd_delta": round(closed["average_cost_usd"] - baseline["average_cost_usd"], 8),
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "modes": by_mode,
        "by_tag": by_tag,
        "by_difficulty": by_difficulty,
        "by_tool": _tool_summary(results),
        "comparison": comparison,
    }


def render_markdown(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = ["# RhinoCoder Benchmark Report", "", f"Generated: {summary['generated_at']}", ""]
    lines.extend([
        "## Modes",
        "",
        "| Mode | Pass@1 | Partial | Avg score | Stable tasks | Avg latency | Avg cost |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for mode, data in summary["modes"].items():
        lines.append(
            f"| {mode} | {data['pass_rate']:.1%} | {data['partial_rate']:.1%} | "
            f"{data['average_score']:.3f} | {data['stable_tasks']}/{data['unique_tasks']} | "
            f"{data['average_duration_ms']:.0f} ms | ${data['average_cost_usd']:.6f} |"
        )
    if summary["comparison"]:
        comparison = summary["comparison"]
        lines.extend([
            "",
            "## Closed-loop delta",
            "",
            f"- Pass@1: {comparison['pass_rate_delta']:+.1%}",
            f"- Average latency: {comparison['duration_ms_delta']:+.0f} ms",
            f"- Average cost: ${comparison['cost_usd_delta']:+.6f}",
        ])

    lines.extend([
        "",
        "## By tag",
        "",
        "| Tag | Mode | Pass@1 | Avg score |",
        "|---|---|---:|---:|",
    ])
    for tag, mode_data in summary["by_tag"].items():
        for mode, data in mode_data.items():
            lines.append(f"| {tag} | {mode} | {data['pass_rate']:.1%} | {data['average_score']:.3f} |")

    lines.extend([
        "",
        "## By difficulty",
        "",
        "| Difficulty | Mode | Pass@1 | Avg score |",
        "|---|---|---:|---:|",
    ])
    for difficulty, mode_data in summary["by_difficulty"].items():
        for mode, data in mode_data.items():
            lines.append(
                f"| L{difficulty} | {mode} | {data['pass_rate']:.1%} | {data['average_score']:.3f} |"
            )

    lines.extend([
        "",
        "## By tool",
        "",
        "| Tool | Calls | Success | Failures | Success rate | Avg latency | Attempts |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for name, data in summary["by_tool"].items():
        lines.append(
            f"| {name} | {data['calls']} | {data['successful_calls']} | "
            f"{data['failed_calls']} | {data['success_rate']:.1%} | "
            f"{data['average_duration_ms']:.0f} ms | {data['attempts']} |"
        )

    lines.extend([
        "",
        "## Failure categories",
        "",
        "| Mode | Category | Count |",
        "|---|---|---:|",
    ])
    for mode, data in summary["modes"].items():
        for category, count in sorted(data["failure_categories"].items()):
            lines.append(f"| {mode} | {category} | {count} |")

    lines.extend(["", "## Failures", "", "| Mode | Task | Repeat | Category | Reasons |", "|---|---|---:|---|---|"])
    for result in results:
        if result["passed"]:
            continue
        reasons = "; ".join(result["failed_reasons"]) or "No assertion detail"
        reasons = reasons.replace("|", "\\|").replace("\n", " ")[:300]
        lines.append(
            f"| {result['mode']} | {result['id']} | {result['repeat']} | "
            f"{result['failure_category'] or 'unknown'} | {reasons} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    results_dir: Path,
    report_dir: Path,
) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"benchmark_{stamp}.json"
    report_path = report_dir / f"benchmark_{stamp}.md"
    json_path.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(render_markdown(summary, results), encoding="utf-8")
    return json_path, report_path


async def run_benchmark(
    tasks: list[dict[str, Any]],
    *,
    modes: list[str],
    repeats: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total = len(tasks) * len(modes) * repeats
    current = 0
    for mode in modes:
        closed_loop = mode == "closed_loop"
        for repeat in range(1, repeats + 1):
            for task in tasks:
                current += 1
                print(f"[{current}/{total}] {mode} r{repeat} {task['id']}: {task['instruction'][:42]}…")
                results.append(
                    await eval_one(task, closed_loop=closed_loop, repeat_index=repeat)
                )
    return results


async def _amain(args: argparse.Namespace, tasks: list[dict[str, Any]]) -> int:
    modes = ["baseline", "closed_loop"] if args.mode == "both" else [args.mode]
    results = await run_benchmark(tasks, modes=modes, repeats=args.runs)
    summary = build_summary(results)
    json_path, report_path = write_outputs(
        results,
        summary,
        Path(args.output_dir),
        Path(args.report_dir),
    )
    print(render_markdown(summary, results))
    print(f"JSON: {json_path}")
    print(f"Report: {report_path}")

    if "closed_loop" in summary["modes"]:
        return 0 if summary["modes"]["closed_loop"]["pass_rate"] >= args.min_pass_rate else 3
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="RhinoCoder 端到端基准评测器")
    parser.add_argument("path", nargs="?", default=None, help="任务文件或目录；默认 eval/tasks")
    parser.add_argument("--dry-run", action="store_true", help="只校验任务格式")
    parser.add_argument("--mode", choices=("baseline", "closed_loop", "both"), default="both")
    parser.add_argument("--runs", type=int, default=3, help="每个模式重复次数；默认 3")
    parser.add_argument("--min-pass-rate", type=float, default=0.70)
    parser.add_argument("--output-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = parser.parse_args()

    task_files = collect_task_files(args.path)
    if not task_files:
        raise SystemExit("未找到任务文件")
    tasks = load_all_tasks(task_files)
    if args.runs < 1:
        raise SystemExit("--runs 必须大于等于 1")

    if args.dry_run:
        for path in task_files:
            print(f"  ✓ {path} ({len(load_tasks(path))} 条)")
        print(f"\n格式校验通过，共 {len(tasks)} 条任务。")
        raise SystemExit(0)

    raise SystemExit(asyncio.run(_amain(args, tasks)))


if __name__ == "__main__":
    main()
