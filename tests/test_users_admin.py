"""Admin kullanici yonetimi: olusturma, guncelleme, sifre sifirlama, silme."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _token(client, username, password):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


_admin_token_cache: dict[str, str] = {}


def _admin_headers(client):
    if "tok" not in _admin_token_cache:
        _admin_token_cache["tok"] = _token(client, "admin", "admin")
    return {"Authorization": f"Bearer {_admin_token_cache['tok']}"}


def test_admin_creates_user_and_user_can_login(client):
    h = _admin_headers(client)
    r = client.post("/api/v1/users", headers=h, json={
        "username": "yeni.calisan", "password": "gecici123",
        "department": "hr", "label": "Yeni Calisan",
    })
    assert r.status_code == 201, r.text
    tok = _token(client, "yeni.calisan", "gecici123")
    assert tok


def test_duplicate_username_conflict(client):
    h = _admin_headers(client)
    body = {"username": "tekrar.eden", "password": "gecici123", "department": "hr"}
    assert client.post("/api/v1/users", headers=h, json=body).status_code == 201
    assert client.post("/api/v1/users", headers=h, json=body).status_code == 409


def test_unknown_department_rejected(client):
    h = _admin_headers(client)
    r = client.post("/api/v1/users", headers=h, json={
        "username": "kayip.dept", "password": "gecici123", "department": "yok-boyle-dept",
    })
    assert r.status_code == 400
    assert "Bilinmeyen departman" in r.json()["detail"]


def test_invalid_role_rejected_by_schema(client):
    h = _admin_headers(client)
    r = client.post("/api/v1/users", headers=h, json={
        "username": "rolsuz", "password": "gecici123", "department": "hr", "role": "patron",
    })
    assert r.status_code == 422


def test_non_admin_cannot_create_user(client):
    tok = _token(client, "marketing_user", "mkt123")
    r = client.post("/api/v1/users", headers={"Authorization": f"Bearer {tok}"}, json={
        "username": "kacak", "password": "gecici123", "department": "hr",
    })
    assert r.status_code == 403


def test_admin_resets_password(client):
    h = _admin_headers(client)
    client.post("/api/v1/users", headers=h, json={
        "username": "sifre.unutan", "password": "eski-sifre1", "department": "general",
    })
    r = client.put("/api/v1/users/sifre.unutan", headers=h, json={"new_password": "yeni-sifre1"})
    assert r.status_code == 200
    assert "sifre" in r.json()["changed"]
    assert _token(client, "sifre.unutan", "yeni-sifre1")
    bad = client.post("/login", json={"username": "sifre.unutan", "password": "eski-sifre1"})
    assert bad.status_code == 401


def test_admin_updates_department_and_role(client):
    h = _admin_headers(client)
    client.post("/api/v1/users", headers=h, json={
        "username": "terfi.eden", "password": "gecici123", "department": "hr",
    })
    r = client.put("/api/v1/users/terfi.eden", headers=h, json={
        "department": "engineering", "role": "admin",
    })
    assert r.status_code == 200
    users = client.get("/api/v1/users", headers=h).json()["users"]
    row = next(u for u in users if u["username"] == "terfi.eden")
    assert row["department"] == "engineering"
    assert row["role"] == "admin"


def test_admin_cannot_demote_self(client):
    h = _admin_headers(client)
    r = client.put("/api/v1/users/admin", headers=h, json={"role": "user"})
    assert r.status_code == 400


def test_update_unknown_user_404(client):
    h = _admin_headers(client)
    assert client.put("/api/v1/users/hayalet", headers=h,
                      json={"new_password": "abcdef"}).status_code == 404


def test_update_without_fields_400(client):
    h = _admin_headers(client)
    client.post("/api/v1/users", headers=h, json={
        "username": "bos.istek", "password": "gecici123", "department": "general",
    })
    assert client.put("/api/v1/users/bos.istek", headers=h, json={}).status_code == 400


def test_delete_created_user(client):
    h = _admin_headers(client)
    client.post("/api/v1/users", headers=h, json={
        "username": "gidici", "password": "gecici123", "department": "general",
    })
    r = client.delete("/api/v1/users/gidici", headers=h)
    assert r.status_code == 200
    assert client.post("/login", json={"username": "gidici", "password": "gecici123"}).status_code == 401
