"""app/discovery.py — uzak model kesfi birim + endpoint testleri."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import discovery


SAMPLE_LIBRARY_HTML = """
<ul>
  <li x-test-model class="flex">
    <div x-test-model-title title="qwen3" class="t"></div>
    <p class="max-w-lg break-words text">Yeni nesil cok dilli model.</p>
    <span x-test-capability>tools</span>
    <span x-test-size class="s">0.6b</span>
    <span x-test-size class="s">8b</span>
    <span x-test-pull-count>87.2M</span>
    <span x-test-tag-count>20</span>
    <span x-test-updated>2 weeks ago</span>
  </li>
  <li x-test-model class="flex">
    <div x-test-model-title title="nomic-embed-text" class="t"></div>
    <p class="max-w-lg break-words text">Embedding modeli.</p>
    <span x-test-capability>embedding</span>
    <span x-test-size class="s">1.5b</span>
    <span x-test-pull-count>5.1M</span>
  </li>
  <li x-test-model class="flex">
    <div x-test-model-title title="deepseek-r1" class="t"></div>
    <p class="max-w-lg break-words text">Reasoning distill.</p>
    <span x-test-capability>thinking</span>
    <span x-test-size class="s">7b</span>
    <span x-test-pull-count>1.3K</span>
  </li>
