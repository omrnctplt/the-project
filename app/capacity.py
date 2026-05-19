"""Kapasite planlayicisi — donanim + katalog + config'den aktif model listesi uretir."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

CATEGORIES_PRIORITY = ("text", "code", "reasoning", "fallback")
BUDGET_HEADROOM = 0.75   # toplam belleğin %75'ini model yukleme icin ayir
FALLBACK_RESERVE = 1.0    # GB — fallback modeline ayrilan rezerv


@dataclass
class CapacityPlan:
    accelerator: str           # "gpu" | "cpu"
    budget_total_gb: float
    budget_used_gb: float
    active_models: list[str] = field(default_factory=list)
    passive_models: list[str] = field(default_factory=list)
    max_concurrent_requests: int = 1
    expected_users: int = 0
    expected_concurrency: int = 0
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accelerator": self.accelerator,
            "budget_total_gb": round(self.budget_total_gb, 2),
            "budget_used_gb": round(self.budget_used_gb, 2),
            "budget_free_gb": round(self.budget_total_gb - self.budget_used_gb, 2),
            "active_models": self.active_models,
            "passive_models": self.passive_models,
            "max_concurrent_requests": self.max_concurrent_requests,
            "expected_users": self.expected_users,
            "expected_concurrency": self.expected_concurrency,
            "warnings": self.warnings,
            "notes": self.notes,
        }


def _model_size_gb(model: dict[str, Any], accelerator: str) -> float:
    if accelerator == "gpu":
        return float(model.get("vram_gb") or model.get("ram_gb") or 0.0)
    return float(model.get("ram_gb") or model.get("vram_gb") or 0.0)


def _budget_total_gb(hw: dict[str, Any]) -> tuple[str, float]:
    gpu = hw.get("gpu") or {}
    if gpu.get("available") and gpu.get("vram_total_gb", 0) > 0:
        return "gpu", float(gpu["vram_total_gb"]) * BUDGET_HEADROOM
    mem = hw.get("memory") or {}
    total = float(mem.get("effective_total_gb") or mem.get("host_total_gb") or 0.0)
    return "cpu", max(total * BUDGET_HEADROOM, 1.0)


def _max_parallel_per_model(num_parallel_env: int) -> int:
    return max(1, num_parallel_env)


def _choose_models_for_category(
    catalog_models: dict[str, dict[str, Any]],
    category: str,
    accelerator: str,
    remaining_budget_gb: float,
) -> list[tuple[str, float]]:
    candidates = [
        (mid, m) for mid, m in catalog_models.items()
        if m.get("category") == category
    ]
    candidates.sort(key=lambda kv: _model_size_gb(kv[1], accelerator))
    chosen: list[tuple[str, float]] = []
    budget = remaining_budget_gb
    for mid, model in candidates:
        size = _model_size_gb(model, accelerator)
        if size <= 0:
            continue
        if size <= budget:
            chosen.append((mid, size))
            budget -= size
        else:
            break
    if not chosen and candidates:
        smallest_id, smallest = candidates[0]
        size = _model_size_gb(smallest, accelerator)
        if size <= remaining_budget_gb:
            chosen.append((smallest_id, size))
    return chosen


def plan(
    hw_profile: dict[str, Any],
    catalog: dict[str, Any],
    runtime_config: dict[str, Any],
    ollama_num_parallel: int = 2,
    ollama_max_loaded_models: int = 3,
) -> CapacityPlan:
    accelerator, budget_total = _budget_total_gb(hw_profile)
    models_catalog: dict[str, dict[str, Any]] = catalog.get("models", {}) or {}

    plan_obj = CapacityPlan(
        accelerator=accelerator,
        budget_total_gb=budget_total,
        budget_used_gb=0.0,
        expected_users=int(runtime_config.get("expected_users", 0) or 0),
        expected_concurrency=int(runtime_config.get("expected_concurrency", 0) or 0),
    )

    manual = runtime_config.get("manual_override") and runtime_config.get("active_models")
    if manual:
        plan_obj.notes.append("Aktif model listesi manuel olarak ayarlandi.")
        active_ids = [m for m in runtime_config["active_models"] if m in models_catalog]
        unknown = [m for m in runtime_config["active_models"] if m not in models_catalog]
        if unknown:
            plan_obj.warnings.append(f"Katalogda olmayan modeller atlandi: {unknown}")
        used = 0.0
        for mid in active_ids:
            size = _model_size_gb(models_catalog[mid], accelerator)
            if used + size > budget_total:
                plan_obj.passive_models.append(mid)
                plan_obj.warnings.append(
                    f"'{mid}' donanim butcesine sigmiyor (gerekli {size:.1f} GB, kalan "
                    f"{max(0.0, budget_total - used):.1f} GB). Pasif olarak isaretlendi."
                )
                continue
            plan_obj.active_models.append(mid)
            used += size
        plan_obj.budget_used_gb = used
    else:
        remaining = budget_total
        used = 0.0
        for category in CATEGORIES_PRIORITY:
            cat_budget = remaining
            if category != "fallback":
                cat_budget = max(0.0, remaining - FALLBACK_RESERVE)
            picks = _choose_models_for_category(models_catalog, category, accelerator, cat_budget)
            for mid, size in picks:
                if mid in plan_obj.active_models:
                    continue
                plan_obj.active_models.append(mid)
                used += size
                remaining -= size
        plan_obj.budget_used_gb = used
        for mid in models_catalog:
            if mid not in plan_obj.active_models:
                plan_obj.passive_models.append(mid)

    loaded_cap = min(ollama_max_loaded_models, max(1, len(plan_obj.active_models)))
    plan_obj.max_concurrent_requests = loaded_cap * _max_parallel_per_model(ollama_num_parallel)

    desired = plan_obj.expected_users * max(1, plan_obj.expected_concurrency)
    if desired and desired > plan_obj.max_concurrent_requests:
        plan_obj.warnings.append(
            f"Beklenen {plan_obj.expected_users} kullanici x {plan_obj.expected_concurrency} "
            f"paralel = {desired} es zamanli istek, ancak donanim {plan_obj.max_concurrent_requests} "
            f"destekliyor. Kuyrukta bekleme yasanabilir."
        )

    if accelerator == "cpu":
        plan_obj.notes.append("GPU bulunamadi; modeller CPU uzerinde calisacak. Yanit suresi daha yuksek olabilir.")

    if not plan_obj.active_models:
        plan_obj.warnings.append("Hicbir model aktif olarak yuklenemedi. Donanim bellegi yetersiz olabilir.")

    return plan_obj
