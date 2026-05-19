"""JWT kimlik dogrulama + kullanici DB (SQLite + bcrypt)."""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import DATA_DIR, load_default_users

log = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "users.db"
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "8"))

if not JWT_SECRET or JWT_SECRET == "lutfen-bu-degeri-uzun-rastgele-bir-stringle-degistirin":
    log.warning("JWT_SECRET zayif veya eksik. .env dosyasinda guclu bir degerle degistirin.")

_lock = RLock()
security = HTTPBearer()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
          username      TEXT PRIMARY KEY,
          password_hash TEXT NOT NULL,
          department    TEXT NOT NULL,
          role          TEXT NOT NULL DEFAULT 'user',
          label         TEXT,
          created_at    TEXT NOT NULL,
          last_login_at TEXT
        );
        """
    )
    conn.commit()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def seed_default_users() -> None:
    with _lock, _connect() as conn:
        _ensure_schema(conn)
        existing = {row["username"] for row in conn.execute("SELECT username FROM users")}
        defaults = load_default_users().get("users") or {}
        now = datetime.now(timezone.utc).isoformat()
        for username, props in defaults.items():
            if username in existing:
                continue
            password = str(props.get("password", "")) or "changeme"
            department = str(props.get("department", "general"))
            role = str(props.get("role", "user"))
            label = props.get("label")
            conn.execute(
                "INSERT INTO users (username, password_hash, department, role, label, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (username, _hash_password(password), department, role, label, now),
            )
            log.info("Demo kullanici eklendi: %s (%s)", username, department)
        conn.commit()


def get_user(username: str) -> dict[str, Any] | None:
    with _connect() as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT username, password_hash, department, role, label FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with _connect() as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT username, department, role, label, created_at, last_login_at FROM users ORDER BY username"
        ).fetchall()
    return [dict(r) for r in rows]


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    user = get_user(username)
    if not user:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE username = ?",
            (datetime.now(timezone.utc).isoformat(), username),
        )
        conn.commit()
    return user


def create_access_token(username: str, department: str, role: str) -> tuple[str, int]:
    expires_in_sec = JWT_EXPIRES_HOURS * 3600
    payload = {
        "sub": username,
        "department": department,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in_sec),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires_in_sec


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token suresi dolmus") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Gecersiz token") from exc


def current_principal(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, Any]:
    payload = decode_token(creds.credentials)
    return {
        "username": payload.get("sub", ""),
        "department": payload.get("department", "general"),
        "role": payload.get("role", "user"),
    }


def require_admin(principal: dict[str, Any] = Depends(current_principal)) -> dict[str, Any]:
    if principal.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yonetici yetkisi gerekli")
    return principal


def change_password(username: str, new_password: str) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (_hash_password(new_password), username),
        )
        conn.commit()
        return cur.rowcount > 0
