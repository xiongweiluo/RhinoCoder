"""Eight newly authored PUBLIC DEVELOPMENT cases, never final test material.

No private corpus is opened. Family separation here is within this packet;
global overlap with private historical corpora has NOT been independently
certified. Geometry below is an analytic design, not observed Rhino readback.
"""
from __future__ import annotations

import copy

from training.c5_formal20_plan import validate_case


DEFINITIONS = (
    ("DEV-S01", "selection", "explicit_alias_order_two_bbox_reads", "multistep",
     "仅按 box-2、box-1 的顺序分别读取一次包围盒，两次读取完成后结束，不修改任何对象。",
     (("get_bounding_box", "box-2"), ("get_bounding_box", "box-1"))),
    ("DEV-S02", "selection", "scene_inventory_then_unique_target_bbox", "multistep",
     "先读取一次完整场景摘要，再读取场景中高度最大的对象的包围盒，各一次，不修改场景。",
     (("get_scene_summary", None), ("get_bounding_box", "box-2"))),
    ("DEV-S03", "selection", "missing_target_disambiguation", "clarification",
     "读取那个对象的包围盒；具体指哪一个对象我稍后确认，现在不要调用工具。", ()),
    ("DEV-S04", "selection", "explicit_deferred_read_permission", "refusal",
     "这次只讨论读取场景摘要的计划，尚未授权执行；现在不得读取或修改场景，不要调用任何工具。", ()),
    ("DEV-A01", "acceptance", "spatially_defined_target_order_two_reads", "multistep",
     "按对象在 X 轴上从左到右的空间顺序，依次读取各自包围盒，各一次，不修改对象。",
     (("get_bounding_box", "box-1"), ("get_bounding_box", "box-2"))),
    ("DEV-A02", "acceptance", "target_bbox_then_scene_inventory", "multistep",
     "先读取 X 方向跨度较大的那个对象的包围盒，再读取完整场景摘要，各一次，不做修改。",
     (("get_bounding_box", "box-2"), ("get_scene_summary", None))),
    ("DEV-A03", "acceptance", "incompatible_target_constraints", "clarification",
     "读取同时完全位于 X 小于零且完全位于 X 大于二十区域的对象包围盒；若没有唯一符合者，先澄清，不调用工具。", ()),
    ("DEV-A04", "acceptance", "authorized_single_scene_inventory", "core_tool",
     "现在授权只读取一次完整场景摘要，不读取单个对象包围盒，也不修改任何对象。",
     (("get_scene_summary", None),)),
)


def fixture_design():
    """At most eight publicly supported seed operations; model writes stay zero."""
    layer, color = "C5-LoraDev", [20, 30, 40]
    recipe = [
        {"operation": "create_box", "arguments": {"width": 3, "depth": 5, "height": 7}},
        {"operation": "set_object_layer", "arguments": {"object_id": "box-1", "layer_name": layer}},
        {"operation": "set_object_color", "arguments": {"object_ids": ["box-1"], "r": 20, "g": 30, "b": 40}},
        {"operation": "create_box", "arguments": {"width": 4, "depth": 6, "height": 8}},
        {"operation": "move_object", "arguments": {"object_id": "box-2", "translate_x": 20,
                                                   "translate_y": 0, "translate_z": 0}},
        {"operation": "set_object_layer", "arguments": {"object_id": "box-2", "layer_name": layer}},
        {"operation": "set_object_color", "arguments": {"object_ids": ["box-2"], "r": 20, "g": 30, "b": 40}},
    ]
    scene = {"unit": "Millimeters", "groups": {}, "objects": [
        {"alias": "box-1", "min": [0, 0, 0], "max": [3, 5, 7], "layer": layer, "color": color, "groups": []},
        {"alias": "box-2", "min": [20, 0, 0], "max": [24, 6, 8], "layer": layer, "color": color, "groups": []},
    ]}
    solid = {"box-1": {"volume": 105, "centroid": [1.5, 2.5, 3.5]},
             "box-2": {"volume": 192, "centroid": [22, 3, 4]}}
    assertions = {"object_count": 2, "objects": {
        o["alias"]: {**{k: v for k, v in o.items() if k != "alias"}, **solid[o["alias"]],
                     "solid": True, "face_count": 6} for o in scene["objects"]},
        "unchanged": ["box-1", "box-2"], "read_result": None}
    return copy.deepcopy((recipe, scene, assertions))


def build_cases():
    recipe, scene, initial = fixture_design()
    cases = []
    for family, role, template, stratum, task, calls in DEFINITIONS:
        operations = []
        for name, target in calls:
            if target is None:
                arguments, result = {}, copy.deepcopy(scene)
            else:
                obj = next(o for o in scene["objects"] if o["alias"] == target)
                arguments = {"object_id": target}
                result = {"object_id": target, "min": obj["min"], "max": obj["max"],
                          "center": [(lo + hi) / 2 for lo, hi in zip(obj["min"], obj["max"])]}
            operations.append({"name": name, "arguments": arguments, "read_result": result})
        final = {**initial, "read_result": operations[-1]["read_result"] if operations else None}
        case = validate_case({"schema_version": 1, "family_id": family,
            "template_family": template, "stratum": stratum,
            "primary_tool": "get_scene_summary" if stratum == "core_tool" else None,
            "task_text": task, "fixture_recipe": recipe, "initial_assertions": initial,
            "final_assertions": final, "expected_operations": operations,
            "max_steps": max(1, len(operations)), "max_reads": len(operations), "max_writes": 0})
        cases.append({"role": role, "case": case})
    return cases
