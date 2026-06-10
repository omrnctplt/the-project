"""Route modullerinin paylastigi FastAPI dependency'leri."""

from __future__ import annotations

from fastapi import Request

from .state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.app_state
