"""Kimlik dogrulama: bcrypt, JWT, rol, sifre degisimi."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth


def test_password_hash_roundtrip():
    h = auth._hash_password("secret123")
    assert h != "secret123"
    assert auth._verify_password("secret123", h)
    assert not auth._verify_password("yanlis", h)


def test_verify_password_handles_bad_hash():
    # Bozuk hash ValueError yutulmali, False donmeli
    assert not auth._verify_password("x", "bozuk-hash-degil")


def test_jwt_roundtrip():
    token, ttl = auth.create_access_token("alice", "hr", "user")
    assert ttl > 0
    payload = auth.decode_token(token)
    assert payload["sub"] == "alice"
    assert payload["department"] == "hr"
    assert payload["role"] == "user"


def test_invalid_token_raises():
    with pytest.raises(HTTPException) as exc:
        auth.decode_token("gecersiz.token.degeri")
    assert exc.value.status_code == 401


def test_seed_and_authenticate():
    auth.seed_default_users()
    user = auth.authenticate("admin", "admin")
    assert user is not None
    assert user["role"] == "admin"
    assert auth.authenticate("admin", "yanlis") is None
    assert auth.authenticate("yok_boyle_kullanici", "x") is None


def test_change_password():
    auth.seed_default_users()
    assert auth.change_password("hr_user", "yeniSifre123")
    assert auth.authenticate("hr_user", "yeniSifre123") is not None
    assert auth.authenticate("hr_user", "hr123") is None


def test_require_admin():
    admin = {"username": "a", "department": "engineering", "role": "admin"}
    assert auth.require_admin(admin) == admin
    with pytest.raises(HTTPException) as exc:
        auth.require_admin({"username": "u", "department": "hr", "role": "user"})
    assert exc.value.status_code == 403
