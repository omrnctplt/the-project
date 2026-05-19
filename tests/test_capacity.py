"""Kapasite planlayicisi icin birim testler."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import capacity as capacity_mod
from app.config import default_runtime_config


CATALOG = {
    "models": {
        "small-text": {"category": "text", "ram_gb": 1.0, "vram_gb": 1.0},
        "medium-text": {"category": "text", "ram_gb": 3.0, "vram_gb": 3.0},
        "small-code": {"category": "code", "ram_gb": 1.2, "vram_gb": 1.2},
        "large-code": {"category": "code", "ram_gb": 5.0, "vram_gb": 5.0},
        "small-reasoning": {"category": "reasoning", "ram_gb": 1.5, "vram_gb": 1.5},
        "fallback-tiny": {"category": "fallback", "ram_gb": 0.5, "vram_gb": 0.5},
    }
}


def _hw(*, ram_gb: float = 8.0, vram_gb: float = 0.0) -> dict:
    return {
        "cpu": {"logical_cores": 4, "physical_cores": 2},
        "memory": {"effective_total_gb": ram_gb, "host_total_gb": ram_gb, "available_gb": ram_gb * 0.9},
        "gpu": (
            {"available": True, "vram_total_gb": vram_gb, "devices": [{"name": "Test", "vram_total_gb": vram_gb}]}
            if vram_gb > 0
            else {"available": False, "vram_total_gb": 0.0, "devices": []}
        ),
        "disk": {"free_gb": 100.0},
    }


def _cfg(**overrides) -> dict:
    cfg = default_runtime_config()
    cfg.update(overrides)
    return cfg


def test_cpu_only_small_budget():
    hw = _hw(ram_gb=4.0, vram_gb=0.0)
    plan = capacity_mod.plan(hw, CATALOG, _cfg())
    assert plan.accelerator == "cpu"
    assert plan.active_models, "En az bir aktif model olmali"
    assert "fallback-tiny" in plan.active_models, "Fallback her zaman secilmeli"
    assert plan.budget_used_gb <= plan.budget_total_gb + 1e-6


def test_gpu_prefers_vram():
    hw = _hw(ram_gb=32.0, vram_gb=8.0)
    plan = capacity_mod.plan(hw, CATALOG, _cfg())
    assert plan.accelerator == "gpu"
    assert plan.budget_total_gb < hw["memory"]["effective_total_gb"]


def test_manual_override_filters_invalid():
    hw = _hw(ram_gb=16.0)
    cfg = _cfg(manual_override=True, active_models=["small-text", "nonexistent"])
    plan = capacity_mod.plan(hw, CATALOG, cfg)
    assert "small-text" in plan.active_models
    assert "nonexistent" not in plan.active_models
    assert any("nonexistent" in w for w in plan.warnings)


def test_too_large_model_in_manual_goes_passive():
    hw = _hw(ram_gb=2.0)
    cfg = _cfg(manual_override=True, active_models=["large-code"])
    plan = capacity_mod.plan(hw, CATALOG, cfg)
    assert "large-code" in plan.passive_models
    assert "large-code" not in plan.active_models
    assert plan.warnings


def test_concurrent_capacity_warning():
    hw = _hw(ram_gb=16.0)
    cfg = _cfg(expected_users=100, expected_concurrency=5)
    plan = capacity_mod.plan(hw, CATALOG, cfg, ollama_num_parallel=2, ollama_max_loaded_models=3)
    assert any("Beklenen" in w for w in plan.warnings)
