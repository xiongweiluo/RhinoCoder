"""带程序化准入门槛的 Human-in-the-loop 轨迹采集器。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=False)

import httpx
import typer

from agent.llm import run_agent
from agent.trace_store import (
    GOLDEN_FILE,
    build_trace_record,
    save_candidate,
    save_golden,
    save_trace,
    validate_golden_candidate,
)
from eval.run_eval import collect_task_files, load_all_tasks
from eval.scene_assert import verify

logger = logging.getLogger("rhinocoder.data_collector")
RHINO_BASE_URL = os.environ.get("RHINOCODER_RHINO_URL", "http://127.0.0.1:8080")
_W = 12


def _echo(phase: str, message: str, err: bool = False) -> None:
    typer.echo(f"[{phase:<{_W}}] {message}", err=err)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    for noisy in ("mcp", "httpx", "httpcore", "anyio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _task_index() -> dict[str, dict]:
    tasks = load_all_tasks(collect_task_files(None))
    return {task["instruction"].strip(): task for task in tasks}


def _eval_headers() -> dict[str, str]:
    token = os.environ.get("RHINOCODER_EVAL_TOKEN", "").strip()
    if not token or token.startswith("<"):
        raise RuntimeError("请在 Agent 与 Rhino 进程中配置相同的 RHINOCODER_EVAL_TOKEN")
    return {"X-RhinoCoder-Eval-Token": token}


async def _reset_rhino_environment() -> None:
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            f"{RHINO_BASE_URL}/reset_environment",
            json={},
            headers=_eval_headers(),
            timeout=httpx.Timeout(connect=3.0, read=20.0, write=5.0, pool=5.0),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            raise RuntimeError(payload.get("message", "环境重置失败"))


async def _scene_summary() -> dict:
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            f"{RHINO_BASE_URL}/get_scene_summary",
            json={},
            timeout=httpx.Timeout(connect=3.0, read=20.0, write=5.0, pool=5.0),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            raise RuntimeError(payload.get("message", "场景读取失败"))
        return payload


async def _collect_loop() -> None:
    tasks = _task_index()
    _echo("COLLECTOR", f"黄金数据集路径: {GOLDEN_FILE}")
    _echo("COLLECTOR", f"已加载 {len(tasks)} 条可程序化验收任务")

    while True:
        try:
            await _reset_rhino_environment()
            _echo("RESET", "场景和撤销记录已清空")
        except Exception as exc:
            _echo("RESET", f"无法进入安全采集状态: {exc}", err=True)
            return

        raw = input("\n🏗️  请输入建模任务（q 退出）: ").strip()
        if raw.lower() == "q":
            return
        if not raw:
            continue

        task = tasks.get(raw)
        if task is None:
            _echo("NOTICE", "该指令不在评测任务集中，只能进入候选集，不能进入黄金集。")

        run = await run_agent(raw, closed_loop=True)
        try:
            summary = await _scene_summary()
            evaluation = verify(summary, task["asserts"]) if task else {
                "passed": False,
                "partial": False,
                "score": 0.0,
                "failed_reasons": ["instruction_not_in_benchmark"],
                "results": [],
            }
        except Exception as exc:
            evaluation = {
                "passed": False,
                "partial": False,
                "score": 0.0,
                "failed_reasons": [f"scene_evaluation_failed: {exc}"],
                "results": [],
            }

        record = build_trace_record(raw, run, evaluation=evaluation)
        trace_path = save_trace(record)
        _echo("TRACE", f"已保存脱敏运行轨迹: {trace_path.name}")
        _echo(
            "VERIFY",
            f"程序化得分={evaluation.get('score', 0):.2f}，场景自检={len(run.scene_checks)} 次",
        )

        verdict = input("👀  人工确认结果是否完全正确？(y 正确 / n 错误 / q 退出): ").strip().lower()
        if verdict == "q":
            return

        gate = validate_golden_candidate(record, human_confirmed=verdict == "y")
        if gate.accepted:
            save_golden(gate)
            _echo("GOLDEN", "✅ 通过全部准入门槛，已加入黄金数据集")
        else:
            record["gate_reasons"] = gate.reasons
            record["human_confirmed"] = verdict == "y"
            save_candidate(record)
            _echo("CANDIDATE", f"未进入黄金集，原因: {', '.join(gate.reasons)}")


def main() -> None:
    _setup_logging()
    typer.echo("=" * 58)
    typer.echo("  RhinoCoder Trace Collector")
    typer.echo("  黄金准入：断言通过 + 场景自检 + 人工确认 + 脱敏")
    typer.echo("=" * 58)
    asyncio.run(_collect_loop())


if __name__ == "__main__":
    main()
