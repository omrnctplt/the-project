"""Kullanim istatistikleri ve rate-limit (in-memory sliding window + SQLite ozet)."""

from __future__ import annotations

import sqlite3
import time
from collections import defaultdict, deque
from datetime import date
from threading import RLock
from typing import Any

from .config import DATA_DIR

DB_PATH = DATA_DIR / "usage.db"
_lock = RLock()
_window: dict[str, deque[float]] = defaultdict(deque)


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
            CREATE TABLE IF NOT EXISTS user_usage (
              username    TEXT NOT NULL,
              day         TEXT NOT NULL,
              model_id    TEXT NOT NULL,
              requests    INTEGER NOT NULL DEFAULT 0,
              tokens_in   INTEGER NOT NULL DEFAULT 0,
              tokens_out  INTEGER NOT NULL DEFAULT 0,
              latency_sum_ms REAL NOT NULL DEFAULT 0.0,
              PRIMARY KEY (username, day, model_id)
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_day ON user_usage(day, username);"
        )
        conn.commit()


def record(
    *,
    username: str,
    model_id: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: float = 0.0,
) -> None:
    today = date.today().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_usage (username, day, model_id, requests, tokens_in, tokens_out, latency_sum_ms)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(username, day, model_id) DO UPDATE SET
              requests        = requests + 1,
              tokens_in       = tokens_in + excluded.tokens_in,
              tokens_out      = tokens_out + excluded.tokens_out,
              latency_sum_ms  = latency_sum_ms + excluded.latency_sum_ms
            """,
            (username, today, model_id, tokens_in, tokens_out, latency_ms),
        )
        conn.commit()


def summary_for_user(username: str, days: int = 30) -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT model_id,
                   SUM(requests) AS req,
                   SUM(tokens_in) AS tin,
                   SUM(tokens_out) AS tout,
                   SUM(latency_sum_ms) AS lat
            FROM user_usage
            WHERE username = ? AND day >= date('now', ?)
            GROUP BY model_id
            ORDER BY req DESC
            """,
            (username, f"-{int(days)} day"),
        ).fetchall()
    by_model = {r["model_id"]: int(r["req"] or 0) for r in rows}
    total_req = sum(int(r["req"] or 0) for r in rows)
    total_tokens = sum(int((r["tin"] or 0) + (r["tout"] or 0)) for r in rows)
    total_latency = sum(float(r["lat"] or 0.0) for r in rows)
    return {
        "username": username,
        "total_requests": total_req,
        "total_tokens": total_tokens,
        "avg_latency_ms": round(total_latency / total_req, 1) if total_req else None,
        "by_model": by_model,
    }


def global_summary(days: int = 30) -> dict[str, Any]:
    with _connect() as conn:
        per_user = conn.execute(
            """
            SELECT username,
                   SUM(requests) AS req,
                   SUM(tokens_in + tokens_out) AS toks
            FROM user_usage
            WHERE day >= date('now', ?)
            GROUP BY username
            ORDER BY req DESC
            """,
            (f"-{int(days)} day",),
        ).fetchall()
        per_model = conn.execute(
            """
            SELECT model_id,
                   SUM(requests) AS req,
                   SUM(latency_sum_ms) AS lat
            FROM user_usage
            WHERE day >= date('now', ?)
            GROUP BY model_id
            ORDER BY req DESC
            """,
            (f"-{int(days)} day",),
        ).fetchall()
    return {
        "users": [
            {"username": r["username"], "requests": int(r["req"] or 0), "tokens": int(r["toks"] or 0)}
            for r in per_user
        ],
        "models": [
            {
                "model_id": r["model_id"],
                "requests": int(r["req"] or 0),
                "avg_latency_ms": (
                    round(float(r["lat"] or 0) / int(r["req"]), 1) if r["req"] else None
                ),
            }
            for r in per_model
        ],
    }


def check_and_record_rate(
    key: str,
    limit_per_min: int,
) -> tuple[bool, int]:
    if limit_per_min <= 0:
        return True, 0
    now = time.monotonic()
    cutoff = now - 60.0
    with _lock:
        bucket = _window[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit_per_min:
            return False, len(bucket)
        bucket.append(now)
        return True, len(bucket)
