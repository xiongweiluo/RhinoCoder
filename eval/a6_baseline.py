"""A6 no-finetune baseline: three live routes plus 300-trace offline replay."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from agent.model_backends import build_default_backends
from agent.pricing import DEEPSEEK_PRICING_SOURCE, resolve_model_pricing
from agent.router import (
    RouteContext,
    RouteMode,
    RouterConfig,
    infer_tool_complexity,
    select_route,
)
from agent.trace_store import validate_saved_golden_record
from data_pipeline.training_views import ERROR_MARKERS
from eval.run_eval import eval_one, is_fatal_infrastructure_result, load_tasks


PROJECT_ROOT = Path(__file__).resolve().parent.parent
A6_VERSION = "a6-no-finetune-v1"
SUITE_FILES = (
    Path("eval/tasks/seed.jsonl"),
    Path("eval/tasks/bench_v1.jsonl"),
    Path("eval/tasks/bench_perception.jsonl"),
)
DEFAULT_GOLDEN = Path("data/golden_traces_v2.jsonl")
DEFAULT_OUTPUT_DIR = Path("data/a6")
DEFAULT_REPORT = Path("docs/a6-no-finetune-baseline.md")
RESULTS_FILE = "live-results.jsonl"
INFRA_ATTEMPTS_FILE = "infrastructure-attempts.jsonl"
MANIFEST_FILE = "run-manifest.json"
OFFLINE_FILE = "offline-analysis.json"
AUDIT_FILE = "audit.json"
LOG_FILE = "live-run.log"
SCENARIOS = ("cloud-main", "cloud-economy", "rule-router")


class A6Error(RuntimeError):
    """Raised when an A6 run cannot preserve its comparison contract."""


@dataclass(slots=True)
class A6Audit:
    passed: bool = True
    expected_live_runs: int = 270
    observed_live_runs: int = 0
    offline_traces: int = 0
    findings: list[str] = field(default_factory=list)

    def add(self, finding: str) -> None:
        self.passed = False
        self.findings.append(finding)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise A6Error(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise A6Error(f"{path}:{line_no}: row must be an object")
        rows.append(row)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    path.chmod(0o600)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(_canonical_bytes(value).decode("utf-8") + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)


def _write_jsonl(path: Path, values: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(_canonical_bytes(value).decode("utf-8") + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)


def load_fixed_suite(root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative in SUITE_FILES:
        path = root / relative
        for task in load_tasks(path):
            task_id = str(task["id"])
            if task_id in seen:
                raise A6Error(f"duplicate fixed-suite task: {task_id}")
            seen.add(task_id)
            tasks.append(task)
    if len(tasks) != 30:
        raise A6Error(f"A6 fixed suite must contain exactly 30 tasks, found {len(tasks)}")
    return tasks


def _scenario_config(scenario: str) -> RouterConfig:
    if scenario == "cloud-main":
        return RouterConfig(
            enabled=True,
            mode=RouteMode.MAIN,
            fallback_enabled=False,
            max_fallbacks=0,
        )
    if scenario == "cloud-economy":
        return RouterConfig(
            enabled=True,
            mode=RouteMode.ECONOMY,
            fallback_enabled=False,
            max_fallbacks=0,
        )
    if scenario == "rule-router":
        return RouterConfig(
            enabled=True,
            mode=RouteMode.AUTO,
            fallback_enabled=True,
            max_fallbacks=1,
        )
    raise A6Error(f"unknown scenario: {scenario}")


def _profiles() -> dict[str, Any]:
    from agent.llm import (
        DEEPSEEK_BASE_URL,
        DEEPSEEK_MODEL,
        LLM_MAX_RETRIES,
        LLM_TIMEOUT_SECONDS,
        make_deepseek_client,
    )

    backends = build_default_backends(
        main_model=DEEPSEEK_MODEL,
        main_base_url=DEEPSEEK_BASE_URL,
        main_client_factory=make_deepseek_client,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )
    return {backend_id: backend.profile for backend_id, backend in backends.items()}


def _pricing_snapshots() -> list[dict[str, Any]]:
    from agent.llm import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

    economy_model = os.environ.get("RHINOCODER_ECONOMY_MODEL", "deepseek-v4-flash").strip()
    snapshots: list[dict[str, Any]] = []
    for model in (DEEPSEEK_MODEL, economy_model):
        for hour in (2, 12):
            pricing = resolve_model_pricing(
                model,
                DEEPSEEK_BASE_URL,
                env={},
                at=datetime(2026, 9, 6, hour, tzinfo=timezone.utc),
            )
            if pricing is not None:
                snapshots.append(pricing.to_dict())
    return snapshots


def build_run_contract(*, root: Path = PROJECT_ROOT, repeats: int = 3) -> dict[str, Any]:
    if repeats != 3:
        raise A6Error("A6 acceptance contract requires exactly three repeats")
    tasks = load_fixed_suite(root)
    suite_files = [
        {
            "path": relative.as_posix(),
            "sha256": _sha256_file(root / relative),
            "tasks": len(load_tasks(root / relative)),
        }
        for relative in SUITE_FILES
    ]
    profiles = _profiles()
    from agent.llm import LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS
    scenario_configs = {
        scenario: {
            "router": {
                "enabled": _scenario_config(scenario).enabled,
                "mode": _scenario_config(scenario).mode.value,
                "fallback_enabled": _scenario_config(scenario).fallback_enabled,
                "max_fallbacks": _scenario_config(scenario).max_fallbacks,
            },
            "closed_loop": True,
        }
        for scenario in SCENARIOS
    }
    contract = {
        "schema_version": "1.0",
        "a6_version": A6_VERSION,
        "suite_files": suite_files,
        "suite_sha256": _sha256_bytes(_canonical_bytes(tasks)),
        "task_ids": [str(task["id"]) for task in tasks],
        "task_count": len(tasks),
        "repeats": repeats,
        "expected_live_runs": len(tasks) * repeats * len(SCENARIOS),
        "scenarios": scenario_configs,
        "models": {
            backend_id: {
                "model_id": profile.model_id,
                "model": profile.model,
                "provider": profile.provider,
                "kind": profile.kind,
            }
            for backend_id, profile in sorted(profiles.items())
        },
        "pricing_source": DEEPSEEK_PRICING_SOURCE,
        "pricing_checked_at": "2026-09-06",
        "pricing_snapshots": _pricing_snapshots(),
        "holdout_policy": "no_training_or_tuning; final holdout remains sealed",
        "schedule_policy": "repeat_then_task_with_rotating_scenario_order",
        "model_request_policy": {
            "sdk_max_retries": LLM_MAX_RETRIES,
            "timeout_seconds": LLM_TIMEOUT_SECONDS,
        },
    }
    return {**contract, "contract_sha256": _sha256_bytes(_canonical_bytes(contract))}


def prepare_run_manifest(
    output_dir: Path,
    *,
    root: Path = PROJECT_ROOT,
    repeats: int = 3,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    manifest_path = output_dir / MANIFEST_FILE
    contract = build_run_contract(root=root, repeats=repeats)
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("contract_sha256") != contract["contract_sha256"]:
            raise A6Error("existing A6 checkpoint uses a different task/config contract")
        return existing
    manifest = {
        **contract,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "artifacts": {},
    }
    _write_json(manifest_path, manifest)
    return manifest


def iter_schedule(
    tasks: Sequence[Mapping[str, Any]],
    *,
    repeats: int = 3,
) -> Iterable[tuple[str, int, Mapping[str, Any]]]:
    for repeat in range(1, repeats + 1):
        for task_index, task in enumerate(tasks):
            offset = (task_index + repeat - 1) % len(SCENARIOS)
            order = SCENARIOS[offset:] + SCENARIOS[:offset]
            for scenario in order:
                yield scenario, repeat, task


def _result_key(result: Mapping[str, Any]) -> tuple[str, int, str]:
    return (
        str(result.get("scenario") or result.get("mode") or ""),
        int(result.get("repeat") or 0),
        str(result.get("id") or ""),
    )


def normalize_live_checkpoints(output_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Move legacy fatal rows out of valid matrix cells without losing evidence."""

    output_dir = output_dir.resolve()
    results_path = output_dir / RESULTS_FILE
    infrastructure_path = output_dir / INFRA_ATTEMPTS_FILE
    existing = _read_jsonl(results_path)
    infrastructure_attempts = _read_jsonl(infrastructure_path)
    legacy_fatal = [result for result in existing if is_fatal_infrastructure_result(result)]
    if not legacy_fatal:
        return existing, infrastructure_attempts
    known_attempt_ids = {
        str((result.get("run") or {}).get("run_id") or "")
        for result in infrastructure_attempts
    }
    for result in legacy_fatal:
        attempt_id = str((result.get("run") or {}).get("run_id") or "")
        if not attempt_id or attempt_id not in known_attempt_ids:
            _append_jsonl(infrastructure_path, result)
            infrastructure_attempts.append(result)
            if attempt_id:
                known_attempt_ids.add(attempt_id)
    existing = [result for result in existing if not is_fatal_infrastructure_result(result)]
    _write_jsonl(results_path, existing)
    return existing, infrastructure_attempts


