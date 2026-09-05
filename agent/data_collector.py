"""带程序化准入门槛、断点续采和人工复核的真实黄金轨迹采集器。"""

from __future__ import annotations

import asyncio
import argparse
import json
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
from agent.privacy import install_privacy_log_filter, sanitize_for_log
from agent.collection_campaign import (
    DEFAULT_CAMPAIGN_MANIFEST,
    CampaignDefinition,
    ai_reviewed_task_ids,
    batch_id_for_task,
    campaign_golden_task_ids,
    campaign_summary,
    load_campaign,
    promote_review_batch,
    review_batch_summary,
    task_metadata,
)
from agent.runtime import utc_now
from agent.trace_store import (
    GOLDEN_FILE,
    build_trace_record,
    save_ai_reviewed_candidate,
    save_golden,
    save_feedback,
    save_rejected_trace,
    save_trace,
    validate_golden_candidate,
)
from eval.scene_assert import verify

logger = logging.getLogger("rhinocoder.data_collector")
RHINO_BASE_URL = os.environ.get("RHINOCODER_RHINO_URL", "http://127.0.0.1:8080")
_W = 12


def _echo(phase: str, message: str, err: bool = False) -> None:
    typer.echo(f"[{phase:<{_W}}] {sanitize_for_log(message)}", err=err)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    install_privacy_log_filter()
    for noisy in ("mcp", "httpx", "httpcore", "anyio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


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


async def _capture_viewport(*, batch_id: str, task_id: str) -> str:
    """请求 Rhino 主线程导出当前任务的真实视口证据。"""
    relative_path = f"data/review_batches/{batch_id}/{task_id}.png"
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            f"{RHINO_BASE_URL}/capture_viewport",
            json={"relative_path": relative_path},
            headers=_eval_headers(),
            timeout=httpx.Timeout(connect=3.0, read=20.0, write=5.0, pool=5.0),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            raise RuntimeError(payload.get("message", "视口截图失败"))
    evidence = str(payload.get("visual_evidence") or "")
    if not evidence:
        raise RuntimeError("视口截图响应未返回证据路径")
    return evidence


def _print_status(campaign: CampaignDefinition, *, as_json: bool = False) -> None:
    summary = campaign_summary(campaign)
    if as_json:
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Campaign: {summary['title']} ({summary['campaign_id']})")
    typer.echo(
        f"任务={summary['target']}，唯一指令={summary['unique_instructions']}，"
        f"标签={summary['unique_tags']}，尝试={summary['attempts']}，黄金={summary['golden']}，"
        f"AI候选={summary['ai_reviewed_candidates']}，待采={summary['remaining_to_collect']}，"
        f"剩余黄金={summary['remaining']}"
    )
    typer.echo(f"难度分布: {summary['difficulty_distribution']}")
    typer.echo(f"最新分流: {summary['latest_dispositions']}")
    typer.echo(
        "累计 token={total_tokens}，成本区间=${lo:.6f}–${hi:.6f}".format(
            total_tokens=summary["total_tokens"],
            lo=summary["estimated_cost_lower_bound_usd"],
            hi=summary["estimated_cost_upper_bound_usd"],
        )
    )


async def _preflight(*, allow_nonempty_reset: bool) -> None:
    summary = await _scene_summary()
    total = int(summary.get("total", len(summary.get("objects") or [])))
    if total and not allow_nonempty_reset:
        raise RuntimeError(
            f"当前 Rhino 文档含 {total} 个对象。请先打开一个新的空白 .3dm 文档；"
            "采集器不会默认清空非空场景。只有确认当前文档可丢弃时才能使用 --allow-nonempty-reset。"
        )
    _eval_headers()
    _echo("PREFLIGHT", f"Listener、评测令牌和场景检查通过（当前对象数={total}）")


async def _collect_loop(
    campaign: CampaignDefinition,
    *,
    limit: int,
    task_id: str | None,
    allow_reset: bool,
    allow_nonempty_reset: bool,
    review_mode: str,
    batch_size: int,
    auto_run: bool,
    auto_review: bool,
) -> None:
    if not allow_reset:
        raise RuntimeError("真实采集会在每条任务前清空当前 Rhino 文档；请在空白专用文档中使用 --allow-reset")
    await _preflight(allow_nonempty_reset=allow_nonempty_reset)

    completed = campaign_golden_task_ids(campaign)
    staged = ai_reviewed_task_ids(campaign.campaign_id)
    pending = [
        task
        for task in campaign.tasks
        if task["id"] not in completed and task["id"] not in staged
    ]
    if task_id:
        pending = [task for task in pending if task["id"] == task_id]
        if not pending:
            raise RuntimeError(f"任务不存在、已经进入黄金集或正在等待批量确认: {task_id}")
    if limit > 0:
        pending = pending[:limit]

    _echo("COLLECTOR", f"黄金数据集路径: {GOLDEN_FILE}")
    _echo(
        "COLLECTOR",
        f"campaign={campaign.campaign_id}，目标={campaign.target}，已入库={len(completed)}，本次最多={len(pending)}",
    )
    if not pending:
        _echo("COMPLETE", "没有待采集任务")
        return

    for index, task in enumerate(pending, 1):
        typer.echo("\n" + "─" * 70)
        _echo(
            "TASK",
            f"{index}/{len(pending)} {task['id']} | 难度 L{task['difficulty']} | {', '.join(task['tags'])}",
        )
        typer.echo(sanitize_for_log(task["instruction"]))
        action = "run" if auto_run else input(
            "输入 RUN 清空当前采集场景并执行；s 跳过；q 退出: "
        ).strip().lower()
        if action == "q":
            return
        if action == "s":
            continue
        if action != "run":
            _echo("SKIP", "未输入 RUN，本任务未执行")
            continue

        try:
            await _reset_rhino_environment()
            _echo("RESET", "场景和撤销记录已清空")
        except Exception as exc:
            _echo("RESET", f"无法进入安全采集状态: {exc}", err=True)
            return

        raw = task["instruction"]
        run = await run_agent(raw, closed_loop=True)
        try:
            summary = await _scene_summary()
            evaluation = verify(summary, task["asserts"])
        except Exception as exc:
            evaluation = {
                "passed": False,
                "partial": False,
                "score": 0.0,
                "failed_reasons": [f"scene_evaluation_failed: {exc}"],
                "results": [],
            }

        record = build_trace_record(
            raw,
            run,
            evaluation=evaluation,
            task=task_metadata(campaign, task),
        )
        trace_path = save_trace(record)
        _echo("TRACE", f"已保存脱敏运行轨迹: {trace_path.name}")
        _echo(
            "VERIFY",
            f"程序化得分={evaluation.get('score', 0):.2f}，场景自检={len(run.scene_checks)} 次",
        )
        for result in evaluation.get("results") or []:
            marker = "✓" if result.get("ok") else "✗"
            _echo("ASSERT", f"{marker} {result.get('reason') or result.get('spec', {}).get('kind')}")

        if review_mode == "batch":
            batch_id = batch_id_for_task(campaign, task, batch_size=batch_size)
            if auto_review:
                try:
                    evidence = await _capture_viewport(batch_id=batch_id, task_id=str(task["id"]))
                    record = save_ai_reviewed_candidate(
                        record,
                        batch_id=batch_id,
                        note=(
                            "自动初审通过：程序断言全部通过，"
                            f"场景自检 {len(run.scene_checks)} 次，已导出 Rhino 视口证据。"
                        ),
                        visual_evidence=evidence,
                    )
                    save_trace(record)
                    save_feedback(record["feedback"] | {
                        "run_id": run.run_id,
                        "instruction": raw,
                        "task": task_metadata(campaign, task),
                    })
                    _echo("AI CANDIDATE", f"自动初审通过，已进入 {batch_id}")
                    continue
                except Exception as exc:
                    _echo("AUTO REVIEW", f"未自动进入候选，保留 Trace 待人工处理: {exc}", err=True)
                    continue
            verdict = input(
                "AI 审核员请检查程序断言、Tool Trace、Scene Summary 和 Rhino 视口。"
                "输入 a=审核通过候选 / u=存疑 / n=错误 / q=退出: "
            ).strip().lower()
            if verdict == "q":
                _echo("UNREVIEWED", f"已保留脱敏 Trace {trace_path.name}，未写入候选或训练数据集")
                return
            while verdict not in {"a", "u", "n"}:
                verdict = input("请输入 a、u 或 n: ").strip().lower()
            if verdict == "a":
                evidence = input("Rhino 视口截图证据路径: ").strip()
                note = input("AI 审核摘要（最多 1000 字）: ").strip()[:1000]
                record = save_ai_reviewed_candidate(
                    record,
                    batch_id=batch_id,
                    note=note,
                    visual_evidence=evidence,
                )
                save_trace(record)
                save_feedback(record["feedback"] | {
                    "run_id": run.run_id,
                    "instruction": raw,
                    "task": task_metadata(campaign, task),
                })
                _echo("AI CANDIDATE", f"已进入 {batch_id}，等待人类一次性批量确认")
                batch = review_batch_summary(campaign, batch_id, batch_size=batch_size)
                _echo(
                    "BATCH",
                    f"{batch_id}: 黄金={batch['golden']}，AI候选={batch['ai_reviewed_candidates']}，"
                    f"缺少={batch['missing']}，ready={batch['ready_for_human_review']}",
                )
                continue

            label = "partial" if verdict == "u" else "rejected"
            note = input("AI 审核备注（最多 1000 字）: ").strip()[:1000]
            record["feedback"] = {
                "label": label,
                "source": "ai_visual_review",
                "timestamp": utc_now(),
                "note": note,
            }
            save_trace(record)
            save_feedback(record["feedback"] | {
                "run_id": run.run_id,
                "instruction": raw,
                "task": task_metadata(campaign, task),
            })
            gate = validate_golden_candidate(record, human_confirmed=False)
            disposition, target = save_rejected_trace(record, gate)
            _echo(
                "REVIEW FLAG",
                f"AI 审核未通过，分流={disposition}，文件={target.name}，需单独人工检查",
            )
            continue

        verdict = input(
            "请在 Rhino 中人工检查。输入 y=完全正确 / p=部分正确 / n=错误 / q=退出且本条不入库: "
        ).strip().lower()
        if verdict == "q":
            _echo("UNREVIEWED", f"已保留脱敏 Trace {trace_path.name}，未写入训练数据集")
            return
        while verdict not in {"y", "p", "n"}:
            verdict = input("请输入 y、p 或 n: ").strip().lower()
        note = input("人工备注（可留空，最多 1000 字）: ").strip()[:1000]

        label = {"y": "accepted", "p": "partial", "n": "rejected"}[verdict]
        record["feedback"] = {
            "label": label,
            "source": "human_review",
            "timestamp": utc_now(),
            "note": note,
        }
        # 将人工反馈与同一 run_id 的脱敏 Trace 绑定，并覆盖反馈前的临时版本。
        save_trace(record)
        save_feedback(
            {
                "run_id": run.run_id,
                "instruction": raw,
                "label": label,
                "source": "human_review",
                "note": note,
                "task": task_metadata(campaign, task),
                "timestamp": record["feedback"]["timestamp"],
            }
        )
        gate = validate_golden_candidate(record, human_confirmed=verdict == "y")
        if gate.accepted:
            save_golden(gate)
            _echo("GOLDEN", "✅ 通过全部准入门槛，已加入黄金数据集")
        else:
            disposition, target = save_rejected_trace(record, gate)
            _echo(
                "REJECTED",
                f"未进入黄金集，分流={disposition}，文件={target.name}，原因: {', '.join(gate.reasons)}",
            )

    typer.echo("")
    _print_status(campaign)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_CAMPAIGN_MANIFEST)
    parser.add_argument("--limit", type=int, default=1, help="本次最多执行的任务数；0 表示全部待办")
    parser.add_argument("--task-id", help="只执行指定任务 ID")
    parser.add_argument(
        "--review-mode",
        choices=("immediate", "batch"),
        default="immediate",
        help="immediate=逐条人工确认；batch=AI 审核后每批统一人工确认",
    )
    parser.add_argument("--batch-size", type=int, default=5, help="批量人工确认的任务数")
    parser.add_argument("--batch-status", help="显示指定审核批次状态，不连接 Rhino")
    parser.add_argument("--approve-batch", help="在一次人类确认后晋级指定完整批次")
    parser.add_argument("--human-note", default="", help="批量确认备注")
    parser.add_argument("--status", action="store_true", help="只显示本地 campaign 进度")
    parser.add_argument("--json", action="store_true", help="状态以 JSON 输出")
    parser.add_argument("--dry-run", action="store_true", help="只校验任务清单，不连接 Rhino 或模型")
    parser.add_argument("--auto-run", action="store_true", help="跳过每条任务前的 RUN 输入；仍需 --allow-reset")
    parser.add_argument("--auto-review", action="store_true", help="自动导出 Rhino 视口并写入 AI 审核候选；仅 batch 模式可用")
    parser.add_argument("--allow-reset", action="store_true", help="确认在每条任务前清空专用 Rhino 文档")
    parser.add_argument(
        "--allow-nonempty-reset",
        action="store_true",
        help="危险：允许清空启动时非空的 Rhino 文档，仅用于确认可丢弃的专用文档",
    )
    args = parser.parse_args()
    _setup_logging()
    campaign = load_campaign(args.manifest)
    if args.batch_size < 1:
        raise SystemExit("--batch-size 必须大于 0")
    if args.auto_review and args.review_mode != "batch":
        raise SystemExit("--auto-review 仅支持 --review-mode batch")
    if args.batch_status:
        typer.echo(json.dumps(
            review_batch_summary(campaign, args.batch_status, batch_size=args.batch_size),
            ensure_ascii=False,
            indent=2,
        ))
        return
    if args.approve_batch:
        batch = review_batch_summary(campaign, args.approve_batch, batch_size=args.batch_size)
        typer.echo(json.dumps(batch, ensure_ascii=False, indent=2))
        if not batch["ready_for_human_review"]:
            raise SystemExit(f"批次尚未收齐，缺少 {batch['missing']} 条")
        confirmation = input(
            f"确认已由人类检查以上 {batch['batch_size']} 条汇总证据；输入 APPROVE 批量晋级: "
        ).strip()
        if confirmation != "APPROVE":
            raise SystemExit("未确认，批次保持 AI 审核候选状态")
        written = promote_review_batch(
            campaign,
            args.approve_batch,
            human_note=args.human_note,
            batch_size=args.batch_size,
        )
        _echo("GOLDEN BATCH", f"已原子晋级 {written} 条新黄金轨迹")
        _print_status(campaign)
        return
    if args.status:
        _print_status(campaign, as_json=args.json)
        return
    if args.dry_run:
        _print_status(campaign, as_json=args.json)
        typer.echo("Campaign manifest validation passed.")
        return
    typer.echo("=" * 58)
    typer.echo("  RhinoCoder Trace Collector")
    typer.echo(f"  {campaign.title}")
    typer.echo("  黄金准入：断言通过 + 场景自检 + 人工确认 + 脱敏 + 任务去重")
    typer.echo("=" * 58)
    try:
        asyncio.run(
            _collect_loop(
                campaign,
                limit=args.limit,
                task_id=args.task_id,
                allow_reset=args.allow_reset,
                allow_nonempty_reset=args.allow_nonempty_reset,
                review_mode=args.review_mode,
                batch_size=args.batch_size,
                auto_run=args.auto_run,
                auto_review=args.auto_review,
            )
        )
    except (KeyboardInterrupt, RuntimeError) as exc:
        _echo("STOP", str(exc), err=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
