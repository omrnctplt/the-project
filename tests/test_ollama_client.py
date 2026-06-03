"""OllamaClient testleri — httpx MockTransport ile (gercek ag yok)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.ollama_client import OllamaClient, OllamaError


def _client(handler):
    c = OllamaClient(base_url="http://test")
    c._client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    return c


def test_generate_ok():
    def handler(_req):
        return httpx.Response(200, json={"response": "merhaba", "eval_count": 5, "prompt_eval_count": 2})
    c = _client(handler)
    res = asyncio.run(c.generate("m", "selam"))
    assert res["response"] == "merhaba"
    assert res["eval_count"] == 5
    asyncio.run(c.aclose())


def test_generate_http_error_raises():
    def handler(_req):
        return httpx.Response(500, text="dahili hata")
    c = _client(handler)
    with pytest.raises(OllamaError):
        asyncio.run(c.generate("m", "x"))
    asyncio.run(c.aclose())


def test_generate_payload_includes_options():
    captured = {}

    def handler(req):
        import json
        captured.update(json.loads(req.content))
        return httpx.Response(200, json={"response": "ok"})
    c = _client(handler)
    asyncio.run(c.generate("m", "x", temperature=0.3, context_window=2048))
    assert captured["options"]["temperature"] == 0.3
    assert captured["options"]["num_ctx"] == 2048
    asyncio.run(c.aclose())


def test_list_local_returns_models():
    def handler(_req):
        return httpx.Response(200, json={"models": [{"name": "a:1"}, {"name": "b:2"}]})
    c = _client(handler)
    models = asyncio.run(c.list_local())
    assert len(models) == 2
    asyncio.run(c.aclose())


def test_is_alive_true_and_false():
    def ok(_req):
        return httpx.Response(200)
    assert asyncio.run(_client(ok).is_alive()) is True

    def boom(_req):
        raise httpx.ConnectError("baglanti yok")
    assert asyncio.run(_client(boom).is_alive()) is False


def test_generate_stream_yields_events():
    def handler(_req):
        body = '{"response":"a","done":false}\n{"response":"b","done":true,"eval_count":2}\n'
        return httpx.Response(200, text=body)
    c = _client(handler)

    async def run():
        return [ev async for ev in c.generate_stream("m", "x")]

    events = asyncio.run(run())
    assert [e.get("response") for e in events] == ["a", "b"]
    assert events[-1]["done"] is True
    asyncio.run(c.aclose())


def test_show_returns_none_on_error():
    def handler(_req):
        return httpx.Response(404)
    c = _client(handler)
    assert asyncio.run(c.show("m")) is None
    asyncio.run(c.aclose())


def test_delete_ok():
    def handler(req):
        assert req.method == "DELETE"
        return httpx.Response(200)
    c = _client(handler)
    assert asyncio.run(c.delete("m")) is True
    asyncio.run(c.aclose())


def test_delete_failure_returns_false():
    def handler(_req):
        return httpx.Response(404)
    c = _client(handler)
    assert asyncio.run(c.delete("m")) is False
    asyncio.run(c.aclose())