</ul>
"""


def test_parse_pull_count():
    assert discovery.parse_pull_count("87.2M") == 87_200_000
    assert discovery.parse_pull_count("1.5K") == 1_500
    assert discovery.parse_pull_count("3B") == 3_000_000_000
    assert discovery.parse_pull_count("12") == 12
    assert discovery.parse_pull_count("") == 0
    assert discovery.parse_pull_count("garip") == 0


def test_parse_size_label():
    assert discovery.parse_size_label("7b") == 7.0
    assert discovery.parse_size_label("0.6b") == 0.6
    assert discovery.parse_size_label("8x7b") == 56.0
    assert discovery.parse_size_label("360m") == 0.36
    assert discovery.parse_size_label("e2b") == 2.0
    assert discovery.parse_size_label("latest") is None
    assert discovery.parse_size_label("") is None


def test_estimate_ram_gb():
    assert discovery.estimate_ram_gb(0.1) == 0.4
    assert abs(discovery.estimate_ram_gb(8.0) - 5.6) < 0.5
    assert abs(discovery.estimate_ram_gb(70.0) - 45.5) < 4.0
    assert discovery.estimate_ram_gb(4.0) < discovery.estimate_ram_gb(8.0) < discovery.estimate_ram_gb(32.0)


def test_tier_for_ram():
    assert discovery.tier_for_ram(2.0) == "edge"
    assert discovery.tier_for_ram(10.0) == "laptop"
    assert discovery.tier_for_ram(30.0) == "workstation"
    assert discovery.tier_for_ram(100.0) == "datacenter"


def test_guess_category():
    assert discovery.guess_category("qwen2.5-coder") == "code"
    assert discovery.guess_category("deepseek-r1", capabilities=["thinking"]) == "reasoning"
    assert discovery.guess_category("dolphin3") == "persona"
    assert discovery.guess_category("llama3.2") == "text"
    assert discovery.guess_category("nomic-embed-text", capabilities=["embedding"]) is None


def test_parse_ollama_library():
    entries = discovery.parse_ollama_library(SAMPLE_LIBRARY_HTML)
    assert len(entries) == 3
    qwen = entries[0]
    assert qwen["name"] == "qwen3"
    assert qwen["pulls"] == 87_200_000
    assert qwen["sizes"] == ["0.6b", "8b"]
    assert qwen["capabilities"] == ["tools"]
    assert qwen["description"] == "Yeni nesil cok dilli model."
    assert qwen["updated"] == "2 weeks ago"


def test_ollama_entries_to_models():
    entries = discovery.parse_ollama_library(SAMPLE_LIBRARY_HTML)
    items = discovery.ollama_entries_to_models(entries)
    tags = [it["tag"] for it in items]
    assert "qwen3:0.6b" in tags and "qwen3:8b" in tags
    assert "deepseek-r1:7b" in tags
    assert not any("nomic" in t for t in tags)  # embedding elendi
    r1 = next(it for it in items if it["tag"] == "deepseek-r1:7b")
    assert r1["category"] == "reasoning"
    assert r1["tier"] == "laptop"
    assert r1["provider"] == "ollama"
    assert r1["cloud"] is False


def test_sizeless_entry_becomes_cloud_item():
    # ollama.com'da boyut etiketi olmayanlar cloud modelleridir (deepseek-v4 vb.)
    entries = [{
        "name": "deepseek-v4-flash", "description": "Verimli MoE, 1M context.",
        "pulls": 1000, "sizes": [], "capabilities": ["tools", "thinking"], "updated": "1 month ago",
    }]
    items = discovery.ollama_entries_to_models(entries)
    assert len(items) == 1
    it = items[0]
    assert it["cloud"] is True
    assert it["tag"] == "deepseek-v4-flash"
    assert it["approx_gb"] is None and it["tier"] is None
    assert it["category"] == "reasoning"


def test_parse_hf_models():
    payload = [
        {
            "id": "bartowski/Llama-3.2-1B-Instruct-GGUF",
            "downloads": 5000,
            "siblings": [{"rfilename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf"}],
        },
        {
            "id": "unsloth/Big-Model-70B-GGUF",
            "downloads": 100,
            "siblings": [
                {"rfilename": "Big-Model-70B-Q4_K_M-00001-of-00002.gguf"},
                {"rfilename": "Big-Model-70B-Q4_K_M-00002-of-00002.gguf"},
            ],
        },
        {"id": "kapali/Gated-7B-GGUF", "gated": True, "downloads": 10, "siblings": []},
        {"id": "adsiz/parametresiz-gguf", "downloads": 10, "siblings": []},
    ]
    items = discovery.parse_hf_models(payload)
    assert len(items) == 1
    it = items[0]
    assert it["tag"] == "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF"
    assert it["parameters_b"] == 1.0
    assert it["provider"] == "huggingface"


def test_cache_roundtrip_and_ttl():
    data = {"fetched_at": time.time(), "models": [{"key": "x"}]}
    discovery.save_cache(data)
    loaded = discovery.load_cache()
    assert loaded and loaded["models"][0]["key"] == "x"
    assert discovery.cache_is_fresh(loaded)
    old = {"fetched_at": time.time() - 999_999, "models": []}
    assert not discovery.cache_is_fresh(old)
    discovery.CACHE_PATH.unlink(missing_ok=True)


def _failing_client() -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("ag yok")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_get_remote_catalog_offline_no_cache():
    discovery.CACHE_PATH.unlink(missing_ok=True)

    async def run():
        client = _failing_client()
        try:
            return await discovery.get_remote_catalog(force=True, client=client)
        finally:
            await client.aclose()

    result = asyncio.run(run())
    assert result["models"] == []
    assert len(result["errors"]) == 2


def test_get_remote_catalog_offline_stale_cache():
    discovery.save_cache({"fetched_at": time.time() - 999_999, "models": [{"key": "eski"}]})

    async def run():
        client = _failing_client()
        try:
            return await discovery.get_remote_catalog(force=True, client=client)
        finally:
            await client.aclose()

    result = asyncio.run(run())
    assert result["stale"] is True
    assert result["models"][0]["key"] == "eski"
    discovery.CACHE_PATH.unlink(missing_ok=True)


def test_get_remote_catalog_uses_fresh_cache_without_network():
    discovery.save_cache({"fetched_at": time.time(), "models": [{"key": "taze"}], "stale": False})

    result = asyncio.run(discovery.get_remote_catalog(force=False))
    assert result["models"][0]["key"] == "taze"
    discovery.CACHE_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


def _token(client, username="admin", password="admin"):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_discover_remote_endpoint_with_seeded_cache(client):
    discovery.save_cache({
        "fetched_at": time.time(),
        "stale": False,
        "errors": [],
        "sources": {"ollama": 2, "huggingface": 0},
        "models": [
            {
                "key": "ollama:minik:1b", "provider": "ollama", "name": "minik",
                "tag": "minik:1b", "label": "Minik 1B", "blurb": "test",
                "category": "text", "parameters_b": 1.0, "approx_gb": 0.9,
                "tier": "edge", "popularity": 500, "updated": None, "capabilities": [],
            },
            {
                "key": "ollama:dev:70b", "provider": "ollama", "name": "dev",
                "tag": "dev:70b", "label": "Dev 70B", "blurb": "test",
                "category": "text", "parameters_b": 70.0, "approx_gb": 45.5,
                "tier": "workstation", "popularity": 900, "updated": None, "capabilities": [],
            },
        ],
    })
    token = _token(client)
    r = client.get(
        "/api/v1/system/discover/remote",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    tags = {m["tag"] for m in body["models"]}
    assert tags == {"minik:1b", "dev:70b"}
    for m in body["models"]:
        assert {"fits", "fits_total", "recommended", "in_catalog", "pulled"} <= set(m.keys())
    r2 = client.get(
        "/api/v1/system/discover/remote?provider=huggingface",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.json()["total"] == 0
    discovery.CACHE_PATH.unlink(missing_ok=True)
