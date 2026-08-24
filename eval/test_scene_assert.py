"""
eval/test_scene_assert.py  —  scene_assert 原语单测（无需 Rhino，可在 CI 跑）

运行:
    pytest eval/test_scene_assert.py -v
    # 或直接 python eval/test_scene_assert.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.scene_assert import (
    select, select_one, assert_count, assert_property,
    assert_spatial_relation, verify,
)


# ── 构造一个假场景：一个灰色立方体基座 + 其正上方一个红色球体 ──────────────
def _scene() -> dict:
    return {
        "objects": [
            {  # 20x20x2 灰色基座，中心在 (0,0,1)
                "object_id": "guid-base-xyz", "name": "Unnamed", "type": "Polysurface",
                "center": [0, 0, 1], "layer": "Default", "color": [128, 128, 128],
                "groups": [], "size": [20, 20, 2],
            },
            {  # 半径 8 红球，bbox 16x16x16，底面贴在基座顶(z=2)，中心 z=10
                "object_id": "guid-sphere-xyz", "name": "Unnamed", "type": "Surface",
                "center": [0, 0, 10], "layer": "Default", "color": [255, 0, 0],
                "groups": ["g1"], "size": [16, 16, 16],
            },
        ],
        "total": 2, "capped": False,
    }


def test_select_by_type_and_color():
    s = _scene()
    assert len(select(s, {"type": "Surface"})) == 1
    assert len(select(s, {"color": [255, 0, 0]})) == 1
    assert len(select(s, {"type": "Polysurface", "color": [128, 128, 128]})) == 1
    assert len(select(s, {"type": "Mesh"})) == 0


def test_select_one_uniqueness():
    s = _scene()
    obj, why = select_one(s, {"type": "Surface"})
    assert obj is not None and why == ""
    obj, why = select_one(s, {})  # 命中 2 个 → 非唯一
    assert obj is None and "唯一" in why


def test_assert_count():
    s = _scene()
    assert assert_count(s, {}, 2)[0]
    assert assert_count(s, {"type": "Surface"}, 1)[0]
    assert assert_count(s, {}, 1, ">=")[0]
    assert not assert_count(s, {}, 3)[0]


def test_assert_property_color_and_size():
    s = _scene()
    sphere = select_one(s, {"type": "Surface"})[0]
    assert assert_property(sphere, "size", [16, 16, 16])[0]
    assert assert_property(sphere, "color", [255, 0, 0])[0]
    assert assert_property(sphere, "color", [250, 5, 3])[0]   # 容差内
    assert not assert_property(sphere, "color", [0, 0, 255])[0]
    assert assert_property(sphere, "groups", "g1")[0]


def test_spatial_above_and_on_top():
    s = _scene()
    sphere = select_one(s, {"type": "Surface"})[0]
    base = select_one(s, {"type": "Polysurface"})[0]
    assert assert_spatial_relation(sphere, base, "above")[0]
    assert assert_spatial_relation(sphere, base, "center_aligned")[0]
    assert assert_spatial_relation(sphere, base, "on_top_of")[0]   # 球底 z=2 == 基座顶 z=2
    assert not assert_spatial_relation(base, sphere, "above")[0]


def test_spatial_distance():
    s = _scene()
    sphere = select_one(s, {"type": "Surface"})[0]
    base = select_one(s, {"type": "Polysurface"})[0]
    # 中心距 = |10 - 1| = 9
    assert assert_spatial_relation(sphere, base, "distance", value=9.0)[0]
    assert not assert_spatial_relation(sphere, base, "distance", value=5.0)[0]


def test_verify_full_pass():
    s = _scene()
    asserts = [
        {"kind": "count", "selector": {}, "n": 2},
        {"kind": "property", "selector": {"type": "Surface"},
         "props": {"size": [16, 16, 16], "color": [255, 0, 0]}},
        {"kind": "spatial", "a": {"type": "Surface"}, "b": {"type": "Polysurface"},
         "relation": "on_top_of"},
    ]
    res = verify(s, asserts)
    assert res["passed"] and res["score"] == 1.0 and not res["partial"]


def test_verify_partial_pass():
    s = _scene()
    asserts = [
        {"kind": "count", "selector": {}, "n": 2},                       # pass
        {"kind": "property", "selector": {"type": "Surface"},
         "props": {"color": [0, 0, 255]}},                               # fail (球是红的)
    ]
    res = verify(s, asserts)
    assert res["partial"] and res["score"] == 0.5 and not res["passed"]
    assert len(res["failed_reasons"]) == 1


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  ✗ {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} 通过")
    sys.exit(0 if passed == len(fns) else 1)
