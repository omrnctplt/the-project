"""Kapasite planlayicisi icin birim testler."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import capacity as capacity_mod
from app.config import default_runtime_config


CATALOG = {
    "models": {
        "fallback-tiny": {"category": "fallback", "ram_gb": 0.5, "vram_gb": 0.5},
        "small-text": {"category": "text", "ram_gb": 1.2, "vram_gb": 1.2},
        "medium-text": {"category": "text", "ram_gb": 3.0, "vram_gb": 3.0},
        "small-code": {"category": "code", "ram_gb": 1.3, "vram_gb": 1.3},
        "large-code": {"category": "code", "ram_gb": 5.0, "vram_gb": 5.0},
        "small-reasoning": {"category": "reasoning", "ram_gb": 1.5, "vram_gb": 1.5},
    }
}


def _hw(*, ram_gb: float = 8.0, vram_gb: float = 0.0) -> dict:
    return {
        "cpu": {"logical_cores": 4, "physical_cores": 2},
        "memory": {
            "effective_total_gb": ram_gb,
            "host_total_gb": ram_gb,
            "available_gb": ram_gb * 0.9,
            "effective_source": "test",
        },
        "gpu": (
            {"available": True, "vram_total_gb": vram_gb,
             "devices": [{"name": "Test", "vram_total_gb": vram_gb}]}
            if vram_gb > 0
            else {"available": False, "vram_total_gb": 0.0, "devices": []}
        ),
        "disk": {"free_gb": 100.0},
    }


def _cfg(**overrides) -> dict:
    cfg = default_runtime_config()
    cfg.update(overrides)
    return cfg


def test_auto_profile_lite_for_low_ram():
    assert capacity_mod.auto_select_profile(_hw(ram_gb=4.0)) == "lite"


def test_auto_profile_balanced_for_typical_laptop():
    assert capacity_mod.auto_select_profile(_hw(ram_gb=8.0)) == "balanced"
    assert capacity_mod.auto_select_profile(_hw(ram_gb=16.0)) == "balanced"


def test_auto_profile_performance_for_gpu():
    assert capacity_mod.auto_select_profile(_hw(ram_gb=32.0, vram_gb=16.0)) == "performance"


def test_lite_profile_keeps_active_count_one():
    hw = _hw(ram_gb=4.0)
    plan = capacity_mod.plan(hw, CATALOG, _cfg(profile="lite"))
    assert plan.profile == "lite"
    assert len(plan.active_models) == 1
    assert "fallback-tiny" in plan.active_models
    assert plan.max_concurrent_requests == 1


def test_balanced_includes_fallback_and_text_and_code():
    hw = _hw(ram_gb=16.0)
    plan = capacity_mod.plan(hw, CATALOG, _cfg(profile="balanced"))
    assert plan.profile == "balanced"
    cats = {CATALOG["models"][m]["category"] for m in plan.active_models}
    assert "fallback" in cats
    assert "text" in cats
    assert "code" in cats
    assert "reasoning" not in cats   # balanced reasoning iceremz


def test_performance_can_include_reasoning():
    hw = _hw(ram_gb=32.0, vram_gb=16.0)
    plan = capacity_mod.plan(hw, CATALOG, _cfg(profile="performance"))
    assert plan.profile == "performance"
    cats = {CATALOG["models"][m]["category"] for m in plan.active_models}
    assert "reasoning" in cats


def test_budget_does_not_exceed_total():
    for prof in ("lite", "balanced", "performance"):
        plan = capacity_mod.plan(_hw(ram_gb=16.0, vram_gb=0.0), CATALOG, _cfg(profile=prof))
        assert plan.budget_used_gb <= plan.budget_total_gb + 1e-6, prof


def test_manual_override_filters_invalid():
    hw = _hw(ram_gb=16.0)
    cfg = _cfg(profile="balanced", manual_override=True, active_models=["small-text", "nonexistent"])
    plan = capacity_mod.plan(hw, CATALOG, cfg)
    assert "small-text" in plan.active_models
    assert "nonexistent" not in plan.active_models
    assert any("nonexistent" in w for w in plan.warnings)


def test_too_large_model_in_manual_goes_passive():
    hw = _hw(ram_gb=2.0)
    cfg = _cfg(profile="balanced", manual_override=True, active_models=["large-code"])
    plan = capacity_mod.plan(hw, CATALOG, cfg)
    assert "large-code" in plan.passive_models
    assert "large-code" not in plan.active_models
    assert plan.warnings


def test_concurrent_capacity_warning():
    hw = _hw(ram_gb=16.0)
    cfg = _cfg(profile="balanced", expected_users=100, expected_concurrency=5)
    plan = capacity_mod.plan(hw, CATALOG, cfg)
    assert any("Beklenen" in w for w in plan.warnings)


def test_gpu_prefers_vram_budget():
    hw = _hw(ram_gb=32.0, vram_gb=8.0)
    plan = capacity_mod.plan(hw, CATALOG, _cfg(profile="balanced"))
    assert plan.accelerator == "gpu"
    assert plan.budget_total_gb <= hw["gpu"]["vram_total_gb"]


def test_dynamic_max_loaded_scales_with_budget():
    assert capacity_mod.dynamic_max_loaded(2.2, 1) == 1
    assert capacity_mod.dynamic_max_loaded(12.8, 2) == 2
    assert capacity_mod.dynamic_max_loaded(38.4, 2) == 6
    assert capacity_mod.dynamic_max_loaded(64.0, 2) == 8
