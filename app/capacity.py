"""Kapasite planlayicisi.

Profil bazli, donanima gore kendini ayarlayan plan. Amac: sistem bellegini
asla doldurmadan, kategori cesitliligi koruyacak sekilde modelleri sirala.

Profiller:
  - lite        : Cok dusuk kaynak. Sadece fallback + en kucuk text modeli.
  - balanced    : Tipik laptop / mini-PC. 2-3 model: text, code, fallback.
  - performance : GPU veya yuksek RAM. Kategori basina 1-2 model.

Donanim profili verildiginde uygun profili otomatik secer; kullanici
runtime_config['profile'] ile override edebilir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

CATEGORY_PRIORITY = ("fallback", "text", "code", "reasoning", "persona")

PROFILES: dict[str, dict[str, Any]] = {
    "lite": {
        "budget_ratio_cpu": 0.25,
        "budget_ratio_gpu": 0.55,
        "max_active": 1,
        "max_loaded_models": 1,
        "num_parallel": 1,
        "allowed_categories": ["fallback"],
        "label": "Lite (cok dusuk kaynak)",
    },
    "balanced": {
        "budget_ratio_cpu": 0.40,
        "budget_ratio_gpu": 0.70,
        "max_active": 3,
        "max_loaded_models": 1,
        "num_parallel": 1,
        "allowed_categories": ["fallback", "text", "code"],
        "label": "Balanced (tipik laptop)",
    },
    "performance": {
        "budget_ratio_cpu": 0.55,
        "budget_ratio_gpu": 0.80,
        "max_active": 6,
        "max_loaded_models": 2,
        "num_parallel": 2,
        "allowed_categories": ["fallback", "text", "code", "reasoning", "persona"],
        "label": "Performance (GPU / yuksek RAM)",
    },
}

DEFAULT_PROFILE = "balanced"
FALLBACK_RESERVE_GB = 0.8

MAX_LOADED_HARD_CAP = 8
TYPICAL_LOADED_MODEL_GB = 6.0


def dynamic_max_loaded(budget_total_gb: float, profile_base: int) -> int:
    """Ayni anda bellekte tutulabilecek model sayisi butceyle olceklenir.

    Profil tabani alt sinirdir; buyuk makinelerde (orn. 48 GB VRAM -> 6,
    80 GB -> 8) farkli ekipler farkli modelleri es zamanli kullanabilir.
    """
    by_budget = int(budget_total_gb // TYPICAL_LOADED_MODEL_GB)
    return max(int(profile_base), min(MAX_LOADED_HARD_CAP, by_budget))


@dataclass
class CapacityPlan:
    accelerator: str
    profile: str
    profile_label: str
    profile_auto: bool
    budget_total_gb: float
    budget_used_gb: float
    hardware_tier: str = "laptop"
    active_models: list[str] = field(default_factory=list)
    passive_models: list[str] = field(default_factory=list)
    max_concurrent_requests: int = 1
    max_loaded_models: int = 1
    num_parallel: int = 1
    expected_users: int = 0
    expected_concurrency: int = 0
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accelerator": self.accelerator,
            "hardware_tier": self.hardware_tier,
            "profile": self.profile,
            "profile_label": self.profile_label,
            "profile_auto": self.profile_auto,
            "budget_total_gb": round(self.budget_total_gb, 2),
            "budget_used_gb": round(self.budget_used_gb, 2),
            "budget_free_gb": round(max(0.0, self.budget_total_gb - self.budget_used_gb), 2),
            "active_models": self.active_models,
            "passive_models": self.passive_models,
            "max_concurrent_requests": self.max_concurrent_requests,
            "max_loaded_models": self.max_loaded_models,
            "num_parallel": self.num_parallel,
            "expected_users": self.expected_users,
            "expected_concurrency": self.expected_concurrency,
            "warnings": self.warnings,
            "notes": self.notes,
        }


def _model_size_gb(model: dict[str, Any], accelerator: str) -> float:
    if accelerator == "gpu":
        return float(model.get("vram_gb") or model.get("ram_gb") or 0.0)
    return float(model.get("ram_gb") or model.get("vram_gb") or 0.0)


def _accelerator_and_total(hw: dict[str, Any]) -> tuple[str, float]:
    gpu = hw.get("gpu") or {}
    if gpu.get("available") and float(gpu.get("vram_total_gb") or 0) >= 2.0:
        return "gpu", float(gpu["vram_total_gb"])
    mem = hw.get("memory") or {}
    total = float(mem.get("effective_total_gb") or mem.get("host_total_gb") or 0.0)
    return "cpu", max(total, 1.0)


def hardware_tier(hw: dict[str, Any]) -> str:
    """Donanimi bir tier'a yerlestirir: edge / laptop / workstation / datacenter.

    Discover/onerme bu tier'a gore yapilir. GPU'da VRAM, GPU yoksa RAM baz alinir.
    """
    accel, total = _accelerator_and_total(hw)
    if accel == "gpu":
        if total >= 48:
            return "datacenter"
        if total >= 16:
            return "workstation"
        if total >= 6:
            return "laptop"
        return "edge"
    # CPU-only: datacenter pratik degil; buyuk RAM en fazla workstation
    if total >= 64:
        return "workstation"
    if total >= 16:
        return "laptop"
    return "edge"


# Tier siralamasi — komsu tier onerileri ve karsilastirma icin
TIER_ORDER = ("edge", "laptop", "workstation", "datacenter")


def auto_select_profile(hw: dict[str, Any]) -> str:
    accel, total = _accelerator_and_total(hw)
    if accel == "gpu":
        if total >= 12.0:
            return "performance"
        if total >= 6.0:
            return "balanced"
        return "lite"
    if total < 6.0:
        return "lite"
    if total < 16.0:
        return "balanced"
    return "balanced"


def _smallest_in_category(
    catalog_models: dict[str, dict[str, Any]],
    category: str,
    accelerator: str,
    budget_gb: float,
    already_chosen: set[str],
) -> tuple[str, float] | None:
    cand: list[tuple[str, dict[str, Any], float]] = []
    for mid, m in catalog_models.items():
        if mid in already_chosen:
            continue
        if m.get("category") != category:
            continue
        size = _model_size_gb(m, accelerator)
        if size <= 0:
            continue
        cand.append((mid, m, size))
    cand.sort(key=lambda t: t[2])
    for mid, _, size in cand:
        if size <= budget_gb:
            return mid, size
    return None


def _pick_active_models(
    catalog_models: dict[str, dict[str, Any]],
    accelerator: str,
    budget_total_gb: float,
    profile_cfg: dict[str, Any],
) -> tuple[list[tuple[str, float]], float]:
    allowed = list(profile_cfg["allowed_categories"])
    max_active = int(profile_cfg["max_active"])

    chosen: list[tuple[str, float]] = []
    chosen_ids: set[str] = set()
    used = 0.0
    remaining = budget_total_gb

    fb = _smallest_in_category(catalog_models, "fallback", accelerator, remaining, chosen_ids)
    if fb:
        chosen.append(fb)
        chosen_ids.add(fb[0])
        used += fb[1]
        remaining -= fb[1]

    for category in [c for c in CATEGORY_PRIORITY if c != "fallback" and c in allowed]:
        if len(chosen) >= max_active:
            break
        reserve = FALLBACK_RESERVE_GB if any(catalog_models[m].get("category") == "fallback" for m, _ in chosen) else 0.0
        cat_budget = max(0.0, remaining - reserve)
        pick = _smallest_in_category(catalog_models, category, accelerator, cat_budget, chosen_ids)
        if not pick:
            continue
        chosen.append(pick)
        chosen_ids.add(pick[0])
        used += pick[1]
        remaining -= pick[1]

    for category in [c for c in CATEGORY_PRIORITY if c in allowed]:
        if len(chosen) >= max_active:
            break
        pick = _smallest_in_category(catalog_models, category, accelerator, remaining, chosen_ids)
        if not pick:
            continue
        chosen.append(pick)
        chosen_ids.add(pick[0])
        used += pick[1]
        remaining -= pick[1]

    return chosen, used


def plan(
    hw_profile: dict[str, Any],
    catalog: dict[str, Any],
    runtime_config: dict[str, Any],
    ollama_num_parallel: int | None = None,
    ollama_max_loaded_models: int | None = None,
) -> CapacityPlan:
    accelerator, total_gb = _accelerator_and_total(hw_profile)
    models_catalog: dict[str, dict[str, Any]] = catalog.get("models", {}) or {}

    requested_profile = runtime_config.get("profile")
    profile_auto = not requested_profile or requested_profile == "auto"
    profile_name = requested_profile if (requested_profile in PROFILES) else auto_select_profile(hw_profile)
    profile_cfg = PROFILES[profile_name]

    ratio = profile_cfg["budget_ratio_gpu"] if accelerator == "gpu" else profile_cfg["budget_ratio_cpu"]
    budget_total = max(0.5, total_gb * ratio)

    num_parallel = int(ollama_num_parallel) if ollama_num_parallel else int(profile_cfg["num_parallel"])
    max_loaded = (
        int(ollama_max_loaded_models) if ollama_max_loaded_models
        else dynamic_max_loaded(budget_total, profile_cfg["max_loaded_models"])
    )

    plan_obj = CapacityPlan(
        accelerator=accelerator,
        hardware_tier=hardware_tier(hw_profile),
        profile=profile_name,
        profile_label=str(profile_cfg["label"]),
        profile_auto=profile_auto,
        budget_total_gb=budget_total,
        budget_used_gb=0.0,
        max_loaded_models=max_loaded,
        num_parallel=num_parallel,
        expected_users=int(runtime_config.get("expected_users", 0) or 0),
        expected_concurrency=int(runtime_config.get("expected_concurrency", 0) or 0),
    )

    manual = bool(runtime_config.get("manual_override")) and bool(runtime_config.get("active_models"))
    if manual:
        plan_obj.notes.append("Aktif model listesi manuel olarak ayarlandi.")
        used = 0.0
        for mid in runtime_config["active_models"]:
            if mid not in models_catalog:
                plan_obj.warnings.append(f"Katalogda olmayan model atlandi: {mid}")
                continue
            size = _model_size_gb(models_catalog[mid], accelerator)
            if size <= 0:
                plan_obj.warnings.append(f"Model boyut bilgisi yok: {mid}")
                plan_obj.passive_models.append(mid)
                continue
            if used + size > budget_total:
                plan_obj.passive_models.append(mid)
                plan_obj.warnings.append(
                    f"'{mid}' bellek butcesine sigmiyor (gerekli {size:.1f} GB, kalan "
                    f"{max(0.0, budget_total - used):.1f} GB). Pasif isaretlendi."
                )
                continue
            plan_obj.active_models.append(mid)
            used += size
        plan_obj.budget_used_gb = used
    else:
        picks, used = _pick_active_models(models_catalog, accelerator, budget_total, profile_cfg)
        plan_obj.active_models = [mid for mid, _ in picks]
        plan_obj.budget_used_gb = used

    actives = set(plan_obj.active_models) | set(plan_obj.passive_models)
    for mid in models_catalog:
        if mid not in actives:
            plan_obj.passive_models.append(mid)

    loaded_cap = min(max_loaded, max(1, len(plan_obj.active_models)))
    plan_obj.max_concurrent_requests = loaded_cap * max(1, num_parallel)

    desired = plan_obj.expected_users * max(1, plan_obj.expected_concurrency)
    if desired and desired > plan_obj.max_concurrent_requests:
        plan_obj.warnings.append(
            f"Beklenen {plan_obj.expected_users} kullanici x {plan_obj.expected_concurrency} "
            f"paralel = {desired} es zamanli istek, ancak donanim {plan_obj.max_concurrent_requests} "
            f"destekliyor. Kuyrukta bekleme yasanabilir."
        )

    if accelerator == "cpu":
        plan_obj.notes.append(
            "GPU bulunamadi; modeller CPU uzerinde calisacak. Yanit suresi daha yuksek olabilir."
        )
    plan_obj.notes.append(
        f"Profil: {profile_name} ({'otomatik' if profile_auto else 'manuel'}). "
        f"Bellek butcesi: {budget_total:.1f} GB / {total_gb:.1f} GB."
    )

    if not plan_obj.active_models:
        plan_obj.warnings.append(
            "Hicbir model aktif olarak yuklenemedi. 'lite' profili veya daha kucuk modeller deneyin."
        )

    return plan_obj
