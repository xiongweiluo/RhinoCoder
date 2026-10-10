"""Rhino-main-thread alias snapshot/resolution for the isolated R candidate.

Python 3.9 + stdlib at import time. No HTTP route or write operation is
registered. Raw GUIDs stay inside Rhino; only alias names and a document-bound
digest may be exported to the model/review process.
"""

from __future__ import annotations

import re


_ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_EMPTY_GUID = "00000000-0000-0000-0000-000000000000"


class AliasGateError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _all_objects(doc):
    import Rhino  # noqa: PLC0415

    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.NormalObjects = True
    settings.HiddenObjects = True
    settings.LockedObjects = True
    settings.ReferenceObjects = True
    settings.IncludeLights = True
    settings.IncludeGrips = True
    return list(doc.Objects.GetObjectList(settings))


def _name(obj):
    attributes = getattr(obj, "Attributes", None)
    if attributes is None:
        raise AliasGateError("object_attributes_unavailable")
    value = attributes.Name
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AliasGateError("object_name_unreadable")
    return value


def candidate_scene_snapshot(doc, gate):
    """Export one scene bound to the atomic gate's exact document/session."""

    try:
        before = gate.snapshot()  # Enforces Rhino main-thread ownership.
        objects = _all_objects(doc)
        aliases = [name for obj in objects if (name := _name(obj)) and _ALIAS.fullmatch(name)]
        summary = {
            "aliases": aliases,
            "object_count": len(objects),
            "unit": str(doc.ModelUnitSystem),
            "document_key": before["document_key"],
        }
        after = gate.snapshot()
    except AliasGateError:
        raise
    except Exception as exc:
        raise AliasGateError("scene_unavailable") from exc
    if before != after:
        raise AliasGateError("scene_changed")
    return {
        "document_key": before["document_key"],
        "revision": before["revision"],
        "scene_sha256": before["scene_sha256"],
        "summary": summary,
    }


def _writable_layer(doc, index):
    """Require visible, unlocked current layer and every ancestor."""

    try:
        layer = doc.Layers.FindIndex(index)
        seen = set()
        while layer is not None:
            layer_id = str(layer.Id).lower()
            if layer_id in seen or layer.IsDeleted or not layer.IsVisible or layer.IsLocked:
                return False
            seen.add(layer_id)
            parent = str(layer.ParentLayerId).lower()
            if parent == _EMPTY_GUID:
                return True
            layer = doc.Layers.FindId(layer.ParentLayerId)
    except Exception:
        return False
    return False


def resolve_unique_writable_alias(doc, gate, expected_snapshot, alias):
    """Return a Rhino object ID only inside Rhino after exact scene recheck.

    The caller must still perform human consent consumption and the durable
    RhinoAtomicGate.execute reservation before any mutation. This function is
    target resolution, not approval or execution.
    """

    if not isinstance(alias, str) or not _ALIAS.fullmatch(alias):
        raise AliasGateError("invalid_alias")
    if not isinstance(expected_snapshot, dict):
        raise AliasGateError("invalid_expected_scene")
    current = candidate_scene_snapshot(doc, gate)
    if current != expected_snapshot:
        raise AliasGateError("scene_changed")
    try:
        matches = [obj for obj in _all_objects(doc) if _name(obj) == alias]
    except AliasGateError:
        raise
    except Exception as exc:
        raise AliasGateError("scene_unavailable") from exc
    if len(matches) != 1:
        raise AliasGateError("target_not_unique")
    obj = matches[0]
    try:
        writable = bool(obj.IsNormal) and not bool(obj.IsReference) and _writable_layer(
            doc, obj.Attributes.LayerIndex,
        )
        object_id = obj.Id
    except Exception as exc:
        raise AliasGateError("target_unavailable") from exc
    if not writable:
        raise AliasGateError("target_not_writable")
    if candidate_scene_snapshot(doc, gate) != expected_snapshot:
        raise AliasGateError("scene_changed")
    return object_id
