from __future__ import annotations

import os
import sys
from types import SimpleNamespace

from plugin.rhino_listener import listener_main, tools_transform


class _Handler:
    def __init__(self, token: str = "") -> None:
        self.headers = {"X-RhinoCoder-Eval-Token": token}
        self.sent = []
        self.enqueued = []

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
