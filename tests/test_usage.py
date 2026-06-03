"""Kullanim kaydi ve rate-limit (sliding window) testleri."""

from __future__ import annotations

from app import usage


def test_rate_limit_allows_under_limit():
    key = "test:under"
    for _ in range(5):
        ok, _count = usage.check_and_record_rate(key, 10)
        assert ok


def test_rate_limit_blocks_over_limit():
    key = "test:over"
    for _ in range(3):
        ok, _ = usage.check_and_record_rate(key, 3)
        assert ok
    ok, count = usage.check_and_record_rate(key, 3)
    assert not ok
    assert count >= 3


def test_rate_limit_zero_means_unlimited():
    for _ in range(50):
        ok, _ = usage.check_and_record_rate("test:unlimited", 0)
        assert ok


def test_record_and_summary():
    usage.ensure_schema()
    usage.record(username="bob", model_id="m1", tokens_in=10, tokens_out=20, latency_ms=100.0)
    usage.record(username="bob", model_id="m1", tokens_in=5, tokens_out=15, latency_ms=50.0)
    s = usage.summary_for_user("bob")
    assert s["total_requests"] == 2
    assert s["total_tokens"] == 50
    assert s["by_model"]["m1"] == 2
    assert s["avg_latency_ms"] == 75.0


def test_global_summary_lists_user_and_model():
    usage.ensure_schema()
    usage.record(username="carol", model_id="m2", tokens_in=1, tokens_out=1, latency_ms=10.0)
    g = usage.global_summary()
    assert any(u["username"] == "carol" for u in g["users"])
    assert any(m["model_id"] == "m2" for m in g["models"])
