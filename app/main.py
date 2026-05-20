"""FastAPI ana uygulama — gateway, router, orchestrator hepsi burada birleser."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import json as _json

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import audit, auth, capacity as capacity_mod, config as cfg, hwprobe, metrics, usage
from .models import (
    CatalogModelRequest,
    ChatRequest,
    ChatResponse,
    ChatStreamRequest,
    ConfigUpdateRequest,
    LoginRequest,
    PasswordChangeRequest,
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


def _env_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        log.warning("%s degeri sayi degil: %r", name, raw)
        return None


def _refresh_capacity_metrics(state: AppState) -> None:
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


def _build_orchestrator(state: AppState) -> Orchestrator:
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


def _make_plan(state: AppState) -> dict[str, Any]:
    plan = capacity_mod.plan(
        hw_profile=state.hw_profile,
        catalog=state.catalog,
        runtime_config=state.runtime_config,
        ollama_num_parallel=_env_int("OLLAMA_NUM_PARALLEL"),
        ollama_max_loaded_models=_env_int("OLLAMA_MAX_LOADED_MODELS"),
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
        "Donanim: %s CPU, %.1f GB effective RAM (kaynak: %s), GPU=%s",
        profile["cpu"]["logical_cores"],
        profile["memory"]["effective_total_gb"],
        profile["memory"].get("effective_source", "?"),
        profile["gpu"]["vram_total_gb"] if profile["gpu"]["available"] else "yok",
    )

    state.catalog = cfg.load_catalog()
    state.runtime_config = cfg.load_runtime_config()
    _make_plan(state)
    _refresh_capacity_metrics(state)

    orch = _build_orchestrator(state)
    state.orchestrator = orch
    state.router = Router(state.catalog, orch)

    state.ready = True
    log.info("Gateway hazir. Seed model arka planda iniyor olabilir.")

    async def _seed_loop() -> None:
        try:
            await orch.pull_initial()
            if state.catalog.get("defaults", {}).get("warmup_on_start"):
                await orch.warmup_all()
        except Exception as exc:
            log.exception("Seed pull/warmup hatasi: %s", exc)

    state.tasks.append(asyncio.create_task(_seed_loop()))
    state.tasks.append(asyncio.create_task(orch.idle_sweep_loop()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    app.state.app_state = state
    try:
        await _bootstrap(state)
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


APP_ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(APP_ROOT / "ui" / "templates"))

app = FastAPI(
    title="On-Premise AI Gateway",
    version="0.2.0",
    description="Profil bazli, donanima gore kendini ayarlayan AI gateway.",
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
        "profile": (state.capacity or {}).get("profile"),
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
                metrics.MODEL_PULL_PROGRESS.labels(model=st["model_id"]).set(
                    float(st.get("pull_progress") or 0.0)
                )
            elif st.get("pulled"):
                metrics.MODEL_PULL_PROGRESS.labels(model=st["model_id"]).set(1.0)
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
            try:
                decision = state.router.decide(department, body.prompt)
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Henuz hazir model yok: {exc}. Modeller indiriliyor olabilir veya Ollama erisilemez.",
                ) from exc
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


@app.post("/api/v1/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    request: Request,
    principal: dict[str, Any] = Depends(auth.current_principal),
) -> StreamingResponse:
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
        try:
            decision = state.router.decide(department, body.prompt)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Henuz hazir model yok: {exc}.",
            ) from exc
        decision_model = decision.model_id
        category = decision.category
        matched_rule = decision.matched_rule
        fallback = decision.fallback_triggered
        fallback_reason = decision.fallback_reason
        if fallback:
            metrics.FALLBACKS.labels(department=department).inc()

    async def event_source():
        metrics.INFLIGHT.inc()
        header = {
            "event": "start",
            "model_id": decision_model,
            "category": category,
            "matched_rule": matched_rule,
            "fallback_triggered": fallback,
            "fallback_reason": fallback_reason,
        }
        yield _json.dumps(header, ensure_ascii=False) + "\n"
        total_eval = 0
        total_prompt_eval = 0
        latency_ms = 0.0
        status = "ok"
        try:
            with metrics.LATENCY.labels(model=decision_model, category=category).time():
                async for event in state.orchestrator.call_stream(  # type: ignore[union-attr]
                    decision_model,
                    body.prompt,
                    temperature=body.temperature,
                    context_window=state.catalog.get("defaults", {}).get("context_window"),
                ):
                    if event.get("eval_count"):
                        total_eval = int(event["eval_count"])
                    if event.get("prompt_eval_count"):
                        total_prompt_eval = int(event["prompt_eval_count"])
                    out = {
                        "event": "token",
                        "response": event.get("response", ""),
                        "done": bool(event.get("done", False)),
                    }
                    if event.get("done"):
                        out["eval_count"] = total_eval
                        out["prompt_eval_count"] = total_prompt_eval
                    yield _json.dumps(out, ensure_ascii=False) + "\n"
            metrics.REQUESTS.labels(
                model=decision_model, category=category,
                department=department, status="ok",
            ).inc()
            metrics.TOKENS_OUT.labels(model=decision_model).inc(total_eval)
        except Exception as exc:
            status = "error"
            metrics.REQUESTS.labels(
                model=decision_model, category=category,
                department=department, status="error",
            ).inc()
            err = {"event": "error", "detail": str(exc)}
            yield _json.dumps(err, ensure_ascii=False) + "\n"
        finally:
            metrics.INFLIGHT.dec()
            usage.record(
                username=username, model_id=decision_model,
                tokens_in=total_prompt_eval, tokens_out=total_eval,
                latency_ms=latency_ms,
            )
            audit.write(
                username=username, department=department, prompt=body.prompt,
                model_id=decision_model, category=category, matched_rule=matched_rule,
                fallback=fallback, status=status, latency_ms=latency_ms,
                tokens_in=total_prompt_eval, tokens_out=total_eval,
            )

    return StreamingResponse(event_source(), media_type="application/x-ndjson")


@app.post("/api/v1/me/password")
async def me_change_password(
    body: PasswordChangeRequest,
    principal: dict[str, Any] = Depends(auth.current_principal),
) -> dict[str, str]:
    username = principal["username"]
    if not auth.verify_password(username, body.current_password):
        raise HTTPException(status_code=401, detail="Mevcut sifre hatali")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="Yeni sifre eskisinden farkli olmali")
    ok = auth.change_password(username, body.new_password)
    if not ok:
        raise HTTPException(status_code=500, detail="Sifre guncellenemedi")
    return {"status": "ok"}


@app.get("/api/v1/system/catalog")
async def get_catalog(request: Request, _=Depends(auth.current_principal)) -> dict[str, Any]:
    state = _state(request)
    overrides = cfg.load_catalog_overrides().get("models") or {}
    return {
        "models": state.catalog.get("models", {}),
        "departments": state.catalog.get("departments", {}),
        "overridden": list(overrides.keys()),
    }


@app.post("/api/v1/system/catalog/models")
async def add_catalog_model(
    body: CatalogModelRequest,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = _state(request)
    payload = body.model_dump(exclude_none=True)
    model_id = payload.pop("model_id")
    cfg.add_catalog_override(model_id, payload)
    state.catalog = cfg.load_catalog()
    return await _replan(request)


@app.delete("/api/v1/system/catalog/models/{model_id}")
async def delete_catalog_model(
    model_id: str,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = _state(request)
    if not cfg.remove_catalog_override(model_id):
        raise HTTPException(status_code=404, detail="Override bulunamadi (orijinal katalog dosyasi degistirilemez)")
    state.catalog = cfg.load_catalog()
    return await _replan(request)


@app.get("/api/v1/system/ollama/local")
async def ollama_local(request: Request, _=Depends(auth.require_admin)) -> dict[str, Any]:
    state = _state(request)
    if not state.orchestrator:
        return {"models": []}
    try:
        local = await state.orchestrator.client.list_local()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama'ya ulasilamadi: {exc}") from exc
    return {"models": local}


@app.post("/api/v1/system/ollama/inspect")
async def ollama_inspect(
    body: dict[str, str],
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = _state(request)
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


@app.get("/api/v1/system/profiles")
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
    cfg.update_runtime_config(**changes)
    return await _replan(request)


@app.post("/api/v1/system/replan")
async def replan(request: Request, _=Depends(auth.require_admin)) -> dict[str, Any]:
    return await _replan(request)


@app.post("/api/v1/system/pull/{model_id}")
async def pull_model(
    model_id: str,
    request: Request,
    _=Depends(auth.require_admin),
) -> dict[str, Any]:
    state = _state(request)
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator hazir degil")
    if not state.orchestrator.get_state(model_id):
        raise HTTPException(status_code=404, detail=f"Model bulunamadi: {model_id}")
    state.tasks.append(
        asyncio.create_task(state.orchestrator.ensure_pulled(model_id))
    )
    return {"status": "pull_started", "model_id": model_id}


async def _replan(request: Request) -> dict[str, Any]:
    state = _state(request)
    state.runtime_config = cfg.load_runtime_config()
    _make_plan(state)
    if state.orchestrator:
        try:
            await state.orchestrator.client.aclose()
        except Exception:
            pass
    state.orchestrator = _build_orchestrator(state)
    state.router = Router(state.catalog, state.orchestrator)
    _refresh_capacity_metrics(state)
    state.tasks.append(asyncio.create_task(state.orchestrator.pull_initial()))
    state.tasks.append(asyncio.create_task(state.orchestrator.idle_sweep_loop()))
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
