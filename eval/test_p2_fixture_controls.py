from __future__ import annotations

import sys
from types import SimpleNamespace

from plugin.rhino_listener import tools_evaluation


class _Handler:
    def __init__(self, token="", body=None):
        self.headers = {"X-RhinoCoder-Eval-Token": token}
        self.body = body
        self.sent = []
        self.enqueued = []

    def _parse_body(self):
        return self.body

    def _send_json(self, status, payload):
        self.sent.append((status, payload))

    def _enqueue_and_wait(self, operation, params):
        self.enqueued.append((operation, params))


def test_fixture_route_requires_matching_eval_token(monkeypatch):
    monkeypatch.setenv("RHINOCODER_EVAL_TOKEN", "expected-token")
    handler = _Handler("wrong", {"fixture_id": "empty", "fixtures_sha256": "0" * 64})
    tools_evaluation._route_setup_p2_fixture(handler)
    assert handler.sent[0][0] == 403
    assert handler.sent[0][1]["error"]["code"] == "eval.invalid_token"
    assert not handler.enqueued


def test_fixture_route_verifies_hash_before_enqueue(monkeypatch):
    monkeypatch.setenv("RHINOCODER_EVAL_TOKEN", "expected-token")
    handler = _Handler("expected-token", {"fixture_id": "empty", "fixtures_sha256": "0" * 64})
    tools_evaluation._route_setup_p2_fixture(handler)
    assert handler.sent[0][0] == 409
    assert handler.sent[0][1]["error"]["code"] == "eval.fixture_integrity"
    assert not handler.enqueued


def test_one_shot_response_loss_fault_is_consumed_once(monkeypatch):
    monkeypatch.setenv("RHINOCODER_EVAL_TOKEN", "expected-token")
    handler = _Handler(
        "expected-token",
        {"fault_id": "drop_first_create_box_response_after_commit"},
    )
    tools_evaluation._route_configure_p2_fault(handler)
    assert handler.sent == [(200, {"status": "ok", "fault_id": "drop_first_create_box_response_after_commit", "armed": True})]
    assert tools_evaluation.consume_response_drop("create_box") is True
    assert tools_evaluation.consume_response_drop("create_box") is False


def test_fixture_setup_creates_named_colored_selected_objects_and_groups(monkeypatch):
    class Doc:
        class ObjectsTable:
            @staticmethod
            def Delete(object_id, quiet):
                return True

        Objects = ObjectsTable()

        @staticmethod
        def ClearUndoRecords(purge):
            assert purge is True

    monkeypatch.setitem(sys.modules, "scriptcontext", SimpleNamespace(doc=Doc()))

    class FakeRS:
        objects = {}
        groups = {}
        selected = set()
        serial = 0

        @classmethod
        def AllObjects(cls):
            return list(cls.objects)

        @classmethod
        def NormalObjects(cls):
            return list(cls.objects)

        @classmethod
        def DeleteObjects(cls, object_ids):
            for object_id in object_ids:
                cls.objects.pop(object_id, None)
            return object_ids

        @classmethod
        def AddBox(cls, corners):
            cls.serial += 1
            object_id = "box-%d" % cls.serial
            cls.objects[object_id] = {"corners": corners, "groups": []}
            return object_id

        @classmethod
        def ObjectName(cls, object_id, value=None):
            if value is not None:
                cls.objects[object_id]["name"] = value
            return cls.objects[object_id].get("name", "")

        @staticmethod
        def IsLayer(layer):
            return True

        @classmethod
        def ObjectLayer(cls, object_id, value=None):
            if value is not None:
                cls.objects[object_id]["layer"] = value
            return cls.objects[object_id].get("layer", "Default")

        @classmethod
        def ObjectColor(cls, object_id, value=None):
            if value is not None:
                cls.objects[object_id]["color"] = value
            color = cls.objects[object_id].get("color", (0, 0, 0))
            return SimpleNamespace(R=color[0], G=color[1], B=color[2])

        @staticmethod
        def RotateObject(*args, **kwargs):
            return True

        @classmethod
        def IsGroup(cls, group):
            return group in cls.groups

        @classmethod
        def AddGroup(cls, group):
            cls.groups[group] = []
            return group

        @classmethod
        def AddObjectsToGroup(cls, members, group):
            cls.groups[group].extend(members)
            for member in members:
                cls.objects[member]["groups"].append(group)
            return len(members)

        @classmethod
        def UnselectAllObjects(cls):
            cls.selected.clear()

        @classmethod
        def SelectObject(cls, object_id):
            cls.selected.add(object_id)
            return True

        @staticmethod
        def Redraw():
            return None

    fixture = {
        "objects": [
            {
                "logical_id": "panel",
                "kind": "box",
                "size": [10, 20, 2],
                "center": [5, 10, 1],
                "name": "Panel",
                "color": [10, 20, 30],
                "groups": ["Module"],
                "selected": True,
            }
        ]
    }
    result = tools_evaluation._exec_setup_p2_fixture(
        FakeRS,
        {"fixture_id": "unit", "fixture": fixture},
    )
    object_id = result["object_ids"]["panel"]
    assert result["object_count"] == 1
    assert FakeRS.objects[object_id]["name"] == "Panel"
    assert FakeRS.objects[object_id]["color"] == (10, 20, 30)
    assert FakeRS.groups == {"Module": [object_id]}
    assert FakeRS.selected == {object_id}
