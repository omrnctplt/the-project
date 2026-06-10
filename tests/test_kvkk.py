"""KVKK ozellikleri — retention, veri silme hakki, aydinlatma sayfasi, cok turlu prompt."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import audit, usage
from app.models import ChatRequest, ChatTurn
from app.routes.chat_routes import _compose_prompt


def _insert_old_audit(username: str, days_ago: int) -> None:
    old_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    with audit._connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (timestamp, username, department, status) VALUES (?, ?, ?, ?)",
            (old_ts, username, "general", "ok"),
        )
        conn.commit()


def _insert_old_usage(username: str, days_ago: int) -> None:
    old_day = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    with usage._connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_usage (username, day, model_id, requests) VALUES (?, ?, 'm', 1)",
            (username, old_day),
        )
        conn.commit()


def test_audit_purge_older_than():
    audit.ensure_schema()
    _insert_old_audit("eski_kullanici", days_ago=400)
    audit.write(
        username="yeni_kullanici", department="general", prompt="test",
        model_id="m", category="text", matched_rule="r", fallback=False,
        status="ok", latency_ms=1.0,
    )
    removed = audit.purge_older_than(180)
    assert removed >= 1
    remaining = audit.query(username="eski_kullanici")
    assert remaining == []
    assert audit.query(username="yeni_kullanici")


def test_usage_purge_older_than():
    usage.ensure_schema()
    _insert_old_usage("eski_kullanici", days_ago=400)
    usage.record(username="yeni_kullanici", model_id="m")
    removed = usage.purge_older_than(180)
    assert removed >= 1
    assert usage.summary_for_user("yeni_kullanici")["total_requests"] >= 1


def test_purge_zero_days_disabled():
    assert audit.purge_older_than(0) == 0
    assert usage.purge_older_than(0) == 0


def test_compose_prompt_without_history():
    body = ChatRequest(prompt="merhaba")
    assert _compose_prompt(body) == "merhaba"


def test_compose_prompt_with_history():
    body = ChatRequest(
        prompt="devam et",
        history=[
            ChatTurn(role="user", content="ilk soru"),
            ChatTurn(role="assistant", content="ilk yanit"),
        ],
    )
    composed = _compose_prompt(body)
    assert "ilk soru" in composed
    assert "ilk yanit" in composed
    assert composed.rstrip().endswith("Asistan:")
    assert "devam et" in composed


def test_compose_prompt_caps_history_chars():
    huge = "x" * 8000
    body = ChatRequest(
        prompt="soru",
        history=[ChatTurn(role="user", content=huge), ChatTurn(role="assistant", content=huge)],
    )
    composed = _compose_prompt(body)
    assert len(composed) < 16000


def test_chat_turn_role_validated():
    with pytest.raises(ValueError):
        ChatTurn(role="system", content="olmaz")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


def _token(client, username="admin", password="admin"):
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_privacy_page_public(client):
    r = client.get("/ui/privacy")
    assert r.status_code == 200
    assert "Aydinlatma" in r.text
    assert "KVKK" in r.text


def test_erase_user_data_endpoint(client):
    usage.record(username="marketing_user", model_id="m1")
    audit.write(
        username="marketing_user", department="marketing", prompt="gizli",
        model_id="m1", category="text", matched_rule="r", fallback=False,
        status="ok", latency_ms=1.0,
    )
    token = _token(client)
    r = client.delete(
        "/api/v1/users/marketing_user/data",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "erased"
    assert body["audit_rows_removed"] >= 1
    assert body["usage_rows_removed"] >= 1
    assert audit.query(username="marketing_user") == []


def test_erase_requires_admin(client):
    token = _token(client, "dev_user", "dev123")
    r = client.delete(
        "/api/v1/users/marketing_user/data",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_delete_account_endpoint(client):
    token = _token(client)
    r = client.delete("/api/v1/users/guest", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"}).json()["users"]
    assert "guest" not in [u["username"] for u in users]


def test_cannot_delete_self_or_admin(client):
    token = _token(client)
    assert client.delete("/api/v1/users/admin", headers={"Authorization": f"Bearer {token}"}).status_code == 400


def test_login_rate_limited(client):
    for _ in range(10):
        client.post("/login", json={"username": "olmayan_xyz", "password": "yanlis"})
    r = client.post("/login", json={"username": "olmayan_xyz", "password": "yanlis"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers
