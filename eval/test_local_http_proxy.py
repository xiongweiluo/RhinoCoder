from __future__ import annotations

import asyncio
import json

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
