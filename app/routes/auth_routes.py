"""Kimlik dogrulama — login + kendi sifresini degistirme."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, usage
from ..models import LoginRequest, PasswordChangeRequest, TokenResponse

router = APIRouter()

LOGIN_RATE_PER_MIN = 10


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    allowed, _ = usage.check_and_record_rate(
        key=f"login:{body.username}", limit_per_min=LOGIN_RATE_PER_MIN
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Cok fazla giris denemesi, biraz bekleyin",
            headers={"Retry-After": "60"},
        )
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


@router.post("/api/v1/me/password")
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
