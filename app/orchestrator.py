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
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from .ollama_client import OllamaClient, OllamaError

log = logging.getLogger(__name__)

OLLAMA_MODELS_DIR = os.getenv("OLLAMA_MODELS_DIR", "")
STALE_PARTIAL_MAX_AGE_HOURS = float(os.getenv("STALE_PARTIAL_MAX_AGE_HOURS", "24") or 24)


def _blobs_dir() -> Path | None:
    if not OLLAMA_MODELS_DIR:
        return None
    blobs = Path(OLLAMA_MODELS_DIR) / "blobs"
    return blobs if blobs.is_dir() else None


def remove_partial_blobs(digests: set[str]) -> int:
    """Iptal edilen pull'un yarim kalan blob dosyalarini siler.

    Yalnizca `-partial` sonekli dosyalara dokunur — tamamlanmis blob'lar ve
    diger modellerin katmanlari guvendedir.
    """
    blobs = _blobs_dir()
    if not blobs or not digests:
        return 0
    removed = 0
    for digest in digests:
        stem = digest.replace(":", "-")
        for f in blobs.glob(f"{stem}-partial*"):
            try:
                f.unlink()
                removed += 1
            except OSError as exc:
                log.warning("Partial blob silinemedi [%s]: %s", f.name, exc)
    if removed:
        log.info("%d yarim blob dosyasi temizlendi", removed)
    return removed


def _normalize_tag(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def _parse_expires_in_seconds(raw: Any) -> float | None:
    """Ollama /api/ps 'expires_at' (RFC3339, nanosaniye hassasiyetli) -> kalan sn."""
    if not raw:
        return None
    text = re.sub(r"\.(\d{1,6})\d*", r".\1", str(raw))
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.year <= 1:
        return None
    return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())


