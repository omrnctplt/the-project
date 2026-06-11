"""Orchestrator yasam dongusu testleri — sahte OllamaClient ile."""

from __future__ import annotations

import asyncio

import pytest

from app import orchestrator as orchestrator_mod
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
        yield {"status": "pulling manifest"}
        yield {"status": "pulling abc123", "digest": "abc123", "total": 100, "completed": 50}
        yield {"status": "pulling def456", "digest": "def456", "total": 300, "completed": 150}
        yield {"status": "verifying sha256 digest"}
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


class SlowPullClient(FakeClient):
    async def pull(self, tag):
        self.pulled.append(tag)
        yield {"status": "pulling manifest"}
        for i in range(200):
            await asyncio.sleep(0.02)
            yield {"status": "pulling sha256:slow", "digest": "sha256:slow", "total": 2000, "completed": (i + 1) * 10}
        yield {"status": "success"}


def _orch(active=None, passive=None, auto_pull=True, client=None):
    fake = client or FakeClient()
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


def test_ensure_pulled_tracks_layer_bytes_and_stage():
    o, _ = _orch()
    asyncio.run(o.ensure_pulled("fb"))
    st = o.get_state("fb")
    assert st.pull_total_bytes == 400      # 100 + 300 (iki katman)
    assert st.pull_completed_bytes == 400  # success'te tamamlanmis sayilir
    assert st.pull_stage == "success"
    pub = st.to_public()
    assert pub["pull_stage"] == "success"
    assert pub["pull_total_mb"] >= 0
    assert "pull_speed_mbps" in pub and "pull_eta_seconds" in pub


def test_call_stream_yields_pull_progress_before_tokens():
    o, _ = _orch()

    async def run():
        return [ev async for ev in o.call_stream("fb", "selam")]

    events = asyncio.run(run())
    pull_events = [e for e in events if "_pull_progress" in e]
    assert pull_events, "indirilmemis modelde once pull ilerlemesi yayinlanmali"
    assert pull_events[0]["_pull_progress"]["model_id"] == "fb"
    token_idx = next(i for i, e in enumerate(events) if e.get("response"))
    last_pull_idx = max(i for i, e in enumerate(events) if "_pull_progress" in e)
    assert last_pull_idx < token_idx
    assert any(e.get("done") for e in events)


def test_call_stream_skips_pull_events_when_already_pulled():
    o, _ = _orch()
    asyncio.run(o.ensure_pulled("fb"))

    async def run():
        return [ev async for ev in o.call_stream("fb", "selam")]

    events = asyncio.run(run())
    assert not [e for e in events if "_pull_progress" in e]


def test_queued_status_while_another_pull_holds_lock():
    o, _ = _orch()

    async def run():
        async with o._pull_lock:
            waiter = asyncio.create_task(o.ensure_pulled("txt"))
            await asyncio.sleep(0.01)
            assert o.get_state("txt").status == "queued"
        await waiter

    asyncio.run(run())
    st = o.get_state("txt")
    assert st.pulled and st.status == "ready"


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


def test_cancel_pull_resets_state_and_cleans_partials(tmp_path, monkeypatch):
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    partial = blobs / "sha256-slow-partial"
    partial.write_bytes(b"yarim")
    monkeypatch.setattr(orchestrator_mod, "OLLAMA_MODELS_DIR", str(tmp_path))
    o, fake = _orch(client=SlowPullClient())

    async def run():
        o.start_pull("fb")
        await asyncio.sleep(0.1)
        assert o.get_state("fb").status == "pulling"
        assert await o.cancel_pull("fb") is True

    asyncio.run(run())
    st = o.get_state("fb")
    assert st.pulled is False
    assert st.status == "unknown"
    assert st.pull_stage == "iptal edildi"
    assert "fb:1" in fake.deleted
    assert not partial.exists()


def test_cancel_pull_without_active_download_returns_false():
    o, _ = _orch()
    assert asyncio.run(o.cancel_pull("fb")) is False


def test_pull_events_converts_external_cancel_to_ollama_error():
    o, _ = _orch(client=SlowPullClient())

    async def run():
        seen = 0
        with pytest.raises(OllamaError, match="iptal"):
            async for _ev in o.pull_events("fb"):
                seen += 1
                if seen == 2:
                    await o.cancel_pull("fb")
        assert seen >= 2

    asyncio.run(run())


def test_start_pull_returns_same_task_for_running_pull():
    o, _ = _orch(client=SlowPullClient())

    async def run():
        t1 = o.start_pull("fb")
        t2 = o.start_pull("fb")
        assert t1 is t2
        await o.cancel_pull("fb")

    asyncio.run(run())


def test_cancel_queued_pull_resets_state():
    o, _ = _orch(client=SlowPullClient())

    async def run():
        o.start_pull("fb")
        await asyncio.sleep(0.05)
        o.start_pull("txt")
        await asyncio.sleep(0.05)
        assert o.get_state("txt").status == "queued"
        assert await o.cancel_pull("txt") is True
        assert o.get_state("txt").status == "unknown"
        assert o.get_state("txt").pull_stage == "iptal edildi"
        assert o.get_state("fb").status == "pulling"
        await o.cancel_pull("fb")

    asyncio.run(run())


def test_shutdown_pulls_cancels_and_reports():
    o, _ = _orch(client=SlowPullClient())

    async def run():
        o.start_pull("fb")
        o.start_pull("txt")
        await asyncio.sleep(0.05)
        interrupted = await o.shutdown_pulls()
        assert set(interrupted) == {"fb", "txt"}
        assert o.get_state("fb").status in ("unknown", "passive")

    asyncio.run(run())


def test_pull_initial_skips_when_auto_pull_off():
    o, fake = _orch(auto_pull=False)
    asyncio.run(o.pull_initial())
    assert fake.pulled == []
    assert all(not s.pulled for s in [o.get_state("fb"), o.get_state("txt")])


def test_pull_initial_seeds_when_auto_pull_on():
    o, fake = _orch(auto_pull=True)
    asyncio.run(o.pull_initial())
    assert "fb:1" in fake.pulled


def test_sweep_stale_partials_removes_only_old_files(tmp_path, monkeypatch):
    import os as _os
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    old = blobs / "sha256-eski-partial"
    old.write_bytes(b"x")
    _os.utime(old, (1, 1))
    fresh = blobs / "sha256-taze-partial"
    fresh.write_bytes(b"x")
    done = blobs / "sha256-tam"
    done.write_bytes(b"x")
    monkeypatch.setattr(orchestrator_mod, "OLLAMA_MODELS_DIR", str(tmp_path))
    removed = orchestrator_mod.sweep_stale_partials(max_age_hours=24)
    assert removed == 1
    assert not old.exists()
    assert fresh.exists() and done.exists()
