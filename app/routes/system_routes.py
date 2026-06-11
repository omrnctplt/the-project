"""Sistem — profil, kapasite, runtime config, kaynaklar, bootstrap durumu."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from .. import auth, capacity as capacity_mod, config as cfg, runtime, sysmonitor
from ..deps import get_state
from ..models import ConfigUpdateRequest, SystemProfileResponse

router = APIRouter()


@router.get("/api/v1/system/bootstrap", include_in_schema=False)
async def bootstrap_status(request: Request) -> dict[str, Any]:
    """Bootstrap state'i — frontend buradan canli takip eder.

    Token gerektirmez; sistem hazirlanirken login ekraninda gosterilebilsin.
    """
    state = get_state(request)
    return {
        "ready": bool(state.ready),
        **state.bootstrap.to_dict(),
    }


@router.get("/api/v1/system/profile", response_model=SystemProfileResponse)
async def system_profile(request: Request, _=Depends(auth.current_principal)) -> SystemProfileResponse:
    state = get_state(request)
    return SystemProfileResponse(
        hardware=state.hw_profile,
        capacity=state.capacity,
        runtime_config=state.runtime_config,
    )


@router.get("/api/v1/system/profiles")
async def system_profiles(_=Depends(auth.current_principal)) -> dict[str, Any]:
    return {
        name: {
            "label": cfg_obj["label"],
            "max_active": cfg_obj["max_active"],
            "max_loaded_models": cfg_obj["max_loaded_models"],
            "num_parallel": cfg_obj["num_parallel"],
            "allowed_categories": cfg_obj["allowed_categories"],
        }
        for name, cfg_obj in capacity_mod.PROFILES.items()
    }


@router.get("/api/v1/system/config")
async def get_runtime_config(_=Depends(auth.current_principal)) -> dict[str, Any]:
    return cfg.load_runtime_config()


@router.put("/api/v1/system/config")
async def update_runtime_config(
    body: ConfigUpdateRequest,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg.update_runtime_config(**changes)
    return await runtime.replan_state(get_state(request))


@router.post("/api/v1/system/replan")
async def replan(request: Request, _=Depends(auth.require_admin)) -> dict[str, Any]:
    return await runtime.replan_state(get_state(request))


@router.get("/api/v1/system/resources")
async def system_resources(_=Depends(auth.require_admin)) -> dict[str, Any]:
    """Sistem kaynak ozeti — host CPU/mem/disk + top processes + actions."""
    return sysmonitor.snapshot()


@router.get("/api/v1/onboarding/state")
async def onboarding_state(request: Request, _=Depends(auth.current_principal)) -> dict[str, Any]:
    """Ilk acilis akisi icin: bir model pull edilmis mi, kullanici ne yapmali?"""
    state = get_state(request)
    has_orch = state.orchestrator is not None
    pulled = []
    if has_orch:
        for s in state.orchestrator.states():
            if s["pulled"]:
                pulled.append(s)
    return {
        "needs_onboarding": len(pulled) == 0,
        "pulled_count": len(pulled),
        "pulled_models": [p["model_id"] for p in pulled],
        "current_profile": state.capacity.get("profile") if state.capacity else None,
        "active_models": state.capacity.get("active_models", []) if state.capacity else [],
    }
