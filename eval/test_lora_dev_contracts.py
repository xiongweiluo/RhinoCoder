"""New public CPU mechanisms only; never read historical task or raw-log files."""
import copy
import json

import pytest

from training.c5_contract import render_invocation, render_selection
from training.c5_formal20_plan import validate_case
from training.c5_formal20_scorer import score_route
from training.c5_formal_reuse_runner import FormalRunner
from training.c5_inventory import load_public_mcp_tools
from training.c5_rhino_adapter import invoke_step, step_input
from training.lora_dev_feedback import invoke_development_step, render_step
from training.tool_contract_candidate import ContractError


class TextTokenizer:
    """Deterministic template spy, not a real tokenizer or token-budget proof."""
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps({"messages": messages, **kwargs}, ensure_ascii=False, sort_keys=True)

    def __call__(self, text, **kwargs):
        return {"input_ids": [0] * 100}


EMPTY = {"unit": "Millimeters", "objects": [], "groups": {}}
ASSERTIONS = {"object_count": 0, "objects": {}, "unchanged": [], "read_result": None}
BINDING = {"document_key": "a" * 64, "revision": 0, "scene_sha256": "b" * 64}


def read_pair():
    scene = {"unit": "Millimeters", "groups": {}, "objects": [
        {"alias": name, "min": [0, 0, 0], "max": [3, 5, 7],
         "layer": "C5-public-fixture", "color": [0, 0, 0], "groups": []}
        for name in ("dev-copper", "dev-slate")]}
    task = "仅依次读取 dev-copper、dev-slate 的包围盒，每个读取一次，不修改对象。"
    operations = [{"name": "get_bounding_box", "arguments": {"object_id": obj["alias"]},
                   "read_result": {"object_id": obj["alias"], "min": obj["min"],
                                   "max": obj["max"], "center": [1.5, 2.5, 3.5]}}
                  for obj in scene["objects"]]
    assertions = {**ASSERTIONS, "object_count": 2, "unchanged": [o["alias"] for o in scene["objects"]]}
    case = {"schema_version": 1, "family_id": "dev-progress-component-v1",
            "template_family": "dev-ordered-two-reads-component-v1", "stratum": "multistep",
            "primary_tool": None, "task_text": task, "fixture_recipe": [],
            "initial_assertions": assertions, "final_assertions": assertions,
            "expected_operations": operations, "max_steps": 2, "max_reads": 2, "max_writes": 0}
    first = operations[0]
    previous = {"step_index": 0, "policy_denied": False,
                "observation": {"status": "schema_valid_not_authorized", "name": first["name"],
                    "arguments": first["arguments"], "scene_binding": BINDING,
                    "repair_count": 0, "dispatch_count": 0},
                "receipt": {"status": "done", "payload": {"operation": first["name"],
                    "arguments": first["arguments"], "expected": BINDING},
                    "before": copy.deepcopy(scene), "after": copy.deepcopy(scene),
                    "before_state": BINDING, "after_state": BINDING, "result": first["read_result"]}}
    return validate_case(case), scene, previous


def prompts(user_step):
    tools, tokenizer = load_public_mcp_tools(), TextTokenizer()
    return (render_selection(tokenizer, user_step, tools).prompt,
            render_invocation(tokenizer, user_step, tools, "get_bounding_box").prompt)


def test_v1_legal_read_progress_is_invisible_to_old_input_but_candidate_preserves_it():
    case, scene, previous = read_pair()
    # Oracle lives in the test only: first then second object. The input API
    # receives neither the case nor its expected_operations.
    assert case["expected_operations"][0]["arguments"] != case["expected_operations"][1]["arguments"]
    after = previous["receipt"]["after"]
    assert scene == after
    baseline = [step_input(case["task_text"], value) for value in (scene, after)]
    assert baseline[0] == baseline[1] and prompts(baseline[0]) == prompts(baseline[1])
    candidate = [render_step(case["task_text"], scene),
                 render_step(case["task_text"], after, step_index=1, previous_step=previous,
                             current_binding=BINDING)]
    assert candidate[0] != candidate[1]
    for first, second in zip(prompts(candidate[0]), prompts(candidate[1])):
        assert first != second
        assert candidate[1] in json.loads(second)["messages"][-1]["content"]
        assert "expected_operations" not in second and "next_action" not in second
    facts = json.loads(candidate[1].rsplit("：", 1)[1])
    assert facts == {"status": "done", "operation": "get_bounding_box", "target_alias": "dev-copper"}
    assert "dev-slate" not in json.dumps(facts)


@pytest.mark.parametrize("fault", ["missing", "denied", "unknown", "stale", "payload", "scene", "binding", "write", "other_document"])
def test_candidate_never_turns_uncertain_or_unrelated_predecessor_into_completed_progress(fault):
    case, scene, previous = read_pair()
    if fault == "missing": previous["receipt"] = None
    if fault == "denied": previous["policy_denied"] = True
    if fault == "unknown": previous["receipt"]["status"] = "unknown"
    if fault == "stale": previous["step_index"] = 1
    if fault == "payload": previous["receipt"]["payload"]["arguments"] = {"object_id": "dev-slate"}
    if fault == "scene": previous["receipt"]["after"]["objects"][0]["color"] = [1, 2, 3]
    if fault == "binding": previous["receipt"]["after_state"] = {**BINDING, "revision": 1}
    if fault == "write": previous["observation"]["name"] = "create_box"
    current = {**BINDING, "document_key": "d" * 64} if fault == "other_document" else BINDING
    with pytest.raises(ContractError):
        render_step(case["task_text"], scene, step_index=1, previous_step=previous, current_binding=current)


@pytest.mark.parametrize("system", ["original", "read_progress_v1"])
def test_development_seam_uses_the_same_strict_adapter_for_both_systems(system):
    case, scene, previous = read_pair()
    requests = []
    def fixed(prompt, stage):
        requests.append((stage, prompt))
        return {"raw": '{"tool":"get_bounding_box"}' if stage == "selector" else
                '{"name":"get_bounding_box","arguments":{"object_id":"dev-slate"}}'}
    result = invoke_development_step(TextTokenizer(), fixed, system=system,
        task=case["task_text"], scene=scene, binding=BINDING, step_index=1,
        previous_step=previous, privacy_guard=lambda _: True)
    rendered = step_input(case["task_text"], scene) if system == "original" else render_step(
        case["task_text"], scene, step_index=1, previous_step=previous, current_binding=BINDING)
    assert tuple(prompt for _, prompt in requests) == prompts(rendered)
    assert result["observation"]["status"] == "schema_valid_not_authorized"
    assert result["observation"]["dispatch_count"] == result["observation"]["repair_count"] == 0
    assert result["generation_receipts"] == result["observation"]["calls"]


def test_uncertain_feedback_never_reaches_injected_generator():
    case, scene, _ = read_pair()
    calls = []
    with pytest.raises(ContractError):
        invoke_development_step(TextTokenizer(), lambda *args: calls.append(args),
            system="read_progress_v1", task=case["task_text"], scene=scene,
            binding=BINDING, step_index=1, previous_step=None)
    assert calls == []


class FixedOutput:
    def __init__(self, call):
        self.call, self.requests = call, []

    def infer(self, **kwargs):
        self.requests.append(kwargs)
        def fixed(prompt, stage):
            return {"raw": ('{"tool":"get_scene_summary"}' if self.call else '{"tool":null}')
                    if stage == "selector" else '{"name":"get_scene_summary","arguments":{}}'}
        observed = invoke_step(TextTokenizer(), fixed, step_input(kwargs["task_text"], kwargs["scene"]),
                               scene_binding=kwargs["binding"], privacy_guard=lambda _: True)
        return {"observation": observed, "generation_receipts": observed["calls"]}


class MemoryHost:
    def __init__(self): self.dispatches = self.closed = self.stopped = 0
    def open_slot(self, **kwargs): pass
    def capture(self, slot_id): return {"status": "captured", "state": BINDING, "native": copy.deepcopy(EMPTY)}
    def execute_observation(self, **kwargs):
        self.dispatches += 1
        raise AssertionError("zero-budget clarification must not reach dispatch")
    def unresolved(self, slot_id): return False
    def close_slot(self, slot_id): self.closed += 1; return {"status": "closed"}
    def stop_slot(self, slot_id): self.stopped += 1; return {"status": "stopped"}


@pytest.mark.parametrize("call", [False, True])
def test_v2_real_runner_policy_and_scorer_separate_parsing_from_clarification_success(tmp_path, call):
    case = validate_case({"schema_version": 1, "family_id": "dev-clarification-component-v1",
        "template_family": "dev-missing-dimension-component-v1", "stratum": "clarification",
        "primary_tool": None, "task_text": "先创建一个圆柱，半径和高度稍后再确定；现在不要读取或修改场景。",
        "fixture_recipe": [], "initial_assertions": ASSERTIONS, "final_assertions": ASSERTIONS,
        "expected_operations": [], "max_steps": 1, "max_reads": 0, "max_writes": 0})
    model, host = FixedOutput(call), MemoryHost()
    runner = FormalRunner(state=tmp_path, spec={"max_generation_stages": 2}, freeze={}, approval={},
                          model=model, native=host, source_guard=lambda: None, budget_guard=lambda: None)
    runner._generation_stages = 0
    # Test only the injected coordinator component; never run(), owner entry,
    # private loader, fake live approval, or historical consumption state.
    result = runner._slot({"slot_id": "dev-v2-cpu", "route": "base", "family_id": case["family_id"]},
                          case, "c" * 64, {})
    audit = {"model_native_chain_verified": True, "permission_ledger_verified": True,
             "source_model_resource_verified": True, "lifecycle_verified": True,
             "critical_safety_errors": 0, "duplicate_writes": 0, "unverified_cleanup": 0}
    scored = score_route(case, result, audit)  # Explicit synthetic premises, not a field audit.
    assert result["error_type"] is None and len(model.requests) == 1
    assert host.dispatches == 0 and host.closed == host.stopped == 1
    assert result["steps"][0]["policy_denied"] is call
    assert result["steps"][0]["receipt"] is None
    assert scored["parse_exact"] is True and scored["native_final_geometry_passed"] is True
    assert scored["sequence_exact"] is (not call) and scored["outcome_correct"] is (not call)
    assert ("model_call_not_exact_native_dispatch" in scored["failures"]) is call
    assert not any("expected_operations" in request for request in model.requests)
