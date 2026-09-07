#!/usr/bin/env python3
"""Deterministically generate the 200 coverage-driven A7 tasks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_phase3_tasks import COLORS, _count, _property, _spatial  # noqa: E402

DEFAULT_OUTPUT = ROOT / "eval" / "tasks" / "a7_expansion.jsonl"


def _color(index: int) -> tuple[str, list[int]]:
    return COLORS[index % len(COLORS)]


def _rgb(item: tuple[str, list[int]]) -> str:
    name, value = item
    return f"{name}色 RGB({value[0]},{value[1]},{value[2]})"


def _task(
    number: int,
    instruction: str,
    *,
    tags: list[str],
    gap: str,
    family: str,
    asserts: list[dict[str, Any]],
    difficulty: int = 5,
    expected_route: str = "cloud-main",
    clean: bool = False,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": f"a7-{number:03d}",
        "instruction": instruction,
        "tags": tags,
        "difficulty": difficulty,
        "coverage_gap": gap,
        "workflow_family": family,
        "expected_route": expected_route,
        "asserts": asserts,
    }
    if clean:
        row["requires_clean_tool_trace"] = True
    return row


def build_tasks() -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []

    # 001-020: two explicit observations around an in-place revision.
    for i in range(20):
        wrong, final = _color(i), _color(i + 7)
        w, d, h = 18 + i, 11 + i % 7, 8 + i % 5
        dx, dy = 20 + i, -8 - i
        center = [w / 2 + dx, d / 2 + dy, h / 2]
        tasks.append(_task(
            i + 1,
            f"创建 {w}x{d}x{h} 的方块，先设为{_rgb(wrong)}并平移 ({dx},{dy},0)，"
            "调用场景摘要记录第一版。随后必须在同一对象上完成第二轮修订："
            f"改为{_rgb(final)}，以自身中心绕 Z 轴旋转 90 度，再次调用场景摘要确认最终状态；不得删除重建。",
            tags=["multi_round", "revision", "edit", "move", "rotate", "perception", "final_state"],
            gap="multi_round_revision",
            family="observe_revise_observe",
            asserts=[
                _count({}, 1),
                _count({"color": wrong[1]}, 0),
                _property({"color": final[1]}, {"size": [d, w, h], "center": center}, 1.0),
            ],
        ))

    # 021-040: mixed edits whose group/layer membership must survive transforms.
    for i in range(20):
        c0, c1, c2 = _color(i), _color(i + 6), _color(i + 13)
        h0, h1, h2 = 10 + i, 14 + i, 18 + i
        group, layer = f"A7编辑组-{i + 1:02d}", f"A7工作流::编辑-{i + 1:02d}"
        tasks.append(_task(
            21 + i,
            f"创建三根半径分别为 3、4、5，高度分别为 {h0}、{h1}、{h2} 的圆柱，"
            f"设为{_rgb(c0)}、{_rgb(c1)}、{_rgb(c2)}，轴心 X 分别为 0、18、40。"
            f"把三者加入群组“{group}”并移入图层“{layer}”；再将中间圆柱以自身中心按 XYZ=(1.5,1.5,0.75) 缩放。"
            "最后读取场景摘要，确认变换后群组、图层和其他两个成员均未丢失。",
            tags=["complex_edit", "group", "layer", "scale", "cylinder", "perception", "multi_step"],
            gap="complex_edit_membership",
            family="group_layer_transform",
            asserts=[
                _count({"in_group": group}, 3), _count({"layer": layer}, 3),
                _property({"color": c0[1]}, {"size": [6, 6, h0]}),
                _property({"color": c1[1]}, {"size": [12, 12, h1 * 0.75]}, 1.2),
                _property({"color": c2[1]}, {"size": [10, 10, h2]}),
            ],
        ))

    # 041-060: undo a property edit, a move, and finally the creation itself.
    for i in range(20):
        transient, final = _color(i + 4), _color(i + 12)
        w, d, h = 13 + i, 9 + i % 6, 7 + i % 4
        r, ch = 3 + i % 3, 16 + i
        tasks.append(_task(
            41 + i,
            f"创建一个 {w}x{d}x{h} 的临时方块，把它平移 ({12 + i},5,0) 并设为{_rgb(transient)}。"
            "依次调用三次 undo_last_action，并在每次 Undo 后读取场景摘要：第一次应撤销颜色，第二次应撤销移动，第三次应撤销创建。"
            f"确认场景为空后创建半径 {r}、高度 {ch} 的{_rgb(final)}圆柱；最终只能保留该圆柱。",
            tags=["undo", "recovery", "multi_round", "revision", "perception", "cylinder", "final_state"],
            gap="undo_recovery_sequence",
            family="three_level_undo",
            asserts=[
                _count({}, 1), _count({"color": transient[1]}, 0),
                _property({"color": final[1]}, {"size": [r * 2, r * 2, ch]}),
            ],
            clean=True,
        ))

    # 061-080: detect a non-intersecting cutter and recover without accepting a no-op boolean.
    for i in range(20):
        body = _color(i + 9)
        w, d, h, r = 36 + i, 28 + i % 8, 16 + i % 7, 5 + i % 3
        cx, cy = w / 2, d / 2
        tasks.append(_task(
            61 + i,
            f"创建 {w}x{d}x{h} 的{_rgb(body)}盒体，再创建半径 {r} 的球形刀具并故意移到 ({w + 40},{d + 30},{h})。"
            "先读取场景摘要识别刀具与盒体不相交，不得把无变化结果当作成功。调用 Undo 撤销这次错误移动，"
            f"再把同一个球形刀具移到 ({cx:g},{cy:g},{h}) 使其穿出顶面，执行布尔差集形成球冠凹槽。"
            "若布尔调用报告不相交，必须根据包围盒修正位置后仅重试一次；最终只保留一个切割实体并再次读取场景摘要。",
            tags=["boolean", "fallback", "undo", "recovery", "sphere", "box", "perception", "clean_trace"],
            gap="boolean_alternative_recovery",
            family="non_intersection_fallback",
            asserts=[_count({}, 1), _property({"color": body[1]}, {"size": [w, d, h]}, 1.5)],
            clean=True,
        ))

    # 081-100: infer the tallest/shortest objects from an incomplete, unlabeled scene.
    for i in range(20):
        common, marker = _color(i + 2), _color(i + 15)
        hs = [13 + i, 27 + i, 19 + i]
        xs = [0, 22 + i, 51 + i]
        mr = 3 + i % 2
        tasks.append(_task(
            81 + i,
            f"创建三根未命名、均为{_rgb(common)}且半径 4 的圆柱，轴心 X={xs[0]}、{xs[1]}、{xs[2]}，高度依次为 {hs[0]}、{hs[1]}、{hs[2]}。"
            "创建过程中不要依赖对象名称；先读取场景摘要，仅根据位置和包围盒找出最矮与最高圆柱。"
            f"精准删除最矮圆柱，再创建半径 {mr} 的{_rgb(marker)}球并贴合到最高圆柱顶面中心。"
            "最后再次读取场景摘要，确认场景只剩两根圆柱和一个标记球。",
            tags=["perception", "incomplete_scene", "select", "delete", "stack", "cylinder", "sphere", "spatial"],
            gap="incomplete_perception",
            family="unlabeled_height_selection",
            asserts=[
                _count({}, 3), _count({"color": common[1]}, 2),
                _count({"color": common[1], "size": [8, 8, hs[0]]}, 0),
                _spatial({"color": marker[1]}, {"color": common[1], "size": [8, 8, hs[1]]}, "on_top_of"),
            ],
        ))

    # 101-120: distribute heterogeneous parts, then revise one selected by geometry.
    for i in range(20):
        colors = [_color(i + j * 5) for j in range(4)]
        widths = [7 + i % 3, 11 + i % 4, 15 + i % 2, 9 + i % 5]
        spacing = 4 + i % 4
        centers = [widths[0] / 2]
        for left, right in zip(widths, widths[1:]):
            centers.append(centers[-1] + left / 2 + spacing + right / 2)
        group = f"A7异构排布-{i + 1:02d}"
        tasks.append(_task(
            101 + i,
            "创建四个深度 8、高度 10、X 向宽度依次为 "
            f"{widths[0]}、{widths[1]}、{widths[2]}、{widths[3]} 的方块，颜色依次为 "
            + "、".join(_rgb(c) for c in colors)
            + f"。沿 X 轴按净间距 {spacing} 分布，第一个方块最小 X 固定为 0。读取场景摘要后，"
            f"仅选择宽度 {max(widths)} 的成员，以自身中心绕 Z 轴旋转 90 度；把四者加入群组“{group}”，再次读取场景摘要。",
            tags=["complex_edit", "distribute", "perception", "select", "rotate", "group", "spacing"],
            gap="complex_edit_selection",
            family="distribute_then_select_edit",
            asserts=[
                _count({"in_group": group}, 4),
                *[
                    _property({"color": colors[j][1]}, {"center": [centers[j], 4, 5]})
                    if widths[j] != max(widths)
                    else _property({"color": colors[j][1]}, {"size": [8, widths[j], 10], "center": [centers[j], 4, 5]}, 1.0)
                    for j in range(4)
                ],
            ],
        ))

    # 121-140: recover from a bad placement before an exact through-hole boolean.
    for i in range(20):
        body = _color(i + 5)
        outer, inner, h = 15 + i, 4 + i % 4, 20 + i
        tasks.append(_task(
            121 + i,
            f"制作外半径 {outer}、高度 {h} 的{_rgb(body)}圆柱体和内半径 {inner}、高度 {h + 10} 的同轴刀具。"
            f"先故意把刀具沿 X 移动 {outer + inner + 5} 造成不相交，调用场景摘要识别错误；"
            "不要执行无效布尔，直接 Undo 这次错误移动，使刀具恢复同轴，再把刀具沿 Z 下移 5 并执行差集。"
            "如果差集失败，只允许根据最新场景摘要选择仍存在的真实 GUID 重试一次。最终保留一个上下贯通的空心圆柱。",
            tags=["boolean", "cylinder", "concentric", "fallback", "undo", "recovery", "perception"],
            gap="boolean_alternative_recovery",
            family="cylindrical_cutter_fallback",
            asserts=[_count({}, 1), _property({"color": body[1]}, {"size": [outer * 2, outer * 2, h]}, 1.2)],
            clean=True,
        ))

    # 141-160: preserve assembly relationships through a late user revision.
    for i in range(20):
        base, top = _color(i), _color(i + 11)
        w, d, h, r = 34 + i, 24 + i % 7, 6 + i % 3, 3 + i % 3
        first_x = r + 3
        revised_x = w - r - 3
        group = f"A7修订装配-{i + 1:02d}"
        tasks.append(_task(
            141 + i,
            f"创建 {w}x{d}x{h} 的{_rgb(base)}底座和半径 {r} 的{_rgb(top)}球。"
            f"第一轮把球放到球心 ({first_x:g},{d / 2:g},{h + r:g})，确认它受底座支撑并读取场景摘要。"
            f"用户随后要求把同一个球改到对称位置 ({revised_x:g},{d / 2:g},{h + r:g})；只能移动原对象，不得创建第二个球。"
            f"最后把两者加入群组“{group}”并再次读取场景摘要。",
            tags=["multi_round", "revision", "supported_by", "move", "group", "perception", "final_state"],
            gap="multi_round_revision",
            family="late_assembly_revision",
            asserts=[
                _count({}, 2), _count({"in_group": group}, 2),
                _property({"color": top[1]}, {"center": [revised_x, d / 2, h + r]}),
                _spatial({"color": top[1]}, {"color": base[1]}, "supported_by"),
            ],
        ))

    # 161-180: an apparently simple request that needs observation and three coordinated edits.
    for i in range(20):
        base, marker = _color(i + 8), _color(i + 17)
        w, d, h, r = 28 + i, 22 + i % 5, 10 + i % 6, 2 + i % 3
        layer = f"A7边界::可靠路由-{i + 1:02d}"
        tasks.append(_task(
            161 + i,
            f"做一个简单标记：创建 {w}x{d}x{h} 的{_rgb(base)}方块和半径 {r} 的{_rgb(marker)}球。"
            "必须先读取场景摘要取得真实对象，再调用 place_on_at 把球精确贴到方块右侧并让 Y/Z 自动居中，"
            f"然后把两者移入图层“{layer}”，最后再次读取场景摘要验证贴合、图层与数量。",
            tags=["route_boundary", "perception", "place", "layer", "spatial", "multi_step"],
            gap="route_misclassification",
            family="simple_wording_complex_workflow",
            asserts=[
                _count({"layer": layer}, 2),
                _property({"color": marker[1]}, {"center": [w + r, d / 2, h / 2]}),
            ],
        ))

    # 181-200: recover from an invalid identifier, then complete an exact final-state edit.
    for i in range(20):
        final = _color(i + 3)
        w, d, h = 16 + i, 10 + i % 8, 8 + i % 5
        dx, dy, dz = 25 + i, -12 - i, 4 + i % 4
        center = [w / 2 + dx, d / 2 + dy, h / 2 + dz]
        tasks.append(_task(
            181 + i,
            f"创建 {w}x{d}x{h} 的方块。先用无效 GUID“a7-invalid-{i + 1:02d}”尝试改色，"
            "确认参数错误没有改变场景；随后读取场景摘要并改用创建工具返回的真实 GUID，"
            f"把原方块设为{_rgb(final)}并平移 ({dx},{dy},{dz})。再次读取场景摘要确认最终中心为 "
            f"({center[0]:g},{center[1]:g},{center[2]:g})，全程不得删除重建。",
            tags=["recovery", "argument_error", "revision", "move", "color", "perception", "final_state"],
            gap="tool_error_recovery",
            family="invalid_guid_final_state",
            asserts=[_count({}, 1), _property({"color": final[1]}, {"center": center})],
        ))

    expected = [f"a7-{i:03d}" for i in range(1, 201)]
    if len(tasks) != 200 or [task["id"] for task in tasks] != expected:
        raise AssertionError("A7 task generation produced an invalid ID sequence")
    return tasks


def render_jsonl(tasks: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(task, ensure_ascii=False, separators=(",", ":")) + "\n"
        for task in tasks
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render_jsonl(build_tasks())
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"A7 task file is stale: {args.output}")
        print(f"A7 task file is current ({args.output}, 200 tasks).")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Generated {args.output} (200 tasks).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
