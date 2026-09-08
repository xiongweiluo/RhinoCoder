#!/usr/bin/env python3
"""Frozen P2 hard-set runner against real Rhino + MCP + configured model.

Raw per-run evidence is written below ``data/p2`` and is ignored by Git.  The
public report generator only consumes a deliberately minimized projection.
This module never imports or opens the A5 holdout split.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

import agent.llm as llm_module
from agent.llm import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    make_deepseek_client,
    run_agent,
)
from agent.model_backends import BackendError, ModelBackend, build_default_backends
from agent.router import RouteContext, RouterConfig
from agent.runtime import AgentRunResult, CancellationToken, RunStatus
from eval.scene_assert import select, verify
from tools.audit_p2_hard_set import MANIFEST_PATH, audit


P2_DIR = ROOT / "eval" / "p2"
TASKS_PATH = P2_DIR / "hard_tasks.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "p2" / "initial-results.jsonl"
RHINO_URL = os.environ.get("RHINOCODER_RHINO_URL", "http://127.0.0.1:8080")
MODEL_AUDIT = ROOT / "data" / "audit" / "model_requests.jsonl"
WRITE_TOOLS = {
    "create_sphere", "create_box", "create_cylinder", "create_line", "create_circle",
    "extrude_curve_straight", "boolean_difference", "move_object", "rotate_object",
    "scale_object", "align_objects", "distribute_objects", "group_objects", "place_on_at",
    "set_object_color", "set_object_layer", "set_object_name", "delete_objects",
}
CREATE_TOOLS = {
    "create_sphere", "create_box", "create_cylinder", "create_line", "create_circle",
    "extrude_curve_straight", "boolean_difference",
}


def _frozen_v1_system_prompt(closed_loop: bool) -> str:
    """Exact prompt contract used when the initial baseline was frozen."""
    base = (
        "你是 RhinoCoder，一个专业、严谨的 Rhino 3D 建模 AI 助手。"
        "你通过调用工具直接在 Rhino 8 中创建并编辑几何体。\n\n"
        "【坐标系与单位约定】\n"
        "- Rhino 使用右手坐标系，Z 轴朝上（Z-up）。高度和叠放沿 +Z。\n"
        "- 世界原点为 (0,0,0)；未指定位置时新建几何体默认落在原点附近。\n"
        "- 颜色使用 0-255 RGB 三元组。尺寸和间距均为模型单位。\n"
        "- 群组操作使用 group_objects；修改既有要求时以最新要求为准。\n"
        "- get_scene_summary 的 type 是 Rhino 几何类别而不是语义形状名。\n\n"
        "【脱敏占位符约定】\n"
        "- <LAYER_REDACTED> 和 <GROUP_REDACTED> 代表本机保留的精确名称。\n"
        "- 工具参数和最终总结中必须原样使用占位符，不得自造或猜测替代名。"
    )
    if not closed_loop:
        return base + "\n请规划并执行用户任务，完成后给出清晰总结。"
    return base + (
        "\n\n【强制闭环：计算 - 执行 - 感知 - 纠错】\n"
        "1. 动手前规划尺寸、位置、颜色和空间关系。\n"
        "2. 调用工具执行。\n"
        "3. 完成后必须调用 get_scene_summary，核对数量、size、color、center、群组和空间关系。\n"
        "4. 发现偏差后使用 move_object、scale_object、set_object_color、delete_objects 或 undo_last_action 修正。\n"
        "5. 修正后再次调用 get_scene_summary；验证通过后才能输出最终总结。"
    )


async def _invoke_agent(prompt: str, *, phase: str, **kwargs: Any) -> AgentRunResult:
    if phase != "initial":
        return await run_agent(prompt, **kwargs)
    current = llm_module._system_prompt
    llm_module._system_prompt = _frozen_v1_system_prompt
    try:
        return await run_agent(prompt, **kwargs)
    finally:
        llm_module._system_prompt = current


def _is_infrastructure_result(row: dict[str, Any]) -> bool:
    if row.get("infrastructure_error"):
        return True
    runs = row.get("runs") or []
    error_code = ((runs[-1].get("error") or {}).get("code")) if runs else None
    # P2-HARD-028 already exposes a deterministic pre-model privacy failure;
    # the subsequent connection error does not invalidate that observation.
    return error_code == "llm.connection" and row.get("task_id") != "P2-HARD-028"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token() -> str:
    value = os.environ.get("RHINOCODER_EVAL_TOKEN", "").strip()
    if not value or value.startswith("<"):
        raise RuntimeError("P2 需要非占位 RHINOCODER_EVAL_TOKEN")
    return value


def _load_tasks() -> list[dict[str, Any]]:
    return [json.loads(line) for line in TASKS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fixture_sha() -> str:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return manifest["files"]["eval/p2/fixtures.json"]


async def _post(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, Any],
    *,
    evaluation: bool = False,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if evaluation:
        headers["X-RhinoCoder-Eval-Token"] = _token()
    if endpoint not in {"/get_scene_summary", "/get_selected_objects", "/get_objects_by_name", "/get_object_info", "/get_bounding_box"}:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    response = await client.post(
        RHINO_URL + endpoint,
        json=payload,
        headers=headers,
        timeout=httpx.Timeout(connect=3, read=35, write=5, pool=5),
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") == "error":
        error = data.get("error") or {}
        raise RuntimeError(f"{error.get('code', 'rhino.error')}: {data.get('message', '')}")
    return data


async def _scene(client: httpx.AsyncClient) -> dict[str, Any]:
    return await _post(client, "/get_scene_summary", {})


async def _inspect(client: httpx.AsyncClient) -> dict[str, Any]:
    return await _post(client, "/inspect_p2_fixture", {}, evaluation=True)


async def _setup(client: httpx.AsyncClient, fixture_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    setup = await _post(
        client,
        "/setup_p2_fixture",
        {"fixture_id": fixture_id, "fixtures_sha256": _fixture_sha()},
        evaluation=True,
    )
    return setup, await _inspect(client)


def _model_audit_offset() -> int:
    try:
        return MODEL_AUDIT.stat().st_size
    except OSError:
        return 0


def _model_audit_delta(offset: int) -> str:
    try:
        with MODEL_AUDIT.open("rb") as stream:
            stream.seek(offset)
            return stream.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


class _FailOnceBackend(ModelBackend):
    def __init__(self, inner: ModelBackend) -> None:
        self.inner = inner
        self.profile = inner.profile
        self.base_url = inner.base_url
        self.failed = False

    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        if not self.failed:
            self.failed = True
            raise BackendError(
                "llm.timeout",
                "P2 frozen one-shot planning timeout injection",
                recoverable=True,
                fallback_eligible=True,
            )
        return await self.inner.complete(messages=messages, tools=tools)


def _fallback_backends() -> Mapping[str, ModelBackend]:
    backends = build_default_backends(
        main_model=DEEPSEEK_MODEL,
        main_base_url=DEEPSEEK_BASE_URL,
        main_client_factory=make_deepseek_client,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )
    backends["cloud-main"] = _FailOnceBackend(backends["cloud-main"])
    return backends


def _route_context(task: dict[str, Any]) -> RouteContext | None:
    raw = task.get("route_context")
    return RouteContext(**raw) if raw else None


def _successful_tools(runs: list[AgentRunResult]) -> list[Any]:
    return [tool for run in runs for tool in run.tool_calls if tool.success]


def _all_tools(runs: list[AgentRunResult]) -> list[Any]:
    return [tool for run in runs for tool in run.tool_calls]


def _bbox(obj: dict[str, Any]) -> tuple[list[float], list[float]]:
    center, size = obj["center"], obj["size"]
    return (
        [center[i] - size[i] / 2 for i in range(3)],
        [center[i] + size[i] / 2 for i in range(3)],
    )


def _fixture_equal(before: dict[str, Any], after: dict[str, Any], logical_id: str, *, geometry_only: bool = False) -> bool:
    left = (before.get("objects") or {}).get(logical_id) or {}
    right = (after.get("objects") or {}).get(logical_id) or {}
    if not left.get("exists") or not right.get("exists") or left.get("object_id") != right.get("object_id"):
        return False
    if geometry_only:
        return left.get("bbox", {}).get("size") == right.get("bbox", {}).get("size")
    keys = ["bbox", "name", "layer", "color", "groups"]
    return all(left.get(key) == right.get(key) for key in keys)


def _check_result(kind: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"kind": kind, "passed": bool(passed), "detail": detail}


def _custom_checks(
    task: dict[str, Any],
    runs: list[AgentRunResult],
    before_scene: dict[str, Any],
    after_scene: dict[str, Any],
    before_fixture: dict[str, Any],
    after_fixture: dict[str, Any],
    controls: dict[str, Any],
    model_audit_delta: str,
) -> list[dict[str, Any]]:
    tools = _all_tools(runs)
    successful = _successful_tools(runs)
    by_name = Counter(tool.name for tool in successful)
    all_by_name = Counter(tool.name for tool in tools)
    results = []
    for spec in task["p2_checks"]:
        kind = spec["kind"]
        ok = False
        detail = ""
        if kind == "required_tool":
            ok = by_name[spec["name"]] >= int(spec.get("min_successes", 1))
        elif kind == "required_tools":
            ok = all(by_name[name] >= 1 for name in spec["names"])
        elif kind == "forbidden_tool":
            ok = all_by_name[spec["name"]] == 0
        elif kind == "forbidden_tools":
            ok = all(all_by_name[name] == 0 for name in spec["names"])
        elif kind == "forbidden_create_tools":
            ok = not any(tool.name in CREATE_TOOLS for tool in tools)
        elif kind == "minimum_tool_calls":
            ok = all_by_name[spec["name"]] >= int(spec["n"])
        elif kind == "min_scene_checks":
            ok = sum(len(run.scene_checks) for run in runs) >= int(spec["n"])
        elif kind == "created_object_count":
            ok = len({oid for run in runs for oid in run.created_object_ids}) == int(spec["n"])
        elif kind == "single_created_identity":
            ok = len({oid for run in runs for oid in run.created_object_ids}) == 1
        elif kind == "created_type_consumed":
            created = by_name[spec["tool"]]
            ok = created >= int(spec["minimum_created"]) and after_scene.get("total", 0) < created + 1
        elif kind == "clarification_before_write":
            phase = controls.get("clarification") or {}
            text = str(phase.get("final_text") or "")
            ok = bool(phase.get("asked")) and not phase.get("write_tools") and all(term.casefold() in text.casefold() for term in spec["required_terms"])
        elif kind in {"all_touch", "bbox_gap"}:
            if kind == "all_touch":
                moving = select(after_scene, spec["moving"])
                targets = select(after_scene, spec["target"])
                if len(targets) == 1 and moving:
                    target_min, target_max = _bbox(targets[0])
                    face = target_min[2] if spec["target_face"] == "min_z" else target_max[2]
                    ok = all(abs((_bbox(item)[1][2] if spec["moving_face"] == "max_z" else _bbox(item)[0][2]) - face) <= float(spec["tol"]) for item in moving)
            else:
                a, b = select(after_scene, spec["a"]), select(after_scene, spec["b"])
                if len(a) == len(b) == 1:
                    axis = "xyz".index(spec["axis"])
                    amn, amx = _bbox(a[0]); bmn, bmx = _bbox(b[0])
                    gap = amn[axis] - bmx[axis] if spec.get("direction") == "a_after_b" else min(abs(amn[axis] - bmx[axis]), abs(bmn[axis] - amx[axis]))
                    ok = abs(gap - float(spec["gap"])) <= float(spec["tol"])
        elif kind == "equal_axis_gaps":
            objects = select(after_scene, spec["selector"])
            axis = "xyz".index(spec["axis"])
            ordered = sorted((_bbox(obj) for obj in objects), key=lambda pair: pair[0][axis])
            gaps = [ordered[i + 1][0][axis] - ordered[i][1][axis] for i in range(len(ordered) - 1)]
            target = spec.get("value")
            tol = float(spec["tol"])
            ok = bool(gaps) and (all(abs(gap - float(target)) <= tol for gap in gaps) if target is not None else max(gaps) - min(gaps) <= tol)
            detail = f"gaps={gaps}"
        elif kind in {"min_face", "same_min_face"}:
            objects = select(after_scene, spec["selector"])
            axis = "xyz".index(spec["axis"])
            values = [_bbox(obj)[0][axis] for obj in objects]
            tol = float(spec["tol"])
            ok = bool(values) and (abs(min(values) - float(spec["value"])) <= tol if kind == "min_face" else max(values) - min(values) <= tol)
            detail = f"faces={values}"
        elif kind == "unique_group_count":
            objects = select(after_scene, spec["selector"])
            groups = {group for obj in objects for group in obj.get("groups") or []}
            ok = len(groups) == int(spec["n"]) and all(obj.get("groups") for obj in objects)
        elif kind in {"group_bbox_gap", "groups_same_min_face"}:
            groups: dict[str, list[dict[str, Any]]] = {}
            for obj in after_scene.get("objects") or []:
                for group in obj.get("groups") or []:
                    groups.setdefault(group, []).append(obj)
            bounds = []
            axis = "xyz".index(spec["axis"])
            for members in groups.values():
                boxes = [_bbox(obj) for obj in members]
                bounds.append((min(box[0][axis] for box in boxes), max(box[1][axis] for box in boxes)))
            if kind == "group_bbox_gap" and len(bounds) == 2:
                bounds.sort()
                ok = abs(bounds[1][0] - bounds[0][1] - float(spec["gap"])) <= float(spec["tol"])
            elif kind == "groups_same_min_face" and len(bounds) == 2:
                ok = abs(bounds[0][0] - bounds[1][0]) <= float(spec["tol"])
        elif kind == "no_duplicate_geometry":
            fingerprints = [(tuple(obj.get("center") or []), tuple(obj.get("size") or []), obj.get("type")) for obj in select(after_scene, spec["selector"])]
            ok = len(fingerprints) == len(set(fingerprints))
        elif kind == "unchanged_fixture_objects":
            ids = spec.get("logical_ids")
            if ids is None:
                prefix = spec["logical_ids_pattern"].rstrip("*")
                ids = [logical_id for logical_id in (before_fixture.get("objects") or {}) if logical_id.startswith(prefix)]
            ok = all(_fixture_equal(before_fixture, after_fixture, logical_id) for logical_id in ids)
        elif kind == "preserve_fixture_identity":
            left = (before_fixture.get("objects") or {}).get(spec["logical_id"], {})
            right = (after_fixture.get("objects") or {}).get(spec["logical_id"], {})
            ok = left.get("object_id") == right.get("object_id") and right.get("exists")
        elif kind == "preserve_no_extra_creation":
            ok = after_scene.get("total") == before_scene.get("total") - 1
        elif kind == "fixture_object_properties":
            item = (after_fixture.get("objects") or {}).get(spec["logical_id"], {})
            ok = item.get("exists") and all(item.get(key) == value for key, value in spec["props"].items())
        elif kind == "fixture_geometry_fingerprint_unchanged":
            ok = _fixture_equal(before_fixture, after_fixture, spec["logical_id"], geometry_only=True)
        elif kind == "precise_rollback":
            deleted = set(controls.get("rollback_deleted") or [])
            created_ids = {(before_fixture["objects"][lid]["object_id"]) for lid in spec["created_logical_ids"]}
            preserved = all((after_fixture.get("objects") or {}).get(lid, {}).get("exists") for lid in spec["preserve_logical_ids"])
            ok = created_ids <= deleted and preserved
        elif kind == "idempotent_second_rollback":
            ok = bool(controls.get("second_rollback_noop"))
        elif kind == "failed_then_successful_tool":
            matching = [tool.success for tool in tools if tool.name == spec["name"]]
            ok = False in matching and True in matching and matching.index(False) < matching.index(True)
        elif kind == "stale_id_recovery_or_safe_failure":
            ok = bool(controls.get("stale_mutated")) and (
                (runs[-1].status is RunStatus.COMPLETED and after_fixture["objects"]["target_panel"].get("exists"))
                or (runs[-1].status is RunStatus.FAILED and not any(tool.name in CREATE_TOOLS for tool in successful))
            )
        elif kind == "min_name_lookups":
            ok = sum(1 for tool in successful if tool.name == "get_objects_by_name" and tool.arguments.get("name") == spec["name"]) >= int(spec["n"])
        elif kind == "fault_consumed":
            ok = after_fixture.get("fault_remaining") == 0
        elif kind == "listener_idempotency_replay":
            ok = by_name[spec["operation"]] == 1 and after_scene.get("total") == 1 and after_fixture.get("fault_remaining") == 0
        elif kind == "terminal_event":
            ok = any(event.type == spec["type"] for run in runs for event in run.events)
        elif kind == "no_writes_after_cancel":
            ok = bool(controls.get("no_writes_after_cancel"))
        elif kind == "precise_rollback_created_objects":
            ok = bool(controls.get("cancel_rollback_complete"))
        elif kind == "maximum_created_before_rollback":
            ok = int(controls.get("cancel_created_count", 10**9)) <= int(spec["n"])
        elif kind == "group_internal_offsets_unchanged":
            ok = bool(controls.get("group_internal_offsets_unchanged"))
        elif kind == "observed_capped_scene":
            ok = any("已截取前 50 个" in tool.output for tool in successful if tool.name == "get_scene_summary")
        elif kind == "fixture_missing_corner_filled":
            expected = [28, -18, 15]
            fixture_ids = {item["object_id"] for item in (before_fixture.get("objects") or {}).values()}
            created = [obj for obj in after_scene.get("objects") or [] if obj.get("object_id") not in fixture_ids]
            ok = len(created) == 1 and all(abs(created[0]["center"][i] - expected[i]) <= float(spec["tol"]) for i in range(3))
        elif kind == "privacy_decision":
            decision = runs[-1].privacy_decision or {}
            ok = all(decision.get(key) == spec[key] for key in ("risk", "action", "cloud_allowed"))
        elif kind == "selected_backend":
            ok = (runs[-1].route_decision or {}).get("selected_backend") == spec["value"]
        elif kind == "no_cloud_request":
            ok = not model_audit_delta.strip()
        elif kind == "no_route_fallback":
            ok = not any(event.type == "route.fallback" for run in runs for event in run.events)
        elif kind == "status_in":
            ok = runs[-1].status.value in spec["values"]
        elif kind == "no_tool_calls":
            ok = not tools
        elif kind == "error_code":
            ok = bool(runs[-1].error and runs[-1].error.code == spec["value"])
        elif kind == "model_request_redacted":
            ok = spec["forbidden"] not in model_audit_delta and spec["required"] in model_audit_delta
        elif kind == "lineage_ids_consistent":
            ok = all(event.run_id == run.run_id for run in runs for event in run.events)
        elif kind == "raw_instruction_absent_from_storage":
            run_dict = runs[-1].to_dict()
            persisted_prompt = json.dumps({"events": run_dict["events"], "error": run_dict["error"]}, ensure_ascii=False)
            ok = task["instruction"] not in persisted_prompt
        elif kind == "metrics_present":
            metrics = runs[-1].metrics.to_dict()
            ok = all(field in metrics and metrics[field] is not None for field in spec["fields"])
        elif kind == "route_fallback":
            decision = runs[-1].route_decision or {}
            ok = decision.get("fallback_from") == spec["from"] and decision.get("selected_backend") == spec["to"] and decision.get("fallback_error_code") == spec["error_code"]
        elif kind == "fallback_before_first_write":
            events = [event for run in runs for event in run.events]
            fallback_seq = min((event.seq for event in events if event.type == "route.fallback"), default=10**9)
            write_seq = min((event.seq for event in events if event.type == "tool.started" and event.payload.get("name") in WRITE_TOOLS), default=10**9)
            ok = fallback_seq < write_seq
        elif kind == "no_duplicate_successful_mutations":
            signatures = [(tool.name, json.dumps(tool.arguments, sort_keys=True, ensure_ascii=False)) for tool in successful if tool.name in WRITE_TOOLS]
            ok = len(signatures) == len(set(signatures))
        else:
            detail = "evaluator has no implementation"
        results.append(_check_result(kind, ok, detail))
    return results


def _group_offsets_unchanged(before: dict[str, Any], after: dict[str, Any]) -> bool:
    groups: dict[str, list[str]] = {}
    for logical_id, item in (before.get("objects") or {}).items():
        for group in item.get("groups") or []:
            groups.setdefault(group, []).append(logical_id)
    for ids in groups.values():
        if len(ids) < 2:
            continue
        anchor = ids[0]
        for logical_id in ids[1:]:
            try:
                b0 = before["objects"][anchor]["bbox"]["center"]
                b1 = before["objects"][logical_id]["bbox"]["center"]
                a0 = after["objects"][anchor]["bbox"]["center"]
                a1 = after["objects"][logical_id]["bbox"]["center"]
            except (KeyError, TypeError):
                return False
            if [round(b1[i] - b0[i], 4) for i in range(3)] != [round(a1[i] - a0[i], 4) for i in range(3)]:
                return False
    return True


async def _run_control_rollback(client: httpx.AsyncClient, task: dict[str, Any], setup: dict[str, Any], controls: dict[str, Any]) -> None:
    spec = next(check for check in task["p2_checks"] if check["kind"] == "precise_rollback")
    object_ids = [setup["object_ids"][logical_id] for logical_id in spec["created_logical_ids"]]
    first = await _post(client, "/delete_objects", {"object_ids": object_ids})
    second = await _post(client, "/delete_objects", {"object_ids": object_ids})
    controls["rollback_deleted"] = first.get("deleted") or []
    controls["second_rollback_noop"] = not (second.get("deleted") or [])
    controls["control_tool_calls"] = 2


async def _run_task(task: dict[str, Any], phase: str, intervention: str) -> dict[str, Any]:
    started = time.monotonic()
    public_run_id = hashlib.sha256(f"{phase}:{task['id']}:{uuid.uuid4()}".encode()).hexdigest()[:16]
    runs: list[AgentRunResult] = []
    controls: dict[str, Any] = {}
    caught: str | None = None
    audit_offset = _model_audit_offset()
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            setup, before_fixture = await _setup(client, task["fixture_id"])
            before_scene = await _scene(client)

            if task["id"] == "P2-HARD-018":
                await _run_control_rollback(client, task, setup, controls)
            else:
                callback_state = {"write_count": 0, "cancel_event_seq": None, "stale_done": False}
                token = CancellationToken() if task["id"] == "P2-HARD-017" else None

                async def on_event(event) -> None:
                    if event.type == "tool.completed" and event.payload.get("success"):
                        name = event.payload.get("name")
                        if name in WRITE_TOOLS:
                            callback_state["write_count"] += 1
                            if token and callback_state["write_count"] >= 2:
                                token.cancel()
                        if task["id"] == "P2-HARD-015" and name == "get_objects_by_name" and not callback_state["stale_done"]:
                            await _post(client, "/mutate_p2_fixture", {"mutation_id": task["fault_id"]}, evaluation=True)
                            callback_state["stale_done"] = True

                if task.get("clarification_answer"):
                    first = await _invoke_agent(
                        task["instruction"],
                        phase=phase,
                        closed_loop=True,
                        event_callback=on_event,
                        route_context=_route_context(task),
                    )
                    runs.append(first)
                    write_names = [tool.name for tool in first.tool_calls if tool.name in WRITE_TOOLS]
                    text = first.final_text
                    asked = ("?" in text or "？" in text or any(word in text for word in ("请确认", "请问", "需要您", "能否")))
                    controls["clarification"] = {"asked": asked, "final_text": text, "write_tools": write_names}
                    if not write_names:
                        if task["id"] == "P2-HARD-012":
                            await _run_control_rollback(client, task, setup, controls)
                        else:
                            answer_prompt = task["instruction"] + "\n用户补充：" + task["clarification_answer"]
                            runs.append(await _invoke_agent(answer_prompt, phase=phase, closed_loop=True, event_callback=on_event, route_context=_route_context(task)))
                            controls["human_intervention_count"] = 1
                else:
                    if task["id"] == "P2-HARD-016":
                        await _post(client, "/configure_p2_fault", {"fault_id": task["fault_id"]}, evaluation=True)
                    registry = _fallback_backends() if task["id"] == "P2-HARD-030" else None
                    run = await _invoke_agent(
                        task["instruction"],
                        phase=phase,
                        closed_loop=True,
                        event_callback=on_event,
                        cancellation_token=token,
                        route_context=_route_context(task),
                        router_config=RouterConfig() if task["id"] == "P2-HARD-030" else None,
                        backend_registry=registry,
                    )
                    runs.append(run)
                    controls["stale_mutated"] = callback_state["stale_done"]
                    if task["id"] == "P2-HARD-017":
                        controls["cancel_created_count"] = len(run.created_object_ids)
                        cancelled = next((event for event in run.events if event.type == "run.cancelled"), None)
                        controls["no_writes_after_cancel"] = bool(cancelled) and not any(
                            event.seq > cancelled.seq and event.type == "tool.started" and event.payload.get("name") in WRITE_TOOLS
                            for event in run.events
                        )
                        if run.created_object_ids:
                            deletion = await _post(client, "/delete_objects", {"object_ids": run.created_object_ids})
                            controls["cancel_rollback_complete"] = set(deletion.get("deleted") or []) == set(run.created_object_ids)
                        else:
                            controls["cancel_rollback_complete"] = True

            after_scene = await _scene(client)
            after_fixture = await _inspect(client)
            controls["group_internal_offsets_unchanged"] = _group_offsets_unchanged(before_fixture, after_fixture)
        except BaseException as exc:
            caught = f"{type(exc).__name__}: {exc}"
            before_scene = locals().get("before_scene", {"objects": [], "total": 0, "capped": False})
            before_fixture = locals().get("before_fixture", {"objects": {}})
            try:
                after_scene = await _scene(client)
                after_fixture = await _inspect(client)
            except BaseException:
                after_scene = {"objects": [], "total": 0, "capped": False}
                after_fixture = {"objects": {}}

    scene_result = verify(after_scene, task["asserts"])
    model_delta = _model_audit_delta(audit_offset)
    custom = _custom_checks(task, runs, before_scene, after_scene, before_fixture, after_fixture, controls, model_delta) if runs or task["id"] == "P2-HARD-018" else []
    terminal_ok = bool(runs and runs[-1].status is RunStatus.COMPLETED)
    if task["id"] in {"P2-HARD-012", "P2-HARD-018"}:
        terminal_ok = True
    if task["id"] in {"P2-HARD-026", "P2-HARD-027", "P2-HARD-028"} and runs:
        terminal_ok = runs[-1].status.value in next((check["values"] for check in task["p2_checks"] if check["kind"] == "status_in"), ["failed", "completed"])
    if task["id"] == "P2-HARD-017" and runs:
        terminal_ok = runs[-1].status is RunStatus.CANCELLED
    automated_pass = caught is None and terminal_ok and scene_result["passed"] and all(item["passed"] for item in custom)
    manual_pending = bool(automated_pass and task.get("manual_checks"))
    failure_category = None if automated_pass else _classify(task, runs, scene_result, custom, caught)
    return {
        "schema_version": "1.0",
        "protocol_id": "p2-hard-v1",
        "phase": phase,
        "intervention": intervention,
        "task_id": task["id"],
        "source_id": task["source_id"],
        "category": task["category"],
        "difficulty": task["difficulty"],
        "public_run_id": public_run_id,
        "started_at": _now(),
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "environment": "real_rhino_8_mcp_configured_model",
        "mock_claimed_as_real": False,
        "automated_pass": automated_pass,
        "manual_evidence_pending": manual_pending,
        "full_acceptance": automated_pass and not task.get("manual_checks"),
        "failure_category": failure_category,
        "infrastructure_error": caught,
        "scene_assertions": scene_result,
        "p2_checks": custom,
        "manual_checks": task.get("manual_checks") or [],
        "human_intervention_count": int(controls.get("human_intervention_count", 0)),
        "recovery_count": sum(1 for run in runs for event in run.events if event.type == "correction.started"),
        "tool_calls": [
            {"name": tool.name, "success": tool.success, "duration_ms": tool.duration_ms, "error_code": tool.error_code}
            for tool in _all_tools(runs)
        ],
        "runs": [run.to_dict() for run in runs],
        "controls": controls,
        "before_scene": before_scene,
        "after_scene": after_scene,
        "before_fixture": before_fixture,
        "after_fixture": after_fixture,
        "holdout_read": 0,
    }


def _classify(task, runs, scene_result, custom, caught) -> str:
    if caught:
        return "infrastructure_error"
    failed = [item["kind"] for item in custom if not item["passed"]]
    if "clarification_before_write" in failed:
        return "clarification_error"
    if any(kind in failed for kind in ("privacy_decision", "no_cloud_request", "model_request_redacted", "raw_instruction_absent_from_storage")):
        return "privacy_error"
    if any(kind in failed for kind in ("selected_backend", "route_fallback", "fallback_before_first_write", "no_route_fallback")):
        return "routing_error"
    if task["category"] == "error_recovery":
        return "recovery_error"
    if task["task_type"] in {"precise_rollback_after_failure", "cancel_mid_mutation", "clarify_then_precise_rollback"}:
        return "product_control_error"
    if not scene_result.get("passed"):
        reasons = " ".join(scene_result.get("failed_reasons") or [])
        return "spatial_error" if any(word in reasons for word in ("尺寸", "中心", "距离", "紧贴", "size")) else "perception_error"
    if runs and runs[-1].status is not RunStatus.COMPLETED:
        return "planning_error"
    return "tool_selection_error"


async def _main(args) -> int:
    audit_result = audit()
    if not audit_result.passed:
        raise RuntimeError("P2 freeze audit failed: " + "; ".join(audit_result.findings))
    tasks = _load_tasks()
    if args.task_id:
        wanted = set(args.task_id)
        tasks = [task for task in tasks if task["id"] in wanted]
        missing = wanted - {task["id"] for task in tasks}
        if missing:
            raise ValueError("未知 task_id: " + ", ".join(sorted(missing)))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("phase") == args.phase and not _is_infrastructure_result(row):
                    completed.add(row["task_id"])
    for index, task in enumerate(tasks, 1):
        if task["id"] in completed and not args.force:
            print(f"[{index}/{len(tasks)}] {task['id']} immutable result already present; skipped", flush=True)
            continue
        print(f"[{index}/{len(tasks)}] {task['id']} starting", flush=True)
        result = await _run_task(task, args.phase, args.intervention)
        with output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(
            f"[{index}/{len(tasks)}] {task['id']} automated_pass={result['automated_pass']} "
            f"failure={result['failure_category']} duration_ms={result['duration_ms']}",
            flush=True,
        )
        if result["infrastructure_error"] and not runs_recoverable(result):
            print("fatal infrastructure gate; remaining tasks not attempted", flush=True)
            return 2
    return 0


def runs_recoverable(result: dict[str, Any]) -> bool:
    text = str(result.get("infrastructure_error") or "").lower()
    return not any(marker in text for marker in ("api key", "authentication", "insufficient", "quota", "connection refused"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("initial", "retest"), default="initial")
    parser.add_argument("--intervention", default="none")
    parser.add_argument("--task-id", action="append")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--force", action="store_true", help="append another explicit attempt; never overwrites")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
