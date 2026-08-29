from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from plugin.rhino_listener import listener_main, tools_geometry, tools_transform


class _Handler:
    def __init__(self, token: str = "", body=None) -> None:
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


def test_reset_environment_disabled_without_server_token(monkeypatch):
    monkeypatch.delenv("RHINOCODER_EVAL_TOKEN", raising=False)
    handler = _Handler("provided")
    tools_transform._route_reset_environment(handler)
    assert handler.sent[0][0] == 503
    assert handler.sent[0][1]["error"]["code"] == "eval.reset_disabled"
    assert not handler.enqueued


def test_reset_environment_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("RHINOCODER_EVAL_TOKEN", "expected-token")
    handler = _Handler("wrong-token")
    tools_transform._route_reset_environment(handler)
    assert handler.sent[0][0] == 403
    assert not handler.enqueued


def test_reset_environment_accepts_matching_token(monkeypatch):
    monkeypatch.setenv("RHINOCODER_EVAL_TOKEN", "expected-token")
    handler = _Handler("expected-token")
    tools_transform._route_reset_environment(handler)
    assert handler.enqueued == [("reset_environment", {})]


def test_delete_objects_reports_partial_failure():
    class FakeRS:
        @staticmethod
        def DeleteObject(object_id):
            return object_id == "ok"

        @staticmethod
        def Redraw():
            return None

    result = tools_transform._exec_delete_objects(FakeRS, {"object_ids": ["ok", "missing"]})
    assert result == {"deleted": ["ok"], "failed": ["missing"], "count": 1}


def test_idempotency_cache_replays_same_request_and_rejects_conflict():
    class Dummy:
        def __init__(self):
            self.headers = {"Idempotency-Key": "12345678"}
            self.sent = []

        def _send_json(self, status, payload):
            self.sent.append((status, payload))

        def _cache_and_send(self, key, signature, payload, *, status=200):
            listener_main._RhinoHTTPHandler._cache_and_send(
                self, key, signature, payload, status=status
            )

    listener_main._idempotency_cache.clear()
    listener_main._idempotency_cache["12345678"] = (
        'create_box:{"height": 2}',
        {"status": "ok", "guid": "existing"},
    )

    same = Dummy()
    listener_main._RhinoHTTPHandler._enqueue_and_wait(same, "create_box", {"height": 2})
    assert same.sent == [(200, {"status": "ok", "guid": "existing"})]

    conflict = Dummy()
    listener_main._RhinoHTTPHandler._enqueue_and_wait(conflict, "create_box", {"height": 3})
    assert conflict.sent[0][0] == 409
    assert conflict.sent[0][1]["error"]["code"] == "http.idempotency_conflict"
    listener_main._idempotency_cache.clear()


def test_legacy_route_errors_receive_standard_error_code():
    payload = listener_main._normalize_response(
        400,
        {"status": "error", "message": "Missing field: object_id"},
    )
    assert payload["error"] == {
        "code": "http.invalid_argument",
        "recoverable": False,
    }


def test_invalid_guid_and_empty_parameters_never_enter_main_thread():
    invalid_guid = _Handler(body={"object_id": "not-a-guid", "translation": [1, 2, 3]})
    tools_transform._route_move_object(invalid_guid)
    assert invalid_guid.sent[0][0] == 400
    assert "GUID" in invalid_guid.sent[0][1]["message"]
    assert not invalid_guid.enqueued

    empty_box = _Handler(body={})
    tools_geometry._route_create_box(empty_box)
    assert empty_box.sent[0][0] == 400
    assert empty_box.sent[0][1]["message"] == "Missing field: width"
    assert not empty_box.enqueued


def test_timeout_response_is_cached_to_prevent_duplicate_enqueue(monkeypatch):
    class Queue:
        def __init__(self):
            self.items = []

        def put(self, item):
            self.items.append(item)

    queue = Queue()
    monkeypatch.setattr(listener_main, "_work_queue", queue)
    monkeypatch.setattr(listener_main, "REQUEST_TIMEOUT", 0)
    listener_main._idempotency_cache.clear()

    class Dummy:
        def __init__(self):
            self.headers = {"Idempotency-Key": "timeout-key-123"}
            self.sent = []

        def _send_json(self, status, payload):
            self.sent.append((status, payload))

        def _cache_and_send(self, key, signature, payload, *, status=200):
            listener_main._RhinoHTTPHandler._cache_and_send(
                self, key, signature, payload, status=status
            )

    first = Dummy()
    listener_main._RhinoHTTPHandler._enqueue_and_wait(first, "create_box", {"width": 1})
    second = Dummy()
    listener_main._RhinoHTTPHandler._enqueue_and_wait(second, "create_box", {"width": 1})

    assert len(queue.items) == 1
    assert first.sent[0][0] == 504
    assert second.sent[0][1]["error"]["code"] == "rhino.main_thread_timeout"
    listener_main._idempotency_cache.clear()


