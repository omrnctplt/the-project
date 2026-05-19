"""Model lifecycle yoneticisi — pull, warmup, kullanim takibi, idle unload."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

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
    idle_unload_minutes: int = 10

    def __post_init__(self) -> None:
        self._states: dict[str, ModelState] = {}
        self._lock = asyncio.Lock()
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
            if not m:
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
        candidates = [s for s in self._states.values() if s.category == category and s.status in ("ready", "loaded")]
        if not candidates:
            return None
        candidates.sort(key=lambda s: (s.inflight_requests, s.last_used_at))
        return candidates[0].model_id

    def least_busy_active(self, category: str | None = None) -> str | None:
        actives = [s for s in self._states.values() if s.status in ("ready", "loaded", "pulling")]
        if category:
            cat = [s for s in actives if s.category == category]
            if cat:
                actives = cat
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
        tag_set = {m.get("name", "").split(":", 1)[0] + ":" + m.get("name", "").split(":", 1)[1]
                   if ":" in m.get("name", "") else m.get("name", "")
                   for m in local}
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
        async with self._lock:
            if state.pulled:
                return
            state.status = "pulling"
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

    async def pull_all_active(self) -> None:
        for mid in list(self._states):
            state = self._states[mid]
            if state.status == "passive":
                continue
            if state.pulled:
                continue
            try:
                await self.ensure_pulled(mid)
            except Exception as exc:
                log.error("Aktif model indirilemedi [%s]: %s", mid, exc)

    async def warmup_all(self) -> None:
        for state in self._states.values():
            if state.status != "ready":
                continue
            try:
                await self.client.warmup(state.ollama_tag)
                state.status = "loaded"
            except Exception as exc:
                log.warning("Warmup basarisiz [%s]: %s", state.model_id, exc)

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
        if not state.pulled and self.auto_pull:
            await self.ensure_pulled(model_id)

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

    async def idle_sweep_loop(self, period_sec: float = 60.0) -> None:
        while True:
            try:
                await asyncio.sleep(period_sec)
                threshold = self.idle_unload_minutes * 60
                now = time.time()
                for state in self._states.values():
                    if state.status != "loaded":
                        continue
                    if state.last_used_at == 0:
                        continue
                    if now - state.last_used_at < threshold:
                        continue
                    log.info("Idle unload: %s (%.0fs bos)", state.model_id, now - state.last_used_at)
                    await self.client.unload(state.ollama_tag)
                    state.status = "ready"
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.warning("Idle sweep hatasi: %s", exc)
