"""
eval/scene_assert.py  —  程序化场景状态断言验证器（阶段一核心）

围绕 get_scene_summary 的结构化输出做断言，是评估（run_eval）与数据自动验收
（data_collector）的共同枢纽。

设计要点（吸收 V2 Review）：
  1. 禁用硬编码 UUID：LLM 生成的 object_id 随机，断言一律用「特征选择器 Selector」
     按 type/color/layer/name/size 等特征定位物体。
  2. 高内聚断言原语：assert_count / assert_property / assert_spatial_relation，
     不写面条式断言。
  3. Partial Pass：verify() 返回 score（通过断言数 / 总数），0<score<1 即部分通过，
     其轨迹对 RLHF 仍有偏好价值。

get_scene_summary 返回结构（来自 plugin/rhino_listener/tools_perception.py）:
  {
    "objects": [
      {
        "object_id": str,           # 随机 GUID —— 禁止在断言中引用
        "name":      str,           # 物体名（未命名为 "Unnamed"）
        "type":      str,           # Rhino 几何类别，非语义形状名！见下表
        "center":    [x, y, z],     # BoundingBox 中心（已 round 2 位）
        "layer":     str,
        "color":     [r, g, b],     # 0-255
        "groups":    [str, ...],    # 所属群组名
        "size":      [w, d, h],     # BoundingBox 三轴尺寸（已 round 2 位）
      }, ...
    ],
    "total": int, "capped": bool
  }

⚠️ type 是几何类别而非形状语义：
    create_sphere   → rs.AddSphere   → "Surface"
    create_box      → rs.AddBox      → "Polysurface"（或 "Extrusion"）
    create_cylinder → rs.AddCylinder → "Polysurface"（带盖）/"Surface"
    create_line     → rs.AddLine     → "Curve"
    create_circle   → rs.AddCircle   → "Curve"
  因此「球 vs 立方体」靠 type（Surface vs Polysurface）+ size 组合区分，
  不能指望 type == "Sphere"。编写任务断言时请遵循该约定。
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# 默认容差
# ---------------------------------------------------------------------------
TOL_POS = 0.5     # 位置/尺寸容差（summary 已 round 2 位，曲面 bbox 亦有微小误差）
TOL_COLOR = 12    # 颜色分量容差（0-255）

Obj = dict[str, Any]


# ===========================================================================
# 特征选择器：按特征定位物体（禁用硬编码 UUID）
# ===========================================================================
def _match_vec3(actual: list, expected: list, tol: float) -> bool:
    if actual is None or expected is None or len(actual) != 3 or len(expected) != 3:
        return False
    return all(abs(float(a) - float(e)) <= tol for a, e in zip(actual, expected))


def _match_color(actual: list, expected: list, tol: int) -> bool:
    if actual is None or expected is None or len(actual) != 3:
        return False
    return all(abs(int(a) - int(e)) <= tol for a, e in zip(actual, expected))


def select(summary: dict, selector: dict) -> list[Obj]:
    """
    按特征筛选物体，返回所有命中的对象 dict 列表。

    selector 支持的字段（全部为「与」关系，缺省即不约束）:
      type:          str 或 [str, ...]   —— 几何类别，大小写不敏感
      color:         [r, g, b]           —— 容差 TOL_COLOR
      layer:         str
      name:          str                 —— 精确
      name_contains: str                 —— 子串
      size:          [w, d, h]           —— 容差 tol（默认 TOL_POS）
      center:        [x, y, z]           —— 容差 tol
      in_group:      str                 —— 属于该群组
      tol:           float               —— 覆盖 size/center 的位置容差
    """
    objs: list[Obj] = summary.get("objects", []) or []
    tol = float(selector.get("tol", TOL_POS))

    want_type = selector.get("type")
    if isinstance(want_type, str):
        want_type = [want_type]
    want_type_lc = [t.lower() for t in want_type] if want_type else None

    out: list[Obj] = []
    for o in objs:
        if want_type_lc is not None and str(o.get("type", "")).lower() not in want_type_lc:
            continue
        if "color" in selector and not _match_color(o.get("color"), selector["color"], TOL_COLOR):
            continue
        if "layer" in selector and o.get("layer") != selector["layer"]:
            continue
        if "name" in selector and o.get("name") != selector["name"]:
            continue
        if "name_contains" in selector and selector["name_contains"] not in str(o.get("name", "")):
            continue
        if "size" in selector and not _match_vec3(o.get("size"), selector["size"], tol):
            continue
        if "center" in selector and not _match_vec3(o.get("center"), selector["center"], tol):
            continue
        if "in_group" in selector and selector["in_group"] not in (o.get("groups") or []):
            continue
        out.append(o)
    return out


def select_one(summary: dict, selector: dict) -> tuple[Optional[Obj], str]:
    """选中且仅选中一个物体；否则返回 (None, 原因)。"""
    matched = select(summary, selector)
    if len(matched) == 1:
        return matched[0], ""
    if not matched:
        return None, f"selector 未命中任何物体: {selector}"
    return None, f"selector 命中 {len(matched)} 个物体（期望唯一）: {selector}"


# ===========================================================================
# bbox 辅助（由 center + size 复原 min/max）
# ===========================================================================
def _bounds(o: Obj) -> tuple[list, list]:
    c, s = o.get("center", [0, 0, 0]), o.get("size", [0, 0, 0])
    mn = [c[i] - s[i] / 2.0 for i in range(3)]
    mx = [c[i] + s[i] / 2.0 for i in range(3)]
    return mn, mx


# ===========================================================================
# 断言原语
# ===========================================================================
def assert_count(summary: dict, selector: dict, n: int, op: str = "==") -> tuple[bool, str]:
    cnt = len(select(summary, selector))
    ok = {
        "==": cnt == n, ">=": cnt >= n, "<=": cnt <= n,
        ">": cnt > n, "<": cnt < n,
    }.get(op, cnt == n)
    return ok, ("" if ok else f"count {cnt} {op} {n} 不成立 (selector={selector})")


def assert_property(obj: Obj, key: str, expected: Any, tol: float = TOL_POS) -> tuple[bool, str]:
    actual = obj.get(key)
    if key == "color":
        ok = _match_color(actual, expected, TOL_COLOR)
    elif key in ("size", "center"):
        ok = _match_vec3(actual, expected, tol)
    elif key == "groups":
        ok = expected in (actual or [])
    else:
        ok = actual == expected
    return ok, ("" if ok else f"属性 {key}: 实际 {actual} ≠ 期望 {expected} (tol={tol})")


def assert_spatial_relation(
    a: Obj, b: Obj, relation: str, tol: float = TOL_POS, value: Optional[float] = None
) -> tuple[bool, str]:
    """
    基于 BoundingBox（center + size 复原）校验 A 相对 B 的空间关系。
      above          A 整体在 B 之上（A 底面 ≥ B 顶面 - tol）
      below          A 整体在 B 之下
      on_top_of      A 紧贴叠放在 B 上（A 底 ≈ B 顶）且 X/Y 中心对齐
      supported_by    A 贴合在 B 顶面上，且 A 的 X/Y 包围盒完全落在 B 顶面范围内
      center_aligned X/Y 中心对齐（不约束 Z）
      concentric     三轴中心重合
      tangent        两物体中心距 ≈ 各自外接半径之和（按 size/2 估算，近似相切）
      distance       两物体三维中心距 ≈ value
      axis_distance  指定坐标轴的中心差绝对值 ≈ value（需提供 axis）
    """
    amn, amx = _bounds(a)
    bmn, bmx = _bounds(b)
    ac, bc = a.get("center", [0, 0, 0]), b.get("center", [0, 0, 0])

    def xy_aligned() -> bool:
        return abs(ac[0] - bc[0]) <= tol and abs(ac[1] - bc[1]) <= tol

    def horizontally_contained() -> bool:
        """A 的投影落在 B 的顶面范围内；允许不超过位置容差的边缘误差。"""
        return (
            amn[0] >= bmn[0] - tol and amx[0] <= bmx[0] + tol
            and amn[1] >= bmn[1] - tol and amx[1] <= bmx[1] + tol
        )

    if relation == "above":
        ok = amn[2] >= bmx[2] - tol
        return ok, ("" if ok else f"A 底 {amn[2]:.2f} 未高于 B 顶 {bmx[2]:.2f}")
    if relation == "below":
        ok = amx[2] <= bmn[2] + tol
        return ok, ("" if ok else f"A 顶 {amx[2]:.2f} 未低于 B 底 {bmn[2]:.2f}")
    if relation == "on_top_of":
        ok = abs(amn[2] - bmx[2]) <= tol and xy_aligned()
        return ok, ("" if ok else f"A 底 {amn[2]:.2f} 未紧贴 B 顶 {bmx[2]:.2f} 或 XY 未对齐")
    if relation == "supported_by":
        ok = abs(amn[2] - bmx[2]) <= tol and horizontally_contained()
        return ok, (
            "" if ok else (
                f"A 底 {amn[2]:.2f} 未紧贴 B 顶 {bmx[2]:.2f}，"
                "或 A 的 X/Y 投影超出 B 顶面范围"
            )
        )
    if relation == "center_aligned":
        ok = xy_aligned()
        return ok, ("" if ok else f"XY 中心未对齐: A={ac[:2]} B={bc[:2]}")
    if relation == "concentric":
        ok = _match_vec3(ac, bc, tol)
        return ok, ("" if ok else f"中心不重合: A={ac} B={bc}")
    if relation == "axis_distance":
        axis = {"x": 0, "y": 1, "z": 2}.get(str(value.get("axis", "")).lower()) if isinstance(value, dict) else None
        expected = value.get("value") if isinstance(value, dict) else None
        if axis is None or expected is None:
            return False, "axis_distance 需要 value={'axis': 'x'|'y'|'z', 'value': 数值}"
        distance = abs(ac[axis] - bc[axis])
        ok = abs(distance - float(expected)) <= tol
        axis_name = "XYZ"[axis]
        return ok, (
            "" if ok else f"{axis_name} 轴中心距 {distance:.2f} ≠ 期望 {expected} (tol={tol})"
        )
    if relation in ("tangent", "distance"):
        d = sum((ac[i] - bc[i]) ** 2 for i in range(3)) ** 0.5
        if relation == "distance":
            ok = value is not None and abs(d - value) <= tol
            return ok, ("" if ok else f"中心距 {d:.2f} ≠ 期望 {value} (tol={tol})")
        ra = max(a.get("size", [0, 0, 0])) / 2.0
        rb = max(b.get("size", [0, 0, 0])) / 2.0
        ok = abs(d - (ra + rb)) <= tol
        return ok, ("" if ok else f"中心距 {d:.2f} ≠ 半径和 {ra + rb:.2f}（非相切）")
    return False, f"未知空间关系: {relation!r}"


# ===========================================================================
# 声明式断言分发 + Partial Pass
# ===========================================================================
def _run_one_assert(summary: dict, spec: dict) -> tuple[bool, str]:
    """
    支持的断言 spec（由任务文件给出）:
      {"kind":"count","selector":{...},"n":3,"op":"=="}
      {"kind":"property","selector":{...},"props":{"size":[16,16,16],"color":[255,0,0]},"tol":0.5}
      {"kind":"spatial","a":{...},"b":{...},"relation":"above","tol":0.5,"value":50}
    """
    kind = spec.get("kind")

    if kind == "count":
        return assert_count(summary, spec["selector"], int(spec["n"]), spec.get("op", "=="))

    if kind == "property":
        obj, why = select_one(summary, spec["selector"])
        if obj is None:
            return False, why
        tol = float(spec.get("tol", TOL_POS))
        for key, expected in (spec.get("props") or {}).items():
            ok, why = assert_property(obj, key, expected, tol)
            if not ok:
                return False, why
        return True, ""

    if kind == "spatial":
        oa, why = select_one(summary, spec["a"])
        if oa is None:
            return False, f"[A] {why}"
        ob, why = select_one(summary, spec["b"])
        if ob is None:
            return False, f"[B] {why}"
        return assert_spatial_relation(
            oa, ob, spec["relation"], float(spec.get("tol", TOL_POS)), spec.get("value")
        )

    return False, f"未知断言 kind: {kind!r}"


def verify(summary: dict, asserts: list[dict]) -> dict:
    """
    对一组声明式断言求值，返回 Partial-Pass 友好的结果。

    返回:
      {
        "score":   float,          # 通过断言数 / 总数，∈ [0, 1]
        "passed":  bool,           # score == 1.0
        "partial": bool,           # 0 < score < 1
        "results": [{"spec":..., "ok":bool, "reason":str}, ...],
        "failed_reasons": [str, ...],
      }
    """
    results, failed = [], []
    for spec in asserts:
        try:
            ok, reason = _run_one_assert(summary, spec)
        except Exception as exc:  # 断言本身异常视为失败，不中断整批
            ok, reason = False, f"断言执行异常: {type(exc).__name__}: {exc}"
        results.append({"spec": spec, "ok": ok, "reason": reason})
        if not ok:
            failed.append(reason)

    total = len(asserts)
    passed_n = sum(1 for r in results if r["ok"])
    score = (passed_n / total) if total else 0.0
    return {
        "score": round(score, 4),
        "passed": total > 0 and passed_n == total,
        "partial": 0 < passed_n < total,
        "results": results,
        "failed_reasons": failed,
    }