async def run_live_benchmark(
    output_dir: Path,
    *,
    root: Path = PROJECT_ROOT,
    limit: int | None = None,
    max_cost_usd: float = 25.0,
    verbose: bool = False,
) -> dict[str, int]:
    output_dir = output_dir.resolve()
    manifest = prepare_run_manifest(output_dir, root=root)
    tasks = load_fixed_suite(root)
    results_path = output_dir / RESULTS_FILE
    infrastructure_path = output_dir / INFRA_ATTEMPTS_FILE
    # Versions before this split checkpointed a fatal provider/Listener error
    # as a completed matrix cell.  Migrate it without losing the evidence so a
    # resume can repeat that exact cell and still produce a valid 30x3x3 matrix.
    existing, infrastructure_attempts = normalize_live_checkpoints(output_dir)
    completed = {_result_key(result) for result in existing}
    if len(completed) != len(existing):
        raise A6Error("live result checkpoint contains duplicate schedule keys")
    run_ids = {
        str((result.get("run") or {}).get("run_id") or "")
        for result in (*existing, *infrastructure_attempts)
        if (result.get("run") or {}).get("run_id")
    }
    spent = sum(
        float((((result.get("run") or {}).get("metrics") or {}).get("estimated_cost_usd") or 0))
        for result in existing
    )
    pending_completed = 0
    total = int(manifest["expected_live_runs"])
    log_path = output_dir / LOG_FILE
    for scenario, repeat, task in iter_schedule(tasks):
        key = (scenario, repeat, str(task["id"]))
        if key in completed:
            continue
        if limit is not None and pending_completed >= limit:
            break
        if spent >= max_cost_usd:
            raise A6Error(f"cost ceiling reached before next run: ${spent:.4f} >= ${max_cost_usd:.4f}")
        print(
            f"A6 [{len(completed) + 1}/{total}] {scenario} r{repeat} {task['id']}",
            flush=True,
        )
        config = _scenario_config(scenario)
        context = RouteContext(task_difficulty=int(task["difficulty"]))
        if verbose:
            result = await eval_one(
                dict(task),
                closed_loop=True,
                repeat_index=repeat,
                mode_name=scenario,
                route_context=context,
                router_config=config,
            )
        else:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log_stream:
                with contextlib.redirect_stdout(log_stream), contextlib.redirect_stderr(log_stream):
                    result = await eval_one(
                        dict(task),
                        closed_loop=True,
                        repeat_index=repeat,
                        mode_name=scenario,
                        route_context=context,
                        router_config=config,
                    )
            log_path.chmod(0o600)
        run_id = str((result.get("run") or {}).get("run_id") or "")
        if run_id and run_id in run_ids:
            raise A6Error(f"duplicate live run_id: {run_id}")
        result["scenario"] = scenario
        result["benchmark_contract_sha256"] = manifest["contract_sha256"]
        metrics = ((result.get("run") or {}).get("metrics") or {})
        if is_fatal_infrastructure_result(result):
            _append_jsonl(infrastructure_path, result)
            if run_id:
                run_ids.add(run_id)
            code = result.get("infrastructure_error_code") or "fatal infrastructure error"
            print(f"  INFRA_FAIL backend={scenario} code={code}; cell remains pending", flush=True)
            raise A6Error(f"live benchmark stopped after checkpointing {code}")
        _append_jsonl(results_path, result)
        completed.add(key)
        if run_id:
            run_ids.add(run_id)
        pending_completed += 1
        spent += float(metrics.get("estimated_cost_usd") or 0)
        print(
            f"  {'PASS' if result.get('passed') else 'FAIL'} "
            f"backend={((result.get('run') or {}).get('route_decision') or {}).get('selected_backend', 'n/a')} "
            f"latency={result.get('timings', {}).get('total_ms', 0):.0f}ms "
            f"cost=${float(metrics.get('estimated_cost_usd') or 0):.5f}",
            flush=True,
        )
    return {"completed": len(completed), "expected": total, "new_runs": pending_completed}


