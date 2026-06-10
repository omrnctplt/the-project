"""FastAPI uygulamasi — app kurulumu, middleware ve saglik endpointleri.

Is mantigi route modullerinde yasar:
  routes/auth_routes     login + sifre degistirme
  routes/chat_routes     one-shot + streaming sohbet
  routes/catalog_routes  katalog, kesif (statik + canli), pull/sil
  routes/system_routes   profil, kapasite, config, kaynaklar
  routes/users_routes    kullanim, denetim, KVKK veri haklari
  routes/ui_routes       Jinja2 sayfalari
Yasam dongusu (bootstrap/replan/retention) runtime.py'de.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import __version__, metrics
from .deps import get_state
from .runtime import lifespan
from .routes import auth_routes, catalog_routes, chat_routes, system_routes, ui_routes, users_routes

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("gateway")

APP_ROOT = Path(__file__).parent

app = FastAPI(
    title="On-Premise AI Gateway",
    version=__version__,
    description="Profil bazli, donanima gore kendini ayarlayan AI gateway.",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(APP_ROOT / "ui" / "static")), name="static")

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(catalog_routes.router)
app.include_router(system_routes.router)
app.include_router(users_routes.router)
app.include_router(ui_routes.router)


_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Tum yanitlara guvenlik basliklari ekler.

    /docs, /redoc ve /openapi.json Swagger/Redoc varliklarini CDN'den
    yukledigi icin CSP disinda birakilir; diger basliklar herkese uygulanir.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    path = request.url.path
    if not (path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi")):
        response.headers.setdefault("Content-Security-Policy", _CSP)
    return response


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:
    state = get_state(request)
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
    state = get_state(request)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, log_level=LOG_LEVEL.lower())
