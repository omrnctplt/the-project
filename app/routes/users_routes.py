"""Kullanicilar, kullanim istatistikleri, denetim kaydi ve KVKK veri haklari."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import audit, auth, usage
from ..deps import get_state
from ..models import UsageSummary, UserCreateRequest, UserUpdateRequest

router = APIRouter()


def _valid_departments(request: Request) -> set[str]:
    state = get_state(request)
    return set(((state.catalog or {}).get("departments") or {}).keys())


@router.get("/api/v1/usage/me", response_model=UsageSummary)
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


@router.get("/api/v1/usage/global")
async def usage_global(_=Depends(auth.require_admin)) -> dict[str, Any]:
    return usage.global_summary()


@router.get("/api/v1/audit")
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


@router.get("/api/v1/users")
async def users(_=Depends(auth.require_admin)) -> dict[str, Any]:
    return {"users": auth.list_users()}


@router.post("/api/v1/users", status_code=201)
async def create_user(
    body: UserCreateRequest,
    request: Request,
    principal: dict[str, Any] = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Yeni calisan hesabi olusturur (admin). Departman katalogdan dogrulanir."""
    valid = _valid_departments(request)
    if valid and body.department not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Bilinmeyen departman: {body.department}. Gecerli: {', '.join(sorted(valid))}",
        )
    if not auth.create_user(
        body.username, body.password, body.department, body.role, body.label
    ):
        raise HTTPException(status_code=409, detail=f"Kullanici zaten var: {body.username}")
    audit.write(
        username=principal["username"], department=principal["department"],
        prompt=f"user_create:{body.username}", model_id=None, category=None,
        matched_rule="user_create", fallback=False, status="ok", latency_ms=None,
    )
    return {"status": "created", "username": body.username}


@router.put("/api/v1/users/{username}")
async def update_user(
    username: str,
    body: UserUpdateRequest,
    request: Request,
    principal: dict[str, Any] = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Departman/rol/etiket gunceller; new_password verilirse sifre sifirlar (admin)."""
    if not auth.get_user(username):
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    if username == principal["username"] and body.role == "user":
        raise HTTPException(status_code=400, detail="Kendi admin yetkinizi kaldiramazsiniz")
    if body.department is not None:
        valid = _valid_departments(request)
        if valid and body.department not in valid:
            raise HTTPException(status_code=400, detail=f"Bilinmeyen departman: {body.department}")
    changed = []
    if any(v is not None for v in (body.department, body.role, body.label)):
        auth.update_user(username, department=body.department, role=body.role, label=body.label)
        changed.append("profil")
    if body.new_password:
        auth.change_password(username, body.new_password)
        changed.append("sifre")
    if not changed:
        raise HTTPException(status_code=400, detail="Guncellenecek alan verilmedi")
    audit.write(
        username=principal["username"], department=principal["department"],
        prompt=f"user_update:{username}:{'+'.join(changed)}", model_id=None, category=None,
        matched_rule="user_update", fallback=False, status="ok", latency_ms=None,
    )
    return {"status": "updated", "username": username, "changed": changed}


@router.delete("/api/v1/users/{username}/data")
async def delete_user_data(
    username: str,
    principal: dict[str, Any] = Depends(auth.require_admin),
) -> dict[str, Any]:
    """KVKK silme hakki (m.7/m.11): kullanicinin audit + usage kayitlarini siler.

    Hesap silinmez; sadece kisisel veri iceren islem kayitlari temizlenir.
    """
    if not auth.get_user(username):
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    removed_audit = audit.delete_user_data(username)
    removed_usage = usage.delete_user_data(username)
    audit.write(
        username=principal["username"], department=principal["department"],
        prompt=f"kvkk_erasure:{username}", model_id=None, category=None,
        matched_rule="kvkk_erasure", fallback=False, status="ok", latency_ms=None,
    )
    return {
        "status": "erased",
        "username": username,
        "audit_rows_removed": removed_audit,
        "usage_rows_removed": removed_usage,
    }


@router.delete("/api/v1/users/{username}")
async def delete_user_account(
    username: str,
    principal: dict[str, Any] = Depends(auth.require_admin),
) -> dict[str, Any]:
    """Hesabi ve tum kisisel verisini siler (KVKK tam silme)."""
    if username == principal["username"]:
        raise HTTPException(status_code=400, detail="Kendi hesabinizi silemezsiniz")
    target = auth.get_user(username)
    if not target:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi")
    if target.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Admin hesaplari bu endpoint ile silinemez")
    removed_audit = audit.delete_user_data(username)
    removed_usage = usage.delete_user_data(username)
    auth.delete_user(username)
    audit.write(
        username=principal["username"], department=principal["department"],
        prompt=f"kvkk_account_delete:{username}", model_id=None, category=None,
        matched_rule="kvkk_account_delete", fallback=False, status="ok", latency_ms=None,
    )
    return {
        "status": "deleted",
        "username": username,
        "audit_rows_removed": removed_audit,
        "usage_rows_removed": removed_usage,
    }
