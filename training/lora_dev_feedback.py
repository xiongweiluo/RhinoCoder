"""Isolated development-only read-progress candidate; no loader or executor.

The caller must already have verified the native receipt. These consistency
checks do not authenticate it or authorize another action. Frozen C5 inputs
remain unchanged; no production or field entry imports this candidate.
"""
from __future__ import annotations

import json

from training.c5_modelbridge_joint_audit import semantic
from training.c5_rhino_adapter import invoke_step, step_input
from training.tool_contract_candidate import ContractError


CONTRACT_ID = "lora-dev-read-progress-v1"
READS = frozenset({"get_bounding_box", "get_scene_summary"})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def read_progress(scene: dict, *, step_index: int, previous_step: dict | None,
                  current_binding: dict | None = None) -> dict:
    """Project the immediately preceding completed read, never a next action.

    Missing/denied/uncertain receipts are refused, not represented as success.
    This narrow candidate deliberately does not support prior writes, error
    recovery, multiple-step history, or inference of completion from geometry.
    """
    _require(type(step_index) is int and 0 <= step_index <= 2, "invalid development step")
    if step_index == 0:
        _require(previous_step is None, "unexpected predecessor at first step")
        return {"status": "no_previous_step", "operation": None, "target_alias": None}
    _require(isinstance(previous_step, dict), "completed predecessor required")
    _require(type(previous_step.get("step_index")) is int
             and previous_step["step_index"] == step_index - 1, "stale predecessor")
    _require(previous_step.get("policy_denied") is False
             and not previous_step.get("execution_rejection")
             and not previous_step.get("failure"), "predecessor was not completed")
    observed, receipt = previous_step.get("observation"), previous_step.get("receipt")
    _require(isinstance(observed, dict) and isinstance(receipt, dict), "missing read evidence")
    _require(observed.get("status") == "schema_valid_not_authorized"
             and observed.get("repair_count") == 0 and observed.get("dispatch_count") == 0,
             "invalid model observation")
    operation, arguments = observed.get("name"), observed.get("arguments")
    _require(isinstance(operation, str) and operation in READS
             and isinstance(arguments, dict), "read-only candidate scope")
    payload = receipt.get("payload")
    _require(receipt.get("status") == "done" and isinstance(payload, dict)
             and payload.get("operation") == operation and payload.get("arguments") == arguments,
             "read receipt does not match observation")
    binding = observed.get("scene_binding")
    _require(isinstance(binding, dict) and binding and current_binding == binding
             and payload.get("expected") == binding
             and receipt.get("before_state") == binding and receipt.get("after_state") == binding,
             "read state binding differs")
    before, after = receipt.get("before"), receipt.get("after")
    _require(isinstance(before, dict) and before == after, "read changed scene")
    try:
        # Normalization ignores object ordering but retains all visible facts.
        _require(step_input("scene comparison", semantic(after)) == step_input("scene comparison", scene),
                 "receipt is not for the current semantic scene")
    except (KeyError, TypeError, ValueError, AssertionError) as error:
        raise ContractError("invalid receipt scene") from error
    target = None
    if operation == "get_bounding_box":
        _require(set(arguments) == {"object_id"} and isinstance(arguments["object_id"], str),
                 "invalid read target")
        target = arguments["object_id"]
        _require(target in {obj["alias"] for obj in scene["objects"]}, "read target absent")
    else:
        _require(not arguments, "scene read takes no arguments")
    return {"status": "done", "operation": operation, "target_alias": target}


def render_step(task: str, scene: dict, *, step_index: int = 0,
                previous_step: dict | None = None, current_binding: dict | None = None) -> str:
    """Keep the original task/scene, then append only bounded observed facts."""
    original = step_input(task, scene)
    facts = read_progress(scene, step_index=step_index, previous_step=previous_step,
                          current_binding=current_binding)
    return (original + "\n上一已完成步骤的事实（不是下一步指令，也不授予执行权）："
            + json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def invoke_development_step(tokenizer, generate, *, system: str, task: str, scene: dict,
                            binding: dict, step_index: int = 0,
                            previous_step: dict | None = None, privacy_guard=None) -> dict:
    """One shared strict adapter for the proposed development ablation.

    No model is loaded here. A future field entry must authorize its injected
    generator and verify the receipt before calling; this API grants neither.
    Rendering rejects uncertain feedback before any generation is attempted.
    """
    _require(system in {"original", "read_progress_v1"}, "unknown development system")
    user_step = (step_input(task, scene) if system == "original" else
                 render_step(task, scene, step_index=step_index, previous_step=previous_step,
                             current_binding=binding))
    observation = invoke_step(tokenizer, generate, user_step, scene_binding=binding,
                              privacy_guard=privacy_guard)
    return {"system": system, "observation": observation,
            "generation_receipts": observation["calls"]}
