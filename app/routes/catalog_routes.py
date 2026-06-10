"""Model katalogu — listeleme, kesif (statik + canli), ekleme/silme, pull."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import auth, capacity as capacity_mod, config as cfg, discovery, runtime
from ..deps import get_state
from ..models import CatalogModelRequest

router = APIRouter()


@router.get("/api/v1/models")
async def list_models(request: Request, _=Depends(auth.current_principal)) -> dict[str, Any]:
    state = get_state(request)
    if not state.orchestrator:
        return {"models": []}
    return {
        "active": state.capacity.get("active_models", []),
        "passive": state.capacity.get("passive_models", []),
        "states": state.orchestrator.states(),
    }


@router.get("/api/v1/system/catalog")
async def get_catalog(request: Request, _=Depends(auth.current_principal)) -> dict[str, Any]:
    state = get_state(request)
    overrides = cfg.load_catalog_overrides().get("models") or {}
    return {
        "models": state.catalog.get("models", {}),
        "departments": state.catalog.get("departments", {}),
        "overridden": list(overrides.keys()),
    }


def _advice_for_verdict(fits_current: bool, fits_total: bool, accel: str) -> str:
    if fits_current:
        return "Model, ayrilan bellek butcesine sigiyor — aktif olarak yuklenebilir."
    if fits_total:
        return ("Mevcut profilin bellek butcesi dolu ama donanim toplaminda yer var. "
                "Daha buyuk bir profil (balanced/performance) secebilirsiniz.")
    return ("Model bu donanim icin cok buyuk. Daha kucuk bir varyant secin "
            f"(orn: 7B yerine 3B) veya {'GPU' if accel == 'cpu' else 'daha buyuk bir GPU'} gerekli.")


@router.post("/api/v1/system/catalog/dry-run")
async def catalog_dry_run(
    body: CatalogModelRequest,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    """Modeli kataloga eklemeden once: butce uygun mu, hangi profilde aktif olur?"""
    state = get_state(request)
    cap = state.capacity or {}
    accelerator = cap.get("accelerator", "cpu")
    budget_total = float(cap.get("budget_total_gb", 0) or 0)
    budget_used = float(cap.get("budget_used_gb", 0) or 0)
    budget_free = max(0.0, budget_total - budget_used)

    size_gb = float(body.vram_gb if (accelerator == "gpu" and body.vram_gb) else body.ram_gb)
    fits_current = size_gb <= budget_free
    fits_total = size_gb <= budget_total

    profiles_result = {}
    for pname, pcfg in capacity_mod.PROFILES.items():
        ratio = pcfg["budget_ratio_gpu"] if accelerator == "gpu" else pcfg["budget_ratio_cpu"]
        hw_total = (
            float((state.hw_profile.get("gpu") or {}).get("vram_total_gb") or 0)
            if accelerator == "gpu"
            else float((state.hw_profile.get("memory") or {}).get("effective_total_gb") or 0)
        )
        prof_budget = max(0.5, hw_total * ratio)
        profiles_result[pname] = {
            "budget_total_gb": round(prof_budget, 2),
            "fits": size_gb <= prof_budget,
            "category_allowed": body.category in pcfg["allowed_categories"],
        }

    return {
        "model_id": body.model_id,
        "size_gb": size_gb,
        "accelerator": accelerator,
        "current_profile": cap.get("profile"),
        "current_budget_free_gb": round(budget_free, 2),
        "current_budget_total_gb": round(budget_total, 2),
        "fits_current_free": fits_current,
        "fits_current_total": fits_total,
        "profiles": profiles_result,
        "verdict": (
            "active" if fits_current else
            ("passive_in_current_profile" if fits_total else "too_large_for_hardware")
        ),
        "advice": _advice_for_verdict(fits_current, fits_total, accelerator),
    }


@router.post("/api/v1/system/catalog/models")
async def add_catalog_model(
    body: CatalogModelRequest,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = get_state(request)
    payload = body.model_dump(exclude_none=True)
    model_id = payload.pop("model_id")
    tag = str(payload.get("ollama_tag", ""))
    payload.setdefault("source", "huggingface" if tag.startswith(("hf.co/", "huggingface.co/")) else "ollama")
    payload.setdefault("tier", "laptop")
    cfg.add_catalog_override(model_id, payload)
    state.catalog = cfg.load_catalog()
    return await runtime.replan_state(state)


@router.delete("/api/v1/system/catalog/models/{model_id}")
async def delete_catalog_model(
    model_id: str,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = get_state(request)
    if not cfg.remove_catalog_override(model_id):
        raise HTTPException(status_code=404, detail="Override bulunamadi (orijinal katalog dosyasi degistirilemez)")
    state.catalog = cfg.load_catalog()
    return await runtime.replan_state(state)


def _model_label(model_id: str, m: dict[str, Any]) -> str:
    return model_id.replace("-", " ").title()


@router.get("/api/v1/system/discover")
async def discover_models(
    q: str | None = None,
    category: str | None = None,
    max_gb: float | None = None,
    tier: str | None = None,
    request: Request = None,  # type: ignore
    _=Depends(auth.current_principal),
) -> dict[str, Any]:
    """Donanima gore onerilen modeller — statik katalog havuzundan."""
    state = get_state(request)
    catalog_models = (state.catalog or {}).get("models", {}) or {}
    cap = state.capacity or {}
    hw_tier = cap.get("hardware_tier", "laptop")
    accelerator = cap.get("accelerator", "cpu")
    budget_total = float(cap.get("budget_total_gb", 0) or 0)
    raw_free = cap.get("budget_free_gb")
    budget_free = budget_total if raw_free is None else float(raw_free)

    pulled_ids: set[str] = set()
    if state.orchestrator:
        for s in state.orchestrator.states():
            if s.get("pulled"):
                pulled_ids.add(s["model_id"])

    ql = (q or "").lower().strip()
    items = []
    for mid, m in catalog_models.items():
        size = float(
            (m.get("vram_gb") if accelerator == "gpu" else m.get("ram_gb"))
            or m.get("ram_gb") or m.get("vram_gb") or 0.0
        )
        mcat = str(m.get("category", "text"))
        mtier = str(m.get("tier", "laptop"))
        label = _model_label(mid, m)
        blurb = str(m.get("profile") or "")
        if category and mcat != category:
            continue
        if tier and mtier != tier:
            continue
        if max_gb is not None and size > max_gb:
            continue
        if ql and ql not in mid.lower() and ql not in str(m.get("ollama_tag", "")).lower() and ql not in label.lower():
            continue
        items.append({
            "model_id": mid,
            "tag": m.get("ollama_tag"),
            "ollama_tag": m.get("ollama_tag"),
            "label": label,
            "blurb": blurb,
            "category": mcat,
            "tier": mtier,
            "source": m.get("source", "ollama"),
            "license": m.get("license"),
            "approx_gb": size,
            "parameters_b": m.get("parameters_b"),
            "in_catalog": True,
            "pulled": mid in pulled_ids,
            "fits": size <= budget_free + 0.01,
            "fits_total": size <= (budget_total + 0.01),
            "recommended": (mtier == hw_tier) and (size <= budget_total + 0.01),
        })

    items.sort(key=lambda it: (not it["recommended"], it["approx_gb"]))
    return {
        "models": items,
        "hardware_tier": hw_tier,
        "accelerator": accelerator,
        "categories": ["text", "code", "reasoning", "persona", "fallback"],
        "tiers": list(capacity_mod.TIER_ORDER),
    }


@router.get("/api/v1/system/discover/remote")
async def discover_remote(
    q: str | None = None,
    category: str | None = None,
    provider: str | None = None,
    tier: str | None = None,
    refresh: bool = False,
    limit: int = 200,
    request: Request = None,  # type: ignore
    principal: dict[str, Any] = Depends(auth.current_principal),
) -> dict[str, Any]:
    """Canli uzak katalog — ollama.com + HuggingFace'ten guncel modeller.

    Sonuc TTL'li cache'ten gelir; `refresh=true` (admin) interneti zorlar.
    Yeni cikan modeller icin UI/katalog guncellemesi gerekmez.
    """
    force = bool(refresh) and principal.get("role") == "admin"
    remote = await discovery.get_remote_catalog(force=force)

    state = get_state(request)
    catalog_models = (state.catalog or {}).get("models", {}) or {}
    catalog_tags = {str(m.get("ollama_tag", "")) for m in catalog_models.values()}
    cap = state.capacity or {}
    hw_tier = cap.get("hardware_tier", "laptop")
    budget_total = float(cap.get("budget_total_gb", 0) or 0)
    raw_free = cap.get("budget_free_gb")
    budget_free = budget_total if raw_free is None else float(raw_free)

    pulled_tags: set[str] = set()
    if state.orchestrator:
        for s in state.orchestrator.states():
            if s.get("pulled"):
                pulled_tags.add(str(s.get("ollama_tag", "")))

    ql = (q or "").lower().strip()
    items = []
    for m in remote.get("models", []):
        if category and m.get("category") != category:
            continue
        if provider and m.get("provider") != provider:
            continue
        if tier and m.get("tier") != tier:
            continue
        if ql and ql not in m.get("tag", "").lower() and ql not in m.get("label", "").lower():
            continue
        size = float(m.get("approx_gb") or 0)
        is_cloud = bool(m.get("cloud"))
        items.append({
            **m,
            "in_catalog": m.get("tag") in catalog_tags,
            "pulled": m.get("tag") in pulled_tags,
            "fits": (not is_cloud) and size <= budget_free + 0.01,
            "fits_total": (not is_cloud) and size <= budget_total + 0.01,
            "recommended": (not is_cloud) and (m.get("tier") == hw_tier) and (size <= budget_total + 0.01),
        })

    items.sort(key=lambda it: (not it["recommended"], -int(it.get("popularity") or 0)))
    fetched_at = float(remote.get("fetched_at") or 0)
    return {
        "models": items[: max(1, min(limit, 1000))],
        "total": len(items),
        "hardware_tier": hw_tier,
        "fetched_at": fetched_at,
        "age_minutes": round((time.time() - fetched_at) / 60, 1) if fetched_at else None,
        "stale": bool(remote.get("stale")),
        "errors": remote.get("errors") or [],
        "sources": remote.get("sources") or {},
    }


@router.get("/api/v1/system/ollama/local")
async def ollama_local(request: Request, _=Depends(auth.require_admin)) -> dict[str, Any]:
    state = get_state(request)
    if not state.orchestrator:
        return {"models": []}
    try:
        local = await state.orchestrator.client.list_local()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama'ya ulasilamadi: {exc}") from exc
    return {"models": local}


@router.post("/api/v1/system/ollama/inspect")
async def ollama_inspect(
    body: dict[str, str],
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = get_state(request)
    tag = body.get("ollama_tag")
    if not tag:
        raise HTTPException(status_code=400, detail="ollama_tag zorunlu")
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator hazir degil")
    info = await state.orchestrator.client.show(tag)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Ollama '{tag}' tagini taniyamadi (pull edilmis olmasi gerek)")
    details = info.get("details") or {}
    size_bytes = float(info.get("size") or 0)
    return {
        "ollama_tag": tag,
        "parameter_size": details.get("parameter_size"),
        "quantization_level": details.get("quantization_level"),
        "family": details.get("family"),
        "estimated_ram_gb": round(size_bytes / 1024**3 * 1.1, 2) if size_bytes else None,
    }


@router.post("/api/v1/system/pull/{model_id}")
async def pull_model(
    model_id: str,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = get_state(request)
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator hazir degil")
    if not state.orchestrator.get_state(model_id):
        raise HTTPException(status_code=404, detail=f"Model bulunamadi: {model_id}")
    state.tasks.append(
        asyncio.create_task(state.orchestrator.ensure_pulled(model_id))
    )
    return {"status": "pull_started", "model_id": model_id}


@router.delete("/api/v1/system/models/{model_id}/pulled")
async def delete_pulled_model(
    model_id: str,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    """Modeli Ollama'dan tamamen siler (disk bosaltir). Katalog tanimi korunur."""
    state = get_state(request)
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator hazir degil")
    if not state.orchestrator.get_state(model_id):
        raise HTTPException(status_code=404, detail=f"Model bulunamadi: {model_id}")
    ok = await state.orchestrator.delete_model(model_id)
    if not ok:
        raise HTTPException(status_code=502, detail="Ollama'dan silinemedi (model yuklu olmayabilir)")
    return {"status": "deleted", "model_id": model_id}
