"""Orchestrator yasam dongusu testleri — sahte OllamaClient ile."""

from __future__ import annotations

import asyncio

import pytest

from app.orchestrator import Orchestrator
from app.ollama_client import OllamaError


CATALOG = {
    "models": {
        "fb": {"ollama_tag": "fb:1", "category": "fallback", "ram_gb": 0.5},
        "txt": {"ollama_tag": "txt:1", "category": "text", "ram_gb": 2.0},
    }
}


class FakeClient:
    def __init__(self):
        self.pulled: list[str] = []
        self.generated: list[tuple[str, str]] = []
        self.unloaded: list[str] = []
        self.deleted: list[str] = []

    async def list_local(self):
        return []

    async def pull(self, tag):
        self.pulled.append(tag)
        yield {"status": "pulling", "total": 100, "completed": 50}
        yield {"status": "success"}

    async def generate(self, tag, prompt, **kw):
        self.generated.append((tag, prompt))
        return {"response": "yanit", "eval_count": 7, "prompt_eval_count": 3}

    async def generate_stream(self, tag, prompt, **kw):
        for tok in ["mer", "ha", "ba"]:
            yield {"response": tok, "done": False}
        yield {"response": "", "done": True, "eval_count": 3, "prompt_eval_count": 2}

    async def unload(self, tag):
        self.unloaded.append(tag)

    async def delete(self, tag):
        self.deleted.append(tag)
        return True

    async def aclose(self):
        pass


def _orch(active=None, passive=None, auto_pull=True):
    fake = FakeClient()
    o = Orchestrator(
        catalog=CATALOG,
        active_model_ids=active if active is not None else ["fb", "txt"],
        passive_model_ids=passive or [],
        client=fake,
        auto_pull=auto_pull,
        max_concurrent_requests=1,
    )
    return o, fake


def test_ensure_pulled_sets_ready():
    o, fake = _orch()
    asyncio.run(o.ensure_pulled("fb"))
    st = o.get_state("fb")
    assert st.pulled and st.status == "ready"
    assert "fb:1" in fake.pulled
    assert st.last_pull_progress == 1.0


def test_call_generates_and_records_metrics():
    o, fake = _orch()
    res = asyncio.run(o.call("fb", "merhaba"))
    assert res["response"] == "yanit"
    assert res["_latency_ms"] >= 0
    st = o.get_state("fb")
    assert st.status == "loaded"
    assert st.total_requests == 1
    assert st.total_tokens == 10  # 7 + 3
    assert fake.generated and fake.generated[0][0] == "fb:1"


def test_call_passive_model_raises():
    o, _ = _orch(active=["fb"], passive=["txt"])
    with pytest.raises(OllamaError):
        asyncio.run(o.call("txt", "x"))


def test_call_without_autopull_raises():
    o, _ = _orch(active=["fb"], auto_pull=False)
    with pytest.raises(OllamaError):
        asyncio.run(o.call("fb", "x"))


def test_call_unknown_model_raises():
    o, _ = _orch()
    with pytest.raises(KeyError):
        asyncio.run(o.call("yok-boyle", "x"))


def test_stream_collects_tokens_and_records():
    o, _ = _orch()

    async def run():
        return [ev async for ev in o.call_stream("fb", "selam")]

    events = asyncio.run(run())
    assert any(e.get("done") for e in events)
    assert o.get_state("fb").total_requests == 1


def test_first_ready_and_least_busy():
    o, _ = _orch()
    asyncio.run(o.ensure_pulled("txt"))  # txt -> ready
    assert o.first_ready("text") == "txt"
    assert o.least_busy_active("text") == "txt"


def test_states_public_shape():
    o, _ = _orch()
    states = o.states()
    assert len(states) == 2
    for s in states:
        assert "model_id" in s and "status" in s and "category" in s


def test_delete_model_resets_state():
    o, fake = _orch()
    asyncio.run(o.ensure_pulled("fb"))
    assert o.get_state("fb").pulled is True
    ok = asyncio.run(o.delete_model("fb"))
    assert ok is True
    assert "fb:1" in fake.deleted
    assert o.get_state("fb").pulled is False


def test_delete_unknown_model_returns_false():
    o, _ = _orch()
    assert asyncio.run(o.delete_model("yok-boyle")) is False
