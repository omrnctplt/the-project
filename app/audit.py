"""Audit log — kim, ne zaman, hangi modele istek atti.

Veri minimizasyonu: prompt icerigi saklanmaz; kurulum-bazli salt ile
SHA-256 ozeti tutulur. Salt sayesinde 'bilinen metni hash'leyip eslestirme'
saldirisi baska kurulumlarda calismaz.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .config import DATA_DIR

DB_PATH = DATA_DIR / "audit.db"
SALT_PATH = DATA_DIR / "audit_salt"
_salt: str | None = None


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def ensure_schema() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
              id                INTEGER PRIMARY KEY AUTOINCREMENT,
              timestamp         TEXT NOT NULL,
              username          TEXT NOT NULL,
              department        TEXT NOT NULL,
              model_id          TEXT,
              category          TEXT,
              matched_rule      TEXT,
              fallback          INTEGER NOT NULL DEFAULT 0,
              prompt_hash       TEXT,
              prompt_length     INTEGER,
              status            TEXT NOT NULL,
              latency_ms        REAL,
              tokens_in         INTEGER,
              tokens_out        INTEGER,
              error             TEXT
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(username, timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_dept ON audit_log(department, timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_model ON audit_log(model_id, timestamp);")
        conn.commit()


def _get_salt() -> str:
    global _salt
    if _salt:
        return _salt
    try:
        existing = SALT_PATH.read_text(encoding="utf-8").strip()
        if existing:
            _salt = existing
            return _salt
    except OSError:
        pass
    _salt = secrets.token_hex(16)
    try:
        SALT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SALT_PATH.write_text(_salt, encoding="utf-8")
    except OSError:
        pass
    return _salt


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256((_get_salt() + prompt).encode("utf-8")).hexdigest()[:16]


def write(
    *,
    username: str,
    department: str,
    prompt: str,
    model_id: str | None,
    category: str | None,
    matched_rule: str | None,
    fallback: bool,
    status: str,
    latency_ms: float | None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    error: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
              (timestamp, username, department, model_id, category, matched_rule,
               fallback, prompt_hash, prompt_length, status, latency_ms,
               tokens_in, tokens_out, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                username,
                department,
                model_id,
                category,
                matched_rule,
                1 if fallback else 0,
                _hash_prompt(prompt),
                len(prompt),
                status,
                latency_ms,
                tokens_in,
                tokens_out,
                error,
            ),
        )
        conn.commit()


def purge_older_than(days: int) -> int:
    """KVKK saklama suresi: verilen gunden eski kayitlari siler, sayisini doner."""
    if days <= 0:
        return 0
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM audit_log WHERE timestamp < datetime('now', ?)",
            (f"-{int(days)} day",),
        )
        conn.commit()
        return cur.rowcount


def delete_user_data(username: str) -> int:
    """KVKK silme hakki: kullanicinin tum audit kayitlarini siler."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM audit_log WHERE username = ?", (username,))
        conn.commit()
        return cur.rowcount


def query(
    *,
    username: str | None = None,
    department: str | None = None,
    model_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params: list[Any] = []
    if username:
        sql += " AND username = ?"
        params.append(username)
    if department:
        sql += " AND department = ?"
        params.append(department)
    if model_id:
        sql += " AND model_id = ?"
        params.append(model_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(min(limit, 1000))
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
