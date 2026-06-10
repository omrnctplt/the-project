"""Model lifecycle yoneticisi.

Sorumluluklar:
  - Aktif/pasif model listesini ModelState olarak tutmak
  - Pull islemini SIRAYLA yapmak (paralel pull yok; disk/network sismaz)
  - Bootstrap'ta sadece fallback modeli pull etmek; digerleri lazy
  - call() sirasinda model yuklu degilse otomatik pull (auto_pull=True ise)
  - Es zamanli inference sayisini kapasite plan'a gore sinirlamak
  - Idle modelleri belirli sure sonra Ollama'dan unload etmek
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from .ollama_client import OllamaClient, OllamaError

log = logging.getLogger(__name__)


@dataclass
class ModelState:
    model_id: str
    ollama_tag: str
    category: str
    status: str = "unknown"          # unknown | pulling | ready | loaded | error | passive
    last_used_at: float = 0.0
    last_pull_progress: float = 0.0
    pulled: bool = False
    error: str | None = None
    inflight_requests: int = 0
    total_requests: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "ollama_tag": self.ollama_tag,
            "category": self.category,
            "status": self.status,
            "pulled": self.pulled,
            "pull_progress": round(self.last_pull_progress, 2),
            "inflight_requests": self.inflight_requests,
            "total_requests": self.total_requests,
            "avg_latency_ms": (
                round(self.total_latency_ms / self.total_requests, 1)
                if self.total_requests
                else None
            ),
            "error": self.error,
            "last_used_seconds_ago": (
                round(time.time() - self.last_used_at, 1) if self.last_used_at else None
            ),
        }


@dataclass
class Orchestrator:
    catalog: dict[str, Any]
    active_model_ids: list[str]
    passive_model_ids: list[str] = field(default_factory=list)
    client: OllamaClient = field(default_factory=OllamaClient)
    auto_pull: bool = True
    idle_unload_minutes: int = 3
    max_concurrent_requests: int = 1

    def __post_init__(self) -> None:
        self._states: dict[str, ModelState] = {}
        self._pull_lock = asyncio.Lock()
        self._inflight_sem = asyncio.Semaphore(max(1, self.max_concurrent_requests))
        models_def: dict[str, Any] = self.catalog.get("models", {}) or {}
        for mid in self.active_model_ids:
            m = models_def.get(mid)
            if not m:
                continue
            self._states[mid] = ModelState(
                model_id=mid,
                ollama_tag=str(m["ollama_tag"]),
                category=str(m.get("category", "text")),
            )
        for mid in self.passive_model_ids:
            m = models_def.get(mid)
            if not m or mid in self._states:
                continue
            self._states[mid] = ModelState(
                model_id=mid,
                ollama_tag=str(m["ollama_tag"]),
                category=str(m.get("category", "text")),
                status="passive",
            )

    def states(self) -> list[dict[str, Any]]:
        return [s.to_public() for s in self._states.values()]

    def get_state(self, model_id: str) -> ModelState | None:
        return self._states.get(model_id)

    def first_ready(self, category: str) -> str | None:
        candidates = [
            s for s in self._states.values()
            if s.category == category and s.status in ("ready", "loaded")
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda s: (s.inflight_requests, s.last_used_at))
        return candidates[0].model_id

    def least_busy_active(self, category: str | None = None) -> str | None:
        actives = [
            s for s in self._states.values()
            if s.status in ("ready", "loaded", "pulling")
        ]
        if category:
            actives = [s for s in actives if s.category == category]
        if not actives:
            return None
        actives.sort(key=lambda s: (s.inflight_requests, -s.total_requests))
        return actives[0].model_id

    async def refresh_pulled_flags(self) -> None:
        try:
            local = await self.client.list_local()
        except Exception as exc:
            log.warning("Yerel model listesi alinamadi: %s", exc)
            return
        tag_set: set[str] = set()
        for m in local:
            name = str(m.get("name", ""))
            if not name:
                continue
            tag_set.add(name)
            if ":" not in name:
                tag_set.add(f"{name}:latest")
        for state in self._states.values():
            if state.ollama_tag in tag_set:
                state.pulled = True
                if state.status in ("unknown", "passive"):
                    state.status = "ready"

    async def ensure_pulled(self, model_id: str) -> None:
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        if state.pulled:
            return
        async with self._pull_lock:
            if state.pulled:
                return
            state.status = "pulling"
            state.error = None
            try:
                async for event in self.client.pull(state.ollama_tag):
                    total = event.get("total") or 0
                    completed = event.get("completed") or 0
                    if total > 0:
                        state.last_pull_progress = min(1.0, completed / total)
                    if event.get("status") == "success":
                        break
                state.pulled = True
                state.status = "ready"
                state.last_pull_progress = 1.0
                log.info("Model indirildi: %s", state.ollama_tag)
            except Exception as exc:
                state.status = "error"
                state.error = str(exc)
                log.error("Pull hatasi [%s]: %s", state.ollama_tag, exc)
                raise

    async def delete_model(self, model_id: str) -> bool:
        """Modeli Ollama'dan siler ve state'i 'indirilmemis' olarak gunceller."""
        state = self._states.get(model_id)
        if not state:
            return False
        ok = await self.client.delete(state.ollama_tag)
        if ok:
            state.pulled = False
            state.last_pull_progress = 0.0
            state.status = "passive" if model_id in self.passive_model_ids else "unknown"
            log.info("Model Ollama'dan silindi: %s", state.ollama_tag)
        return ok

    async def pull_initial(self) -> None:
        """Bootstrap'ta sadece en kucuk 1 modeli (genelde fallback) indir.

        Diger modeller lazy: ilk istek geldiginde indirilir.
        """
        await self.refresh_pulled_flags()
        seed_id = self._pick_seed_model_id()
        if not seed_id:
            log.info("Bootstrap'ta indirilecek seed model bulunamadi.")
            return
        state = self._states[seed_id]
        if state.pulled:
            log.info("Seed model zaten yerel: %s", state.ollama_tag)
            return
        log.info("Seed model indiriliyor (lazy mod): %s", state.ollama_tag)
        try:
            await self.ensure_pulled(seed_id)
        except Exception as exc:
            log.warning("Seed pull basarisiz, sistem yine de calisacak: %s", exc)

    def _pick_seed_model_id(self) -> str | None:
        """Aktif modellerden en kucugunu (oncelikle fallback kategorisi) sec."""
        models_def: dict[str, Any] = self.catalog.get("models", {}) or {}
        actives = [s for s in self._states.values() if s.status != "passive"]
        if not actives:
            return None

        def size_of(s: ModelState) -> float:
            m = models_def.get(s.model_id) or {}
            return float(m.get("ram_gb") or m.get("vram_gb") or 999.0)

        fb = [s for s in actives if s.category == "fallback"]
        if fb:
            fb.sort(key=size_of)
            return fb[0].model_id
        actives.sort(key=size_of)
        return actives[0].model_id

    async def call(
        self,
        model_id: str,
        prompt: str,
        *,
        temperature: float | None = None,
        context_window: int | None = None,
    ) -> dict[str, Any]:
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        if state.status == "passive":
            raise OllamaError(f"Model pasif: {model_id}")
        if not state.pulled:
            if not self.auto_pull:
                raise OllamaError(
                    f"Model henuz indirilmemis ve auto_pull kapali: {model_id}"
                )
            await self.ensure_pulled(model_id)

        async with self._inflight_sem:
            state.inflight_requests += 1
            t0 = time.perf_counter()
            try:
                result = await self.client.generate(
                    state.ollama_tag,
                    prompt,
                    temperature=temperature,
                    context_window=context_window,
                    keep_alive=f"{self.idle_unload_minutes}m",
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                state.last_used_at = time.time()
                state.status = "loaded"
                state.total_requests += 1
                state.total_latency_ms += elapsed_ms
                eval_count = int(result.get("eval_count") or 0)
                prompt_count = int(result.get("prompt_eval_count") or 0)
                state.total_tokens += eval_count + prompt_count
                result["_latency_ms"] = round(elapsed_ms, 1)
                result["_model_id"] = model_id
                return result
            except OllamaError:
                state.error = "generate hatasi"
                raise
            finally:
                state.inflight_requests = max(0, state.inflight_requests - 1)

    async def call_stream(
        self,
        model_id: str,
        prompt: str,
        *,
        temperature: float | None = None,
        context_window: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        if state.status == "passive":
            raise OllamaError(f"Model pasif: {model_id}")
        if not state.pulled:
            if not self.auto_pull:
                raise OllamaError(
                    f"Model henuz indirilmemis ve auto_pull kapali: {model_id}"
                )
            await self.ensure_pulled(model_id)

        async with self._inflight_sem:
            state.inflight_requests += 1
            t0 = time.perf_counter()
            eval_count_final = 0
            prompt_count_final = 0
            try:
                async for event in self.client.generate_stream(
                    state.ollama_tag,
                    prompt,
                    temperature=temperature,
                    context_window=context_window,
                    keep_alive=f"{self.idle_unload_minutes}m",
                ):
                    if event.get("eval_count"):
                        eval_count_final = int(event["eval_count"])
                    if event.get("prompt_eval_count"):
                        prompt_count_final = int(event["prompt_eval_count"])
                    yield event
                    if event.get("done"):
                        break
                elapsed_ms = (time.perf_counter() - t0) * 1000
                state.last_used_at = time.time()
                state.status = "loaded"
                state.total_requests += 1
                state.total_latency_ms += elapsed_ms
                state.total_tokens += eval_count_final + prompt_count_final
            except OllamaError:
                state.error = "generate_stream hatasi"
                raise
            finally:
                state.inflight_requests = max(0, state.inflight_requests - 1)

    async def idle_sweep_loop(self, period_sec: float = 60.0) -> None:
        while True:
            try:
                await asyncio.sleep(period_sec)
                threshold = max(30, self.idle_unload_minutes * 60)
                now = time.time()
                for state in self._states.values():
                    if state.status != "loaded":
                        continue
                    if state.last_used_at == 0:
                        continue
                    if now - state.last_used_at < threshold:
                        continue
                    log.info("Idle unload: %s (%.0fs bos)", state.model_id, now - state.last_used_at)
                    try:
                        await self.client.unload(state.ollama_tag)
                    except Exception as exc:
                        log.warning("Unload hata [%s]: %s", state.model_id, exc)
                        continue
                    state.status = "ready"
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.warning("Idle sweep hatasi: %s", exc)