def sweep_stale_partials(max_age_hours: float = STALE_PARTIAL_MAX_AGE_HOURS) -> int:
    """Acilista eski `-partial` kalintilarini temizler (yarim kalan indirmeler).

    Taze partial'lar korunur: Ollama yeniden pull'da kaldigi yerden devam eder.
    """
    blobs = _blobs_dir()
    if not blobs:
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for f in blobs.glob("sha256-*-partial*"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError as exc:
            log.warning("Eski partial temizlenemedi [%s]: %s", f.name, exc)
    if removed:
        log.info("Acilis temizligi: %d eski yarim blob silindi (>%.0f saat)", removed, max_age_hours)
    return removed


@dataclass
class ModelState:
    model_id: str
    ollama_tag: str
    category: str
    status: str = "unknown"          # unknown | queued | pulling | ready | loaded | error | passive
    last_used_at: float = 0.0
    last_pull_progress: float = 0.0
    pull_stage: str | None = None
    pull_completed_bytes: int = 0
    pull_total_bytes: int = 0
    pull_speed_bps: float = 0.0
    pull_eta_seconds: float | None = None
    pull_started_at: float = 0.0
    pull_digests: set[str] = field(default_factory=set)
    pulled: bool = False
    warming_up: bool = False
    error: str | None = None
    inflight_requests: int = 0
    total_requests: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0

    def reset_pull_telemetry(self) -> None:
        self.last_pull_progress = 0.0
        self.pull_stage = None
        self.pull_completed_bytes = 0
        self.pull_total_bytes = 0
        self.pull_speed_bps = 0.0
        self.pull_eta_seconds = None
        self.pull_started_at = 0.0
        self.pull_digests = set()

    def to_public(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "ollama_tag": self.ollama_tag,
            "category": self.category,
            "status": self.status,
            "pulled": self.pulled,
            "pull_progress": round(self.last_pull_progress, 4),
            "pull_stage": self.pull_stage,
            "pull_completed_mb": round(self.pull_completed_bytes / 1024**2, 1),
            "pull_total_mb": round(self.pull_total_bytes / 1024**2, 1),
            "pull_speed_mbps": round(self.pull_speed_bps / 1024**2, 2),
            "pull_eta_seconds": (
                round(self.pull_eta_seconds) if self.pull_eta_seconds is not None else None
            ),
            "warming_up": self.warming_up,
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
        self._bg_pulls: set[asyncio.Task] = set()
        self._pull_tasks: dict[str, asyncio.Task] = {}
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
            if s.status in ("ready", "loaded", "pulling", "queued")
        ]
        if category:
            actives = [s for s in actives if s.category == category]
        if not actives:
            return None
        actives.sort(key=lambda s: (s.inflight_requests, -s.total_requests))
        return actives[0].model_id

    async def memory_snapshot(self) -> dict[str, Any]:
        """Gercek bellek yerlesimi — tek bakista 'kim diskte, kim bellekte'.

        Kaynak Ollama'nin kendisi: /api/ps (RAM/VRAM'de oturanlar + keep_alive
        bitisi) ve /api/tags (diskteki boyutlar). Gateway'in status alani
        Ollama gercegiyle senkronlanir: keep_alive dolup model kendiliginden
        bosalmissa 'loaded' -> 'ready', dis kanaldan yuklenmisse tersi.
        """
        reachable = True
        try:
            running, local = await asyncio.gather(
                self.client.list_running(), self.client.list_local()
            )
        except Exception as exc:
            log.warning("Bellek goruntusu alinamadi: %s", exc)
            running, local, reachable = [], [], False

        running_by_tag: dict[str, dict[str, Any]] = {}
        for m in running:
            name = str(m.get("name") or m.get("model") or "")
            if name:
                running_by_tag[_normalize_tag(name)] = m
        disk_by_tag: dict[str, dict[str, Any]] = {}
        for m in local:
            name = str(m.get("name") or "")
            if name:
                disk_by_tag[_normalize_tag(name)] = m

        models: list[dict[str, Any]] = []
        managed_tags: set[str] = set()
        for state in self._states.values():
            tag = _normalize_tag(state.ollama_tag)
            managed_tags.add(tag)
            run = running_by_tag.get(tag)
            disk = disk_by_tag.get(tag)
            if reachable:
                if disk is not None and not state.pulled:
                    state.pulled = True
                    if state.status == "unknown":
                        state.status = "ready"
                if run is not None and state.status in ("ready", "unknown"):
                    state.pulled = True
                    state.status = "loaded"
                elif run is None and state.status == "loaded":
                    state.status = "ready"
            size = int((run or {}).get("size") or 0)
            size_vram = int((run or {}).get("size_vram") or 0)
            models.append({
                **state.to_public(),
                "loaded": run is not None,
                "memory_bytes": size,
                "vram_bytes": size_vram,
                "ram_bytes": max(0, size - size_vram),
                "expires_in_seconds": _parse_expires_in_seconds((run or {}).get("expires_at")),
                "disk_bytes": int((disk or {}).get("size") or 0),
            })

        unmanaged: list[dict[str, Any]] = []
        for tag, disk in disk_by_tag.items():
            if tag in managed_tags:
                continue
            run = running_by_tag.get(tag)
            size = int((run or {}).get("size") or 0)
            size_vram = int((run or {}).get("size_vram") or 0)
            unmanaged.append({
                "ollama_tag": tag,
                "disk_bytes": int(disk.get("size") or 0),
                "loaded": run is not None,
                "memory_bytes": size,
                "vram_bytes": size_vram,
                "ram_bytes": max(0, size - size_vram),
            })

        total_mem = sum(int(m.get("size") or 0) for m in running)
        total_vram = sum(int(m.get("size_vram") or 0) for m in running)
        return {
            "reachable": reachable,
            "models": models,
            "unmanaged": unmanaged,
            "totals": {
                "loaded_count": len(running),
                "memory_bytes": total_mem,
                "vram_bytes": total_vram,
                "ram_bytes": max(0, total_mem - total_vram),
                "disk_bytes": sum(int(m.get("size") or 0) for m in local),
            },
        }

    async def load_model(self, model_id: str) -> None:
        """Modeli bellege onceden yukler — ilk istegi beklemeden hazir tutar.

        Bos prompt'lu generate Ollama'da yalnizca yukleme yapar, uretim
        calistirmaz; istatistikler etkilenmez.
        """
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        if not state.pulled:
            raise OllamaError(f"Model henuz indirilmemis: {model_id}")
        state.warming_up = True
        try:
            await self.client.generate(
                state.ollama_tag, prompt="",
                keep_alive=f"{self.idle_unload_minutes}m",
            )
            state.status = "loaded"
            state.last_used_at = time.time()
            state.error = None
            log.info("Model bellege yuklendi: %s", state.ollama_tag)
        except Exception as exc:
            state.error = f"Bellege yukleme hatasi: {exc}"
            log.warning("Bellege yukleme basarisiz [%s]: %s", state.ollama_tag, exc)
        finally:
            state.warming_up = False

    async def unload_model(self, model_id: str) -> None:
        """Modeli RAM/VRAM'dan cikarir; diskte kalir, gerekince yeniden yuklenir."""
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        await self.client.unload(state.ollama_tag)
        if state.status == "loaded":
            state.status = "ready"
        log.info("Model bellekten cikarildi: %s", state.ollama_tag)

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
        if self._pull_lock.locked() and state.status != "pulling":
            state.status = "queued"
            state.pull_stage = "sirada bekliyor"
        try:
            await self._pull_locked(model_id, state)
        except asyncio.CancelledError:
            if state.status == "queued":
                state.status = "passive" if model_id in self.passive_model_ids else "unknown"
                state.error = None
                state.reset_pull_telemetry()
                state.pull_stage = "iptal edildi"
                log.info("Siradaki pull iptal edildi: %s", state.ollama_tag)
            raise

    async def _pull_locked(self, model_id: str, state: ModelState) -> None:
        async with self._pull_lock:
            if state.pulled:
                if state.status == "queued":
                    state.status = "ready"
                return
            state.status = "pulling"
            state.error = None
            state.reset_pull_telemetry()
            state.pull_stage = "baslatiliyor"
            state.pull_started_at = time.time()
            layers: dict[str, tuple[int, int]] = {}
            speed_t0 = time.monotonic()
            speed_bytes0 = 0
            try:
                async for event in self.client.pull(state.ollama_tag):
                    stage = str(event.get("status") or "")
                    if stage:
                        state.pull_stage = stage
                    digest = str(event.get("digest") or "")
                    if digest:
                        state.pull_digests.add(digest)
                    total = int(event.get("total") or 0)
                    completed = int(event.get("completed") or 0)
                    if total > 0:
                        layers[digest or stage or "_"] = (completed, total)
                        agg_done = sum(c for c, _ in layers.values())
                        agg_total = sum(t for _, t in layers.values())
                        state.pull_completed_bytes = agg_done
                        state.pull_total_bytes = agg_total
                        state.last_pull_progress = min(1.0, agg_done / agg_total)
                        now = time.monotonic()
                        dt = now - speed_t0
                        if dt >= 0.5:
                            inst = max(0.0, (agg_done - speed_bytes0) / dt)
                            state.pull_speed_bps = (
                                inst if state.pull_speed_bps <= 0
                                else 0.3 * inst + 0.7 * state.pull_speed_bps
                            )
                            speed_t0 = now
                            speed_bytes0 = agg_done
                            if state.pull_speed_bps > 0:
                                state.pull_eta_seconds = max(
                                    0.0, (agg_total - agg_done) / state.pull_speed_bps
                                )
                    if event.get("status") == "success":
                        break
                state.pulled = True
                state.status = "ready"
                state.last_pull_progress = 1.0
                state.pull_stage = "success"
                state.pull_speed_bps = 0.0
                state.pull_eta_seconds = None
                if state.pull_total_bytes:
                    state.pull_completed_bytes = state.pull_total_bytes
                log.info("Model indirildi: %s", state.ollama_tag)
            except asyncio.CancelledError:
                digests = set(state.pull_digests)
                state.status = "passive" if model_id in self.passive_model_ids else "unknown"
                state.error = None
                state.reset_pull_telemetry()
                state.pull_stage = "iptal edildi"
                state.pull_digests = digests
                log.info("Pull iptal edildi: %s", state.ollama_tag)
                raise
            except Exception as exc:
                state.status = "error"
                state.error = str(exc)
                log.error("Pull hatasi [%s]: %s", state.ollama_tag, exc)
                raise

    def _reap_pull_task(self, task: asyncio.Task) -> None:
        self._bg_pulls.discard(task)
        for mid, t in list(self._pull_tasks.items()):
            if t is task:
                self._pull_tasks.pop(mid, None)
        if not task.cancelled():
            task.exception()

    def start_pull(self, model_id: str) -> asyncio.Task:
        """Indirmeyi izlenebilir/iptal edilebilir arka plan gorevi olarak baslatir.

        Ayni model icin suren bir gorev varsa onu dondurur (tek indirme).
        """
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        existing = self._pull_tasks.get(model_id)
        if existing and not existing.done():
            return existing
        task = asyncio.create_task(self.ensure_pulled(model_id))
        self._pull_tasks[model_id] = task
        self._bg_pulls.add(task)
        task.add_done_callback(self._reap_pull_task)
        return task

    async def cancel_pull(self, model_id: str) -> bool:
        """Suren indirmeyi durdurur ve yarim kalan dosyalari temizler."""
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        task = self._pull_tasks.get(model_id)
        if not task or task.done():
            return False
        was_pulling = state.status == "pulling"
        digests = set(state.pull_digests)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        if was_pulling:
            async with self._pull_lock:
                await self.client.delete(state.ollama_tag)
                remove_partial_blobs(digests)
                if state.status not in ("pulling", "queued"):
                    state.pull_digests = set()
        return True

    async def shutdown_pulls(self) -> list[str]:
        """Tum suren/siradaki pull gorevlerini iptal eder (replan/kapanis icin).

        Kesilen model id'lerini dondurur; cagiran taraf yeni orchestrator'da
        bunlari start_pull ile devam ettirebilir (Ollama partial'dan surdurur).
        """
        active = {mid: t for mid, t in self._pull_tasks.items() if not t.done()}
        for t in active.values():
            t.cancel()
        for t in active.values():
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        return list(active.keys())

    async def pull_events(self, model_id: str) -> AsyncIterator[dict[str, Any]]:
        """Pull'u arka plan gorevi olarak baslatir, bitene kadar periyodik
        ilerleme anlik goruntuleri uretir. Tuketici baglantiyi koparsa
        indirme arka planda devam eder; hata son `await`te yukari tasinir.
        """
        state = self._states.get(model_id)
        if not state:
            raise KeyError(f"Bilinmeyen model: {model_id}")
        if state.pulled:
            return
        task = self.start_pull(model_id)
        yield state.to_public()
        while not task.done():
            await asyncio.wait({task}, timeout=0.7)
            yield state.to_public()
        try:
            await task
        except asyncio.CancelledError:
            if task.cancelled():
                raise OllamaError(f"Model indirmesi iptal edildi: {model_id}") from None
            raise

    async def delete_model(self, model_id: str) -> bool:
        """Modeli Ollama'dan siler ve state'i 'indirilmemis' olarak gunceller."""
        state = self._states.get(model_id)
        if not state:
            return False
        ok = await self.client.delete(state.ollama_tag)
        if ok:
            state.pulled = False
            state.reset_pull_telemetry()
            state.status = "passive" if model_id in self.passive_model_ids else "unknown"
            log.info("Model Ollama'dan silindi: %s", state.ollama_tag)
        return ok

    async def pull_initial(self) -> None:
        """auto_pull aciksa en kucuk 1 modeli (genelde fallback) indir.

        auto_pull kapaliyken (varsayilan) hicbir sey indirilmez — kullanici
        secinceye kadar disk/ag yuku olmaz; yalnizca pulled bayraklari tazelenir.
        """
        await self.refresh_pulled_flags()
        if not self.auto_pull:
            log.info("auto_pull kapali; seed pull atlandi (lazy mod)")
            return
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
            task = self.start_pull(model_id)
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if task.cancelled():
                    raise OllamaError(f"Model indirmesi iptal edildi: {model_id}") from None
                raise

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
            async for snapshot in self.pull_events(model_id):
                yield {"_pull_progress": snapshot}

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
