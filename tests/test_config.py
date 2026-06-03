"""Runtime config ve katalog override testleri."""

from __future__ import annotations

from app import config as cfg


def test_default_runtime_config_has_keys():
    c = cfg.default_runtime_config()
    for key in ("profile", "expected_users", "expected_concurrency", "auto_pull", "idle_unload_minutes"):
        assert key in c


def test_runtime_config_roundtrip():
    cfg.update_runtime_config(expected_users=42)
    c = cfg.load_runtime_config()
    assert c["expected_users"] == 42


def test_invalid_profile_rejected():
    cfg.update_runtime_config(profile="auto")
    cfg.update_runtime_config(profile="gecersiz-profil")
    c = cfg.load_runtime_config()
    assert c["profile"] in cfg.VALID_PROFILES


def test_unknown_key_ignored():
    before = cfg.load_runtime_config()
    cfg.update_runtime_config(rastgele_anahtar=123)
    after = cfg.load_runtime_config()
    assert "rastgele_anahtar" not in after
    assert set(after.keys()) == set(before.keys())


def test_catalog_override_add_remove():
    cfg.add_catalog_override("test-model", {"ollama_tag": "test:1", "category": "text", "ram_gb": 1.0})
    cat = cfg.load_catalog()
    assert "test-model" in cat["models"]
    assert cfg.remove_catalog_override("test-model")
    assert not cfg.remove_catalog_override("test-model")


def test_load_catalog_has_models_and_departments():
    cat = cfg.load_catalog()
    assert len(cat.get("models", {})) > 0
    assert "departments" in cat
    assert "routing_rules" in cat
