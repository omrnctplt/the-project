"""UI sayfalari — Jinja2 template'leri servis eder."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..auth import demo_mode_enabled
from ..runtime import RETENTION_DAYS

APP_ROOT = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(APP_ROOT / "ui" / "templates"))
templates.env.globals["app_version"] = __version__
templates.env.globals["retention_days"] = RETENTION_DAYS
templates.env.globals["demo_mode"] = demo_mode_enabled()

router = APIRouter(include_in_schema=False)

PAGES = {
    "/ui/login": "login.html",
    "/ui/dashboard": "dashboard.html",
    "/ui/chat": "chat.html",
    "/ui/admin": "admin.html",
    "/ui/models": "models.html",
    "/ui/onboarding": "onboarding.html",
    "/ui/resources": "resources.html",
    "/ui/privacy": "privacy.html",
}


@router.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    # Token client-side localStorage'da; minimal HTML ile yonlendiriyoruz.
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'>"
        "<title>Inference Hub</title>"
        "<script>"
        "  var t = localStorage.getItem('token');"
        "  location.replace(t ? '/ui/dashboard' : '/ui/login');"
        "</script>"
    )


def _make_page_handler(template_name: str):
    async def handler(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, template_name)
    return handler


for path, template_name in PAGES.items():
    router.add_api_route(path, _make_page_handler(template_name), response_class=HTMLResponse)
