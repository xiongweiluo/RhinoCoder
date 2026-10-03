"""Independent task-level readback assertions; no model, tool forcing or writes.

Requires actual native volume/topology/vertices and attributes, not bbox-only
or self-reported success. This pure geometric component is not itself a proof
of consent/ledger/cleanup; a formal auditor must require those independently.
"""
from __future__ import annotations

import math

ABS_TOL = 1e-6
REL_TOL = 1e-6
FIELDS = frozenset({"min", "max", "volume", "centroid", "solid", "face_count",
                    "edge_count", "vertices", "layer", "color", "groups", "geometry_sha256"})


def _equal(actual, expected):
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isfinite(actual) and math.isfinite(expected) and math.isclose(
            actual, expected, abs_tol=ABS_TOL, rel_tol=REL_TOL)
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, dict):
        return isinstance(actual, dict) and set(actual) == set(expected) and all(_equal(actual[k], expected[k]) for k in expected)
    return type(actual) is type(expected) and actual == expected


def score_readback(before, after, assertions, *, read_result=None):
    """Return all failures; no success-subset denominator or assertion defaults."""
    failures = []
    if not isinstance(assertions, dict) or set(assertions) != {"object_count", "objects", "unchanged", "read_result"}:
        raise ValueError("complete frozen task assertions required")
    if type(assertions["object_count"]) is not int or not 0 <= assertions["object_count"] <= 16:
        raise ValueError("invalid asserted object count")
    if not isinstance(assertions["objects"], dict) or not isinstance(assertions["unchanged"], list):
        raise ValueError("invalid assertions")
    indexes = []
    for scene in (before, after):
        if not isinstance(scene, dict) or scene.get("unit") != "Millimeters" or not isinstance(scene.get("objects"), list):
            return {"geometry_passed": False, "failures": ["native_scene_missing"], "formal_task_passed": False}
        objects = scene["objects"]
        if any(not isinstance(o, dict) or not isinstance(o.get("alias"), str) for o in objects):
            return {"geometry_passed": False, "failures": ["native_objects_invalid"], "formal_task_passed": False}
        indexed = {o["alias"]: o for o in objects}
        if len(indexed) != len(objects):
            return {"geometry_passed": False, "failures": ["duplicate_alias"], "formal_task_passed": False}
        indexes.append(indexed)
    prior, current = indexes
    if len(current) != assertions["object_count"]:
        failures.append("object_count")
    for alias, fields in assertions["objects"].items():
        if not isinstance(fields, dict) or not fields or set(fields)-FIELDS:
            raise ValueError("unknown/empty object assertion")
        # Every scored solid requires actual 3-D mass/topology evidence. Pure
        # attribute tasks may additionally require unchanged geometry hash.
        if not {"volume", "solid", "face_count"} <= set(fields):
            raise ValueError("bbox/attributes alone cannot score a solid task")
        if alias not in current:
            failures.append(alias+":missing")
            continue
        for field, expected in fields.items():
            actual = current[alias].get(field)
            exact = (type(actual) is int and type(expected) is int and actual == expected
                     if field in {"face_count", "edge_count"} else
                     actual == expected and isinstance(actual, list) and all(type(n) is int for n in actual)
                     if field == "color" else _equal(actual, expected))
            if field not in current[alias] or not exact:
                failures.append(alias+":"+field)
    for alias in assertions["unchanged"]:
        if not isinstance(alias, str): raise ValueError("invalid unchanged alias")
        if alias not in prior or alias not in current or not _equal(prior[alias], current[alias]):
            failures.append(alias+":unexpected_change")
    if not _equal(read_result, assertions["read_result"]):
        failures.append("read_result")
    return {"geometry_passed": not failures, "failures": failures, "formal_task_passed": False,
            "scope": "geometric/attribute component only; separate raw permission/ledger/cleanup audit mandatory"}
