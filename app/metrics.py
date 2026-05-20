"""Prometheus metrik tanimlari."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter(
    "ai_gateway_requests_total",
    "Gateway tarafindan modele yonlendirilen toplam istek",
    ["model", "category", "department", "status"],
)

FALLBACKS = Counter(
    "ai_gateway_fallback_total",
    "Fallback rotasi kullanildi (hedef kategori bos)",
    ["department"],
)

RATE_LIMITED = Counter(
    "ai_gateway_rate_limited_total",
    "Departman/kullanici rate limit asildi",
    ["department"],
)

LATENCY = Histogram(
    "ai_gateway_request_latency_seconds",
    "Model yaniti gecikmesi",
    ["model", "category"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
)

ACTIVE_MODELS = Gauge(
    "ai_gateway_active_models",
    "Sistemde aktif olarak isaretli model sayisi",
)

LOADED_MODELS = Gauge(
    "ai_gateway_loaded_models",
    "Ollama'da su anda RAM/VRAM'e yuklu model sayisi",
)

INFLIGHT = Gauge(
    "ai_gateway_inflight_requests",
    "Su anda islenmekte olan istek sayisi",
)

TOKENS_OUT = Counter(
    "ai_gateway_tokens_out_total",
    "Modellerin urettigi toplam token",
    ["model"],
)

MODEL_PULL_PROGRESS = Gauge(
    "ai_gateway_model_pull_progress",
    "Aktif model indirme ilerlemesi (0..1)",
    ["model"],
)

HARDWARE_INFO = Gauge(
    "ai_gateway_hardware_info",
    "Donanim profili (sabit deger 1, etiketlerde detay)",
    ["accelerator", "profile", "gpu_count", "ram_gb", "vram_gb"],
)