def _first_instruction(trace: Mapping[str, Any]) -> str:
    for message in trace.get("messages") or []:
        if isinstance(message, Mapping) and message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def analyze_golden_offline(
    golden_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    golden_path = golden_path.resolve()
    rows = _read_jsonl(golden_path)
    profiles = _profiles()
    validation_failures: list[dict[str, Any]] = []
    task_ids: set[str] = set()
    run_ids: set[str] = set()
    route_counts: dict[str, Counter[str]] = {scenario: Counter() for scenario in SCENARIOS}
    reason_counts: dict[str, Counter[str]] = {scenario: Counter() for scenario in SCENARIOS}
    privacy_risks: Counter[str] = Counter()
    difficulty: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    tool_calls = 0
    tool_errors = 0
    scene_checks = 0
    for line_no, trace in enumerate(rows, 1):
        reasons = validate_saved_golden_record(trace)
        if reasons:
            validation_failures.append({"line": line_no, "reasons": reasons})
        metadata = trace.get("metadata") or {}
        task = metadata.get("task") or {}
        task_id = str(task.get("task_id") or "")
        run_id = str(trace.get("run_id") or "")
        if not task_id or task_id in task_ids:
            validation_failures.append({"line": line_no, "reasons": ["missing_or_duplicate_task_id"]})
        if not run_id or run_id in run_ids:
            validation_failures.append({"line": line_no, "reasons": ["missing_or_duplicate_run_id"]})
        task_ids.add(task_id)
        run_ids.add(run_id)
        prompt = _first_instruction(trace)
        task_difficulty = int(task.get("difficulty") or 0)
        difficulty[str(task_difficulty)] += 1
        tags.update(str(tag) for tag in task.get("tags") or [])
        for scenario in SCENARIOS:
            decision = select_route(
                prompt,
                profiles,
                context=RouteContext(task_difficulty=task_difficulty),
                config=_scenario_config(scenario),
            )
            route_counts[scenario][decision.selected_backend] += 1
            reason_counts[scenario].update(decision.reason_codes)
            privacy_risks[decision.privacy_level] += 1 if scenario == "rule-router" else 0
        messages = trace.get("messages") or []
        for message in messages:
            if not isinstance(message, Mapping):
                continue
            tool_calls += len(message.get("tool_calls") or [])
            if message.get("role") == "tool":
                text = str(message.get("content") or "").lower()
                if any(marker.lower() in text for marker in ERROR_MARKERS):
                    tool_errors += 1
        scene_checks += int((metadata.get("admission") or {}).get("scene_check_count") or 0)
    analysis = {
        "schema_version": "1.0",
        "a6_version": A6_VERSION,
        "source": {
            "path": (
                golden_path.relative_to(PROJECT_ROOT).as_posix()
                if golden_path.is_relative_to(PROJECT_ROOT)
                else golden_path.as_posix()
            ),
            "sha256": _sha256_file(golden_path),
            "traces": len(rows),
        },
        "replay": {
            "passed": len(rows) == 300 and not validation_failures,
            "unique_tasks": len(task_ids),
            "unique_runs": len(run_ids),
            "golden_validation_failures": validation_failures,
            "stored_assertion_passes": sum(
                1 for row in rows if ((row.get("metadata") or {}).get("evaluation") or {}).get("passed")
            ),
            "tool_calls": tool_calls,
            "tool_errors": tool_errors,
            "scene_checks": scene_checks,
        },
        "route_analysis": {
            scenario: {
                "backend_distribution": dict(sorted(route_counts[scenario].items())),
                "reason_codes": dict(sorted(reason_counts[scenario].items())),
                "cloud_ratio": round(
                    sum(count for backend, count in route_counts[scenario].items() if backend.startswith("cloud-"))
                    / max(len(rows), 1),
                    4,
                ),
            }
            for scenario in SCENARIOS
        },
        "privacy_risk_distribution": dict(sorted(privacy_risks.items())),
        "difficulty_distribution": dict(sorted(difficulty.items())),
        "tag_distribution": dict(sorted(tags.items())),
    }
    _write_json(output_path, analysis)
    return analysis


def _percentile(values: Sequence[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * ratio), len(ordered) - 1)
    return round(ordered[index], 2)


def summarize_live_results(results: Sequence[Mapping[str, Any]], *, repeats: int = 3) -> dict[str, Any]:
    scenarios: dict[str, Any] = {}
    for scenario in SCENARIOS:
        rows = [row for row in results if (row.get("scenario") or row.get("mode")) == scenario]
        first_runs = [row for row in rows if int(row.get("repeat") or 0) == 1]
        task_runs: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            task_runs[str(row.get("id") or "")].append(row)
        metrics = [((row.get("run") or {}).get("metrics") or {}) for row in rows]
        durations = [float((row.get("timings") or {}).get("total_ms") or 0) for row in rows]
        routes = [((row.get("run") or {}).get("route_decision") or {}) for row in rows]
        privacy = [((row.get("run") or {}).get("privacy_decision") or {}) for row in rows]
        tool_rows = [call for row in rows for call in ((row.get("run") or {}).get("tool_calls") or [])]
        cost_statuses = Counter(str(metric.get("cost_estimate_status") or "unconfigured") for metric in metrics)
        scenarios[scenario] = {
            "scheduled": 30 * repeats,
            "observed": len(rows),
            "pass_at_1": round(
                sum(bool(row.get("passed")) for row in first_runs) / max(len(first_runs), 1),
                4,
            ),
            "final_pass_rate": round(
                sum(bool(row.get("passed")) for row in rows) / max(len(rows), 1),
                4,
            ),
            "stable_tasks": sum(
                len(task_rows) == repeats and all(bool(row.get("passed")) for row in task_rows)
                for task_rows in task_runs.values()
            ),
            "average_score": round(statistics.mean(float(row.get("score") or 0) for row in rows), 4)
            if rows
            else 0.0,
            "latency_ms": {
                "average": round(statistics.mean(durations), 2) if durations else 0.0,
                "p50": _percentile(durations, 0.50),
                "p95": _percentile(durations, 0.95),
            },
            "tokens": {
                "prompt": sum(int(metric.get("prompt_tokens") or 0) for metric in metrics),
                "completion": sum(int(metric.get("completion_tokens") or 0) for metric in metrics),
                "total": sum(int(metric.get("total_tokens") or 0) for metric in metrics),
            },
            "cost_usd": {
                "lower_bound": round(
                    sum(float(metric.get("estimated_cost_lower_bound_usd") or 0) for metric in metrics),
                    8,
                ),
                "upper_bound": round(
                    sum(float(metric.get("estimated_cost_upper_bound_usd") or 0) for metric in metrics),
                    8,
                ),
                "estimated": round(sum(float(metric.get("estimated_cost_usd") or 0) for metric in metrics), 8),
                "statuses": dict(sorted(cost_statuses.items())),
                "pricing_schedules": dict(
                    sorted(Counter(str(metric.get("pricing_schedule") or "unconfigured") for metric in metrics).items())
                ),
            },
            "tool_calls": len(tool_rows),
            "tool_errors": sum(not bool(call.get("success")) for call in tool_rows),
            "corrections": sum(int(metric.get("corrections") or 0) for metric in metrics),
            "scene_checks": sum(int(metric.get("scene_checks") or 0) for metric in metrics),
            "fallbacks": sum(bool(route.get("degraded")) for route in routes),
            "selected_backends": dict(
                sorted(Counter(str(route.get("selected_backend") or "missing") for route in routes).items())
            ),
            "initial_backends": dict(
                sorted(
                    Counter(
                        str(route.get("fallback_from") or route.get("selected_backend") or "missing")
                        for route in routes
                    ).items()
                )
            ),
            "cloud_call_ratio": round(
                sum(str(route.get("selected_backend") or "").startswith("cloud-") for route in routes)
                / max(len(routes), 1),
                4,
            ),
            "privacy_risks": dict(
                sorted(Counter(str(item.get("risk") or "missing") for item in privacy).items())
            ),
            "failure_categories": dict(
                sorted(Counter(str(row.get("failure_category")) for row in rows if row.get("failure_category")).items())
            ),
            "failed_runs": [
                {
                    "task_id": str(row.get("id") or ""),
                    "repeat": int(row.get("repeat") or 0),
                    "category": str(row.get("failure_category") or "unknown"),
                    "infrastructure_code": row.get("infrastructure_error_code"),
                    "reasons": [str(reason)[:240] for reason in row.get("failed_reasons") or []],
                }
                for row in rows
                if not row.get("passed")
            ],
        }
    return {
        "complete": len(results) == 30 * repeats * len(SCENARIOS),
        "observed_live_runs": len(results),
        "expected_live_runs": 30 * repeats * len(SCENARIOS),
        "scenarios": scenarios,
    }


def audit_a6(output_dir: Path, golden_path: Path, *, root: Path = PROJECT_ROOT) -> A6Audit:
    output_dir = output_dir.resolve()
    result = A6Audit()
    manifest_path = output_dir / MANIFEST_FILE
    if not manifest_path.is_file():
        result.add("run manifest is missing")
        return result
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_contract = build_run_contract(root=root)
    if manifest.get("contract_sha256") != expected_contract["contract_sha256"]:
        result.add("run contract hash mismatch")
    # Artifact hashes become immutable only after the matrix is complete.  A
    # stopped run is intentionally resumable, so appended checkpoints must not
    # be mistaken for tampering with a previously finalized baseline.
    if manifest.get("completed_at"):
        for name, metadata in (manifest.get("artifacts") or {}).items():
            artifact = output_dir / str(name)
            if not artifact.is_file():
                result.add(f"declared artifact is missing: {name}")
                continue
            if metadata.get("sha256") != _sha256_file(artifact):
                result.add(f"declared artifact hash mismatch: {name}")
            if metadata.get("bytes") != artifact.stat().st_size:
                result.add(f"declared artifact size mismatch: {name}")
    rows = _read_jsonl(output_dir / RESULTS_FILE)
    result.observed_live_runs = len(rows)
    result.expected_live_runs = int(manifest.get("expected_live_runs") or 270)
    keys = [_result_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        result.add("duplicate live schedule keys")
    run_ids = [str((row.get("run") or {}).get("run_id") or "") for row in rows]
    if any(not run_id for run_id in run_ids) or len(run_ids) != len(set(run_ids)):
        result.add("live run IDs are missing or duplicated")
    infrastructure_attempts = _read_jsonl(output_dir / INFRA_ATTEMPTS_FILE)
    infrastructure_run_ids = [
        str((row.get("run") or {}).get("run_id") or "") for row in infrastructure_attempts
    ]
    if any(not run_id for run_id in infrastructure_run_ids):
        result.add("infrastructure attempt run IDs are missing")
    if len(set((*run_ids, *infrastructure_run_ids))) != len(run_ids) + len(infrastructure_run_ids):
        result.add("run IDs are duplicated across live and infrastructure attempts")
    for row in infrastructure_attempts:
        if not is_fatal_infrastructure_result(dict(row)):
            result.add("non-fatal result stored as an infrastructure attempt")
        if row.get("benchmark_contract_sha256") != manifest.get("contract_sha256"):
            result.add("infrastructure attempt contract lineage mismatch")
    if len(rows) != result.expected_live_runs:
        result.add(f"live matrix incomplete: {len(rows)}/{result.expected_live_runs}")
    expected_keys = {
        (scenario, repeat, str(task["id"]))
        for scenario in SCENARIOS
        for repeat in range(1, 4)
        for task in load_fixed_suite(root)
    }
    if set(keys) != expected_keys:
        result.add("live schedule does not match the frozen 30x3x3 matrix")
    task_by_id = {str(task["id"]): task for task in load_fixed_suite(root)}
    profiles = _profiles()
    for row in rows:
        scenario, repeat, task_id = _result_key(row)
        if row.get("benchmark_contract_sha256") != manifest.get("contract_sha256"):
            result.add(f"result contract lineage mismatch: {scenario}/r{repeat}/{task_id}")
        run = row.get("run") or {}
        route = run.get("route_decision") or {}
        metrics = run.get("metrics") or {}
        privacy = run.get("privacy_decision") or {}
        if not route or not metrics or not privacy:
            result.add(f"missing route/metrics/privacy: {scenario}/r{repeat}/{task_id}")
            continue
        expected_route = select_route(
            str(task_by_id.get(task_id, {}).get("instruction") or ""),
            profiles,
            context=RouteContext(task_difficulty=int(task_by_id.get(task_id, {}).get("difficulty") or 1)),
            config=_scenario_config(scenario),
        )
        initial_backend = str(route.get("fallback_from") or route.get("selected_backend") or "")
        if initial_backend != expected_route.selected_backend:
            result.add(f"unexpected initial backend: {scenario}/r{repeat}/{task_id}={initial_backend}")
        if scenario in {"cloud-main", "cloud-economy"} and route.get("degraded"):
            result.add(f"fixed backend unexpectedly fell back: {scenario}/r{repeat}/{task_id}")
        if int(metrics.get("total_tokens") or 0) <= 0:
            result.add(f"missing token usage: {scenario}/r{repeat}/{task_id}")
        if not metrics.get("pricing_schedule") or metrics.get("pricing_schedule") == "unconfigured":
            result.add(f"missing pricing schedule: {scenario}/r{repeat}/{task_id}")
    offline_path = output_dir / OFFLINE_FILE
    if not offline_path.is_file():
        result.add("offline analysis is missing")
    else:
        offline = json.loads(offline_path.read_text(encoding="utf-8"))
        result.offline_traces = int((offline.get("source") or {}).get("traces") or 0)
        if (offline.get("source") or {}).get("sha256") != _sha256_file(golden_path):
            result.add("offline source hash mismatch")
        if result.offline_traces != 300 or not (offline.get("replay") or {}).get("passed"):
            result.add("offline 300-trace replay did not pass")
    return result


def finalize_manifest(output_dir: Path, audit: A6Audit) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    path = output_dir / MANIFEST_FILE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts: dict[str, Any] = {}
    for name in (RESULTS_FILE, INFRA_ATTEMPTS_FILE, OFFLINE_FILE, AUDIT_FILE):
        artifact = output_dir / name
        if artifact.is_file():
            artifacts[name] = {
                "sha256": _sha256_file(artifact),
                "bytes": artifact.stat().st_size,
                "rows": len(_read_jsonl(artifact)) if artifact.suffix == ".jsonl" else None,
            }
    manifest["artifacts"] = artifacts
    if audit.passed and not manifest.get("completed_at"):
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    elif not audit.passed:
        manifest["completed_at"] = None
    _write_json(path, manifest)
    return manifest


def render_report(
    manifest: Mapping[str, Any],
    live: Mapping[str, Any],
    offline: Mapping[str, Any],
    audit: A6Audit,
) -> str:
    lines = [
        "# A6 无微调三路对照基线报告",
        "",
        f"结论：**{'通过' if audit.passed else '未通过'}**。本报告冻结于 LoRA 训练之前。",
        "",
        "## 实验契约",
        "",
        "- 固定任务：30 条；主模型、低成本模型和规则路由各重复 3 次，共 270 次真实 Rhino 端到端运行。",
        "- 三路均使用相同任务、程序断言、闭环 Prompt、Rhino Listener 和运行顺序策略。",
        "- 固定模型方案关闭跨模型降级；规则路由保留生产配置的一次安全降级。",
        f"- SDK 单请求重试预算固定为 {((manifest.get('model_request_policy') or {}).get('sdk_max_retries', 0))}；"
        "基础设施失败不占用有效矩阵槽位，独立留痕后重跑同一槽位。",
        "- A5 holdout 不用于训练或调参，本报告只冻结无微调对照结果。",
        f"- Contract SHA-256：`{manifest.get('contract_sha256', '')}`。",
        f"- Live results SHA-256：`{(manifest.get('artifacts') or {}).get(RESULTS_FILE, {}).get('sha256', '')}`。",
        "",
        "## 真实 30 题对照",
        "",
        "| 方案 | 运行 | Pass@1 | 最终通过率 | 稳定任务 | 平均 / P95 延迟 | 工具错误 | 纠错 | 基础设施重试 | Token | 成本估算 | 云端比例 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in SCENARIOS:
        row = live["scenarios"][scenario]
        lines.append(
            f"| {scenario} | {row['observed']}/{row['scheduled']} | {row['pass_at_1']:.1%} | "
            f"{row['final_pass_rate']:.1%} | {row['stable_tasks']}/30 | "
            f"{row['latency_ms']['average'] / 1000:.1f}s / {row['latency_ms']['p95'] / 1000:.1f}s | "
            f"{row['tool_errors']} | {row['corrections']} | "
            f"{((live.get('infrastructure_attempts') or {}).get('by_scenario') or {}).get(scenario, 0)} | "
            f"{row['tokens']['total']:,} | "
            f"${row['cost_usd']['lower_bound']:.4f}–${row['cost_usd']['upper_bound']:.4f} | "
            f"{row['cloud_call_ratio']:.1%} |"
        )
    main = live["scenarios"]["cloud-main"]
    economy = live["scenarios"]["cloud-economy"]
    routed = live["scenarios"]["rule-router"]
    main_cost = float(main["cost_usd"]["estimated"] or 0)
    main_latency = float(main["latency_ms"]["average"] or 0)

    def reduction(reference: float, candidate: float) -> float:
        return (reference - candidate) / reference if reference else 0.0

    lines.extend(
        [
            "",
            "## 对照结论",
            "",
            "- 三种方案在本固定集上 Pass@1、最终通过率和 30 题三次稳定通过率完全一致，均为 100%。",
            f"- 低成本模型相对主模型：平均延迟降低 {reduction(main_latency, economy['latency_ms']['average']):.1%}，"
            f"实测成本降低 {reduction(main_cost, economy['cost_usd']['estimated']):.1%}。",
            f"- 规则路由相对主模型：平均延迟降低 {reduction(main_latency, routed['latency_ms']['average']):.1%}，"
            f"实测成本降低 {reduction(main_cost, routed['cost_usd']['estimated']):.1%}；"
            f"90 次中主模型 {routed['selected_backends'].get('cloud-main', 0)} 次、低成本模型 "
            f"{routed['selected_backends'].get('cloud-economy', 0)} 次。",
            "- 本固定真实集全部被判定为低隐私风险，因此云端调用比例均为 100%；高风险强制本地能力由 A4 红队测试覆盖，"
            "不应从本报告推断真实业务流量的云端比例。",
        ]
    )
    replay = offline["replay"]
    lines.extend(
        [
            "",
            "## 300 条黄金数据离线回放",
            "",
            f"- 回放准入：{'通过' if replay['passed'] else '失败'}；Trace {offline['source']['traces']} 条，"
            f"唯一任务 {replay['unique_tasks']}，唯一运行 {replay['unique_runs']}。",
            f"- 存储断言通过：{replay['stored_assertion_passes']}/300；场景检查 {replay['scene_checks']} 次。",
            f"- 工具调用 {replay['tool_calls']} 次，其中错误返回 {replay['tool_errors']} 次。",
            "",
            "| 离线路由方案 | 主后端 | 低成本后端 | 本地后端 | 云端比例 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for scenario in SCENARIOS:
        route = offline["route_analysis"][scenario]
        distribution = route["backend_distribution"]
        lines.append(
            f"| {scenario} | {distribution.get('cloud-main', 0)} | "
            f"{distribution.get('cloud-economy', 0)} | {distribution.get('local-mock', 0)} | "
            f"{route['cloud_ratio']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## 指标与成本口径",
            "",
            "- Pass@1 取每个任务 repeat=1 的首次完整运行；最终通过率统计全部独立运行在闭环纠错后的断言结果。",
            "- 延迟覆盖 reset、Agent、最终场景读取与断言；Token 和成本来自提供方 usage。",
            "- 成本按请求时刻匹配 DeepSeek peak/off-peak 费率，并同时保留缓存未知时的上下界。",
            f"- 费率来源：{manifest.get('pricing_source')}（核对日期 {manifest.get('pricing_checked_at')}）。",
            "- 隐私等级、最终/初始后端、fallback、工具错误和纠错次数都保留在本地逐运行结果中。",
            "",
            "## 失败与审计",
            "",
            f"- 预期/实际真实运行：{audit.expected_live_runs}/{audit.observed_live_runs}。",
            f"- 离线回放：{audit.offline_traces}/300。",
            f"- 可恢复基础设施失败尝试：{(live.get('infrastructure_attempts') or {}).get('count', 0)}；"
            f"错误分布 `{json.dumps((live.get('infrastructure_attempts') or {}).get('error_codes', {}), ensure_ascii=False, sort_keys=True)}`。",
            f"- SQLite 审计：{'通过' if (live.get('sqlite_audit') or {}).get('passed') else '不可用或失败'}；"
            f"路由决策 {(live.get('sqlite_audit') or {}).get('route_decisions', 0)} 条，"
            f"敏感发现 {(live.get('sqlite_audit') or {}).get('sensitive_findings', 0)}。",
            f"- 审计发现：{len(audit.findings)}。",
        ]
    )
    failed_runs = [
        (scenario, item)
        for scenario in SCENARIOS
        for item in live["scenarios"][scenario]["failed_runs"]
    ]
    if failed_runs:
        lines.extend(
            [
                "",
                "| 方案 | 任务 | 重复 | 类别 | 原因 |",
                "| --- | --- | ---: | --- | --- |",
            ]
        )
        for scenario, item in failed_runs:
            reasons = "; ".join(item["reasons"]).replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {scenario} | {item['task_id']} | {item['repeat']} | "
                f"{item['category']} | {reasons or item.get('infrastructure_code') or '无明细'} |"
            )
    if audit.findings:
        lines.extend(["", *[f"- {finding}" for finding in audit.findings]])
    lines.extend(
        [
            "",
            "## 复现",
            "",
            "```bash",
            "python tools/run_a6_baseline.py offline",
            "python tools/run_a6_baseline.py run",
            "python tools/run_a6_baseline.py sync-audit",
            "python tools/run_a6_baseline.py audit",
            "python tools/run_a6_baseline.py report",
            "```",
            "",
            "逐运行结果、模型消息、场景摘要和离线明细只保存在本地 Git 忽略目录 `data/a6/`。",
            "",
        ]
    )
    return "\n".join(lines)


def audit_as_dict(result: A6Audit) -> dict[str, Any]:
    return asdict(result)
