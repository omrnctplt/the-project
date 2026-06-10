"""Denetim kaydi: yazma, sorgu, KVKK uyumlu prompt hash'leme."""

from __future__ import annotations

from app import audit


def test_audit_write_and_query():
    audit.ensure_schema()
    audit.write(
        username="dave", department="hr", prompt="merhaba dunya",
        model_id="m1", category="text", matched_rule="r1",
        fallback=False, status="ok", latency_ms=12.5,
        tokens_in=3, tokens_out=7,
    )
    rows = audit.query(username="dave")
    assert len(rows) >= 1
    assert rows[0]["username"] == "dave"
    assert rows[0]["status"] == "ok"


def test_prompt_is_hashed_not_stored():
    audit.ensure_schema()
    secret = "cok gizli prompt icerigi 12345"
    audit.write(
        username="erin", department="hr", prompt=secret,
        model_id="m", category="text", matched_rule="r",
        fallback=False, status="ok", latency_ms=1.0,
    )
    row = audit.query(username="erin")[0]
    # Ham prompt hicbir alanda olmamali; sadece hash + uzunluk tutulur
    assert secret not in str(dict(row))
    assert row["prompt_length"] == len(secret)
    assert row["prompt_hash"] and len(row["prompt_hash"]) == 16


def test_audit_filter_by_department():
    audit.ensure_schema()
    audit.write(
        username="frank", department="finance", prompt="x", model_id="m",
        category="reasoning", matched_rule="r", fallback=False,
        status="ok", latency_ms=1.0,
    )
    rows = audit.query(department="finance")
    assert rows
    assert all(r["department"] == "finance" for r in rows)


def test_audit_query_limit():
    audit.ensure_schema()
    for i in range(5):
        audit.write(
            username="grace", department="hr", prompt=f"p{i}", model_id="m",
            category="text", matched_rule="r", fallback=False,
            status="ok", latency_ms=1.0,
        )
    rows = audit.query(username="grace", limit=3)
    assert len(rows) == 3
