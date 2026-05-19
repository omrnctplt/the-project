"""FastAPI ana uygulama — gateway, router, orchestrator hepsi burada birleser."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import audit, auth, capacity as capacity_mod, config as cfg, hwprobe, metrics, usage
from .models import (
    ChatRequest,
    ChatResponse,
    ConfigUpdateRequest,
    LoginRequest,
    SystemProfileResponse,
    TokenResponse,
    UsageSummary,
)
from .ollama_client import OllamaClient, OllamaError
from .orchestrator import Orchestrator
from .router import Router
from .state import AppState

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("gateway")


def _refresh_capacity_metrics(state: AppState) -> None:
    cap = state.capacity or {}
    metrics.ACTIVE_MODELS.set(len(cap.get("active_models") or []))
    hw = state.hw_profile or {}
    gpu = (hw.get("gpu") or {})
    mem = (hw.get("memory") or {})
    try:
        metrics.HARDWARE_INFO.labels(
            accelerator=cap.get("accelerator", "?"),
            gpu_count=str(len(gpu.get("devices") or [])),
            ram_gb=str(mem.get("effective_total_gb", "?")),
            vram_gb=str(gpu.get("vram_total_gb", "?")),
        ).set(1)
    except Exception:
        pass


async def _bootstrap(state: AppState) -> None:
    log.info("Bootstrap basliyor...")

    audit.ensure_schema()
    usage.ensure_schema()
    auth.seed_default_users()

    log.info("Donanim profili cikariliyor...")
    profile = hwprobe.probe()
    hwprobe.write_profile(profile)
    state.hw_profile = profile
    log.info(
        "Donanim: %s CPU, %.1f GB RAM, GPU=%s",
        profile["cpu"]["logical_cores"],
        profile["memory"]["effective_total_gb"],
        profile["gpu"]["vram_total_gb"] if profile["gpu"]["available"] else "yok",
    )

    catalog = cfg.load_catalog()
    state.catalog = catalog
    state.runtime_config = cfg.load_runtime_config()

    ollama_num_parallel = int(os.getenv("OLLAMA_NUM_PARALLEL", "2"))
    ollama_max_loaded = int(os.getenv("OLLAMA_MAX_LOADED_MODELS", "3"))
    plan = capacity_mod.plan(
        hw_profile=profile,
        catalog=catalog,
        runtime_config=state.runtime_config,
        ollama_num_parallel=ollama_num_parallel,
        ollama_max_loaded_models=ollama_max_loaded,
    )
    state.capacity = plan.to_dict()
    log.info(
        "Kapasite plani: %s, %d aktif model, ~%d es zamanli istek",
        plan.accelerator,
        len(plan.active_models),
        plan.max_concurrent_requests,
    )
    for warn in plan.warnings:
        log.warning("Kapasite uyari: %s", warn)
    _refresh_capacity_metrics(state)

    orch = Orchestrator(
        catalog=catalog,
        active_model_ids=plan.active_models,
        passive_model_ids=plan.passive_models,
        client=OllamaClient(),
        auto_pull=state.runtime_config.get("auto_pull", True),
        idle_unload_minutes=int(state.runtime_config.get("idle_unload_minutes", 10)),
    )
    state.orchestrator = orch
    state.router = Router(catalog, orch)

    state.ready = True
    log.info("Gateway hazir. /healthz 200, modeller arka planda iniyor olabilir.")

    async def _pull_loop() -> None:
        try:
            await orch.refresh_pulled_flags()
            if orch.auto_pull:
                log.info("Aktif modeller indiriliyor (background)...")
                await orch.pull_all_active()
            if catalog.get("defaults", {}).get("warmup_on_start"):
                await orch.warmup_all()
        except Exception as exc:
            log.exception("Pull/warmup hatasi: %s", exc)

    asyncio.create_task(_pull_loop())
    asyncio.create_task(orch.idle_sweep_loop())


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    app.state.app_state = state
    try:
        await _bootstrap(state)
    except Exception as exc:
        log.exception("Bootstrap hata aldi: %s", exc)
        state.ready = False
    yield
    if state.orchestrator:
        await state.orchestrator.client.aclose()
    log.info("Gateway kapaniyor.")


APP_ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(APP_ROOT / "ui" / "templates"))

app = FastAPI(
    title="On-Premise AI Gateway",
    version="0.1.0",
    description="Departman bazli akilli yonlendirme + denetim katmani.",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(APP_ROOT / "ui" / "static")), name="static")


def _state(request: Request) -> AppState:
    return request.app.state.app_state


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:
    state = _state(request)
    ollama_alive = False
    if state.orchestrator:
        ollama_alive = await state.orchestrator.client.is_alive()
    payload = {
        "ready": bool(state.ready and ollama_alive),
        "ollama": ollama_alive,
        "active_models": (state.capacity or {}).get("active_models", []),
    }
    code = 200 if payload["ready"] else 503
    return JSONResponse(payload, status_code=code)


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Any:
    from fastapi.responses import Response
    state = _state(request)
    if state.orchestrator:
        try:
            running = await state.orchestrator.client.list_running()
            metrics.LOADED_MODELS.set(len(running))
        except Exception:
            pass
        for st in state.orchestrator.states():
            if st.get("status") == "pulling":
                metrics.MODEL_PULL_PROGRESS.labels(model=st["model_id"]).set(0.5)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    user = auth.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Kullanici adi veya sifre hatali")
    token, ttl = auth.create_access_token(
        username=user["username"],
        department=user["department"],
        role=user["role"],
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        department=user["department"],
        role=user["role"],
        label=user.get("label"),
        expires_in=ttl,
    )


def _resolve_rate_limit(catalog: dict[str, Any], department: str) -> int:
    dept = (catalog.get("departments") or {}).get(department) or {}
    return int(dept.get("rate_limit_per_min", 30))


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    principal: dict[str, Any] = Depends(auth.current_principal),
) -> ChatResponse:
    state = _state(request)
    if not state.ready or not state.router or not state.orchestrator:
        raise HTTPException(status_code=503, detail="Gateway henuz hazir degil")

    department = principal["department"]
    username = principal["username"]
    rate_limit = _resolve_rate_limit(state.catalog, department)
    allowed, _count = usage.check_and_record_rate(
        key=f"user:{username}", limit_per_min=rate_limit
    )
    if not allowed:
        metrics.RATE_LIMITED.labels(department=department).inc()
        raise HTTPException(
            status_code=429,
            detail=f"Departman/kullanici dakika basina {rate_limit} istek limitini asti",
        )

    metrics.INFLIGHT.inc()
    try:
        if body.model_id and principal["role"] == "admin":
            override = state.orchestrator.get_state(body.model_id)
            if not override:
                raise HTTPException(status_code=400, detail=f"Model bulunamadi: {body.model_id}")
            decision_model = body.model_id
            category = override.category
            matched_rule = "admin_override"
            fallback = False
            fallback_reason: str | None = None
        else:
            decision = state.router.decide(department, body.prompt)
            decision_model = decision.model_id
            category = decision.category
            matched_rule = decision.matched_rule
            fallback = decision.fallback_triggered
            fallback_reason = decision.fallback_reason
            if fallback:
                metrics.FALLBACKS.labels(department=department).inc()

        try:
            with metrics.LATENCY.labels(model=decision_model, category=category).time():
                result = await state.orchestrator.call(
                    decision_model,
                    body.prompt,
                    temperature=body.temperature,
                    context_window=state.catalog.get("defaults", {}).get("context_window"),
                )
        except OllamaError as exc:
            metrics.REQUESTS.labels(
                model=decision_model, category=category,
                department=department, status="error",
            ).inc()
            audit.write(
                username=username, department=department, prompt=body.prompt,
                model_id=decision_model, category=category, matched_rule=matched_rule,
                fallback=fallback, status="error", latency_ms=None, error=str(exc),
            )
            raise HTTPException(status_code=502, detail=f"Model hatasi: {exc}") from exc

        response_text = str(result.get("response") or "")
        latency_ms = float(result.get("_latency_ms") or 0.0)
        eval_count = int(result.get("eval_count") or 0)
        prompt_eval_count = int(result.get("prompt_eval_count") or 0)

        metrics.REQUESTS.labels(
            model=decision_model, category=category,
            department=department, status="ok",
        ).inc()
        metrics.TOKENS_OUT.labels(model=decision_model).inc(eval_count)

        usage.record(
            username=username, model_id=decision_model,
            tokens_in=prompt_eval_count, tokens_out=eval_count,
            latency_ms=latency_ms,
        )
        audit.write(
            username=username, department=department, prompt=body.prompt,
            model_id=decision_model, category=category, matched_rule=matched_rule,
            fallback=fallback, status="ok", latency_ms=latency_ms,
            tokens_in=prompt_eval_count, tokens_out=eval_count,
        )

        return ChatResponse(
            model_id=decision_model,
            category=category,
            matched_rule=matched_rule,
            fallback_triggered=fallback,
            fallback_reason=fallback_reason,
            response=response_text,
            latency_ms=latency_ms,
            eval_count=eval_count,
            prompt_eval_count=prompt_eval_count,
        )
    finally:
        metrics.INFLIGHT.dec()


@app.get("/api/v1/models")
async def list_models(request: Request, _=Depends(auth.current_principal)) -> dict[str, Any]:
    state = _state(request)
    if not state.orchestrator:
        return {"models": []}
    return {
        "active": state.capacity.get("active_models", []),
        "passive": state.capacity.get("passive_models", []),
        "states": state.orchestrator.states(),
    }


@app.get("/api/v1/system/profile", response_model=SystemProfileResponse)
async def system_profile(request: Request, _=Depends(auth.current_principal)) -> SystemProfileResponse:
    state = _state(request)
    return SystemProfileResponse(
        hardware=state.hw_profile,
        capacity=state.capacity,
        runtime_config=state.runtime_config,
    )


@app.get("/api/v1/system/config")
async def get_runtime_config(_=Depends(auth.current_principal)) -> dict[str, Any]:
    return cfg.load_runtime_config()


@app.put("/api/v1/system/config")
async def update_runtime_config(
    body: ConfigUpdateRequest,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    new_cfg = cfg.update_runtime_config(**changes)
    await _replan(request)
    return new_cfg


@app.post("/api/v1/system/replan")
async def replan(request: Request, _=Depends(auth.require_admin)) -> dict[str, Any]:
    return await _replan(request)


async def _replan(request: Request) -> dict[str, Any]:
    state = _state(request)
    state.runtime_config = cfg.load_runtime_config()
    plan = capacity_mod.plan(
        hw_profile=state.hw_profile,
        catalog=state.catalog,
        runtime_config=state.runtime_config,
        ollama_num_parallel=int(os.getenv("OLLAMA_NUM_PARALLEL", "2")),
        ollama_max_loaded_models=int(os.getenv("OLLAMA_MAX_LOADED_MODELS", "3")),
    )
    state.capacity = plan.to_dict()
    if state.orchestrator:
        await state.orchestrator.client.aclose()
    state.orchestrator = Orchestrator(
        catalog=state.catalog,
        active_model_ids=plan.active_models,
        passive_model_ids=plan.passive_models,
        client=OllamaClient(),
        auto_pull=state.runtime_config.get("auto_pull", True),
        idle_unload_minutes=int(state.runtime_config.get("idle_unload_minutes", 10)),
    )
    state.router = Router(state.catalog, state.orchestrator)
    _refresh_capacity_metrics(state)
    if state.orchestrator.auto_pull:
        asyncio.create_task(state.orchestrator.pull_all_active())
    asyncio.create_task(state.orchestrator.idle_sweep_loop())
    return state.capacity


@app.get("/api/v1/usage/me", response_model=UsageSummary)
async def usage_me(principal: dict[str, Any] = Depends(auth.current_principal)) -> UsageSummary:
    summary = usage.summary_for_user(principal["username"])
    return UsageSummary(
        username=principal["username"],
        department=principal["department"],
        total_requests=summary["total_requests"],
        total_tokens=summary["total_tokens"],
        avg_latency_ms=summary["avg_latency_ms"],
        by_model=summary["by_model"],
    )


@app.get("/api/v1/usage/global")
async def usage_global(_=Depends(auth.require_admin)) -> dict[str, Any]:
    return usage.global_summary()


@app.get("/api/v1/audit")
async def audit_log(
    username: str | None = None,
    department: str | None = None,
    model_id: str | None = None,
    limit: int = 100,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    return {"entries": audit.query(
        username=username, department=department, model_id=model_id, limit=limit
    )}


@app.get("/api/v1/users")
async def users(_=Depends(auth.require_admin)) -> dict[str, Any]:
    return {"users": auth.list_users()}


# --- Basit UI ---

@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/login")


@app.get("/ui/login", include_in_schema=False, response_class=HTMLResponse)
async def ui_login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/ui/dashboard", include_in_schema=False, response_class=HTMLResponse)
async def ui_dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/ui/chat", include_in_schema=False, response_class=HTMLResponse)
async def ui_chat(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/ui/admin", include_in_schema=False, response_class=HTMLResponse)
async def ui_admin(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("admin.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, log_level=LOG_LEVEL.lower())
