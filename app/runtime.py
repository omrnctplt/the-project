"""Uygulama yasam dongusu — bootstrap, kapasite plani, replan, periyodik gorevler.

main.py'deki FastAPI app tanimi ile route modullerinin ikisinin de ihtiyac
duydugu durum-yonetimi mantigi burada yasar; boylece import dongusu olusmaz.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from . import audit, auth, capacity as capacity_mod, config as cfg, hwprobe, metrics, usage
from .ollama_client import OllamaClient
from .orchestrator import Orchestrator
from .router import Router
from .state import AppState

log = logging.getLogger("gateway")

RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "180") or 0)
RETENTION_SWEEP_HOURS = 24


def env_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        log.warning("%s degeri sayi degil: %r", name, raw)
        return None


def refresh_capacity_metrics(state: AppState) -> None:
    cap = state.capacity or {}
    metrics.ACTIVE_MODELS.set(len(cap.get("active_models") or []))
    hw = state.hw_profile or {}
    gpu = (hw.get("gpu") or {})
    mem = (hw.get("memory") or {})
    try:
        metrics.HARDWARE_INFO.labels(
            accelerator=cap.get("accelerator", "?"),
            profile=cap.get("profile", "?"),
            gpu_count=str(len(gpu.get("devices") or [])),
            ram_gb=str(mem.get("effective_total_gb", "?")),
            vram_gb=str(gpu.get("vram_total_gb", "?")),
        ).set(1)
    except Exception:
        pass


def build_orchestrator(state: AppState) -> Orchestrator:
    cap = state.capacity or {}
    return Orchestrator(
        catalog=state.catalog,
        active_model_ids=list(cap.get("active_models") or []),
        passive_model_ids=list(cap.get("passive_models") or []),
        client=OllamaClient(),
        auto_pull=bool(state.runtime_config.get("auto_pull", False)),
        idle_unload_minutes=int(state.runtime_config.get("idle_unload_minutes", 3)),
        max_concurrent_requests=int(cap.get("max_concurrent_requests", 1)),
    )


def make_plan(state: AppState) -> dict[str, Any]:
    plan = capacity_mod.plan(
        hw_profile=state.hw_profile,
        catalog=state.catalog,
        runtime_config=state.runtime_config,
        ollama_num_parallel=env_int("OLLAMA_NUM_PARALLEL"),
        ollama_max_loaded_models=env_int("OLLAMA_MAX_LOADED_MODELS"),
    )
    state.capacity = plan.to_dict()
    for warn in plan.warnings:
        log.warning("Kapasite uyari: %s", warn)
    log.info(
        "Kapasite plani: profil=%s, %s, %d aktif model, ~%d es zamanli istek (butce %.1f/%.1f GB)",
        plan.profile,
        plan.accelerator,
        len(plan.active_models),
        plan.max_concurrent_requests,
        plan.budget_used_gb,
        plan.budget_total_gb,
    )
    return state.capacity


async def replan_state(state: AppState) -> dict[str, Any]:
    state.runtime_config = cfg.load_runtime_config()
    make_plan(state)
    if state.sweep_task and not state.sweep_task.done():
        state.sweep_task.cancel()
    interrupted_pulls: list[str] = []
    if state.orchestrator:
        try:
            interrupted_pulls = await state.orchestrator.shutdown_pulls()
        except Exception as exc:
            log.warning("Replan: pull gorevleri durdurulamadi: %s", exc)
        try:
            await state.orchestrator.client.aclose()
        except Exception:
            pass
    state.tasks = [t for t in state.tasks if not t.done()]
    state.orchestrator = build_orchestrator(state)
    state.router = Router(state.catalog, state.orchestrator, state.runtime_config.get("category_assignments"))
    refresh_capacity_metrics(state)
    state.tasks.append(asyncio.create_task(state.orchestrator.pull_initial()))
    for mid in interrupted_pulls:
        if state.orchestrator.get_state(mid):
            log.info("Replan: kesilen indirme devam ettiriliyor: %s", mid)
            state.tasks.append(state.orchestrator.start_pull(mid))
    state.sweep_task = asyncio.create_task(state.orchestrator.idle_sweep_loop())
    state.tasks.append(state.sweep_task)
    return state.capacity


async def retention_loop(days: int = RETENTION_DAYS, period_hours: float = RETENTION_SWEEP_HOURS) -> None:
    """KVKK saklama suresi: audit/usage kayitlarini periyodik temizler."""
    if days <= 0:
        return
    while True:
        try:
            removed_audit = audit.purge_older_than(days)
            removed_usage = usage.purge_older_than(days)
            if removed_audit or removed_usage:
                log.info(
                    "KVKK retention: %d audit + %d usage kaydi silindi (>%d gun)",
                    removed_audit, removed_usage, days,
                )
        except Exception as exc:
            log.warning("Retention temizligi basarisiz: %s", exc)
        try:
            await asyncio.sleep(period_hours * 3600)
        except asyncio.CancelledError:
            return


async def bootstrap(state: AppState) -> None:
    bt = state.bootstrap
    bt.add("schema",     "Veritabani semalari hazirlaniyor")
    bt.add("users",      "Demo kullanicilar seed ediliyor")
    bt.add("hw",         "Donanim taraniyor")
    bt.add("catalog",    "Model katalogu yukleniyor")
    bt.add("plan",       "Kapasite plani uretiliyor")
    bt.add("orch",       "Orchestrator + router baslatiliyor")
    bt.add("local_scan", "Ollama'daki yerel modeller taraniyor")
    log.info("Bootstrap basliyor...")

    bt.start("schema")
    try:
        audit.ensure_schema()
        usage.ensure_schema()
        bt.finish("schema", "ok", "audit + usage tablolari hazir")
    except Exception as exc:
        bt.finish("schema", "error", str(exc))
        log.exception("Schema hata: %s", exc)
        raise

    bt.start("users")
    try:
        auth.seed_default_users()
        bt.finish("users", "ok")
    except Exception as exc:
        bt.finish("users", "warn", str(exc))
        log.warning("User seed hata: %s", exc)

    bt.start("hw")
    profile = hwprobe.probe()
    hwprobe.write_profile(profile)
    state.hw_profile = profile
    bt.finish(
        "hw", "ok",
        f"{profile['cpu']['logical_cores']} CPU, "
        f"{profile['memory']['effective_total_gb']:.1f} GB RAM, "
        f"GPU: {profile['gpu']['vram_total_gb'] if profile['gpu']['available'] else 'yok'}"
    )
    log.info(
        "Donanim: %s CPU, %.1f GB RAM (%s), GPU=%s",
        profile["cpu"]["logical_cores"],
        profile["memory"]["effective_total_gb"],
        profile["memory"].get("effective_source", "?"),
        profile["gpu"]["vram_total_gb"] if profile["gpu"]["available"] else "yok",
    )

    bt.start("catalog")
    try:
        state.catalog = cfg.load_catalog()
        state.runtime_config = cfg.load_runtime_config()
        bt.finish("catalog", "ok", f"{len(state.catalog.get('models', {}))} model tanimi yuklendi")
    except Exception as exc:
        bt.finish("catalog", "error", str(exc))
        raise

    bt.start("plan")
    try:
        make_plan(state)
        refresh_capacity_metrics(state)
        cap = state.capacity
        bt.finish(
            "plan", "ok",
            f"Profil: {cap.get('profile')}, {len(cap.get('active_models') or [])} aktif model, "
            f"butce {cap.get('budget_used_gb', 0):.1f}/{cap.get('budget_total_gb', 0):.1f} GB"
        )
    except Exception as exc:
        bt.finish("plan", "error", str(exc))
        raise

    bt.start("orch")
    orch = build_orchestrator(state)
    state.orchestrator = orch
    state.router = Router(state.catalog, orch, state.runtime_config.get("category_assignments"))
    bt.finish("orch", "ok", f"max {orch.max_concurrent_requests} eszamanli istek")

    bt.start("local_scan")
    try:
        await orch.refresh_pulled_flags()
        pulled = [m for m in orch.states() if m["pulled"]]
        bt.finish("local_scan", "ok",
                  f"{len(pulled)} model Ollama'da yerel bulundu" if pulled
                  else "yerel model yok (kullanici secimi bekleniyor)")
    except Exception as exc:
        bt.finish("local_scan", "warn", f"Ollama'ya ulasilamadi: {exc}")

    try:
        from . import orchestrator as orch_mod
        orch_mod.sweep_stale_partials()
    except Exception as exc:
        log.warning("Eski partial temizligi atlandi: %s", exc)

    state.ready = True
    state.bootstrap.finished_at = time.time()
    log.info("Gateway hazir. ONBOARDING bekleniyor — kullanici model secinceye kadar pull yapilmaz.")

    state.sweep_task = asyncio.create_task(orch.idle_sweep_loop())
    state.tasks.append(state.sweep_task)
    state.tasks.append(asyncio.create_task(retention_loop()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    app.state.app_state = state
    try:
        await bootstrap(state)
    except Exception as exc:
        log.exception("Bootstrap hata aldi: %s", exc)
        state.ready = False
    try:
        yield
    finally:
        for t in state.tasks:
            t.cancel()
        for t in state.tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        if state.orchestrator:
            try:
                await state.orchestrator.client.aclose()
            except Exception:
                pass
        log.info("Gateway kapaniyor.")
