#!/usr/bin/env python3
"""Deterministically generate the 200-task phase3 long-tail expansion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "eval" / "tasks" / "phase3_expansion.jsonl"

COLORS = [
    ("朱红", [220, 60, 50]), ("湖蓝", [40, 130, 210]),
    ("翠绿", [40, 170, 90]), ("琥珀", [230, 150, 30]),
    ("紫罗兰", [140, 80, 190]), ("青绿", [20, 170, 170]),
    ("玫红", [210, 60, 140]), ("靛蓝", [70, 80, 180]),
    ("橄榄", [130, 150, 50]), ("棕褐", [150, 100, 60]),
    ("珊瑚", [235, 105, 85]), ("天蓝", [80, 170, 230]),
    ("松绿", [45, 145, 105]), ("金黄", [240, 190, 45]),
    ("兰紫", [125, 90, 205]), ("孔雀蓝", [30, 145, 170]),
    ("莓红", [190, 55, 110]), ("群青", [55, 75, 170]),
    ("草绿", [100, 165, 55]), ("陶土", [175, 95, 65]),
]


def _color(index: int) -> tuple[str, list[int]]:
    return COLORS[index % len(COLORS)]


def _rgb(name: str, value: list[int]) -> str:
    return f"{name}色 RGB({value[0]},{value[1]},{value[2]})"


def _count(selector: dict[str, Any], n: int) -> dict[str, Any]:
    return {"kind": "count", "selector": selector, "n": n}


def _property(selector: dict[str, Any], props: dict[str, Any], tol: float = 1.0) -> dict[str, Any]:
    return {"kind": "property", "selector": selector, "props": props, "tol": tol}


def _spatial(a: dict[str, Any], b: dict[str, Any], relation: str, *, value: Any = None, tol: float = 1.0) -> dict[str, Any]:
    spec: dict[str, Any] = {"kind": "spatial", "a": a, "b": b, "relation": relation, "tol": tol}
    if value is not None:
        spec["value"] = value
    return spec


def _task(number: int, instruction: str, tags: list[str], difficulty: int, asserts: list[dict[str, Any]], *, clean: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": f"p3-{number:03d}", "instruction": instruction,
        "tags": tags, "difficulty": difficulty, "asserts": asserts,
    }
    if clean:
        row["requires_clean_tool_trace"] = True
    return row


def build_tasks() -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []

    # 001-010: robust through-hole booleans.
    for i in range(10):
        name, color = _color(i)
        width, depth, height, radius = 38 + i * 2, 30 + i, 18 + i, 4 + i % 3
        tasks.append(_task(
            i + 1,
            f"创建一个 {width}x{depth}x{height} 的{_rgb(name, color)}盒体；在盒体 X/Y 正中心放置半径 {radius}、高度 {height + 10} 的圆柱刀具，使刀具底面位于 Z=-5 并贯穿上下表面。用圆柱从盒体做布尔差集，最终只保留一个带竖直通孔的{name}盒体，并调用场景摘要确认。",
            ["boolean", "box", "cylinder", "perception", "recovery", "high_complexity"], 5,
            [_count({}, 1), _property({"color": color}, {"size": [width, depth, height]}, 1.2)], clean=True,
        ))

    # 011-020: hollow cylinders.
    for i in range(10):
        name, color = _color(i + 10)
        outer, inner, height = 16 + i, 5 + i % 4, 22 + i * 2
        tasks.append(_task(
            11 + i,
            f"制作一根外半径 {outer}、高度 {height} 的{_rgb(name, color)}圆柱；再建立内半径 {inner}、高度 {height + 8} 的同轴圆柱，内圆柱底面下移到 Z=-4。完成布尔差集得到上下贯通的空心圆柱，删除刀具结果，仅保留一个实体并用场景摘要复核外包围盒。",
            ["boolean", "cylinder", "concentric", "perception", "recovery"], 5,
            [_count({}, 1), _property({"color": color}, {"size": [outer * 2, outer * 2, height]}, 1.2)], clean=True,
        ))

    # 021-030: sphere cuts that deliberately intersect an exterior face.
    for i in range(10):
        name, color = _color(i)
        width, depth, height, radius = 42 + i, 32 + i, 16 + i, 7 + i % 4
        center = [width / 2, depth / 2, height]
        tasks.append(_task(
            21 + i,
            f"创建 {width}x{depth}x{height} 的{_rgb(name, color)}方块；建立半径 {radius} 的球形刀具并把球心移动到 ({center[0]:g},{center[1]:g},{height})，让球体明确穿出方块顶面。用球体从方块切出顶部球冠凹槽，最终场景只能保留切割后的一个{name}实体。",
            ["boolean", "sphere", "box", "spatial", "perception", "recovery"], 5,
            [_count({}, 1), _property({"color": color}, {"size": [width, depth, height]}, 1.5)], clean=True,
        ))

    # 031-040: supported objects, avoiding false center-alignment assumptions.
    for i in range(10):
        base_name, base_color = _color(i + 10)
        left_name, left_color = _color(i)
        right_name, right_color = _color(i + 1)
        width, depth, height = 40 + i * 2, 28 + i, 6 + i % 3
        r1, r2 = 3 + i % 2, 4 + i % 3
        left_center = [r1 + 3, depth / 2, height + r1]
        right_center = [width - r2 - 3, depth / 2, height + r2]
        tasks.append(_task(
            31 + i,
            f"搭建一个 {width}x{depth}x{height} 的{_rgb(base_name, base_color)}底座；把半径 {r1} 的{_rgb(left_name, left_color)}球放到球心 ({left_center[0]:g},{left_center[1]:g},{left_center[2]:g})，把半径 {r2} 的{_rgb(right_name, right_color)}球放到球心 ({right_center[0]:g},{right_center[1]:g},{right_center[2]:g})。两球底部都必须贴合 Z={height}，其水平投影完整落在底座范围内，但不要求与底座中心对齐。",
            ["stack", "supported_by", "sphere", "spatial", "perception", "color"], 4,
            [
                _count({}, 3), _property({"color": left_color}, {"center": left_center}),
                _property({"color": right_color}, {"center": right_center}),
                _spatial({"color": left_color}, {"color": base_color}, "supported_by"),
                _spatial({"color": right_color}, {"color": base_color}, "supported_by"),
            ],
        ))

    # 041-050: centered three-level grouped stacks.
    for i in range(10):
        n0, c0 = _color(i); n1, c1 = _color(i + 7); n2, c2 = _color(i + 14)
        base, middle, top = 44 + i * 2, 32 + i * 2, 22 + i
        h0, h1, h2 = 6 + i % 2, 5 + i % 3, 4 + i % 2
        group = f"P3三层台-{i + 1:02d}"
        tasks.append(_task(
            41 + i,
            f"用 {base}x{base}x{h0} 的{_rgb(n0, c0)}底层、{middle}x{middle}x{h1} 的{_rgb(n1, c1)}中层和 {top}x{top}x{h2} 的{_rgb(n2, c2)}顶层制作三层居中台座。各层依次紧贴叠放，全部加入群组“{group}”，并在完成后读取场景摘要确认层级和数量。",
            ["stack", "group", "align", "spatial", "compose", "perception"], 5,
            [_count({"in_group": group}, 3), _spatial({"color": c1}, {"color": c0}, "on_top_of"), _spatial({"color": c2}, {"color": c1}, "on_top_of")],
        ))

    # 051-060: grouped fence rows with layer assignment.
    for i in range(10):
        name, color = _color(i + 5)
        radius, height, gap = 2 + i % 2, 20 + i, 9 + i % 4
        group, layer = f"P3栏杆-{i + 1:02d}", f"P3结构::栏杆-{i + 1:02d}"
        tasks.append(_task(
            51 + i,
            f"创建 5 根半径 {radius}、高度 {height} 的{_rgb(name, color)}圆柱，底面均在 Z=0，沿 X 轴以中心间距 {gap + radius * 2} 排成一行。把五根柱加入群组“{group}”，并全部移入图层“{layer}”；最后用场景摘要核对群组和图层。",
            ["array", "cylinder", "group", "layer", "perception", "color"], 4,
            [_count({"in_group": group}, 5), _count({"layer": layer}, 5), _count({"color": color}, 5)],
        ))

    # 061-070: group-aware bottom alignment.
    for i in range(10):
        n0, c0 = _color(i); n1, c1 = _color(i + 8); n2, c2 = _color(i + 15)
        w0, w1, h0, h1, h2 = 10 + i, 12 + i, 12 + i, 16 + i, 20 + i
        group = f"P3抬高模块-{i + 1:02d}"
        tasks.append(_task(
            61 + i,
            f"创建{_rgb(n0, c0)}、{w0}x10x{h0} 方块和{_rgb(n1, c1)}、{w1}x10x{h1} 方块，使二者最小 X 分别为 0 与 24，并把二者整体抬高 6 后组成群组“{group}”。另创建{_rgb(n2, c2)}、半径 5、高 {h2} 的圆柱，使其轴心 X=52 且底面 Z=0。使用群组感知对齐，让群组与圆柱沿 Z 轴最小端对齐，保持群组内部相对位置不变。",
            ["group", "align", "cylinder", "spatial", "recovery", "perception"], 5,
            [
                _count({"in_group": group}, 2),
                _property({"color": c0}, {"center": [w0 / 2, 5, h0 / 2]}),
                _property({"color": c1}, {"center": [24 + w1 / 2, 5, h1 / 2]}),
                _property({"color": c2}, {"center": [52, 0, h2 / 2]}),
            ],
        ))

    # 071-080: exact net-spacing distribution with mixed widths.
    for i in range(10):
        widths = [8 + i % 3, 12 + i % 2, 10 + i % 4, 14 + i % 3]
        spacing = 5 + i % 4
        selected = [_color(i + offset * 5) for offset in range(4)]
        centers = [0.0]
        for left, right in zip(widths, widths[1:]):
            centers.append(centers[-1] + left / 2 + spacing + right / 2)
        color_text = "、".join(_rgb(name, color) for name, color in selected)
        tasks.append(_task(
            71 + i,
            f"创建 {color_text}四个高度和深度均为 8、X 向宽度依次为 {widths[0]}、{widths[1]}、{widths[2]}、{widths[3]} 的方块。先让它们沿 X 轴按该顺序分散，再以净间距 {spacing} 执行等距分布，第一个方块中心固定在 X=0；完成后用场景摘要检查相邻包围盒净空。",
            ["distribute", "array", "spacing", "box", "perception", "spatial"], 4,
            [_count({}, 4), *[_property({"color": selected[j][1]}, {"center": [centers[j], 4, 4]}) for j in range(4)]],
        ))

    # 081-090: undo removes the transient object, not only a property edit.
    for i in range(10):
        final_name, final = _color(i + 10)
        radius, height = 4 + i % 3, 18 + i
        tasks.append(_task(
            81 + i,
            f"先创建一个尺寸 {18 + i}x{12 + i}x8 的默认颜色临时方块，不改色也不执行任何其他操作，立即调用 undo_last_action 撤销这次创建。随后创建一个半径 {radius}、高度 {height} 的{_rgb(final_name, final)}圆柱并读取场景摘要。最终只能存在该圆柱，临时方块必须不存在。",
            ["undo", "revision", "recovery", "perception", "cylinder", "color"], 4,
            [_count({}, 1), _count({"color": final}, 1), _property({"color": final}, {"size": [radius * 2, radius * 2, height]})],
        ))

    # 091-100: explicit invalid-GUID recovery exercises.
    for i in range(10):
        name, color = _color(i + 5)
        width, depth, height = 16 + i, 10 + i, 8 + i
        dx, dy = 24 + i * 2, -10 - i
        tasks.append(_task(
            91 + i,
            f"创建一个 {width}x{depth}x{height} 的{_rgb(name, color)}方块。先故意用无效 GUID“not-a-valid-guid-{i + 1}”尝试移动一次以验证参数错误接管；收到错误后必须改用创建工具返回的真实 GUID，将方块平移 ({dx},{dy},0)，调用场景摘要确认最终只有一个正确方块。",
            ["recovery", "argument_error", "move", "perception", "box", "color"], 5,
            [_count({"color": color}, 1), _property({"color": color}, {"center": [dx + width / 2, dy + depth / 2, height / 2]})],
        ))

    # 101-110: perceive the tallest member before placing a marker.
    for i in range(10):
        marker_name, marker = _color(i)
        heights, xs = [16 + i, 30 + i * 2, 22 + i], [0, 24 + i, 52 + i * 2]
        radius = 3 + i % 2
        # Preserve p3-103's already-collected instruction; clarify only tasks
        # whose prior attempts exposed the ambiguous "top-face center" wording.
        marker_placement = (
            "最高圆柱顶面中心"
            if i == 2
            else "最高圆柱上，使球体底部紧贴圆柱顶面且球心与该顶面中心的 X/Y 坐标一致"
        )
        tasks.append(_task(
            101 + i,
            f"在 X={xs[0]}、{xs[1]}、{xs[2]} 处创建三根半径 5、底面 Z=0、高度分别为 {heights[0]}、{heights[1]}、{heights[2]} 的圆柱。必须先调用场景摘要识别最高圆柱，再把半径 {radius} 的{_rgb(marker_name, marker)}标记球放到{marker_placement}；不得按创建顺序猜测。",
            ["perception", "select", "cylinder", "stack", "spatial", "sphere"], 4,
            [_count({}, 4), _spatial({"color": marker}, {"size": [10, 10, heights[1]]}, "on_top_of")],
        ))

    # 111-120: perceive the shortest member, delete it, then bridge survivors.
    for i in range(10):
        survivor_name, survivor = _color(i + 10)
        heights, x2 = [24 + i, 12 + i, 32 + i], 48 + i * 2
        tasks.append(_task(
            111 + i,
            f"在 X=0、X={24 + i}、X={x2} 创建三根半径 4、高度依次为 {heights[0]}、{heights[1]}、{heights[2]} 的圆柱，并全部设为{_rgb(survivor_name, survivor)}。读取场景摘要找出最矮圆柱并用 delete_objects 精准删除它，再画一条连接剩余两根圆柱底面中心的直线。最终保留两根圆柱和一条长度 {x2} 的直线。",
            ["perception", "select", "delete", "line", "revision", "cylinder"], 5,
            [_count({"color": survivor}, 2), _count({"type": "Curve"}, 1), _property({"type": "Curve"}, {"size": [x2, 0, 0]})],
        ))

    # 121-130: deterministic local rotation plus translation.
    for i in range(10):
        name, color = _color(i)
        width, depth, height = 28 + i * 2, 10 + i, 8 + i % 4
        dx, dy = 18 + i, 12 + i * 2
        tasks.append(_task(
            121 + i,
            f"创建 {width}x{depth}x{height} 的{_rgb(name, color)}长方体，绕自身包围盒中心的 Z 轴正向旋转 90 度，再平移 ({dx},{dy},0)。旋转不得使用世界原点作为中心；完成后读取场景摘要核对 X/Y 尺寸已交换且中心只发生指定平移。",
            ["rotate", "move", "box", "perception", "spatial", "multi_step"], 4,
            [_count({"color": color}, 1), _property({"color": color}, {"size": [depth, width, height], "center": [width / 2 + dx, depth / 2 + dy, height / 2]})],
        ))

    # 131-140: non-uniform scaling anchored at object center.
    for i in range(10):
        name, color = _color(i + 10)
        width, depth, height = 12 + i, 16 + i, 10 + i
        factors = [1.5 + (i % 2) * 0.5, 0.5 + (i % 3) * 0.25, 2.0]
        final_size = [width * factors[0], depth * factors[1], height * factors[2]]
        tasks.append(_task(
            131 + i,
            f"创建 {width}x{depth}x{height} 的{_rgb(name, color)}方块，以自身中心为锚点按 XYZ={factors} 做非均匀缩放。禁止以世界原点缩放；完成后调用 get_bounding_box 与场景摘要，确认中心保持不变、三轴尺寸分别变为 {final_size[0]:g}、{final_size[1]:g}、{final_size[2]:g}。",
            ["scale", "box", "perception", "spatial", "edit"], 4,
            [_count({"color": color}, 1), _property({"color": color}, {"size": final_size, "center": [width / 2, depth / 2, height / 2]})],
        ))

    # 141-150: three-sphere tangent chains.
    for i in range(10):
        colors = [_color(i + offset * 6) for offset in range(3)]
        radii = [4 + i % 3, 6 + i % 2, 3 + i % 4]
        x1, x2, x3 = 0, radii[0] + radii[1], radii[0] + 2 * radii[1] + radii[2]
        tasks.append(_task(
            141 + i,
            f"创建半径依次为 {radii[0]}、{radii[1]}、{radii[2]} 的三个球，分别设为{_rgb(*colors[0])}、{_rgb(*colors[1])}、{_rgb(*colors[2])}。将球心放在 X={x1}、{x2}、{x3} 且 Y=Z=0，使第一个只与第二个外切、第二个只与第三个外切；调用场景摘要复核，不允许球体互相穿透。",
            ["tangent", "sphere", "spatial", "perception", "compose", "color"], 4,
            [_count({}, 3), _spatial({"color": colors[0][1]}, {"color": colors[1][1]}, "tangent"), _spatial({"color": colors[1][1]}, {"color": colors[2][1]}, "tangent")],
        ))

    # 151-160: concentric grouped spheres and cylinder.
    for i in range(10):
        outer_name, outer = _color(i); inner_name, inner = _color(i + 10); cylinder_name, cylinder = _color(i + 5)
        outer_r, inner_r, cyl_r, cyl_h = 14 + i, 6 + i % 4, 3 + i % 3, 18 + i * 2
        center_z, group = cyl_h / 2, f"P3同心核-{i + 1:02d}"
        tasks.append(_task(
            151 + i,
            f"创建半径 {outer_r} 的{_rgb(outer_name, outer)}球和半径 {inner_r} 的{_rgb(inner_name, inner)}球，并将二者球心共同移到 (0,0,{center_z:g})；再创建半径 {cyl_r}、高 {cyl_h} 的{_rgb(cylinder_name, cylinder)}圆柱，使圆柱轴线与球心同轴且包围盒中心也是 (0,0,{center_z:g})。把三者加入群组“{group}”并读取场景摘要。",
            ["concentric", "group", "sphere", "cylinder", "perception", "spatial"], 5,
            [_count({"in_group": group}, 3), _spatial({"color": outer}, {"color": inner}, "concentric"), _spatial({"color": inner}, {"color": cylinder}, "concentric")],
        ))

    # 161-170: circle extrusion plus supported marker.
    for i in range(10):
        body_name, body = _color(i + 10); marker_name, marker = _color(i)
        radius, height, marker_r = 10 + i, 12 + i * 2, 3 + i % 3
        tasks.append(_task(
            161 + i,
            f"在世界原点画半径 {radius} 的圆并沿 Z 轴向上拉伸 {height} 形成实体，将拉伸体设为{_rgb(body_name, body)}。再创建半径 {marker_r} 的{_rgb(marker_name, marker)}球，使用精确贴合把球放在拉伸体顶面中心；最后读取场景摘要确认只剩拉伸实体和标记球。",
            ["circle", "extrude", "stack", "place", "perception", "color"], 4,
            [_count({}, 2), _property({"color": body}, {"size": [radius * 2, radius * 2, height]}), _spatial({"color": marker}, {"color": body}, "on_top_of")],
        ))

    # 171-180: all six place_on_at directions with exact centers.
    sides = ["top", "bottom", "left", "right", "front", "back", "top", "right", "front", "back"]
    for i, side in enumerate(sides):
        base_name, base = _color(i); target_name, target = _color(i + 10)
        width, depth, height, radius = 30 + i * 2, 24 + i, 14 + i, 3 + i % 3
        centers = {
            "top": [width / 2, depth / 2, height + radius], "bottom": [width / 2, depth / 2, -radius],
            "left": [-radius, depth / 2, height / 2], "right": [width + radius, depth / 2, height / 2],
            "front": [width / 2, -radius, height / 2], "back": [width / 2, depth + radius, height / 2],
        }
        chinese_side = {"top": "上方", "bottom": "下方", "left": "左侧", "right": "右侧", "front": "前侧", "back": "后侧"}[side]
        tasks.append(_task(
            171 + i,
            f"创建 {width}x{depth}x{height} 的{_rgb(base_name, base)}参考方块和半径 {radius} 的{_rgb(target_name, target)}目标球。必须调用 place_on_at 将目标球吸附到参考方块{chinese_side}（side={side}），同时让另外两个方向自动居中；完成后读取包围盒确认两者恰好接触。",
            ["place", "spatial", "sphere", "box", "perception", "alignment"], 4,
            [_count({}, 2), _property({"color": target}, {"center": centers[side]})],
        ))

    # 181-190: five-part table assemblies.
    for i in range(10):
        top_name, top = _color(i); leg_name, leg = _color(i + 10)
        width, depth, thickness, leg_h, leg_w = 46 + i * 2, 30 + i, 4 + i % 2, 24 + i, 4
        group, layer = f"P3工作台-{i + 1:02d}", f"P3装配::工作台-{i + 1:02d}"
        tasks.append(_task(
            181 + i,
            f"制作一个 {width}x{depth}x{thickness} 的{_rgb(top_name, top)}桌面和四根 {leg_w}x{leg_w}x{leg_h} 的{_rgb(leg_name, leg)}桌腿。四腿底面位于 Z=0、靠近桌面四角，腿顶贴合桌面底面；把桌面与四腿组成群组“{group}”并全部移到图层“{layer}”。最后读取场景摘要验证五个成员。",
            ["high_complexity", "compose", "group", "layer", "stack", "perception"], 5,
            [_count({"in_group": group}, 5), _count({"layer": layer}, 5), _count({"color": leg}, 4), _property({"color": top}, {"center": [width / 2, depth / 2, leg_h + thickness / 2]})],
        ))

    # 191-200: explicit final-state correction without delete/recreate.
    for i in range(10):
        wrong_name, wrong = _color(i); final_name, final = _color(i + 10)
        width, depth, height = 18 + i, 12 + i, 10 + i
        dx, dz = 26 + i * 2, 8 + i
        final_center = [width / 2 + dx, depth / 2, height / 2 + dz]
        correction = [final_center[0] + 10, final_center[1] - 5, final_center[2]]
        tasks.append(_task(
            191 + i,
            f"创建 {width}x{depth}x{height} 的方块，先故意设成{wrong_name}色并将其中心移到错误位置 (-10,5,0)。调用场景摘要发现错误后，把同一个方块改为{_rgb(final_name, final)}，并从当前错误位置精确平移向量 ({correction[0]:g},{correction[1]:g},{correction[2]:g})，使最终中心为 ({final_center[0]:g},{final_center[1]:g},{final_center[2]:g})；不得删除重建。最终只保留一个方块，并再次调用场景摘要确认颜色与中心。",
            ["revision", "recovery", "perception", "move", "color", "edit", "final_state"], 5,
            [_count({"color": wrong}, 0), _count({"color": final}, 1), _property({"color": final}, {"center": final_center})],
        ))

    if len(tasks) != 200 or [row["id"] for row in tasks] != [f"p3-{i:03d}" for i in range(1, 201)]:
        raise AssertionError("phase3 task generation produced an invalid ID sequence")
    return tasks


def render_jsonl(tasks: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(task, ensure_ascii=False, separators=(",", ":")) + "\n" for task in tasks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Verify that the committed file is current")
    args = parser.parse_args()
    rendered = render_jsonl(build_tasks())
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"phase3 task file is stale: {args.output}")
        print(f"Phase3 task file is current ({args.output}, 200 tasks).")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Generated {args.output} (200 tasks).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
