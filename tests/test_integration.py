"""Uctan uca endpoint testleri — gercek FastAPI lifespan (bootstrap) ile.

Ollama calismadan da gateway 'ready' olmali (lazy pull mimarisi).
"""

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


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_bootstrap_completes_without_ollama(client):
    r = client.get("/api/v1/system/bootstrap")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_version_matches_package(client):
    import app as pkg
    assert app.version == pkg.__version__


def test_login_wrong_password(client):
    r = client.post("/login", json={"username": "admin", "password": "yanlis"})
    assert r.status_code == 401


def test_protected_requires_auth(client):
    assert client.get("/api/v1/users").status_code in (401, 403)


def test_profile_with_token(client):
    tok = _token(client, "admin", "admin")
    r = client.get("/api/v1/system/profile", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert "hardware" in body and "capacity" in body


def test_user_cannot_access_admin_endpoint(client):
    tok = _token(client, "marketing_user", "mkt123")
    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_models_endpoint(client):
    tok = _token(client, "marketing_user", "mkt123")
    r = client.get("/api/v1/models", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert "states" in r.json()


def test_metrics_endpoint_exposes_counters(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "ai_gateway_requests_total" in r.text


def test_ui_login_page_served(client):
    r = client.get("/ui/login")
    assert r.status_code == 200
    assert "Inference Hub" in r.text


def test_security_headers_present(client):
    r = client.get("/ui/login")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in r.headers
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_docs_excluded_from_csp(client):
    # Swagger UI varliklari CDN'den geldigi icin /docs CSP disinda olmali
    r = client.get("/docs")
    assert r.status_code == 200
    assert "Content-Security-Policy" not in r.headers
    # Ortak guvenlik basliklari yine de bulunmali
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_chat_invalid_temperature_rejected(client):
    tok = _token(client, "marketing_user", "mkt123")
    r = client.post("/api/v1/chat", json={"prompt": "x", "temperature": 5},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422


def test_chat_empty_prompt_rejected(client):
    tok = _token(client, "marketing_user", "mkt123")
    r = client.post("/api/v1/chat", json={"prompt": ""},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422


def test_chat_without_ready_model_returns_controlled_error(client):
    # Ollama calismadigi icin model hazir degil -> kontrollu 502/503, cokme yok
    tok = _token(client, "marketing_user", "mkt123")
    r = client.post("/api/v1/chat", json={"prompt": "merhaba"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code in (502, 503)
    assert "detail" in r.json()
