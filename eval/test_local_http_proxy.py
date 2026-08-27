from __future__ import annotations

import asyncio
import json
import uuid

import agent.ui_server as ui_server
import plugin.mcp_server._client as mcp_client
import tools.doctor as doctor


class _HTTPXResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"status": "ok", "service": "listener"}


class _HTTPXClient:
    created_with = None

    def __init__(self, **kwargs):
        type(self).created_with = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, *_args, **_kwargs):
        return _HTTPXResponse()


def test_mcp_health_check_ignores_environment_proxy(monkeypatch):
    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", _HTTPXClient)
    ok, payload = asyncio.run(mcp_client.health_check())
    assert ok
    assert payload["status"] == "ok"
    assert _HTTPXClient.created_with["trust_env"] is False


def test_ui_health_check_ignores_environment_proxy(monkeypatch):
    monkeypatch.setattr(ui_server.httpx, "AsyncClient", _HTTPXClient)
    response = asyncio.run(ui_server._health(None))
    payload = json.loads(response.text)
    assert payload["rhino"]["status"] == "ok"
    assert _HTTPXClient.created_with["trust_env"] is False


def test_doctor_builds_proxy_free_opener(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"status":"ok"}'

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    def fake_build_opener(handler):
        assert handler.proxies == {}
        return Opener()

    monkeypatch.setattr(doctor.urllib.request, "build_opener", fake_build_opener)
    ok, detail = doctor._http_json("http://127.0.0.1:8080/health")
    assert ok
    assert json.loads(detail)["status"] == "ok"


def test_mutation_network_retry_reuses_idempotency_key(monkeypatch):
    seen_headers = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"status": "ok", "guid": "created-once"}

    class Client:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            seen_headers.append(kwargs["headers"])
            self.calls += 1
            if self.calls == 1:
                raise mcp_client.httpx.ReadTimeout("lost response")
            return Response()

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", Client)
    monkeypatch.setattr(mcp_client.asyncio, "sleep", no_sleep)
    ok, result = asyncio.run(mcp_client.call_rhino("/create_box", {"width": 1}))

    assert ok and result == "created-once"
    assert len(seen_headers) == 2
    assert seen_headers[0]["Idempotency-Key"] == seen_headers[1]["Idempotency-Key"]
    uuid.UUID(seen_headers[0]["Idempotency-Key"])


def test_mcp_success_logs_only_redacted_shapes(monkeypatch, caplog):
    secret_guid = "2aee62c7-1d6e-4cd6-9a8f-803cb2f6f76d"
    secret_name = "confidential-project-layer"

    class Response:
        status_code = 200

        def json(self):
            return {
                "status": "ok",
                "objects": [{"object_id": secret_guid, "name": secret_name}],
                "total": 1,
            }

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return Response()

    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", Client)
    ok, result = asyncio.run(
        mcp_client.call_rhino("/get_scene_summary", {"project_name": secret_name})
    )

    assert ok and result["total"] == 1
    assert secret_guid not in caplog.text
    assert secret_name not in caplog.text
    assert "objects_count=1" in caplog.text