def test_listener_loads_eval_token_from_project_env(monkeypatch, tmp_path):
    monkeypatch.delenv("RHINOCODER_EVAL_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DEEPSEEK_API_KEY=not-loaded\nRHINOCODER_EVAL_TOKEN='local-eval-token'\n",  # secret-scan: allow
        encoding="utf-8",
    )
    assert listener_main._load_eval_token_from_project_env(env_path)
    assert os.environ["RHINOCODER_EVAL_TOKEN"] == "local-eval-token"


def test_listener_does_not_enable_placeholder_eval_token(monkeypatch, tmp_path):
    monkeypatch.delenv("RHINOCODER_EVAL_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("RHINOCODER_EVAL_TOKEN=<placeholder>\n", encoding="utf-8")
    assert not listener_main._load_eval_token_from_project_env(env_path)
    assert not listener_main._eval_reset_enabled()


def test_stop_listener_does_not_shutdown_an_already_dead_server_thread(monkeypatch):
    class DeadThread:
        @staticmethod
        def is_alive():
            return False

    class StaleServer:
        def __init__(self):
            self.shutdown_calls = 0
            self.close_calls = 0

        def shutdown(self):
            self.shutdown_calls += 1

        def server_close(self):
            self.close_calls += 1

    server = StaleServer()
    monkeypatch.setattr(listener_main, "_server_instance", server)
    monkeypatch.setattr(listener_main, "_server_thread", DeadThread())
    monkeypatch.setattr(listener_main, "_idle_registered", False)

    listener_main.stop_listener()

    assert server.shutdown_calls == 0
    assert server.close_calls == 1
    assert listener_main._server_instance is None
    assert listener_main._server_thread is None


def test_reset_environment_uses_supported_clear_undo_overload(monkeypatch):
    class Doc:
        clear_args = None

        def ClearUndoRecords(self, purge_deleted_objects):
            self.clear_args = purge_deleted_objects

    doc = Doc()
    monkeypatch.setitem(sys.modules, "scriptcontext", SimpleNamespace(doc=doc))

    class FakeRS:
        deleted = None

        @staticmethod
        def AllObjects():
            return ["one", "two"]

        @classmethod
        def DeleteObjects(cls, object_ids):
            cls.deleted = object_ids

        @staticmethod
        def Redraw():
            return None

    result = tools_transform._exec_reset_environment(FakeRS, {})
    assert FakeRS.deleted == ["one", "two"]
    assert doc.clear_args is True
    assert "场景已清空" in result["message"]


class _UndoDoc:
    def __init__(self) -> None:
        self.started = []
        self.ended = []

    def BeginUndoRecord(self, name):
        self.started.append(name)
        return 42

    def EndUndoRecord(self, serial):
        self.ended.append(serial)


def test_mutating_operation_is_wrapped_in_rhino_undo_record():
    doc = _UndoDoc()

    result = listener_main._execute_with_undo_record(
        doc,
        "create_box",
        lambda rs, params: {"created": params["width"]},
        object(),
        {"width": 5},
    )

    assert result == {"created": 5}
    assert doc.started == ["RhinoCoder: create_box"]
    assert doc.ended == [42]


@pytest.mark.parametrize("operation", ["get_scene_summary", "undo_last_action", "reset_environment"])
def test_query_and_undo_control_operations_do_not_create_undo_record(operation):
    doc = _UndoDoc()

    listener_main._execute_with_undo_record(
        doc,
        operation,
        lambda rs, params: "ok",
        object(),
        {},
    )

    assert not doc.started
    assert not doc.ended


def test_failed_mutating_operation_closes_undo_record():
    doc = _UndoDoc()

    def fail(rs, params):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        listener_main._execute_with_undo_record(
            doc,
            "move_object",
            fail,
            object(),
            {},
        )

    assert doc.started == ["RhinoCoder: move_object"]
    assert doc.ended == [42]
